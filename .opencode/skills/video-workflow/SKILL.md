---
name: video-workflow
description: Use this skill when running the storyteller video generation workflow — generating reference sheets, keyframes, storyboard and per-shot video clips with Gemini images and Higgsfield video, including the mandatory approval and prompt-review gates.
---

# Storyteller video generation workflow

Run the pipeline for a project in `projects/<id>/project.json` (or
`examples/<id>/project.json`). Work in order. Two gates are absolute:

- **Money gate:** never make a billable API call without the user's explicit
  approval for that step. Completed Higgsfield generations are never refunded.
- **Prompt gate:** before generating any video clips, show the user every
  shot's video prompt and wait for approval. Do not proceed without it.

All commands run via uv from the repo root: `uv run main.py <command>
<path-to-project.json> ...`.

> **Examples are structure references only.** `examples/pc_story` and
> `examples/rainy_cafe` exist purely to show the field layout of
> `project.json`. The stories, locations, prompts and prompting style in them
> are illustrative — do not copy or imitate any of their content when
> building a new project. Take the field names and structure, write fresh
> content for the user's actual story.

## 0. Author `project.json` (user-reviewed before anything generates)

Build `project.json` for the user's actual story (never copy example
content). Fill every field with specific, concrete detail — empty or generic
fields weaken every downstream prompt:

- **characters**: exact skin tone/texture/marks, face shape and eyes, hair,
  wardrobe down to fabrics and colors, `default_expression`,
  `distinguishing_features` (one memorable anchor, e.g. a mole), and
  `consistency_notes` for things that must never change.
- **locations**: `architecture_layout` (where things are relative to each
  other), `key_elements`, `materials_textures`, `default_lighting`,
  `ambient_details` — the small specific objects that make a scene feel real.
- **props**: `size_scale`, `materials`, `condition` (wear, chips, scratches).
- **shots**: full `camera` block (shot_size, angle, lens_mm, movement,
  movement_speed), `lighting` (key direction, quality, color temperature),
  per-subject `pose` / `action` / `facial_expression` / `gaze` / `hands` /
  `interaction` / `emotional_state` — say what the hands are doing and what
  the character is touching, not just the mood. `composition` (framing rule,
  negative space, screen direction), `background` depth layers.
- **motion** (drives the video prompt): `subject_motion` (what visibly
  moves), `camera_motion`, `environment_motion`, `pacing`,
  `audio_notes` (ambience, dialogue, no-dialogue), and optionally a
  hand-written `video_prompt`. Include spoken lines with accent/tone hints if
  dialogue is wanted.
- **assets**: list reference sheets, keyframes and the storyboard sheet with
  `input_asset_ids` dependencies.

**Then show the user the authored `project.json` — entity descriptions,
shots and prompts — and get their explicit approval before running any
generation.** Regenerate the file on request and re-review. Content review
happens here, before spending.

## 1. Validate and plan

```
uv run main.py validate <project.json>
uv run main.py plan <project.json>
```

`validate` checks schema and reference integrity. `plan` prints the job list
in dependency order with an estimated cost. Report both to the user before
generating anything.

## 2. Reference sheets first (characters, locations, props, style)

Identity consistency flows from these sheets into every later stage, so they
come first.

```
uv run main.py generate <project.json> --type character_reference
uv run main.py generate <project.json> --type location_reference
uv run main.py generate <project.json> --type prop_reference
```

Then build the review gallery and ask the user to pick one candidate per
asset:

```
uv run main.py review <project.json>   # open storyboard/review.html in a browser
uv run main.py approve <project.json> <asset_id> <candidate_filename>
uv run main.py reject <project.json> <asset_id>   # clear an approval, files kept
```

Only approved images feed later stages. `status` shows what is approved.

## 3. Keyframes (start required, end optional)

```
uv run main.py generate <project.json> --type keyframe
uv run main.py review <project.json>
```

