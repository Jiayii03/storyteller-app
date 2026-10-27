# Higgsfield video generation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Gemini/Veo motion-test path and all Kling naming with a Higgsfield-powered `video` subcommand that generates one image-to-video clip per shot from approved keyframes.

**Architecture:** New REST client `storyteller/higgsfield_client.py` (upload inputs → submit → poll → download, httpx with injectable transport). New orchestrator `storyteller/video.py` walks shots in `sequence_index` order, collects each shot's approved references (start keyframe + character/location sheets), confirms cost per shot, stores clips in the shot motion candidates folder for the existing approve flow. Model catalog (reference-to-video workflows, durations, resolutions, prices, params) lives in `config.yaml` under `higgsfield:`. `runner.generate` becomes images-only; `veo_client.py` is deleted.

**Tech Stack:** Python 3.11, httpx (new dependency), pydantic, PyYAML, rich, pytest. No Higgsfield SDK.

**Spec:** `docs/superpowers/specs/2026-10-27-higgsfield-video-design.md`

## Global Constraints

- Auth header exactly: `Authorization: Key {HF_API_KEY_ID}:{HF_API_KEY_SECRET}`; credentials read from env/`.env` only, never logged or written to any file.
- Submit carries `Idempotency-Key` (uuid4). Base URL `https://api.higgsfield.ai`.
- Terminal statuses: `completed`, `failed`, `nsfw`, `canceled`. Poll interval `video_poll_interval_sec`, hard timeout `video_timeout_sec` (existing config).
- Catalog prices are list prices (conservative); per-second figures are estimates (Seedance bills per token). Unknown pricing → `cost_usd=unknown`, never a guess.
- Per-shot confirmation before every submission unless `--yes`; `--dry-run` makes zero HTTP calls.
- Completed generations are never refunded: download MP4 bytes immediately; never leave results as URLs only.
- `video_prompt` is the schema name; `kling_prompt` is read as a fallback wherever `video_prompt` is empty.
- The API key(s) never appear in logs, meta files, sidecars, or `state.json`.

## Review Focus

1. Unknown model id passed to `--model` or `models.video_model` → clear error listing catalog ids, exit code 2, no HTTP call. Test: Task 4 step 1 (`test_unknown_model_errors`).
2. Shot duration outside the model's allowed set → clamp to nearest allowed (smallest ≥ requested, else longest) and log a warning line; never send an unsupported duration. Test: Task 4 (`test_duration_clamped`).
3. Shot without an approved start keyframe → error naming the approve command, run continues with other shots. Test: Task 4 (`test_missing_keyframe_skips_shot`).
4. Poll ends in `failed`/`nsfw`/`canceled` or times out → `HiggsfieldError` with status, shot marked failed in state, no cost billed. Test: Task 3 (`test_poll_failure_raises`).
5. Process killed mid-poll → `request_id` + idempotency key stored in state at submit; rerun (without `--force`) resumes polling instead of re-submitting. Test: Task 4 (`test_resume_polls_existing_request`).

---

### Task 1: Remove Veo/Kling; rename `kling_prompt` → `video_prompt`

**Files:**
- Delete: `storyteller/veo_client.py`
- Modify: `storyteller/schema.py` (Motion, ~line 383)
- Modify: `storyteller/prompt_builder.py` (~lines 496–521)
- Modify: `storyteller/export.py` (lines 1, 27–38)
- Modify: `storyteller/runner.py` (remove VeoClient import, `_generate_motion`, motion_clip branches)
- Modify: `storyteller/cli.py` (TEMPLATE `target_video_model`, export help text)
- Modify: `.env.example`, `examples/rainy_cafe/project.json`
- Test: `tests/test_schema.py`, `tests/test_prompt_builder.py`, `tests/test_export.py` (create)

**Interfaces:**
- Produces: `Motion.video_prompt: str = ""` in `schema.py`; `prompt_builder.compose_motion_prompt(shot: Shot) -> str` (auto-composed body, shared by export and Task 4); manifest key `video_prompt`.
- `generate` on a `motion_clip` asset appends SKIP `(asset_id, "motion clips moved to the `video` subcommand")` and continues; `AssetType.motion_clip` stays in the enum so old projects validate.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_schema.py
def test_motion_video_prompt_and_kling_fallback():
    from storyteller.schema import Motion
    assert Motion.model_validate({}).video_prompt == ""
    m = Motion.model_validate({"kling_prompt": "legacy"})
    assert m.video_prompt == "" and m.model_extra["kling_prompt"] == "legacy"

