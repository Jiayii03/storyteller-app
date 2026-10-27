"""Export manifest tests: video_prompt key, approved keyframe paths."""

import json
from pathlib import Path

from storyteller import export, storage
from storyteller.schema import Project
from storyteller.storage import ProjectPaths

EXAMPLE = Path(__file__).parent.parent / "examples" / "rainy_cafe" / "project.json"


def _tmp_project(tmp_path: Path) -> tuple[ProjectPaths, Project]:
    data = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    data["shots"][0]["motion"]["subject_motion"] = "slow blink"
    data["shots"][0]["motion"]["kling_prompt"] = ""
    project = Project.model_validate(data)
    root = tmp_path / "p"
    root.mkdir()
    (root / "project.json").write_text(json.dumps(data), encoding="utf-8")
    paths = ProjectPaths(storage.project_root(root / "project.json"))
    paths.ensure_dirs()
    # fake approved start keyframe
    kf = paths.shot_keyframe_dir("S01", "start") / "approved"
    kf.mkdir(parents=True)
    (kf / "v01_a.png").write_bytes(b"png")
    return paths, project


def test_manifest_video_prompt_key(tmp_path):
    paths, project = _tmp_project(tmp_path)
    out = export.build_manifest(paths, project)
    manifest = json.loads(out.read_text(encoding="utf-8"))
    entry = manifest["shots"][0]
    assert "kling_prompt" not in entry
    assert entry["video_prompt"].startswith("Animate this frame.")
    assert "Camera: very slow push in" in entry["video_prompt"]
    assert "Subject motion: slow blink." in entry["video_prompt"]
    assert entry["start_keyframe"] is not None
