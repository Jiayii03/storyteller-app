"""`video` subcommand: one reference-to-video clip per shot via Higgsfield.

Walks shots in sequence order, collects each shot's approved references
(start keyframe first, then character and location sheets), shows a per-shot
cost estimate and asks before every submission (Higgsfield never refunds
completed work), downloads the clip into the shot motion candidates folder,
and records state under `video_<shot_id>` so a killed run resumes polling
instead of re-submitting."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from . import cost as cost_mod
from . import prompt_builder, resolver, storage
from .config import Config, hf_credentials
from .higgsfield_client import HiggsfieldClient, HiggsfieldError
from .schema import AssetType, Project, Shot
from .storage import ProjectPaths


class VideoReport:
    def __init__(self):
        self.done: list[tuple[str, str]] = []
        self.failed: list[tuple[str, str]] = []
        self.skipped: list[tuple[str, str]] = []
        self.warnings: list[str] = []
        self.estimates: dict[str, float] = {}
        self.calls: int = 0
        self.cost_usd: float = 0.0
        self.unknown_cost_calls: int = 0


def _video_model_for_shot(project: Project, shot: Shot, model_flag: str | None) -> str:
    if model_flag:
        return model_flag
    for a in resolver.effective_assets(project):
        if a.asset_type == AssetType.motion_clip and a.target_id == shot.id \
                and a.model_override:
            return a.model_override
    model = project.models.video_model
    if not model:
        raise HiggsfieldError(
            "No video model set. Use `video --model <id>` or set "
            "models.video_model in project.json.")
    return model


def _catalog_pricing(cfg: Config) -> dict[str, dict[str, float]]:
    return {mid: (e.get("price_per_sec_usd") or {})
            for mid, e in cfg.higgsfield_models.items()}


def _clamp_duration(cfg: Config, model: str, requested: float) -> tuple[int, str | None]:
    entry = cfg.higgsfield_models[model]
    lo, hi = entry["durations_sec"]["min"], entry["durations_sec"]["max"]
    duration = max(lo, min(int(round(requested)), hi))
    if duration != requested:
        return duration, (f"duration clamped: requested {requested:g}s, model "
                          f"{model} allows {lo}-{hi}s; using {duration}s")
    return duration, None


def shot_references(paths: ProjectPaths, project: Project, shot: Shot,
                    allow_unapproved: bool) -> tuple[Path, list[Path]]:
    """(start keyframe, [character sheets..., location sheet]) — approved
    images only unless allow_unapproved. Raises ValueError naming the
    approve command when the start keyframe is missing."""
    start_asset_id = resolver.start_keyframe_asset_id(project, shot.id)
    if start_asset_id is None:
        raise ValueError(
            f"Shot {shot.id} has no start keyframe asset in project.json")
    first = resolver.resolve_input_image(paths, project, start_asset_id,
                                         allow_unapproved)
    refs: list[Path] = []
    for subj in shot.subjects:
        aid = resolver.reference_asset_id(project, "character", subj.character_id)
        if aid:
            try:
                refs.append(resolver.resolve_input_image(
                    paths, project, aid, allow_unapproved))
            except ValueError:
                pass  # unapproved reference: skip rather than block the shot
    if shot.location_id:
        aid = resolver.reference_asset_id(project, "location", shot.location_id)
        if aid:
            try:
                refs.append(resolver.resolve_input_image(
                    paths, project, aid, allow_unapproved))
            except ValueError:
                pass
    return first, refs


def run_video(
    project_file: Path,
    project: Project,
    cfg: Config,
    shots: list[str] | None = None,
    model: str | None = None,
    resolution: str | None = None,
    dry_run: bool = False,
    yes: bool = False,
    force: bool = False,
    allow_unapproved: bool = False,
) -> VideoReport:
    report = VideoReport()
    paths = ProjectPaths(storage.project_root(project_file))
    paths.ensure_dirs()
    state = storage.load_state(paths)
    pricing = _catalog_pricing(cfg)

    ordered = sorted(project.shots, key=lambda s: s.sequence_index)
    selected = [s for s in ordered if not shots or s.id in shots]

    # validate models + catalog entry shape before any spending
    per_shot: list[tuple[Shot, str, int, float | None, str | None]] = []
    for shot in selected:
        mid = _video_model_for_shot(project, shot, model)
        entry = cfg.higgsfield_models.get(mid)
        if entry is None:
            known = ", ".join(sorted(cfg.higgsfield_models))
            raise HiggsfieldError(
                f"Unknown Higgsfield model {mid!r}. Catalog entries: {known}. "
                "Add it under `higgsfield.models` in config.yaml.")
        missing = [k for k in ("workflow", "durations_sec", "resolutions")
                   if not entry.get(k)]
        if missing:
            raise HiggsfieldError(
                f"Catalog entry {mid!r} is missing {', '.join(missing)} "
                "in config.yaml `higgsfield.models`.")
        res = resolution or project.models.video_resolution or "480p"
        if res not in (entry.get("resolutions") or []):
            raise HiggsfieldError(
                f"Model {mid} does not offer resolution {res!r} "
                f"(offers: {', '.join(entry['resolutions'])}).")
        duration, warn = _clamp_duration(cfg, mid, shot.duration_sec)
        clip_cost = cost_mod.higgsfield_video_cost(mid, res, duration, pricing)
        per_shot.append((shot, mid, duration, clip_cost, warn))
        if warn:
            report.warnings.append(f"{shot.id}: {warn}")
        report.estimates[shot.id] = clip_cost["cost_usd"] if clip_cost else -1.0

    print("Planned video jobs:")
    for shot, mid, duration, clip_cost, warn in per_shot:
        cost_txt = f"~${clip_cost['cost_usd']:.2f}" if clip_cost else "cost unknown"
        print(f"  {shot.id:8} {mid:20} {duration:>3g}s {resolution or project.models.video_resolution or '480p':5} {cost_txt}")
        if warn:
            print(f"  [warn] {shot.id}: {warn}")
    if dry_run:
        print("Dry run: no API calls made.")
        return report

    key_id, key_secret = hf_credentials()
    if not (key_id and key_secret):
        report.failed.append(("*", "HF credentials not set. Put HF_API_KEY="
                             "key_id:secret (or HF_API_KEY_ID / "
                             "HF_API_KEY_SECRET) in .env or the environment."))
        return report
    client = HiggsfieldClient(key_id, key_secret, cfg, paths)

    for shot, mid, duration, clip_cost, _warn in per_shot:
        st = storage.asset_state(state, f"video_{shot.id}")
        if st.get("status") in ("generated", "approved") and not force:
            report.skipped.append((shot.id, f"already {st['status']}"))
            continue
        cost_txt = f"~${clip_cost['cost_usd']:.2f}" if clip_cost else "unknown cost"
        if not yes:
            try:
                answer = input(
                    f"Generate {shot.id}: {duration}s {mid} at "
                    f"{resolution or project.models.video_resolution or '480p'}, "
                    f"{cost_txt}? [y/N] ")
            except EOFError:
                answer = ""
            if answer.strip().lower() not in ("y", "yes"):
                report.skipped.append((shot.id, "aborted by user"))
                break
        try:
            ok = _run_shot(paths, project, shot, cfg, state, client, mid, duration,
                           resolution or project.models.video_resolution or "480p",
                           force, allow_unapproved, report)
            if ok:
                report.done.append((shot.id, "clip generated"))
        except Exception as e:  # noqa: BLE001
            st["status"] = "failed"
            st["error"] = str(e)
            report.failed.append((shot.id, str(e)))
        storage.save_state(paths, state)
    storage.save_state(paths, state)
    return report


def _run_shot(
    paths: ProjectPaths, project: Project, shot: Shot, cfg: Config,
    state: dict[str, Any], client: HiggsfieldClient, model: str,
    duration: int, resolution: str, force: bool, allow_unapproved: bool,
    report: VideoReport,
) -> bool:
    try:
        first, refs = shot_references(paths, project, shot, allow_unapproved)
    except ValueError as e:
        report.skipped.append((shot.id, str(e)))
        return False

    prompt = prompt_builder.compose_motion_prompt(shot)
    state_key = f"video_{shot.id}"
    st = storage.asset_state(state, state_key)
    motion_dir = paths.shot_motion_dir(shot.id)
    resuming = bool(st.get("request_id")) and not force
    if resuming:
        print(f"Resuming {shot.id}: polling existing request "
              f"{st['request_id']} (no new submission)")
    version = int(st.get("version", 0)) + 1
    filename = f"clip_v{version:02d}.mp4"
    destination = motion_dir / "candidates" / filename

    def _persist_request_id(rid: str) -> None:
        # persist before polling: a kill mid-poll must resume, never re-submit
        st["request_id"] = rid
        storage.save_state(paths, state)

    if not resuming:
        report.calls += 1
    clip, usage, request_id = client.generate_clip(
        model=model, prompt=prompt, first_image=first, references=refs,
        duration_sec=duration, resolution=resolution,
        aspect_ratio=project.project.aspect_ratio.value,
        destination=destination, asset_id=state_key,
        request_id=st.get("request_id") if resuming else None,
        on_submitted=_persist_request_id,
    )
    clip_cost = cost_mod.higgsfield_video_cost(
        model, resolution, duration, _catalog_pricing(cfg))

    st["version"] = version
    st["status"] = "generated"
    st["error"] = None
    st["candidates"].append(str(clip.relative_to(paths.root)))
    u = st.setdefault("usage", {"calls": 0, "cost_usd": 0.0})
    u["calls"] += 1
    if clip_cost is not None:
        u["cost_usd"] = round(u["cost_usd"] + clip_cost["cost_usd"], 4)
        report.cost_usd += clip_cost["cost_usd"]
        cost_usd: float | None = clip_cost["cost_usd"]
    else:
        report.unknown_cost_calls += 1
        cost_usd = None

    sidecar = {
        "asset_id": state_key, "asset_type": "video_clip",
        "target_id": shot.id, "prompt": prompt, "model": model,
        "resolution": resolution, "duration_sec": duration,
        "first_image": str(first.relative_to(paths.root) if first.is_relative_to(paths.root) else first),
        "references": [str(r.relative_to(paths.root) if r.is_relative_to(paths.root) else r)
                       for r in refs],
        "request_id": request_id, "usage": usage, "cost_usd": cost_usd,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    (clip.parent / (clip.name + ".meta.json")).write_text(
        json.dumps(sidecar, indent=2, ensure_ascii=False), encoding="utf-8")
    if cost_usd is None:
        storage.log_api_call(paths, f"usage asset={state_key} model={model} "
                                    "cost_usd=unknown (no price entry; add "
                                    "price_per_sec_usd in config.yaml)")
    return True