# tests/test_prompt_builder.py
def test_compose_motion_prompt_prefers_video_prompt_then_kling():
    from storyteller.prompt_builder import compose_motion_prompt
    from storyteller.schema import Shot
    s = Shot.model_validate({"id": "S01", "motion": {"video_prompt": "handheld chase"}})
    assert compose_motion_prompt(s) == "handheld chase"
    s2 = Shot.model_validate({"id": "S01", "motion": {"kling_prompt": "legacy text"}})
    assert compose_motion_prompt(s2) == "legacy text"
    s3 = Shot.model_validate({"id": "S01", "motion": {"subject_motion": "boy types"}})
    assert "Subject motion: boy types." in compose_motion_prompt(s3)
```

Also in `tests/test_export.py` (new file, build a minimal project with one shot + a fake approved keyframe, following the fixture style of `tests/conftest.py`): assert `manifest["shots"][0]["video_prompt"] == "..."` and `"kling_prompt" not in manifest["shots"][0]`.

- [ ] **Step 2: Run tests, verify FAIL** — `uv run pytest tests/test_schema.py tests/test_prompt_builder.py tests/test_export.py -v` → AttributeError/KeyError on `video_prompt`/`compose_motion_prompt`.

- [ ] **Step 3: Implement**
  - `schema.py`: rename `kling_prompt` field to `video_prompt` (extra="allow" keeps old keys parseable).
  - `prompt_builder.py`: extract the motion-clip prompt body (lines 500–515) into `compose_motion_prompt(shot)`; use `m.video_prompt or m.model_extra.get("kling_prompt", "")` as override; motion_clip branch calls it.
  - `export.py`: `kling_prompt = ...` block becomes `video_prompt = shot.motion.video_prompt or shot.motion.model_extra.get("kling_prompt", "") or compose_motion_prompt(shot)`; manifest key `"video_prompt"`; docstring updated.
  - `runner.py`: delete `from .veo_client import VeoClient`, `_generate_motion`, the `veo_client` parameter plumbing, and `AssetType.motion_clip` from `need_key_types`/`_est_calls`; in the `generate` loop, before `dep_ok`: `if a.asset_type == AssetType.motion_clip: report.skipped.append((a.asset_id, "motion clips moved to the `video` subcommand")); continue`. Delete `storyteller/veo_client.py`.
  - `cli.py`: TEMPLATE `"target_video_model": "higgsfield"`; export parser help → `"write export/manifest.json (video prompts + approved keyframes)"`.
  - `.env.example`: remove `KLING_API_KEY` line (Higgsfield vars land in Task 2). `examples/rainy_cafe/project.json`: `"kling_prompt": ""` → `"video_prompt": ""`, `"target_video_model": "higgsfield"`.

- [ ] **Step 4: Run tests, verify PASS** — `uv run pytest -v` (full suite; existing tests referencing Veo/motion generation are updated in this step, not skipped).

- [ ] **Step 5: Commit** — `git add -A && git commit -m "refactor: remove Veo client and Kling naming, rename kling_prompt to video_prompt"`

### Task 2: Higgsfield catalog config, credentials, cost

**Files:**
- Modify: `storyteller/config.py` (DEFAULTS, Config, load_config, new `hf_credentials()`)
- Modify: `storyteller/cost.py` (new `higgsfield_video_cost`)
- Modify: `config.yaml` (seed catalog), `.env.example`
- Modify: `pyproject.toml` (httpx)
- Test: `tests/test_config_hf.py` (create), `tests/test_cost.py`

**Interfaces:**
- Produces: `Config.higgsfield_models: dict[str, dict]` — each entry `{"workflow": str (reference-to-video path), "durations_sec": list[int], "resolutions": list[str], "price_per_sec_usd": dict[str, float], "params": list[str], "max_references": int}`. `Config.higgsfield_base_url: str = "https://api.higgsfield.ai"`. `hf_credentials() -> tuple[str, str]` (raise-free; returns `("", "")` when unset). `higgsfield_video_cost(model: str, resolution: str, duration_sec: float, pricing: dict | None) -> dict | None` returning `{"cost_usd": float, "rate_per_sec": float}` or `None`.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_config_hf.py
def test_catalog_defaults_and_pricing():
    from storyteller.config import load_config
    cfg = load_config()
    assert "seedance-2-5" in cfg.higgsfield_models
    e = cfg.higgsfield_models["seedance-2-5"]
    assert e["workflow"] == "bytedance/seedance-2.5/reference-to-video"
    assert e["price_per_sec_usd"]["480p"] == 0.174
def test_hf_credentials_reads_env(monkeypatch):
    from storyteller.config import hf_credentials
    monkeypatch.setenv("HF_API_KEY_ID", "id1"); monkeypatch.setenv("HF_API_KEY_SECRET", "sec1")
    assert hf_credentials() == ("id1", "sec1")

# tests/test_cost.py (add)
def test_higgsfield_video_cost():
    from storyteller.cost import higgsfield_video_cost
    c = higgsfield_video_cost("seedance-2-5", "480p", 8, None)
    assert c["cost_usd"] == round(0.174 * 8, 4)
    assert higgsfield_video_cost("nope", "480p", 8, None) is None
```

