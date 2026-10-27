"""HiggsfieldClient tests: fake SDK, no network."""

from pathlib import Path

import pytest
import higgsfield_client as real_sdk

from storyteller.config import load_config
from storyteller.higgsfield_client import HiggsfieldClient, HiggsfieldError


class FakeController:
    request_id = "req-fake"

    def __init__(self, statuses, result):
        self._statuses = statuses
        self._result = result

    def poll_request_status(self, *, delay=0.5):
        for s in self._statuses:
            yield s

    def get(self):
        return self._result


class FakeSDK:
    def __init__(self, controller, result=None):
        self.controller = controller
        self.result_dict = result or {"video": {"url": "https://cdn/x.mp4"}}
        self.uploaded: list[str] = []
        self.submitted: list[tuple[str, dict]] = []
        self.resumed: list[str] = []

    def upload_file(self, path):
        self.uploaded.append(str(path))
        return f"https://cdn/upload-{len(self.uploaded)}.jpg"

    def submit(self, workflow, arguments):
        self.submitted.append((workflow, arguments))
        return self.controller

    def get_request_controller(self, request_id):
        self.resumed.append(request_id)
        return self.controller


@pytest.fixture(autouse=True)
def fake_download(monkeypatch):
    import storyteller.higgsfield_client as hfc

    def _dl(url, dst):
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(b"mp4bytes")
    monkeypatch.setattr(hfc, "download", _dl)


def make_client(sdk, **cfg_overrides):
    cfg = load_config()
    for k, v in cfg_overrides.items():
        setattr(cfg, k, v)
    return HiggsfieldClient("id", "secret", cfg, sdk=sdk)


def _clip_kwargs(tmp_path, refs=None):
    kf = tmp_path / "kf.png"; kf.write_bytes(b"png")
    ref_paths = []
    for i in range(refs or 0):
        r = tmp_path / f"ref{i}.png"; r.write_bytes(b"png"); ref_paths.append(r)
    dest = tmp_path / "out" / "clip.mp4"
    return dict(model="seedance-2-5", prompt="animate", first_image=kf,
                references=ref_paths, duration_sec=8, resolution="480p",
                aspect_ratio="16:9", destination=dest, asset_id="video_S01")


def test_happy_path(tmp_path):
    sdk = FakeSDK(FakeController([real_sdk.Queued(), real_sdk.Completed()],
                                 {"video": {"url": "https://cdn/x.mp4"}}))
    client = make_client(sdk)
    kwargs = _clip_kwargs(tmp_path, refs=2)
    clip, usage, request_id = client.generate_clip(**kwargs)
    assert clip.read_bytes() == b"mp4bytes"
    assert request_id
    wf, args = sdk.submitted[0]
    assert wf == "bytedance/seedance-2.5/reference-to-video"
    assert args["image_urls"] == ["https://cdn/upload-1.jpg",
                                  "https://cdn/upload-2.jpg",
                                  "https://cdn/upload-3.jpg"]
    assert args["duration"] == 8 and args["resolution"] == "480p"
    assert args["generate_audio"] is True


def test_poll_failure_raises(tmp_path):
    sdk = FakeSDK(FakeController([real_sdk.Failed()], {}))
    client = make_client(sdk)
    with pytest.raises(HiggsfieldError, match="failed"):
        client.generate_clip(**_clip_kwargs(tmp_path))


def test_timeout_raises(tmp_path, monkeypatch):
    sdk = FakeSDK(FakeController([real_sdk.Queued()] * 100, {}))
    client = make_client(sdk, video_timeout_sec=0)
    with pytest.raises(HiggsfieldError, match="timed out"):
        client.generate_clip(**_clip_kwargs(tmp_path))


def test_resume_skips_submit(tmp_path):
    sdk = FakeSDK(FakeController([real_sdk.Completed()],
                                 {"video": {"url": "https://cdn/x.mp4"}}))
    client = make_client(sdk)
    kwargs = _clip_kwargs(tmp_path)
    clip, usage, request_id = client.generate_clip(**kwargs, request_id="req-1")
    assert sdk.submitted == [] and sdk.resumed == ["req-1"]
    assert request_id == "req-1"


def test_unknown_model_raises(tmp_path):
    sdk = FakeSDK(FakeController([], {}))
    client = make_client(sdk)
    kwargs = _clip_kwargs(tmp_path)
    kwargs["model"] = "nope"
    with pytest.raises(HiggsfieldError, match="seedance-2-5"):
        client.generate_clip(**kwargs)
    assert sdk.uploaded == []


def test_uploads_first_frame_then_references(tmp_path):
    sdk = FakeSDK(FakeController([real_sdk.Completed()],
                                 {"video": {"url": "https://cdn/x.mp4"}}))
    client = make_client(sdk)
    kwargs = _clip_kwargs(tmp_path, refs=2)
    client.generate_clip(**kwargs)
    assert len(sdk.uploaded) == 3
    assert sdk.uploaded[0].endswith("kf.png")


def test_max_references_truncated(tmp_path):
    sdk = FakeSDK(FakeController([real_sdk.Completed()],
                                 {"video": {"url": "https://cdn/x.mp4"}}))
    client = make_client(sdk)
    entry = client.cfg.higgsfield_models["seedance-2-5"]
    entry["max_references"] = 2
    kwargs = _clip_kwargs(tmp_path, refs=4)
    client.generate_clip(**kwargs)
    _, args = sdk.submitted[0]
    assert len(args["image_urls"]) == 3  # first frame + 2 refs


def test_unsupported_param_omitted(tmp_path):
    sdk = FakeSDK(FakeController([real_sdk.Completed()],
                                 {"video": {"url": "https://cdn/x.mp4"}}))
    client = make_client(sdk)
    entry = client.cfg.higgsfield_models["seedance-2-5"]
    entry["params"] = ["prompt", "image_urls", "duration"]  # no resolution etc.
    kwargs = _clip_kwargs(tmp_path)
    client.generate_clip(**kwargs)
    _, args = sdk.submitted[0]
    assert set(args) == {"prompt", "image_urls", "duration"}
