"""Contact sheet of approved start keyframes (Pillow), labelled with captions."""

from __future__ import annotations

import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from . import resolver, storage
from .config import Config
from .schema import AssetType, FrameRole, Project
from .storage import ProjectPaths

LABEL_H = 72
CELL_W = 480


def build_storyboard(paths: ProjectPaths, project: Project, cfg: Config,
                     columns: int | None = None) -> Path:
    cols = columns or cfg.storyboard_columns
    start_assets = [
        a for a in resolver.effective_assets(project)
        if a.asset_type == AssetType.keyframe and a.frame_role in (FrameRole.start, FrameRole.single)
    ]
    shot_by_id = {s.id: s for s in project.shots}
    ordered = sorted(
        start_assets,
        key=lambda a: shot_by_id.get(a.target_id).sequence_index if a.target_id in shot_by_id else 0,
    )
    cells: list[tuple[Image.Image, str]] = []
    total_sec = 0.0
    for a in ordered:
        adir = resolver.asset_dir_for(paths, project, a)
        img_path = storage.approved_file(adir)
        if img_path is None:
            continue
        shot = shot_by_id.get(a.target_id)
        label = a.target_id
        if shot is not None:
            total_sec += shot.duration_sec
            label = f"{shot.id}  {shot.duration_sec:g}s  {shot.summary}"
        im = Image.open(img_path).convert("RGB")
        ratio = CELL_W / im.width
        im = im.resize((CELL_W, int(im.height * ratio)))
        cells.append((im, label))
    if not cells:
        raise ValueError(
            "No approved start keyframes. Approve keyframe candidates first, e.g.: "
            "uv run main.py approve " + project.project.id + " kf_S01_start v01_a.png")

    rows = (len(cells) + cols - 1) // cols
    cell_h = max(im.height for im, _ in cells) + LABEL_H
    canvas = Image.new("RGB", (cols * CELL_W + (cols + 1) * 16,
                               rows * cell_h + (rows + 1) * 16 + 48), (18, 18, 18))
    draw = ImageDraw.Draw(canvas)
    try:
        font = ImageFont.load_default(16)
        big = ImageFont.load_default(20)
    except TypeError:  # Pillow < 10.1
        font = ImageFont.load_default()
        big = font
    for idx, (im, label) in enumerate(cells):
        r, c = divmod(idx, cols)
        x = 16 + c * (CELL_W + 16)
        y = 16 + r * (cell_h + 16)
        canvas.paste(im, (x, y))
        wrapped = "\n".join(textwrap.wrap(label, width=46)[:3])
        draw.text((x + 4, y + im.height + 6), wrapped, fill=(240, 240, 240), font=font)
    draw.text((16, canvas.height - 38),
              f"Total running time: {total_sec:g}s",
              fill=(200, 200, 200), font=big)
    paths.storyboard.mkdir(parents=True, exist_ok=True)
    out = paths.storyboard / "storyboard_v01.png"
    out.write_bytes(b"")
    canvas.save(out)
    return out
