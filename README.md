# Storyteller

Reference images, keyframes, storyboard sheets and final video clips for an AI
video pipeline: Gemini images + Higgsfield video (reference-to-video).

## Setup

```sh
uv sync                     # installs dependencies into .venv
cp .env.example .env        # or create .env manually
# .env must contain:
#   GEMINI_API_KEY=your_key
#   HF_API_KEY=key_id:key_secret   (from https://console.higgsfield.ai)
```

## Usage

All commands take the path to a `project.json`:

```sh
uv run main.py init my_project                          # scaffold template
uv run main.py validate projects/my_project/project.json
uv run main.py plan projects/my_project/project.json    # job order + cost estimate
uv run main.py prompt projects/my_project/project.json kf_S01_start   # dry-run prompt
uv run main.py generate projects/my_project/project.json --dry-run
uv run main.py generate projects/my_project/project.json
uv run main.py video projects/my_project/project.json --dry-run   # jobs + cost, no API call
uv run main.py video projects/my_project/project.json             # per-shot cost confirm
uv run main.py video projects/my_project/project.json --shot S01 --model seedance-2-5 --resolution 480p
uv run main.py review projects/my_project/project.json   # storyboard/review.html
uv run main.py approve projects/my_project/project.json char_mia v01_a.png
uv run main.py reject projects/my_project/project.json char_mia
uv run main.py storyboard projects/my_project/project.json
uv run main.py export projects/my_project/project.json   # export/manifest.json for Kling
uv run main.py status projects/my_project/project.json
uv run main.py schema > project.schema.json
```

## Model catalog (verified 2026-10-27)

Live-verified against `client.models.list()` and Google AI pricing docs.
Prices change; before writing a `project.json`, an agent should re-check
https://ai.google.dev/gemini-api/docs/pricing. Per-model rates also live in
`config.yaml` under `pricing` — update both when Google changes them.
`gemini-2.5-flash-image` is deprecated (shut down 2026-10-02); do not use it.

### Image models (image generation / reference sheets / keyframes)

| Model id | Tier | Price @1K image | Input $/Mtok | Text out $/Mtok | Notes |
|---|---|---|---|---|---|
| `gemini-3.1-flash-lite-image` | cheap | $0.034 | $0.25 | $1.50 | Fastest, lowest fidelity. Good for motion-test iterations and drafts. |
| `gemini-3.1-flash-image` (= Nano Banana 2) | balanced | $0.067 | $0.50 | $3.00 | Default workhorse. Good consistency. 2K $0.101, 4K $0.151. |
| `gemini-nano-banana-2.1` | balanced | $0.067 | $0.50 | $3.00 | Same pricing; newer Nano Banana 2.1 update. |
| `gemini-3.1-flash-image-preview` | balanced | $0.067 | $0.50 | $3.00 | Preview alias of the line above. |
| `gemini-3-pro-image` (= Nano Banana Pro) | premium | $0.134 | $2.00 | $12.00 | Best text rendering and detail. 2K $0.134, 4K $0.24. |
| `gemini-3-pro-image-preview`, `nano-banana-pro-preview` | premium | $0.134 | $2.00 | $12.00 | Preview aliases. |

Batch tier is roughly half price. Every generated image carries a SynthID
watermark. Image output is billed as tokens: a 1K image ≈1120 tokens.

### Video models (final clips — Higgsfield reference-to-video)

