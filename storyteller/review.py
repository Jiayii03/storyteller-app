"""Static HTML review gallery of all candidates with approve commands."""

from __future__ import annotations

import html
import json
from pathlib import Path

from . import resolver, storage
from .schema import AssetType, Project
from .storage import ProjectPaths


def build_review(paths: ProjectPaths, project: Project, project_file: Path) -> Path:
    assets = resolver.effective_assets(project)
    blocks: list[str] = []
    slug = project.project.id

    for a in assets:
        adir = resolver.asset_dir_for(paths, project, a)
        cands = storage.list_candidates(adir)
        approved = storage.approved_file(adir)
        if not cands and approved is None:
            continue
        imgs: list[str] = []
        for c in cands:
            meta = {}
            mpath = c.with_suffix(c.suffix + ".meta.json")
            if mpath.exists():
                try:
                    meta = json.loads(mpath.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    pass
            rel = c.relative_to(paths.root).as_posix()
            prompt = html.escape((meta.get("prompt") or "")[:600])
            marker = ""
            if approved is not None and approved.name == c.name:
                marker = " (APPROVED)"
            cmd = f"uv run main.py approve {slug} {a.asset_id} {c.name}"
            imgs.append(
                f"<figure><img src='../{rel}' loading='lazy'>"
                f"<figcaption>{html.escape(c.name)}{marker}<br>"
                f"<code>{html.escape(cmd)}</code><br>"
                f"<details><summary>prompt</summary><pre>{prompt}</pre></details>"
                f"</figcaption></figure>"
            )
        blocks.append(
            f"<section><h2>{html.escape(a.asset_id)} <small>{a.asset_type.value}"
            f"</small></h2><div class='grid'>{''.join(imgs)}</div></section>"
        )

    doc = f"""<!doctype html><html><head><meta charset='utf-8'>
<title>Review: {html.escape(project.project.title)}</title>
<style>
body{{font-family:system-ui,sans-serif;margin:2rem;background:#111;color:#eee}}
h2{{border-bottom:1px solid #444;padding-bottom:.3rem}}
.grid{{display:flex;flex-wrap:wrap;gap:1rem}}
figure{{max-width:340px;margin:0;background:#1c1c1c;padding:.5rem;border-radius:8px}}
img{{max-width:100%;border-radius:4px}}
code{{background:#000;padding:.1rem .3rem;border-radius:4px;user-select:all}}
pre{{white-space:pre-wrap;font-size:.8rem}}
summary{{cursor:pointer;color:#8cf}}
</style></head><body>
<h1>{html.escape(project.project.title)} — review candidates</h1>
{''.join(blocks) or '<p>No candidates yet. Run: <code>uv run main.py generate</code></p>'}
</body></html>"""
    paths.storyboard.mkdir(parents=True, exist_ok=True)
    out = paths.storyboard / "review.html"
    out.write_text(doc, encoding="utf-8")
    return out