- [ ] **Step 2: Run tests, verify FAIL**

- [ ] **Step 3: Implement**
  - `pyproject.toml`: add `"httpx>=0.27"` to dependencies; `uv sync`.
  - `cost.py`: `HIGGSFIELD_PRICING` dict mirroring the catalog prices (same shape as `VIDEO_PRICING`; ref-to-video list rates — Seedance 2.5: 480p 0.174, 720p 0.389 (0.462 × 0.6 rounded to the published ref-row figure; use the model docs page value), 1080p per docs page); `higgsfield_video_cost` like `video_cost` but audio/silent ignored (single rate per resolution), resolution fallback `next(iter(entry.values()))`.
  - `config.py`: `Config` fields `higgsfield_base_url`, `higgsfield_models` (seed dict `HIGGSFIELD_MODELS` in `config.py`); `load_config` reads `higgsfield:` block from config.yaml, merging over defaults. `hf_credentials()` mirrors `api_key()` (dotenv fallback).
  - `config.yaml`: seed `higgsfield:` block — reference-to-video entries only: `seedance-2-5` (workflow `bytedance/seedance-2.5/reference-to-video`, durations `[4,5,6,7,8,9,10]` + note 4–30 allowed, resolutions `["480p","720p","1080p"]`, prices from the model docs page — 480p 0.174, `params` verified from https://docs.higgsfield.ai/docs/models/wan-3/reference-to-video.md-style pages for each model, `max_references` from the page). Same verification for `seedance-2-0`, `kling-3-0-standard`, `wan-3-0-prime` — seed only models whose reference-to-video page verifies a workflow path and parameter names; `# verified 2026-10-27` comment per entry; skip any model that has no ref-to-video workflow.
  - `.env.example`: replace KLING line with `HF_API_KEY_ID=your_key_id_here` + `HF_API_KEY_SECRET=your_key_secret_here`.

- [ ] **Step 4: Run tests, verify PASS** — `uv run pytest tests/test_config_hf.py tests/test_cost.py -v`

- [ ] **Step 5: Commit** — `git commit -am "feat: higgsfield model catalog, credentials and video cost"`

### Task 3: `HiggsfieldClient` — submit, upload, poll, download

**Files:**
- Create: `storyteller/higgsfield_client.py`
- Test: `tests/test_higgsfield_client.py` (create)

**Interfaces:**
- Consumes: `Config.higgsfield_base_url/.higgsfield_models/.video_poll_interval_sec/.video_timeout_sec` (Task 2), `storage.log_api_call`.
- Produces:
```python
class HiggsfieldError(Exception): ...
class HiggsfieldClient:
    def __init__(self, key_id: str, key_secret: str, cfg: Config,
                 paths: ProjectPaths | None = None, transport: httpx.BaseTransport | None = None): ...
    def generate_clip(self, model: str, prompt: str, first_image: Path,
                      references: list[Path], duration_sec: int, resolution: str,
                      aspect_ratio: str, destination: Path, asset_id: str,
                      request_id: str | None = None,
                      idempotency_key: str | None = None,
                      ) -> tuple[Path, dict | None, str, str]:
        """Uploads first_image + references, submits to the model's
        reference-to-video workflow. Returns (clip_path, usage_dict_or_None,
        request_id, idempotency_key)."""
```
- Body built from the model's catalog `params` list: `prompt`, first-frame image field + references field (names verified per model from its docs page), `duration`, `resolution`, `aspect_ratio`, `generate_audio: True`, `output_format: "mp4"` — only keys present in `params`. More references than `max_references` → truncate with a logged warning. Unknown param name in catalog → `HiggsfieldError` at call time.

- [ ] **Step 1: Write failing tests** using `httpx.MockTransport` covering: (a) happy path — POST returns queued with `request_id`, one 202/`queued` poll then `completed` with `{"videos": [{"url": ...}]}`, second route serves MP4 bytes; assert bytes written to `destination`, returned ids non-empty; (b) `test_poll_failure_raises` — terminal `failed` → `HiggsfieldError` containing `failed`; (c) `test_timeout_raises` — always-`queued` with `video_timeout_sec` patched to 0 → `HiggsfieldError` containing `timed out`; (d) `test_resume_skips_submit` — `request_id` passed in → no POST recorded by the handler, polls directly; (e) `test_unknown_model_raises` — model not in catalog → `HiggsfieldError` listing catalog ids, zero HTTP calls; (f) `test_upload_flow` — first_image + 2 references: assert one `POST /files/generate-upload-url` + PUT per input, the POST body carries the returned public URLs in the model's documented field names, and the auth header matches `Key id:secret`; (g) `test_max_references_truncated` — 4 references, `max_references: 2` → only 2 URLs in body, warning logged.
- [ ] **Step 2: Run tests, verify FAIL** — ModuleNotFoundError.
- [ ] **Step 3: Implement `storyteller/higgsfield_client.py`** — httpx.Client(base_url, transport=transport); `_upload_image(path) -> str`: POST `/files/generate-upload-url` {content_type} → PUT bytes to returned URL → return `public_url`; `_submit(body, idem_key)`; `_poll(request_id)` loop with `time.sleep(cfg.video_poll_interval_sec)`; download via `client.stream` into `destination` (mkdir parents); usage dict = any `usage`/`duration` fields present in the completed status JSON, else `None`. Log submit/poll-complete/download via `log_api_call` (never credentials).
- [ ] **Step 4: Run tests, verify PASS** — `uv run pytest tests/test_higgsfield_client.py -v`
- [ ] **Step 5: Commit** — `git commit -am "feat: higgsfield REST client (upload, submit, poll, download)"`

### Task 4: `video` subcommand — orchestration, per-shot gate, state

**Files:**
- Create: `storyteller/video.py`
- Modify: `storyteller/cli.py` (parser + `cmd_video`, approve/reject accept `video_<shot_id>`, status shows video rows)
- Modify: `storyteller/export.py` (use `prompt_builder.compose_motion_prompt`)
- Test: `tests/test_video.py` (create)

**Interfaces:**
- Consumes: `HiggsfieldClient.generate_clip` (Task 3), `hf_credentials`/catalog (Task 2), `storage.*`, `prompt_builder.compose_motion_prompt` (Task 1).
- Produces:
```python
class VideoReport: done/failed/skipped: list[tuple[str, str]]; calls: int; cost_usd: float; unknown_cost_calls: int
def run_video(project_file: Path, project: Project, cfg: Config, *,
              shots: list[str] | None, model: str | None, resolution: str | None,
              dry_run: bool, yes: bool, force: bool, allow_unapproved: bool) -> VideoReport
def shot_references(paths: ProjectPaths, project: Project, shot: Shot,
                    allow_unapproved: bool) -> tuple[Path, list[Path]]:
    """(start keyframe, [character sheets for shot.subjects, location sheet]).
    Raises ValueError naming the approve command when the start keyframe is
    missing; references included only when approved/resolvable."""
```
- State: per shot under key `video_<shot_id>` with `{"status", "error", "candidates": [], "request_id", "idempotency_key", "usage": {"calls", "cost_usd"}}`. Clips written via `storage.write_candidate` into `paths.shot_motion_dir(shot.id)` with filename `clip_v{n:02d}.mp4` (bump `version`). `cmd_approve`/`cmd_reject`: when the id matches `video_<shot_id>` and no asset matches, operate on `paths.shot_motion_dir`. `cmd_status`: after asset rows, add rows for `video_*` state keys.

- [ ] **Step 1: Write failing tests** (fake client injected by monkeypatching `video.HiggsfieldClient`): (a) `test_dry_run_no_http` — 2-shot project, `dry_run=True` → report lists both shots with costs, client never constructed; (b) `test_unknown_model_errors` — `--model nope` → SystemExit 2, error lists catalog ids; (c) `test_duration_clamped` — shot 8 s, catalog durations `[4,5,6]` → submitted duration 6, warning logged; (d) `test_missing_keyframe_skips_shot` — no approved keyframe for S02, S01 fine → S01 in done, S02 in skipped with approve-command hint; (d2) `test_references_resolved` — project with approved char/location sheets referenced by the shot → client receives first frame + 2 references, in order [char..., location]; unapproved sheet omitted; (e) `test_per_shot_confirm` — patch `builtins.input` returning "n" on shot 2 → shot 2 skipped "aborted", shot 1 done; "y" both times → both done; (f) `test_resume_polls_existing_request` — state pre-seeded `video_S01.request_id` → client called with that `request_id`; (g) `test_state_and_sidecar` — after run, `state["video_S01"]["status"] == "generated"`, candidate + `.meta.json` exist in motion dir, meta has prompt/model/cost, no key material; (h) `test_manifest_uses_composed_prompt` — export manifest `video_prompt` populated for a shot with only `subject_motion`.
- [ ] **Step 2: Run tests, verify FAIL**
- [ ] **Step 3: Implement `storyteller/video.py` + CLI wiring** — shot order `sorted(project.shots, key=sequence_index)`, filtered by `--shot`; `shot_references` collects start keyframe + approved character sheets (`resolver`-style lookup by `character_id` via `reference_asset_id`/`storage.approved_file`) + location sheet; model resolution order: `--model` → motion_clip asset's `model_override` targeting the shot → `project.models.video_model` → error; duration clamp (smallest allowed ≥ `shot.duration_sec`, else longest, log warning); per-shot confirm prints `~$<cost> for <n>s <model> <resolution>` unless `yes`/`dry_run`; resume path passes stored `request_id`/`idempotency_key`; `cmd_video` mirrors `cmd_generate` output lines.
- [ ] **Step 4: Run tests, verify PASS** — `uv run pytest -v` (full suite).
- [ ] **Step 5: Commit** — `git commit -am "feat: video subcommand generating per-shot clips via higgsfield"`

### Task 5: Docs

**Files:**
- Modify: `README.md` (usage, workflow, new "Higgsfield models" section replacing Kling mentions)
- Modify: `SPEC-v0.1.md` header note only (v0.1 is historical; add one line: video now via `video` subcommand / Higgsfield)

- [ ] **Step 1: Update README** — top line: "Gemini images + Higgsfield video clips"; usage block gains `uv run main.py video ...` with `--shot/--model/--resolution/--dry-run/--yes/--force/--allow-unapproved`; new section "Higgsfield model catalog" (config.yaml `higgsfield:` block, re-check https://open.higgsfield.ai/pricing, prices are list estimates); workflow step 5 → `video` replaces the manual Kling step; credentials note (`HF_API_KEY_ID`/`HF_API_KEY_SECRET`).
- [ ] **Step 2: Full verification** — `uv run pytest` and `uv run main.py video projects/pc_story/project.json --dry-run` (no `.env` keys needed for dry-run; expect job table + estimated cost).
- [ ] **Step 3: Commit** — `git commit -am "docs: higgsfield video subcommand"`