Video generation runs through the [Higgsfield](https://docs.higgsfield.ai) API:
one credential, many models, async submit-and-poll. The `video` subcommand
uses each model's **reference-to-video** workflow: per shot it uploads the
approved start keyframe (first frame) plus the approved character and location
reference sheets as identity references, so character and location consistency
holds across the whole clip. Models without a reference-to-video workflow are
not offered; there is no image-to-video fallback.

The catalog lives in `config.yaml` under `higgsfield:` (verified 2026-10-27):

| Model id | Workflow | Duration | Resolutions | Known price/sec | Notes |
|---|---|---|---|---|---|
| `seedance-2-5` | `bytedance/seedance-2.5/reference-to-video` | 4–30 s | 480p/720p/1080p | 480p $0.174 | up to 30 image refs, native audio |
| `seedance-2-0` | `bytedance/seedance-2.0/reference-to-video` | 4–15 s | 480p/720p/1080p/4k | 480p $0.168 | up to 9 image refs |
| `wan-3-0` | `alibaba/wan-3.0/reference-to-video` | 2–30 s | 480p/720p/1080p | 720p $0.050 | prompt required, refs optional |

- Prices are **list estimates** (Seedance bills per video token); a resolution
  without a verified rate logs `cost_usd=unknown` rather than guessing.
  Re-check https://open.higgsfield.ai/pricing before spending, and update
  `price_per_sec_usd` per model in `config.yaml` when rates change.
- Selection: `models.video_model` in `project.json`, `--model` flag, or the
  `model_override` of a `motion_clip` asset targeting the shot.
- Every submission asks for confirmation with its cost (`--yes` skips);
  `--dry-run` shows jobs and costs without calling the API.
- Completed generations are never refunded. Failed ones refund automatically.
- State lives under `video_<shot_id>` in `state.json`; a killed run resumes
  polling the same request instead of re-submitting. Clips land in the shot's
  motion `candidates/` folder — approve with
  `uv run main.py approve <project> video_<shot_id> clip_vNN.mp4`.
- Higgsfield serves outputs for ~7 days; clips download immediately.

### Choosing per project or per asset

- Project default: `models.image_model` / `models.video_model` in `project.json` (`video_model` must be a Higgsfield catalog id for the `video` subcommand).
- Per asset: `model_override` on any asset in `assets[]`, e.g. draft keyframes
  on `gemini-3.1-flash-lite-image`, final character sheet on `gemini-3-pro-image`.

```json
"assets": [
  { "asset_id": "kf_S01_start", "asset_type": "keyframe", "target_id": "S01",
    "frame_role": "start", "model_override": "gemini-3.1-flash-lite-image" }
]
```

### Usage and cost logging

Every successful API call writes a line to
`projects/<id>/logs/run_<timestamp>.log`:

```
17:55:59  usage asset=char_testcat model=gemini-3.1-flash-lite-image prompt_tokens=111 cost_usd=0.034
```

- Each candidate's `.meta.json` sidecar stores `usage` (prompt/candidates/total
  tokens from the API) and `cost_usd` computed from the `pricing` table.
- `uv run main.py status` shows calls and accumulated cost per asset (image
  assets and `video_<shot_id>` clip state).
- `generate` prints the run total (tokens, dollars); `video` prints per-shot
  cost before each submission and the run total at the end. Calls without a
  pricing entry are logged as `cost_usd=unknown` — add a rate to `config.yaml`.
- Estimates only; prices drift. Compare occasionally with your Google AI
  Studio and Higgsfield billing pages.

## Workflow

1. Edit `project.json`: entities (characters/locations/props) define identity,
   shots define what is on screen, assets define what to generate.
2. `generate` produces `candidates/` images per asset in dependency order
   (references → keyframes → storyboard sheet). Images only — video is its
   own step.
3. `review` builds an HTML gallery with copy-paste `approve` commands.
4. Approve one candidate per asset — only approved images feed later stages.
5. `video` generates one clip per shot from the approved start keyframe +
   identity references (per-shot cost confirm). Approve clips with
   `uv run main.py approve <project> video_<shot_id> clip_vNN.mp4`.
6. `export` writes `export/manifest.json` (per-shot approved keyframes,
   `video_prompt`, clip paths) for editing/stitching downstream.

Rerunning `generate` or `video` never repeats finished jobs; state lives in
`state.json`. Model ids change often — see the catalogs above; update
`config.yaml` pricing when Google or Higgsfield change rates.
- The API key is read only from the environment or `.env` and is never written
  to logs, meta files or the project folder.
- Example project: `examples/rainy_cafe/project.json`.

## Tests

```sh
uv run pytest
```
