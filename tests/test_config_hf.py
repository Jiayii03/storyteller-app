"""Higgsfield catalog + credential tests."""

from storyteller.config import hf_credentials, load_config


def test_catalog_defaults():
    cfg = load_config()
    e = cfg.higgsfield_models["seedance-2-5"]
    assert e["workflow"] == "bytedance/seedance-2.5/reference-to-video"
    assert e["price_per_sec_usd"]["480p"] == 0.174
    assert e["durations_sec"] == {"min": 4, "max": 30}
    assert e["max_references"] == 30
    assert "image_urls" in e["params"]
    # only ref-to-video workflows seeded
    for mid, entry in cfg.higgsfield_models.items():
        assert "reference-to-video" in entry["workflow"], mid
    assert "seedance-2-0" in cfg.higgsfield_models
    assert "wan-3-0" in cfg.higgsfield_models


def test_catalog_yaml_override(tmp_path):
    (tmp_path / "config.yaml").write_text(
        "higgsfield:\n"
        "  models:\n"
        "    my-model:\n"
        "      workflow: vendor/my-model/reference-to-video\n"
        "      durations_sec: {min: 4, max: 8}\n"
        "      resolutions: ['480p']\n"
        "      price_per_sec_usd: {'480p': 0.5}\n"
        "      params: [prompt, image_urls, duration]\n"
        "      max_references: 3\n",
        encoding="utf-8")
    cfg = load_config(tmp_path)
    assert cfg.higgsfield_models["my-model"]["workflow"] == "vendor/my-model/reference-to-video"
    # defaults still present
    assert "seedance-2-5" in cfg.higgsfield_models


def test_hf_credentials_combined(monkeypatch):
    monkeypatch.setenv("HF_API_KEY", "id1:sec1")
    monkeypatch.delenv("HF_API_KEY_ID", raising=False)
    monkeypatch.delenv("HF_API_KEY_SECRET", raising=False)
    assert hf_credentials() == ("id1", "sec1")


def test_hf_credentials_split(monkeypatch):
    monkeypatch.delenv("HF_API_KEY", raising=False)
    monkeypatch.setenv("HF_API_KEY_ID", "id2")
    monkeypatch.setenv("HF_API_KEY_SECRET", "sec2")
    assert hf_credentials() == ("id2", "sec2")


def test_hf_credentials_missing(monkeypatch, tmp_path):
    for name in ("HF_API_KEY", "HF_API_KEY_ID", "HF_API_KEY_SECRET"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)  # away from the repo's real .env
    assert hf_credentials() == ("", "")
