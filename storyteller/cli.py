"""CLI: argparse subcommands. Entry point used by main.py."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pydantic import ValidationError
from rich.console import Console
from rich.table import Table

from . import __version__, resolver, storage
from .config import Config, load_config
from .schema import Project, format_validation_error

console = Console()
err_console = Console(stderr=True, style="red")

TEMPLATE = {
    "schema_version": "0.1",
    "project": {
        "id": "REPLACE_PROJECT_ID",
        "title": "New project",
        "logline": "",
        "aspect_ratio": "16:9",
        "target_video_model": "higgsfield",
        "target_total_duration_sec": 30,
    },
    "models": {
        "image_model": "gemini-3.1-flash-image",
        "video_model": "gemini-omni-1.1-flash",
        "image_resolution": "1K",
        "video_resolution": "720p",
    },
    "style_bible": {
        "medium": "cinematic_film_still",
        "genre_mood": "",
        "color_palette": [],
        "color_grade": "",
        "film_stock_or_look": "",
        "default_lens_mm": 35,
        "lighting_style": "",
        "texture_detail": "",
        "era_setting": "",
        "global_negative_prompt": ["text", "watermark", "logo", "blurry", "distorted face"],
        "reference_image_paths": [],
    },
    "characters": [],
    "locations": [],
    "props": [],
    "shots": [],
    "assets": [],
}

GITIGNORE = """.env
__pycache__/
*.pyc
.venv/
"""


# ---------------------------------------------------------------- helpers


def _load_project(path_str: str) -> Project:
    path = Path(path_str)
    if not path.exists():
        err_console.print(f"[red]Project file not found: {path}[/red]")
        raise SystemExit(2)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return Project.model_validate(data)
    except ValidationError as e:
        for line in format_validation_error(e):
            err_console.print(f"[red]validation error[/red] {line}")
        raise SystemExit(2)
    except json.JSONDecodeError as e:
        err_console.print(f"[red]Invalid JSON in {path}: {e}[/red]")
        raise SystemExit(2)


def _cfg_for(path_str: str) -> Config:
    p = Path(path_str).parent if path_str else Path.cwd()
    return load_config(p if p.exists() else None)


def _paths_for(path_str: str) -> storage.ProjectPaths:
    return storage.ProjectPaths(storage.project_root(Path(path_str)))


# ---------------------------------------------------------------- commands


def cmd_init(args: argparse.Namespace) -> None:
    root = Path("projects") / args.project_id
    if root.exists() and not args.force:
        err_console.print(f"[red]Folder already exists: {root} (use --force to overwrite)[/red]")
        raise SystemExit(2)
    root.mkdir(parents=True, exist_ok=True)
    (root / "inputs").mkdir(exist_ok=True)
    (root / ".gitignore").write_text(GITIGNORE, encoding="utf-8")
    tpl = dict(TEMPLATE)
    tpl["project"] = {**TEMPLATE["project"], "id": args.project_id}
    (root / "project.json").write_text(
        json.dumps(tpl, indent=2, ensure_ascii=False), encoding="utf-8")
    console.print(f"[green]Scaffolded {root / 'project.json'}. Edit it, then:[/green] "
                  f"uv run main.py plan {root / 'project.json'}")


def cmd_validate(args: argparse.Namespace) -> None:
    project = _load_project(args.project)
    root = storage.project_root(Path(args.project))
    errors, warnings = resolver.validate_project(project, root)
    for w in warnings:
        console.print(f"[yellow]WARN[/yellow] {w}")
    for e in errors:
        err_console.print(f"[red]ERROR[/red] {e}")
    if errors:
        raise SystemExit(1)
    console.print("[green]OK: project valid.[/green]")


def cmd_plan(args: argparse.Namespace) -> None:
    from . import runner

    project = _load_project(args.project)
    cfg = _cfg_for(args.project)
    rows = runner.plan_list(project)
    est = runner.estimate(project, cfg)
    table = Table(title=f"Job list: {project.project.title}")
    table.add_column("#")
    table.add_column("asset_id")
    table.add_column("type")
    table.add_column("calls")
    table.add_column("depends on")
    for i, (a, deps) in enumerate(rows, 1):
        v = a.variants or cfg.default_variants
        calls = "0" if a.asset_type.value == "storyboard_sheet" else (
            "1 (video)" if a.asset_type.value == "motion_clip" else str(v))
        table.add_row(str(i), a.asset_id, a.asset_type.value, calls, ", ".join(deps) or "-")
    console.print(table)
    console.print(f"Estimated API calls: {est['calls']} (images) + "
                  f"{est['video_secs']:g}s video, ~${est['cost_usd']:.2f}")
    console.print("Dry-run prompts: uv run main.py prompt <project.json> <asset_id>")


def cmd_prompt(args: argparse.Namespace) -> None:
    from . import prompt_builder
    from .resolver import resolve_inputs

    project = _load_project(args.project)
    paths = _paths_for(args.project)
    assets = resolver.effective_assets(project)
    asset = next((a for a in assets if a.asset_id == args.asset_id), None)
    if asset is None:
        err_console.print(f"[red]Asset not found: {args.asset_id}. Assets: "
                          f"{', '.join(a.asset_id for a in assets)}[/red]")
        raise SystemExit(2)
    try:
        inputs = resolve_inputs(paths, project, asset, args.allow_unapproved)
        built = prompt_builder.build_prompt(project, asset, inputs)
    except ValueError as e:
        err_console.print(f"[red]{e}[/red]")
        raise SystemExit(1)
    console.print(f"[bold]Prompt for {asset.asset_id}[/bold]\n")
    console.print(built["prompt_text"])
    neg = built["negative_prompt"]
    if neg and neg not in built["prompt_text"]:
        console.print(f"\n[yellow]{neg}[/yellow]")
    if built["input_images"]:
        console.print("\n[bold]Input images:[/bold]")
        for p, legend in built["input_images"]:
            console.print(f"  {p}  ({legend})")


def cmd_generate(args: argparse.Namespace) -> None:
    from . import runner

    project = _load_project(args.project)
    cfg = _cfg_for(args.project)
    report = runner.generate(
        Path(args.project), project, cfg,
        asset_filter=args.asset or None,
        type_filter=args.type,
        shot_filter=args.shot,
        variants_override=args.variants,
        force=args.force,
        dry_run=args.dry_run,
        yes=args.yes,
        allow_unapproved=args.allow_unapproved,
    )
    for aid, why in report.skipped:
        console.print(f"[yellow]SKIP[/yellow] {aid}: {why}")
    for aid, why in report.failed:
        err_console.print(f"[red]FAIL[/red] {aid}: {why}")
    if report.failed:
        raise SystemExit(1)
    if args.dry_run:
        return
    console.print(f"[green]Done. {len(report.done)} generated, "
                  f"{len(report.skipped)} skipped, {report.calls} API calls.[/green]")
    usage_line = (f"Usage this run: {report.tokens} input tokens, "
                  f"${report.cost_usd:.4f}")
    if report.unknown_cost_calls:
        usage_line += (f" ({report.unknown_cost_calls} calls without a pricing "
                       "entry - add rates to `pricing` in config.yaml)")
    console.print(usage_line + ". Per-call detail: logs/run_*.log")
    console.print("Review candidates: uv run main.py review " + args.project)


def cmd_review(args: argparse.Namespace) -> None:
    from .review import build_review

    project = _load_project(args.project)
    paths = _paths_for(args.project)
    out = build_review(paths, project, Path(args.project))
    console.print(f"[green]Wrote {out}[/green] - open it in a browser.")


def cmd_approve(args: argparse.Namespace) -> None:
    project = _load_project(args.project)
    paths = _paths_for(args.project)
    assets = resolver.effective_assets(project)
    asset = next((a for a in assets if a.asset_id == args.asset_id), None)
    if asset is None:
        err_console.print(f"[red]Asset not found: {args.asset_id}[/red]")
        raise SystemExit(2)
    adir = resolver.asset_dir_for(paths, project, asset)
    try:
        dst = storage.approve(paths, adir, args.candidate_filename)
    except FileNotFoundError as e:
        err_console.print(f"[red]{e}[/red]")
        raise SystemExit(2)
    state = storage.load_state(paths)
    st = storage.asset_state(state, asset.asset_id)
    st["status"] = "approved"
    st["approved"] = str(dst.relative_to(paths.root))
    st["error"] = None
    storage.save_state(paths, state)
    console.print(f"[green]Approved {args.asset_id}: {dst.relative_to(paths.root)}[/green]")


def cmd_reject(args: argparse.Namespace) -> None:
    project = _load_project(args.project)
    paths = _paths_for(args.project)
    assets = resolver.effective_assets(project)
    asset = next((a for a in assets if a.asset_id == args.asset_id), None)
    if asset is None:
        err_console.print(f"[red]Asset not found: {args.asset_id}[/red]")
        raise SystemExit(2)
    adir = resolver.asset_dir_for(paths, project, asset)
    had = storage.reject(adir)
    state = storage.load_state(paths)
    st = storage.asset_state(state, asset.asset_id)
    st["status"] = "generated" if had else "pending"
    st["approved"] = None
    storage.save_state(paths, state)
    console.print(f"[green]Cleared approval for {args.asset_id} (files kept).[/green]")


def cmd_storyboard(args: argparse.Namespace) -> None:
    from .storyboard import build_storyboard

    project = _load_project(args.project)
    paths = _paths_for(args.project)
    cfg = _cfg_for(args.project)
    try:
        out = build_storyboard(paths, project, cfg, args.columns)
    except ValueError as e:
        err_console.print(f"[red]{e}[/red]")
        raise SystemExit(1)
    console.print(f"[green]Wrote {out}[/green]")


def cmd_export(args: argparse.Namespace) -> None:
    from .export import build_manifest

    project = _load_project(args.project)
    paths = _paths_for(args.project)
    out = build_manifest(paths, project)
    console.print(f"[green]Wrote {out}[/green]")


def cmd_status(args: argparse.Namespace) -> None:
    project = _load_project(args.project)
    paths = _paths_for(args.project)
    state = storage.load_state(paths)
    table = Table(title="Asset status")
    table.add_column("asset_id")
    table.add_column("type")
    table.add_column("status")
    table.add_column("approved")
    table.add_column("calls")
    table.add_column("cost_usd")
    table.add_column("note")
    for a in resolver.effective_assets(project):
        st = state.get("assets", {}).get(a.asset_id, {})
        u = st.get("usage", {}) or {}
        table.add_row(
            a.asset_id, a.asset_type.value,
            st.get("status", "pending"),
            (st.get("approved") or "-"),
            str(u.get("calls", 0) or 0),
            (f"{u.get('cost_usd', 0):.4f}" if u.get("calls") else "-"),
            (st.get("error") or ""),
        )
    console.print(table)


def cmd_schema(_args: argparse.Namespace) -> None:
    from .schema import Project

    print(json.dumps(Project.model_json_schema(), indent=2))


# ---------------------------------------------------------------- parser


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="storyteller",
        description="Reference images, keyframes and motion tests for an AI video pipeline.")
    p.add_argument("--version", action="version", version=f"storyteller {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("init", help="scaffold folder + template project.json")
    sp.add_argument("project_id")
    sp.add_argument("--force", action="store_true")
    sp.set_defaults(func=cmd_init)

    sp = sub.add_parser("validate", help="schema + reference integrity check")
    sp.add_argument("project", help="path to project.json")
    sp.set_defaults(func=cmd_validate)

    sp = sub.add_parser("plan", help="job list, dependency order, estimated calls and cost")
    sp.add_argument("project")
    sp.set_defaults(func=cmd_plan)

    sp = sub.add_parser("prompt", help="print final prompt and input images (no API call)")
    sp.add_argument("project")
    sp.add_argument("asset_id")
    sp.add_argument("--allow-unapproved", action="store_true")
    sp.set_defaults(func=cmd_prompt)

    sp = sub.add_parser("generate", help="generate pending assets in dependency order")
    sp.add_argument("project")
    sp.add_argument("--asset", action="append", help="asset id (repeatable)")
    sp.add_argument("--type", help="filter by asset type")
    sp.add_argument("--shot", help="filter by shot id")
    sp.add_argument("--variants", type=int, help="override variants for this run")
    sp.add_argument("--dry-run", action="store_true")
    sp.add_argument("--yes", action="store_true", help="skip cost confirmation")
    sp.add_argument("--force", action="store_true", help="regenerate even if generated/approved")
    sp.add_argument("--allow-unapproved", action="store_true",
                    help="use newest candidate instead of approved image for inputs")
    sp.set_defaults(func=cmd_generate)

    sp = sub.add_parser("review", help="build storyboard/review.html gallery")
    sp.add_argument("project")
    sp.set_defaults(func=cmd_review)

    sp = sub.add_parser("approve", help="approve one candidate for an asset")
    sp.add_argument("project")
    sp.add_argument("asset_id")
    sp.add_argument("candidate_filename")
    sp.set_defaults(func=cmd_approve)

    sp = sub.add_parser("reject", help="clear approval for an asset (files kept)")
    sp.add_argument("project")
    sp.add_argument("asset_id")
    sp.set_defaults(func=cmd_reject)

    sp = sub.add_parser("storyboard", help="contact sheet from approved start keyframes")
    sp.add_argument("project")
    sp.add_argument("--columns", type=int, default=None)
    sp.set_defaults(func=cmd_storyboard)

    sp = sub.add_parser("export", help="write export/manifest.json (video prompts + approved keyframes)")
    sp.add_argument("project")
    sp.set_defaults(func=cmd_export)

    sp = sub.add_parser("status", help="table of all assets and their status")
    sp.add_argument("project")
    sp.set_defaults(func=cmd_status)

    sp = sub.add_parser("schema", help="print JSON Schema for project.json")
    sp.set_defaults(func=cmd_schema)

    return p


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        args.func(args)
    except SystemExit:
        raise
    except KeyboardInterrupt:
        err_console.print("\n[yellow]Interrupted. State saved; rerun to resume.[/yellow]")
        raise SystemExit(130)
