"""Export manifest: per-shot approved keyframes, video prompt, clips."""

from __future__ import annotations

import json
from pathlib import Path

from . import prompt_builder, resolver, storage
from .schema import AssetType, FrameRole, Project
from .storage import ProjectPaths


def build_manifest(paths: ProjectPaths, project: Project) -> Path:
    shots = sorted(project.shots, key=lambda s: s.sequence_index)
    entries: list[dict] = []
    for shot in shots:
        start_dir = paths.shot_keyframe_dir(shot.id, "start")
        end_dir = paths.shot_keyframe_dir(shot.id, "end")
        motion_dir = paths.shot_motion_dir(shot.id)
        start = storage.approved_file(start_dir)
        end = storage.approved_file(end_dir)
        clip = None
        clips = sorted((p for p in (motion_dir / "approved").glob("*.mp4")
                        if (motion_dir / "approved").exists()), key=lambda p: p.name)
        clip = clips[0] if clips else None
        m = shot.motion
        video_prompt = (m.prompt_override_text
                        or prompt_builder.compose_motion_prompt(shot))
        entries.append({
            "shot_id": shot.id,
            "sequence_index": shot.sequence_index,
            "duration_sec": shot.duration_sec,
            "summary": shot.summary,
            "start_keyframe": str(start.relative_to(paths.root)) if start else None,
            "end_keyframe": str(end.relative_to(paths.root)) if end else None,
            "clip": str(clip.relative_to(paths.root)) if clip else None,
            "video_prompt": video_prompt,
            "transition_out": shot.transition_out.value,
            "audio_notes": m.audio_notes,
        })
    out_dir = paths.root / "export"
    out_dir.mkdir(exist_ok=True)
    out = out_dir / "manifest.json"
    out.write_text(json.dumps({"project": project.project.id, "shots": entries},
                              indent=2, ensure_ascii=False), encoding="utf-8")
    return out