Ask the user to approve one start keyframe per shot (`approve` with the
`kf_<shot>_start` asset id). The end keyframe is optional and only used for
still-image purposes — video clips take one first frame.

## 4. Storyboard sheet

```
uv run main.py storyboard <project.json>
```

Builds a labeled contact sheet of approved keyframes with Pillow. Local and
free — no confirmation needed, but show the output path to the user.

## 5. Cost logging

Every billable call appends a `usage` line to `projects/<id>/logs/run_*.log`,
and each candidate has a `.meta.json` sidecar with prompt, model, request id
and cost. After each generation step, report the run total:

```
uv run main.py status <project.json>
```

`status` shows calls and accumulated cost per asset. A `-` cost means no
pricing entry — never guess a rate; add it under `higgsfield.models.<id>.
price_per_sec_usd` in `config.yaml` from the billing page or
https://open.higgsfield.ai/pricing.

## 6. Prompt review (mandatory gate)

Before any video call, show the user each shot's video prompt. The video
prompt is `shots[].motion.video_prompt` if set (legacy `kling_prompt` key is
still read), else auto-composed from `subject_motion` / `camera_motion` /
`environment_motion`:

```python
from storyteller.prompt_builder import compose_motion_prompt
from storyteller.schema import Project
import json

p = Project.model_validate(json.load(open("<project.json>", encoding="utf-8")))
for s in sorted(p.shots, key=lambda x: x.sequence_index):
    print(s.id, compose_motion_prompt(s))
```

Present the prompts shot by shot with duration, model and per-clip cost
estimate. Let the user edit `motion.video_prompt` in `project.json` and
re-show. Do not continue until the user approves the prompts.

## 7. Video generation (Higgsfield reference-to-video)

Always dry-run first:

```
uv run main.py video <project.json> --dry-run --model <model-id> --resolution <res>
```

Then generate. Recommended for cheap tests: `--model wan-3-0 --resolution
480p` (~$0.02/s billed). Frontier quality: `--model seedance-2-5 --resolution
480p` (~$0.175/s). Catalog and prices live in `config.yaml` under
`higgsfield:`; verify against https://open.higgsfield.ai/pricing before
spending.

```
uv run main.py video <project.json> --model <id> --resolution <res>            # all shots, per-shot confirm
uv run main.py video <project.json> --shot S02 --model <id> --resolution <res>  # one shot
```

Rules:

- Generate **one shot at a time** unless the user asks for a batch. The CLI
  asks y/N before each submission — that is the money gate, do not pass
  `--yes` unless the user already approved that exact spend.
- Each clip uploads the approved start keyframe (first frame) plus the
  approved character/location sheets as identity references.
- Reference-to-video does **not** hard-lock frame 1 (wan drifts on small
  details like screen contents); mention this when the user compares the clip
  to the keyframe.
- Clips land in `assets/shots/<id>/motion/candidates/clip_vNN.mp4` with a
  `.meta.json` sidecar. State lives under `video_<shot_id>` in `state.json`;
  a killed run resumes polling the same request instead of re-submitting.
- `--force` re-submits a shot that already has a clip.

## 8. Approve clips and export

```
uv run main.py review <project.json>
uv run main.py approve <project.json> video_<shot_id> clip_vNN.mp4
uv run main.py export <project.json>   # export/manifest.json: keyframes + video_prompt + clip paths
```

The manifest is the handoff for downstream editing/stitching.

## Cheat sheet

| Step | Command | Costs money |
|---|---|---|
| author project.json + user content review | edit `project.json` | no |
| validate/plan | `validate`, `plan` | no |
| reference sheets | `generate --type ..._reference` | yes |
| review/approve | `review`, `approve`, `reject` | no |
| keyframes | `generate --type keyframe` | yes |
| storyboard | `storyboard` | no |
| status/costs | `status`, `logs/run_*.log` | no |
| prompt review | show `compose_motion_prompt` output | no |
| video clips | `video` (dry-run first) | yes |
| export | `export` | no |
