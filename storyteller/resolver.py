"""Dependency graph, auto job list, input image resolution, validation rules."""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from . import storage
from .schema import (
    AssetJob, AssetType, FrameRole, Project, Status,
)

SLUG_RE = re.compile(r"[A-Za-z0-9_]+")
ALLOWED_INPUT_EXTS = storage.IMAGE_EXTS


# ---------------------------------------------------------------- job list


def auto_assets(project: Project) -> list[AssetJob]:
    """Default job list when assets[] is omitted: one reference per entity,
    one start keyframe per shot, and a storyboard sheet."""
    jobs: list[AssetJob] = []
    for ch in project.characters:
        jobs.append(AssetJob(asset_id=f"char_{ch.id}", asset_type=AssetType.character_reference,
                             target_id=ch.id))
    for loc in project.locations:
        jobs.append(AssetJob(asset_id=f"loc_{loc.id}", asset_type=AssetType.location_reference,
                             target_id=loc.id))
    for pr in project.props:
        jobs.append(AssetJob(asset_id=f"prop_{pr.id}", asset_type=AssetType.prop_reference,
                             target_id=pr.id))
    for shot in project.shots:
        jobs.append(AssetJob(asset_id=f"kf_{shot.id}_start", asset_type=AssetType.keyframe,
                             target_id=shot.id, frame_role=FrameRole.start))
    jobs.append(AssetJob(asset_id="storyboard", asset_type=AssetType.storyboard_sheet,
                         target_id="project"))
    return jobs


def effective_assets(project: Project) -> list[AssetJob]:
    return project.assets if project.assets else auto_assets(project)


# ---------------------------------------------------------------- dependencies


def reference_asset_id(project: Project, kind: str, entity_id: str) -> str | None:
    """Find the reference asset id for an entity, if the job list defines one."""
    type_map = {
        "character": AssetType.character_reference,
        "location": AssetType.location_reference,
        "prop": AssetType.prop_reference,
        "style": AssetType.style_reference,
    }
    want = type_map[kind]
    for a in effective_assets(project):
        if a.asset_type == want:
            if kind == "style" or a.target_id == entity_id:
                return a.asset_id
    return None


def start_keyframe_asset_id(project: Project, shot_id: str) -> str | None:
    """Asset id of a shot's start (or single) keyframe, whatever it is named."""
    for a in effective_assets(project):
        if a.asset_type == AssetType.keyframe and a.target_id == shot_id and \
                a.frame_role in (FrameRole.start, FrameRole.single):
            return a.asset_id
    return None


def dependencies(project: Project, asset: AssetJob) -> list[str]:
    """Asset ids this asset needs approved before it can run."""
    deps: list[str] = list(asset.input_asset_ids)
    shots = {s.id: s for s in project.shots}

    if asset.asset_type == AssetType.keyframe:
        shot = shots.get(asset.target_id)
        if shot is not None:
            if shot.location_id:
                d = reference_asset_id(project, "location", shot.location_id)
                if d and d not in deps:
                    deps.append(d)
            for subj in shot.subjects:
                d = reference_asset_id(project, "character", subj.character_id)
                if d and d not in deps:
                    deps.append(d)
            for p in shot.props_in_shot:
                d = reference_asset_id(project, "prop", p.prop_id)
                if d and d not in deps:
                    deps.append(d)
        # end keyframe needs the start keyframe for the same shot
        if asset.frame_role == FrameRole.end:
            start_id = start_keyframe_asset_id(project, asset.target_id)
            if start_id and start_id != asset.asset_id and start_id not in deps:
                deps.append(start_id)
        # chain_from_previous: depends on the previous shot's start keyframe
        if shot is not None and shot.chain_from_previous:
            ordered = sorted(project.shots, key=lambda s: s.sequence_index)
            prev = None
            for s in ordered:
                if s.id == shot.id:
                    break
                prev = s
            if prev is not None:
                prev_id = start_keyframe_asset_id(project, prev.id)
                if prev_id and prev_id not in deps:
                    deps.append(prev_id)

    if asset.asset_type == AssetType.motion_clip:
        # needs a keyframe asset as input; if none listed, use the shot's start keyframe
        if not asset.input_asset_ids:
            start_id = start_keyframe_asset_id(project, asset.target_id)
            if start_id and start_id not in deps:
                deps.append(start_id)

    if asset.asset_type == AssetType.storyboard_sheet:
        for a in effective_assets(project):
            if a.asset_type == AssetType.keyframe and a.frame_role in (FrameRole.start, FrameRole.single):
                if a.asset_id not in deps:
                    deps.append(a.asset_id)

    return deps


