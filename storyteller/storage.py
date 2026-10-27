"""Folder layout, candidate files, sidecar meta, approvals, state.json."""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from typing import Any

STATE_FILENAME = "state.json"
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}


# ---------------------------------------------------------------- paths


def project_root(project_file: Path) -> Path:
    """Root folder = directory containing project.json."""
    return project_file.parent.resolve()


class ProjectPaths:
    def __init__(self, root: Path):
        self.root = root
        self.inputs = root / "inputs"
        self.assets = root / "assets"
        self.storyboard = root / "storyboard"
        self.logs = root / "logs"
        self.state_file = root / "state.json"

    # --- asset folders -------------------------------------------------
    def style_dir(self) -> Path:
        return self.assets / "style"

    def character_dir(self, character_id: str) -> Path:
        return self.assets / "characters" / character_id

    def location_dir(self, location_id: str) -> Path:
        return self.assets / "locations" / location_id

    def prop_dir(self, prop_id: str) -> Path:
        return self.assets / "props" / prop_id

    def shot_keyframe_dir(self, shot_id: str, role: str) -> Path:
        return self.assets / "shots" / shot_id / "keyframes" / role

    def shot_motion_dir(self, shot_id: str) -> Path:
        return self.assets / "shots" / shot_id / "motion"

    def candidates_dir(self, asset_dir: Path) -> Path:
        return asset_dir / "candidates"

    def approved_dir(self, asset_dir: Path) -> Path:
        return asset_dir / "approved"

    def ensure_dirs(self) -> None:
        for d in (self.inputs, self.assets, self.storyboard, self.logs):
            d.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------- state


def load_state(paths: ProjectPaths) -> dict[str, Any]:
    if paths.state_file.exists():
        return json.loads(paths.state_file.read_text(encoding="utf-8"))
    return {"schema_version": "0.1", "assets": {}}


def save_state(paths: ProjectPaths, state: dict[str, Any]) -> None:
    state["updated"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    tmp = paths.state_file.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(paths.state_file)


def asset_state(state: dict[str, Any], asset_id: str) -> dict[str, Any]:
    return state.setdefault("assets", {}).setdefault(
        asset_id,
        {"status": "pending", "approved": None, "version": 0, "error": None,
         "candidates": [], "attempts": 0},
    )


# ---------------------------------------------------------------- files


def next_candidate_name(paths: ProjectPaths, asset_dir: Path, state: dict[str, Any],
                        asset_id: str, index: int, ext: str = ".png") -> str:
    """v01_a.png, v01_b.png ... version bumps per run that regenerates the asset."""
    st = asset_state(state, asset_id)
    version = int(st.get("version", 0)) + 1
    st["version"] = version
    letter = chr(ord("a") + index)
    return f"v{version:02d}_{letter}{ext}"


def write_candidate(paths: ProjectPaths, asset_dir: Path, filename: str, data: bytes,
                    meta: dict[str, Any]) -> Path:
    cand = paths.candidates_dir(asset_dir)
    cand.mkdir(parents=True, exist_ok=True)
    out = cand / filename
    out.write_bytes(data)
    sidecar = out.with_suffix(out.suffix + ".meta.json")
    sidecar.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    return out


def list_candidates(asset_dir: Path) -> list[Path]:
    cand = asset_dir / "candidates"
    if not cand.exists():
        return []
    return sorted(
        p for p in cand.iterdir()
        if p.is_file() and p.suffix in IMAGE_EXTS
    )


def approved_file(asset_dir: Path) -> Path | None:
    ap = asset_dir / "approved"
    if not ap.exists():
        return None
    for p in sorted(ap.iterdir()):
        if p.is_file() and p.suffix in IMAGE_EXTS:
            return p
    return None


def approve(paths: ProjectPaths, asset_dir: Path, candidate_filename: str) -> Path:
    src = paths.candidates_dir(asset_dir) / candidate_filename
    if not src.exists():
        raise FileNotFoundError(f"Candidate not found: {src}")
    ap = paths.approved_dir(asset_dir)
    ap.mkdir(parents=True, exist_ok=True)
    # exactly one approved image per asset: clear folder first
    for old in ap.iterdir():
        if old.is_file():
            old.unlink()
    dst = ap / src.name
    shutil.copyfile(src, dst)
    return dst


def reject(asset_dir: Path) -> bool:
    ap = asset_dir / "approved"
    had = False
    if ap.exists():
        for p in ap.iterdir():
            if p.is_file():
                p.unlink()
                had = True
    return had


def newest_candidate(asset_dir: Path) -> Path | None:
    cands = list_candidates(asset_dir)
    return cands[-1] if cands else None


def write_meta_only(paths: ProjectPaths, asset_dir: Path, filename: str,
                    meta: dict[str, Any]) -> None:
    sidecar = paths.candidates_dir(asset_dir) / (filename + ".meta.json")
    sidecar.parent.mkdir(parents=True, exist_ok=True)
    sidecar.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")


def log_api_call(paths: ProjectPaths, message: str) -> None:
    """Append one line to logs/run_<date>.log. Never log the API key."""
    paths.logs.mkdir(parents=True, exist_ok=True)
    name = f"run_{time.strftime('%Y%m%d_%H%M%S')}.log"
    with open(paths.logs / name, "a", encoding="utf-8") as f:
        f.write(f"{time.strftime('%H:%M:%S')}  {message}\n")
