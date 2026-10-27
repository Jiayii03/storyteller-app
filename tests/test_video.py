"""video subcommand tests: fake client, no network, no real money."""

import json
from pathlib import Path

import pytest

from storyteller import storage, video
from storyteller.config import load_config
from storyteller.higgsfield_client import HiggsfieldError
from storyteller.schema import Project
from storyteller.storage import ProjectPaths

PROJECT_JSON = {
    "schema_version": "0.1",
    "project": {"id": "vidtest", "title": "Vid", "aspect_ratio": "16:9"},
    "models": {"image_model": "gemini-3.1-flash-image",
               "video_model": "seedance-2-5", "image_resolution": "1K",
               "video_resolution": "480p"},
    "characters": [{"id": "mia", "name": "Mia"}],
    "locations": [{"id": "cafe", "name": "Cafe"}],
    "shots": [
        {"id": "S01", "sequence_index": 1, "duration_sec": 8,
         "summary": "one", "location_id": "cafe",
         "subjects": [{"character_id": "mia"}],
         "motion": {"subject_motion": "slow blink"}},
        {"id": "S02", "sequence_index": 2, "duration_sec": 8,
         "summary": "two", "location_id": "cafe",
         "subjects": [{"character_id": "mia"}],
         "motion": {"video_prompt": "handheld chase"}},
    ],
    "assets": [
        {"asset_id": "char_mia", "asset_type": "character_reference", "target_id": "mia"},
        {"asset_id": "loc_cafe", "asset_type": "location_reference", "target_id": "cafe"},
        {"asset_id": "kf_S01_start", "asset_type": "keyframe", "target_id": "S01",
         "frame_role": "start"},
        {"asset_id": "kf_S02_start", "asset_type": "keyframe", "target_id": "S02",
         "frame_role": "start"},
    ],
}


class FakeClient:
    calls: list[dict] = []
    instances: list = []
    fail_after_submit: bool = False

    def __init__(self, key_id, key_secret, cfg, paths=None, sdk=None):
        self.cfg = cfg
        self.paths = paths
        FakeClient.instances.append(self)

    def generate_clip(self, model, prompt, first_image, references,
                      duration_sec, resolution, aspect_ratio, destination,
                      asset_id, request_id=None, on_submitted=None):
        FakeClient.calls.append({
            "model": model, "prompt": prompt, "first_image": str(first_image),
            "references": [str(r) for r in references],
            "duration_sec": duration_sec, "resolution": resolution,
            "asset_id": asset_id, "request_id": request_id,
        })
        rid = request_id or "req-new"
        if on_submitted is not None:
            on_submitted(rid)
        if FakeClient.fail_after_submit and request_id is None:
            raise HiggsfieldError(
                f"Video generation timed out after 0s for asset {asset_id}.")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"mp4")
        return destination, {"calls": 1}, rid


@pytest.fixture()
def env(tmp_path, monkeypatch):
    root = tmp_path / "p"
    root.mkdir()
    (root / "project.json").write_text(json.dumps(PROJECT_JSON), encoding="utf-8")
    paths = ProjectPaths(storage.project_root(root / "project.json"))
    paths.ensure_dirs()
    project = Project.model_validate(PROJECT_JSON)

    def approve(shot_id):
        kf = paths.shot_keyframe_dir(shot_id, "start") / "approved"
        kf.mkdir(parents=True, exist_ok=True)
        (kf / "v01_a.png").write_bytes(b"png")

    def approve_ref(kind_dir, name):
        d = kind_dir / name / "approved"
        d.mkdir(parents=True, exist_ok=True)
        (d / "v01_a.png").write_bytes(b"png")

    approve("S01")
    approve_ref(paths.assets / "characters", "mia")
    approve_ref(paths.assets / "locations", "cafe")
    FakeClient.instances = []
    FakeClient.calls = []
    FakeClient.fail_after_submit = False
    monkeypatch.setattr(video, "HiggsfieldClient", FakeClient)
    cfg = load_config()
    return paths, project, cfg, approve


def _run(env, project_file=None, **kw):
    paths, project, cfg, approve = env
    pf = project_file or (paths.root / "project.json")
    return video.run_video(pf, project, cfg, **kw)


def test_dry_run_no_http(env, monkeypatch):
    monkeypatch.setattr("builtins.input", lambda *a: "y")
    report = _run(env, shots=None, model=None, resolution="480p",
                  dry_run=True, yes=False, force=False, allow_unapproved=False)
    assert report.done == [] and report.calls == 0
    assert FakeClient.instances == []
    assert set(report.estimates) == {"S01", "S02"}


def test_unknown_model_errors(env):
    with pytest.raises(HiggsfieldError, match="seedance-2-5"):
        _run(env, shots=None, model="nope", resolution="480p",
             dry_run=True, yes=True, force=False, allow_unapproved=False)


