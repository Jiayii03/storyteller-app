# Storyteller

Reference images, keyframes, storyboard sheets and motion tests for an AI video
pipeline: Gemini images + Veo motion tests. Final clips are made later in Kling
or Seedance.

## Setup

```sh
uv sync                     # installs dependencies into .venv
cp .env.example .env        # or create .env manually
# .env must contain: GEMINI_API_KEY=your_key
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

### Video models (motion tests — image-to-video)

**Veo 3.1 Preview shut down on 2026-10-22.** Video generation on the Gemini
Developer API is now **Gemini Omni Flash** through the Interactions API
(`client.interactions.create`). Durations: 3–10 s (minimum 3 s; shorter
requests are generated at 3 s and trimmed with ffmpeg). Audio is always
generated (no silent option on the Developer API). Output: 720p, MP4.

| Model id | Price | Notes |
|---|---|---|
| `gemini-omni-1.1-flash` | ≈$0.10/s (720p) | Current video model. ~5792 tokens/s of video at $17.50/Mtok; input $1.50/Mtok. |
| `gemini-omni-flash-preview` | ≈$0.10/s (720p) | Preview alias. |
| `veo-3.1-generate-001` etc. | $0.40/s (audio) | Shut down in the Developer API; Enterprise Agent Platform only. |

The app sets `video_config.task = "image_to_video"`; a second attached image
acts as the ending frame. Rerunning with `--force` after editing the shot's
`motion` fields re-animates the same keyframe.

### Choosing per project or per asset

- Project default: `models.image_model` / `models.video_model` in `project.json`.
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
- `uv run main.py status` shows calls and accumulated cost per asset.
- `generate` prints the run total (tokens, dollars). Calls without a pricing
  entry are logged as `cost_usd=unknown` — add a rate to `config.yaml`.
- Estimates only; prices drift. Compare occasionally with your Google AI
  Studio billing page.

## Workflow

1. Edit `project.json`: entities (characters/locations/props) define identity,
   shots define what is on screen, assets define what to generate.
2. `generate` produces `candidates/` images per asset in dependency order
   (references → keyframes → motion clips → storyboard sheet).
3. `review` builds an HTML gallery with copy-paste `approve` commands.
4. Approve one candidate per asset — only approved images feed later stages.
5. `export` writes the manifest for the manual Kling/Seedance step.

Rerunning `generate` never repeats finished jobs; state lives in `state.json`.
Model ids change often — see the catalog above; update `config.yaml` pricing
when Google changes rates.
- The API key is read only from the environment or `.env` and is never written
  to logs, meta files or the project folder.
- Example project: `examples/rainy_cafe/project.json`.

## Tests

```sh
uv run pytest
```
