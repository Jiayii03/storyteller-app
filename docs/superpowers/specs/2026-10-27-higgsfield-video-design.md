# Higgsfield video generation — design

Date: 2026-10-27
Status: draft, awaiting approval

## Intent and why

The storyteller CLI currently generates images and motion tests with Google
(Gemini images, Gemini Omni Flash video via `veo_client.py`). The Gemini video
path is no longer wanted. Higgsfield (https://api.higgsfield.ai) replaces it as
the video provider: one API key, many video models (Seedance, Kling, Wan,
MiniMax, …), async submit-and-poll lifecycle. The CLI should be able to use any
available Higgsfield model, chosen per project, per run, or per shot.

This change also removes Kling-specific naming: Kling was only ever the
"manual final clip" target, and Higgsfield now covers that step directly.

## Goals

- New `video` subcommand: generates one clip per shot via Higgsfield
  **reference-to-video** — the approved start keyframe as the first frame,
  plus the shot's approved character and location reference sheets as
  identity anchors, so character/location consistency holds across the whole
  clip, not just frame one.
- Model selection from a Higgsfield catalog in `config.yaml`: per project
  (`models.video_model` in `project.json`), per run (`--model`), per shot
  (`model_override` on the shot's motion_clip-equivalent — resolved via CLI
  flag or project field; see Decisions).
- Cost transparency: per-shot cost estimate before spending, confirmation
  gate, per-call usage logging in the same `logs/run_*.log` format as Gemini.
- Full removal of `veo_client.py` and all Kling naming; `generate` becomes
  images-only.

## Non-goals

- No text-to-video, video-edit or video-extend workflows, and no plain
  image-to-video: **reference-to-video only**. A model without a
  reference-to-video workflow is not offered by the `video` subcommand.
- No webhooks; polling only.
- No automatic approval of clips: the approve-before-final-clip gate stays.
- No new Python SDK dependency on `@higgsfield/client` (Node) — plain REST.

## Anti-goals (failure modes to avoid)

- Silently spending money: completed Higgsfield generations are never
  refunded, so every real submission needs an estimate + confirm, same
  spirit as the existing cost confirmation in `generate`.
- Losing outputs: Higgsfield serves files for only 7 days; clips must be
  downloaded immediately, never left as URLs.

## Constraints

- Auth: `Authorization: Key {HF_API_KEY_ID}:{HF_API_KEY_SECRET}` — two
  credentials from console.higgsfield.ai, read from env/`.env` only, never
  written to logs, meta files, or the project folder.
- Lifecycle: `POST https://api.higgsfield.ai/<model-path>` returns
  `{status: "queued", request_id, status_url, cancel_url}`; poll
  `GET /requests/<request_id>/status` until `completed` / `failed` / `nsfw` /
  `canceled`. `Idempotency-Key` header (uuid4) on submit; repeat the same
  key if submission times out.
- Poll interval and timeout reuse `video_poll_interval_sec` /
  `video_timeout_sec` in `config.yaml`.
- Existing conventions: state in `state.json`, candidates + approve flow,
  `.meta.json` sidecars, usage lines in `run_*.log`, cost via `cost.py`
  backed by `config.yaml` `pricing`.

## Approaches considered

1. **Chosen — `video` subcommand over shots, reference-to-video.** The
   subcommand walks `project.shots` in `sequence_index` order, requires an
   approved start keyframe per shot (relaxed by `--allow-unapproved`),
   collects the shot's approved identity references (character sheets for
   `shot.subjects[].character_id`, location sheet for `shot.location_id`),
   builds the prompt from `motion.video_prompt` (fallback: auto-compose from
   `subject_motion` / `camera_motion` / `environment_motion`, exactly like
   `export.py` does today), and submits to Higgsfield reference-to-video.
   Duration comes from `shot.duration_sec`, clamped to the model's allowed
   durations; aspect ratio from the project. Clips land in the shot's motion
   candidates directory and go through the existing approve flow, so
   `export` keeps working unchanged. Trades: one new subcommand to learn;
   but it reuses all existing state, review, and cost machinery, and matches
   the user's mental model ("final clips now come from Higgsfield").