def test_duration_clamped(env):
    paths, project, cfg, _ = env
    cfg.higgsfield_models["seedance-2-5"]["durations_sec"] = {"min": 4, "max": 6}
    report = _run(env, shots=None, model=None, resolution="480p", dry_run=True,
                  yes=True, force=False, allow_unapproved=False)
    assert all(c["duration_sec"] == 6 for c in FakeClient.calls)
    assert any("clamped" in w for w in report.warnings)


def test_timeout_then_resume_no_resubmit(env):
    paths, project, cfg, approve = env
    approve("S02")
    FakeClient.fail_after_submit = True
    report = _run(env, shots=None, model=None, resolution="480p", dry_run=False,
                  yes=True, force=False, allow_unapproved=False)
    assert [aid for aid, _ in report.failed] == ["S01", "S02"]
    state = storage.load_state(paths)
    assert state["assets"]["video_S01"]["request_id"] == "req-new"
    FakeClient.fail_after_submit = False
    FakeClient.calls = []
    report = _run(env, shots=None, model=None, resolution="480p", dry_run=False,
                  yes=True, force=False, allow_unapproved=False)
    assert [aid for aid, _ in report.done] == ["S01", "S02"]
    assert all(c["request_id"] == "req-new" for c in FakeClient.calls)


def test_bad_catalog_entry_rejected_before_spend(env):
    paths, project, cfg, _ = env
    cfg.higgsfield_models["broken"] = {"resolutions": ["480p"]}  # no workflow
    with pytest.raises(HiggsfieldError, match="workflow"):
        _run(env, shots=None, model="broken", resolution="480p", dry_run=False,
             yes=True, force=False, allow_unapproved=False)


def test_missing_keyframe_skips_shot(env):
    paths, project, cfg, approve = env
    kf2 = paths.shot_keyframe_dir("S02", "start")
    for p in kf2.rglob("*"):
        if p.is_file():
            p.unlink()
    report = _run(env, shots=None, model=None, resolution="480p", dry_run=False,
                  yes=True, force=False, allow_unapproved=False)
    assert [aid for aid, _ in report.done] == ["S01"]
    assert [aid for aid, _ in report.skipped] == ["S02"]
    assert "approve" in report.skipped[0][1]


def test_per_shot_confirm(env, monkeypatch):
    paths, project, cfg, _ = env
    answers = iter(["y", "n"])
    monkeypatch.setattr("builtins.input", lambda *a: next(answers))
    report = _run(env, shots=None, model=None, resolution="480p", dry_run=False,
                  yes=False, force=False, allow_unapproved=False)
    assert [aid for aid, _ in report.done] == ["S01"]
    assert report.skipped[-1][1] == "aborted by user"


def test_resume_polls_existing_request(env):
    paths, project, cfg, _ = env
    state = storage.load_state(paths)
    st = storage.asset_state(state, "video_S01")
    st["request_id"] = "req-9"
    storage.save_state(paths, state)
    _run(env, shots=None, model=None, resolution="480p", dry_run=False,
         yes=True, force=False, allow_unapproved=False)
    call = next(c for c in FakeClient.calls if c["asset_id"] == "video_S01")
    assert call["request_id"] == "req-9"


def test_state_and_sidecar(env):
    paths, project, cfg, approve = env
    approve("S02")
    report = _run(env, shots=None, model=None, resolution="480p", dry_run=False,
                  yes=True, force=False, allow_unapproved=False)
    state = storage.load_state(paths)
    st = state["assets"]["video_S01"]
    assert st["status"] == "generated"
    assert st["candidates"]
    cand = paths.root / st["candidates"][0]
    assert cand.exists() and cand.suffix == ".mp4"
    meta = json.loads((cand.parent / (cand.name + ".meta.json")).read_text(encoding="utf-8"))
    assert meta["model"] == "seedance-2-5"
    assert meta["prompt"]
    assert meta["cost_usd"] is not None
    assert "HF" not in json.dumps(meta)
    assert [aid for aid, _ in report.done] == ["S01", "S02"]


def test_references_resolved(env):
    paths, project, cfg, _ = env
    _run(env, shots=None, model=None, resolution="480p", dry_run=False,
         yes=True, force=False, allow_unapproved=False)
    call = FakeClient.calls[0]
    assert call["first_image"].endswith("v01_a.png")
    assert len(call["references"]) == 2  # char sheet + location sheet


def test_manifest_uses_composed_prompt(env):
    paths, project, cfg, _ = env
    from storyteller import export
    out = export.build_manifest(paths, project)
    manifest = json.loads(out.read_text(encoding="utf-8"))
    s01 = next(s for s in manifest["shots"] if s["shot_id"] == "S01")
    assert "Subject motion: slow blink." in s01["video_prompt"]
    s02 = next(s for s in manifest["shots"] if s["shot_id"] == "S02")
    assert s02["video_prompt"] == "handheld chase"