def topo_order(project: Project) -> list[AssetJob]:
    """Assets in dependency order. Raises ValueError on cycles."""
    assets = effective_assets(project)
    by_id = {a.asset_id: a for a in assets}
    deps: dict[str, list[str]] = {}
    for a in assets:
        d = [x for x in dependencies(project, a) if x != a.asset_id and x in by_id]
        deps[a.asset_id] = d

    state: dict[str, int] = {}  # 0=unvisited 1=in-stack 2=done
    order: list[AssetJob] = []

    def visit(node: str, stack: list[str]) -> None:
        st = state.get(node, 0)
        if st == 2:
            return
        if st == 1:
            cycle = " -> ".join(stack + [node])
            raise ValueError(f"Dependency cycle among assets: {cycle}")
        state[node] = 1
        for dep in deps[node]:
            visit(dep, stack + [node])
        state[node] = 2
        order.append(by_id[node])

    for a in assets:
        visit(a.asset_id, [])
    return order


# ---------------------------------------------------------------- inputs


def asset_dir_for(paths: storage.ProjectPaths, project: Project, asset: AssetJob) -> Path:
    if asset.asset_type == AssetType.style_reference:
        return paths.style_dir()
    if asset.asset_type == AssetType.character_reference:
        return paths.character_dir(asset.target_id)
    if asset.asset_type == AssetType.location_reference:
        return paths.location_dir(asset.target_id)
    if asset.asset_type == AssetType.prop_reference:
        return paths.prop_dir(asset.target_id)
    if asset.asset_type == AssetType.keyframe:
        return paths.shot_keyframe_dir(asset.target_id, asset.frame_role.value)
    if asset.asset_type == AssetType.motion_clip:
        return paths.shot_motion_dir(asset.target_id)
    return paths.storyboard


MISSING_APPROVED_MSG = (
    "Asset {asset_id} has no approved image. Run: uv run main.py approve {project} {asset_id} <candidate_filename>"
)


def resolve_input_image(
    paths: storage.ProjectPaths, project: Project, asset_id: str,
    allow_unapproved: bool,
) -> Path:
    """Resolve one input_asset_id to its approved file (or newest candidate)."""
    target = next((a for a in effective_assets(project) if a.asset_id == asset_id), None)
    if target is None:
        raise ValueError(f"Input asset {asset_id!r} is not defined in the job list.")
    adir = asset_dir_for(paths, project, target)
    approved = storage.approved_file(adir)
    if approved is not None:
        return approved
    if allow_unapproved:
        newest = storage.newest_candidate(adir)
        if newest is not None:
            return newest
    raise ValueError(MISSING_APPROVED_MSG.format(
        asset_id=asset_id, project=project.project.id))


def _legend(kind: str, name: str) -> str:
    if kind == "style":
        return "the style reference: match its look, color palette and lighting"
    if kind == "character":
        return f"the identity reference for {name}: keep face, hair and build identical"
    if kind == "location":
        return f"the reference for the {name} location: keep layout and materials"
    if kind == "prop":
        return f"the reference for the prop {name}: keep its design and condition"
    if kind == "start_keyframe":
        return f"the approved start keyframe for shot {name}: keep everything unchanged except what is listed below"
    if kind == "previous_keyframe":
        return f"the previous approved keyframe (shot {name}): match lighting and color"
    return f"an additional input reference ({name or 'image'})"


def resolve_inputs(
    paths: storage.ProjectPaths, project: Project, asset: AssetJob,
    allow_unapproved: bool,
) -> list[tuple[Path, str]]:
    """All input images for an asset as (path, legend) in fixed order:
    style, characters (shot order), location, props, start keyframe (for end
    role), previous keyframe, explicit input_asset_ids, user-supplied paths.
    Raises ValueError with a clear message if an input is not approved."""
    resolved: list[tuple[Path, str]] = []
    seen_ids: set[str] = set()
    shots = {s.id: s for s in project.shots}

    def add(aid: str, legend: str) -> None:
        if aid in seen_ids:
            return
        resolved.append((resolve_input_image(paths, project, aid, allow_unapproved), legend))
        seen_ids.add(aid)

    if asset.asset_type == AssetType.keyframe:
        shot = shots.get(asset.target_id)
        if shot is not None:
            style = reference_asset_id(project, "style", "")
            if style:
                add(style, _legend("style", ""))
            for subj in shot.subjects:
                aid = reference_asset_id(project, "character", subj.character_id)
                if aid:
                    ch = next((c for c in project.characters if c.id == subj.character_id), None)
                    add(aid, _legend("character", ch.name if ch else subj.character_id))
            if shot.location_id:
                aid = reference_asset_id(project, "location", shot.location_id)
                if aid:
                    loc = next((l for l in project.locations if l.id == shot.location_id), None)
                    add(aid, _legend("location", loc.name if loc else shot.location_id))
            for p in shot.props_in_shot:
                aid = reference_asset_id(project, "prop", p.prop_id)
                if aid:
                    pr = next((x for x in project.props if x.id == p.prop_id), None)
                    add(aid, _legend("prop", pr.name if pr else p.prop_id))
            if asset.frame_role == FrameRole.end:
                start_id = start_keyframe_asset_id(project, shot.id)
                if start_id:
                    add(start_id, _legend("start_keyframe", shot.id))
            if shot.chain_from_previous:
                ordered = sorted(project.shots, key=lambda s: s.sequence_index)
                prev = None
                for s in ordered:
                    if s.id == shot.id:
                        break
                    prev = s
                if prev is not None:
                    prev_id = start_keyframe_asset_id(project, prev.id)
                    if prev_id:
                        add(prev_id, _legend("previous_keyframe", prev.id))

    if asset.asset_type == AssetType.motion_clip:
        for aid in asset.input_asset_ids:
            add(aid, _legend("extra", aid))

    for aid in asset.input_asset_ids:
        add(aid, _legend("extra", aid))

    for path_str in asset.input_image_paths:
        p = (paths.root / path_str) if not Path(path_str).is_absolute() else Path(path_str)
        if not p.exists():
            raise ValueError(f"Input image not found: {p}")
        resolved.append((p, _legend("extra", path_str)))

    return resolved