2. **Rejected — Higgsfield as a drop-in behind `VeoClient` for motion_clip
   assets.** Keeps two video paths and the confusing naming the user
   explicitly asked to remove.
3. **Rejected — batch script over `export/manifest.json`.** No state
   tracking, no resume, no cost logging; a second source of truth.

## Decisions (settled with the product owner)

- `.env.example` gains `HF_API_KEY_ID` / `HF_API_KEY_SECRET`;
  `KLING_API_KEY` is removed. `.env` is never committed.
- `kling_prompt` is renamed to `video_prompt` in the schema
  (`shots[].motion`), the export manifest key, the CLI template, the example
  project, and `prompt_builder`. Old files with `kling_prompt` keep parsing
  (models allow extra fields) and the old key is read as a fallback.
- `veo_client.py` is deleted; `runner.py` loses the motion_clip generation
  path; `generate` reports SKIP for any remaining `motion_clip` assets with
  a pointer to the `video` subcommand (the enum value stays so old
  `project.json` files still validate).
- The Higgsfield catalog lives in `config.yaml` under a `higgsfield:` block:
  per model — display id, **reference-to-video workflow path**, allowed
  durations, allowed resolutions, price per second per resolution (list
  prices, conservative; estimates only — Seedance bills per video token, the
  per-second figure approximates it at a fixed resolution; the ref-to-video
  list rate is used, e.g. Seedance 2.5 480p $0.174/s), and the
  reference-to-video parameters the model accepts (per-model parameter map;
  unsupported parameters are omitted, an unknown parameter shape is a clear
  error), plus the maximum number of accepted references. Seeded with
  verified data for Seedance 2.5, Seedance 2.0, Kling 3.0 Standard, and
  Wan 3.0 Prime from `docs/HIGGSFIELD-MODELS.md` and each model's docs page;
  the README points at https://open.higgsfield.ai/pricing for updates.
  Models without a verified reference-to-video workflow are not seeded.
  Unknown model id = clear error listing catalog entries.
- HTTP client: official Python SDK `higgsfield-client` (submit, poll with
  backoff, upload helpers, cancel, resume by request id) with `httpx` for
  downloading MP4 bytes. Credentials via `HF_API_KEY`/"id:secret" env form,
  passed to the SDK explicitly. Billed usage from the result is used when
  present; otherwise the usage line logs the requested-and-clamped duration
  and the README states the figure is an estimate.
- `video` CLI: `video <project.json>` with `--shot` (repeatable),
  `--model`, `--resolution` (default `480p`), `--dry-run` (jobs + cost, no
  API), `--yes` (skip confirmation), `--force` (re-submit even if a clip
  exists), `--allow-unapproved`. Defaults: `generate_audio: true`,
  `output_format: mp4`.
- Confirmation is **per shot**: before each submission the CLI prints the
  shot's cost and asks y/n (`--yes` skips). A `no` stops the run; earlier
  clips are kept and the shot stays pending, so a later rerun resumes.
- Inputs, per shot: the approved start keyframe (first frame) plus the
  shot's approved identity references — character sheets for every
  `shot.subjects[].character_id` and the location sheet for
  `shot.location_id`, each included only when approved. All inputs go
  through the file-uploads flow (`POST /files/generate-upload-url` → PUT →
  pass back the returned URL); the product owner has accepted that uploaded
  keyframes and reference sheets sit on public CDN URLs while inputs remain
  valid; upload retry on expiry, never logged with credentials. A shot
  with zero approved references beyond the keyframe is still valid
  (keyframe-only reference set).
- Cost accounting: submission + completion logged as usage lines
  (`usage asset=<shot> model=<id> video_sec=<n> cost_usd=<x>`);
  `status` accumulates per shot as it does for images. Refunded failures
  are logged but not billed.

## Left to the builder

- Exact YAML shape of the `higgsfield:` catalog block and its parsing home
  (`config.py`).
- How `video` state is stored in `state.json` (new per-shot video status vs.
  reusing asset-state entries).
- Test breakdown (client submit/poll/download with a fake transport,
  catalog resolution, clamping, cost estimation, CLI wiring).
- README / SPEC updates wording.