# ---------------------------------------------------------------- validation


def validate_project(project: Project, root: Path | None = None) -> tuple[list[str], list[str]]:
    """Returns (errors, warnings). Enum and type checks happen in pydantic."""
    errors: list[str] = []
    warnings: list[str] = []

    assets = effective_assets(project)
    asset_ids = [a.asset_id for a in assets]

    def check_unique(ids: list[str], label: str) -> None:
        seen: set[str] = set()
        for i in ids:
            if i in seen:
                errors.append(f"Duplicate {label} id: {i!r}")
            seen.add(i)
            if not SLUG_RE.fullmatch(i):
                errors.append(f"{label} id not slug-formatted (letters, digits, underscores): {i!r}")

    check_unique([c.id for c in project.characters], "character")
    check_unique([l.id for l in project.locations], "location")
    check_unique([p.id for p in project.props], "prop")
    check_unique([s.id for s in project.shots], "shot")
    check_unique(asset_ids, "asset")

    char_ids = {c.id for c in project.characters}
    loc_ids = {l.id for l in project.locations}
    prop_ids = {p.id for p in project.props}
    shot_ids = {s.id for s in project.shots}
    asset_id_set = set(asset_ids)

    for s in project.shots:
        if s.location_id and s.location_id not in loc_ids:
            errors.append(f"Shot {s.id}: location_id {s.location_id!r} does not exist in locations[]")
        for subj in s.subjects:
            if subj.character_id not in char_ids:
                errors.append(f"Shot {s.id} subject: character_id {subj.character_id!r} does not exist in characters[]")
        for p in s.props_in_shot:
            if p.prop_id not in prop_ids:
                errors.append(f"Shot {s.id} props_in_shot: prop_id {p.prop_id!r} does not exist in props[]")
        if len(s.subjects) > 3:
            warnings.append(
                f"Shot {s.id}: {len(s.subjects)} subjects; consistency drops quickly above 3 people")

    for p in project.props:
        if p.branding_text:
            warnings.append(
                f"Prop {p.id}: branding_text requested ({p.branding_text!r}); image models render text unreliably")

    for a in assets:
        for aid in a.input_asset_ids:
            if aid not in asset_id_set:
                errors.append(f"Asset {a.asset_id}: input_asset_id {aid!r} does not exist in assets[]")
        if a.asset_type == AssetType.keyframe and a.frame_role == FrameRole.end:
            start_id = f"kf_{a.target_id}_start"
            has_start = any(
                x.asset_type == AssetType.keyframe and x.frame_role == FrameRole.start
                and x.target_id == a.target_id for x in assets)
            if not has_start and start_id not in asset_id_set:
                errors.append(
                    f"Asset {a.asset_id}: 'end' keyframe requires a 'start' keyframe asset for shot {a.target_id}")
        if a.asset_type == AssetType.motion_clip:
            kf_inputs = [aid for aid in a.input_asset_ids if aid in asset_id_set and
                         next(x for x in assets if x.asset_id == aid).asset_type == AssetType.keyframe]
            if not kf_inputs:
                errors.append(f"Asset {a.asset_id}: motion_clip requires a keyframe asset in input_asset_ids")

    try:
        topo_order(project)
    except ValueError as e:
        errors.append(str(e))

    if root is not None:
        paths = storage.ProjectPaths(root)
        all_paths = list(project.style_bible.reference_image_paths)
        for c in project.characters:
            all_paths += c.input_reference_images
        for l in project.locations:
            all_paths += l.input_reference_images
        for p in project.props:
            all_paths += p.input_reference_images
        for a in assets:
            all_paths += a.input_image_paths
        limit_bytes = 20 * 1024 * 1024
        for raw in all_paths:
            p = Path(raw) if Path(raw).is_absolute() else root / raw
            if not p.exists():
                errors.append(f"Input image not found: {p}")
                continue
            if p.suffix.lower() not in ALLOWED_INPUT_EXTS:
                errors.append(f"Input image must be PNG, JPG or WEBP: {p}")
            elif p.stat().st_size > limit_bytes:
                warnings.append(f"Input image larger than 20 MB: {p}")

    return errors, warnings

