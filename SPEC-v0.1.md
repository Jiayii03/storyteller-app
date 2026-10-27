# Storyteller App: Technical Spec v0.1

A Python CLI that reads a project JSON file and uses the Gemini API (images) and Veo (short video) to generate reference images, keyframes, storyboard sheets and short motion test clips, saved to an organized folder.

## 1. Purpose and scope

The app prepares materials for an AI video pipeline (final clips are made later in Kling or Seedance). It does three things:

1. **Reference assets**: characters, locations, props and a style reference, so the look stays consistent.
2. **Keyframes**: one or two precisely specified still images per shot (start frame, optional end frame), generated using the reference assets as inputs.
3. **Motion tests (optional)**: a 1 to 2 second clip generated from a keyframe, to check that the motion looks right before spending on Kling.

It also builds a **storyboard sheet** (a contact sheet of approved keyframes with captions) for review.

**Non-goals for v0.1:** no GUI (CLI plus a static HTML review gallery only), no calling Kling or Seedance, no audio, no video editing beyond ffmpeg trimming, no LLM prompt writing (the user or GLM writes the JSON; the app only turns JSON into prompts).

## 2. Tech stack

- Python 3.11+
- `google-genai` (official Google Gen AI SDK) for image generation and Veo video generation
- `pydantic` v2 for schema validation
- `typer` for the CLI, `rich` for progress and logging
- `tenacity` for retries with backoff
- `Pillow` for contact sheets and image handling
- `ffmpeg` (system binary) for trimming clips and extracting frames
- `python-dotenv` for loading `GEMINI_API_KEY` from `.env`

**Important:** model IDs change often. Never hard-code them. They live in the `models` block of the project JSON and in `config.yaml` defaults. The builder should check the current Google AI docs for exact model names, the image-to-video method, and which options (last frame, duration, aspect ratio, resolution) are supported.

## 3. Workflow

Assets have dependencies and must be generated in this order:

1. `style_reference` (optional): sets the visual look.
2. `character_reference`, `location_reference`, `prop_reference`: use the style reference as input if present.
3. `keyframe`: uses character, location and prop references (plus the previous approved keyframe if `chain_from_previous` is true).
4. `motion_clip`: uses an approved keyframe as the first frame (and optionally an approved end keyframe as the last frame).
5. `storyboard_sheet`: built locally from approved keyframes, no API call.

Every generated image goes into a `candidates/` folder. The user reviews them and **approves** one per asset. Only approved assets can be used as inputs to later stages. This is the key cost-control mechanism.

## 4. Project folder layout

```
projects/<project_id>/
  project.json            # the input (user-edited)
  state.json              # job status, approvals, costs (app-managed)
  inputs/                 # user-supplied reference images (face photos, product photos, mood images)
  assets/
    characters/<character_id>/
      candidates/         # v01_a.png, v01_b.png ... plus .meta.json sidecars
      approved/           # exactly one approved image per asset
    locations/<location_id>/ (same structure)
    props/<prop_id>/ (same structure)
    style/ (same structure)
    shots/<shot_id>/
      keyframes/
        start/ candidates/ approved/
        end/   candidates/ approved/
      motion/ candidates/ approved/
  storyboard/
    storyboard_v01.png    # contact sheet
    review.html           # gallery of all candidates for approval
  logs/
    run_<timestamp>.log
```

Every output file has a sidecar `<name>.meta.json` containing: asset\_id, asset\_type, full final prompt, negative prompt, model, parameters, list of input image paths, seed (if any), timestamp, and API usage if returned.

## 5. JSON schema

The input is one `project.json`. Top-level keys:

```
schema_version, project, models, style_bible, characters[], locations[], props[], shots[], assets[]
```

The design principle is **entities define identity once, shots define what is on screen, assets define what to generate**. Prompts are composed from all three, so nothing is repeated by hand.

### 5.1 `project`

| Field | Type | Notes |
| --- | --- | --- |
| id | string | slug, used as folder name |
| title | string |  |
| logline | string | one sentence summary, for context only |
| aspect\_ratio | enum | `16:9`, `9:16`, `1:1`, `4:3`, `3:4`, `21:9`. Applied to all keyframes and clips |
| target\_video\_model | string | free text, e.g. `kling`, `seedance`. Used only in metadata and prompt hints |
| target\_total\_duration\_sec | number | e.g. 30 |
| language | string | default `en` |

### 5.2 `models`

```json
{
  "image_model": "<gemini image model id>",
  "video_model": "<veo model id>",
  "image_resolution": "1K",
  "video_resolution": "720p"
}
```

All values are overridable per asset.

### 5.3 `style_bible` (applied to every generation)

| Field | Type | Notes |
| --- | --- | --- |
| medium | enum | `photorealistic`, `cinematic_film_still`, `3d_render`, `anime`, `illustration`, `watercolor`, `claymation`, `other` |
| genre\_mood | string | e.g. `quiet melancholic drama` |
| color\_palette | string\[\] | named colors or hex |
| color\_grade | string | e.g. `teal and orange, lifted blacks` |
| film\_stock\_or\_look | string | e.g. `35mm grain, halation` |
| default\_lens\_mm | number |  |
| lighting\_style | string | e.g. `soft natural window light` |
| texture\_detail | string | e.g. `visible skin pores, fabric weave` |
| era\_setting | string | e.g. `contemporary urban Tokyo` |
| global\_negative\_prompt | string\[\] | e.g. `extra fingers, text, watermark, logo, blurry, distorted face` |
| reference\_image\_paths | string\[\] | optional mood or style images from `inputs/` |

### 5.4 `characters[]`

Identity is defined here once and reused in every shot. Appearance fields should be concrete and visual.

| Field | Type | Notes |
| --- | --- | --- |
| id | string | slug, e.g. `mia` |
| name | string |  |
| role | string | e.g. `protagonist` |
| gender | string | free text |
| age | integer or string | e.g. `28` or `late 20s` |
| ethnicity\_or\_heritage | string | optional, for accurate depiction |
| height\_build | string | e.g. `170 cm, slim, narrow shoulders` |
| skin | object | `tone`, `texture`, `marks` (freckles, scars, moles) |
| face | object | `shape`, `eyes` (color, shape), `eyebrows`, `nose`, `lips`, `facial_hair`, `distinguishing_features` |
| hair | object | `length`, `style`, `color`, `texture` |
| default\_expression | string | resting expression |
| wardrobe | object | `top`, `bottom`, `outerwear`, `footwear`, `accessories`, `colors`, `fabrics` |
| wardrobe\_variants | object | named alternatives, e.g. `{"night": {...}}`, selectable per shot |
| demeanor\_body\_language | string | posture, gait, mannerisms |
| input\_reference\_images | string\[\] | optional real photos or sketches in `inputs/` |
| consistency\_notes | string | features that must never change |

### 5.5 `locations[]`

| Field | Type | Notes |
| --- | --- | --- |
| id | string |  |
| name | string |  |
| type | enum | `interior`, `exterior`, `mixed` |
| description | string | overall description of the place |
| architecture\_layout | string | spatial layout, where things are |
| key\_elements | string\[\] | fixed objects and set dressing |
| materials\_textures | string\[\] |  |
| default\_time\_of\_day | enum | `dawn`, `morning`, `midday`, `afternoon`, `golden_hour`, `dusk`, `night` |
| default\_weather | string |  |
| default\_lighting | string |  |
| ambient\_details | string\[\] | dust, steam, crowds, traffic and similar |
| input\_reference\_images | string\[\] |  |

### 5.6 `props[]`

`id`, `name`, `description`, `size_scale`, `materials`, `colors`, `condition` (new, worn, damaged), `branding_text` (should be avoided or empty because image models render text poorly), `input_reference_images`.

### 5.7 `shots[]`

This is the core of the schema. Each shot describes everything on screen precisely.

| Field | Type | Notes |
| --- | --- | --- |
| id | string | e.g. `S01` |
| sequence\_index | integer | order in the final video |
| duration\_sec | number | intended clip length in the final video |
| narrative\_purpose | string | what this shot does in the story |
| summary | string | one line, used as storyboard caption |
| location\_id | string | refers to `locations[]` |
| time\_of\_day | enum | overrides location default |
| weather | string |  |
| set\_dressing\_notes | string | anything specific to this shot |
| camera | object | see 5.7.1 |
| lighting | object | see 5.7.2 |
| subjects\[\] | array | see 5.7.3, who is in frame |
| props\_in\_shot | array | `{prop_id, position, state}` |
| background | object | `description`, `depth_layers` (foreground / midground / background), `extras` (background people, vehicles), `focus_state` (sharp, soft, bokeh) |
| composition | object | `framing_rule` (rule of thirds, centered, symmetrical, leading lines), `headroom`, `negative_space`, `screen_direction` (subject facing left or right) |
| color\_grade\_override | string |  |
| keyframes | object | `start` and optional `end`, see 5.7.4 |
| motion | object | see 5.7.5 |
| continuity\_notes | string | what must match adjacent shots |
| transition\_out | enum | `cut`, `dissolve`, `fade_black`, `match_cut`, `whip` |
| negative\_prompt | string\[\] | shot-specific exclusions |
| chain\_from\_previous | boolean | use previous approved keyframe as extra input |

#### 5.7.1 `camera`

| Field | Values |
| --- | --- |
| shot\_size | `extreme_wide`, `wide`, `full`, `medium_wide`, `medium`, `medium_close`, `close_up`, `extreme_close_up`, `insert` |
| angle | `eye_level`, `low_angle`, `high_angle`, `birds_eye`, `worms_eye`, `dutch`, `overhead` |
| perspective | `neutral`, `over_the_shoulder`, `pov`, `two_shot`, `profile`, `three_quarter`, `from_behind` |
| camera\_height | free text, e.g. `chest height` |
| lens\_mm | number, e.g. 35 or 85 |
| depth\_of\_field | `deep`, `medium`, `shallow` |
| aperture\_hint | optional, e.g. `f/1.8` |
| movement | `static`, `push_in`, `pull_out`, `pan_left`, `pan_right`, `tilt_up`, `tilt_down`, `tracking`, `orbit`, `handheld`, `crane_up`, `crane_down`, `dolly_zoom` |
| movement\_speed | `very_slow`, `slow`, `medium`, `fast` |

#### 5.7.2 `lighting`

`key_light` (source and direction, e.g. `window camera-left`), `quality` (`hard`, `soft`, `diffused`), `contrast` (`low`, `medium`, `high`), `color_temperature` (`warm`, `neutral`, `cool` or Kelvin), `practical_lights` (lamps, neon, screens in frame), `atmosphere` (`haze`, `fog`, `rain`, `dust`, `clear`), `shadows` description.

#### 5.7.3 `subjects[]` (each person or main subject in frame)

| Field | Notes |
| --- | --- |
| character\_id | refers to `characters[]` |
| wardrobe\_variant | key from `wardrobe_variants`, else default |
| position\_in\_frame | e.g. `left third, foreground` |
| facing\_direction | e.g. `three-quarter turned toward camera-right` |
| pose | exact body pose |
| action | what they are doing at the start frame |
| facial\_expression | precise, e.g. `eyes slightly wide, lips pressed, suppressed worry` |
| gaze | e.g. `looking off-camera left at the door` |
| hands | what the hands are doing (a common failure area, so specify) |
| interaction | with other subjects or props |
| emotional\_state | internal state, for tone |

#### 5.7.4 `keyframes`

```json
{
  "start": {
    "description": "state of the scene at the first frame",
    "overrides": {}
  },
  "end": {
    "description": "state of the scene at the last frame (optional)",
    "changes_from_start": ["subject has turned toward camera", "door now open"]
  }
}
```

The `end` keyframe is generated from the start keyframe plus the `changes_from_start` list, so that everything unchanged stays identical.

#### 5.7.5 `motion` (used for the motion clip and for the Kling prompt later)

| Field | Notes |
| --- | --- |
| duration\_sec | length of the test clip, normally 1 to 2 |
| subject\_motion | what the subject does |
| camera\_motion | usually derived from `camera.movement`, can be overridden |
| environment\_motion | wind, rain, background people |
| pacing | `slow`, `natural`, `quick` |
| kling\_prompt | optional hand-written motion prompt, passed through to the output manifest |
| audio\_notes | not generated, only stored for later |

### 5.8 `assets[]` (the generation job list)

| Field | Type | Notes |
| --- | --- | --- |
| asset\_id | string | unique, e.g. `kf_S01_start` |
| asset\_type | enum | see below |
| target\_id | string | the entity or shot this belongs to |
| purpose | string | free text note, e.g. `reference for video clip S01` |
| frame\_role | enum | `start`, `end`, `single` (keyframes only) |
| variants | integer | number of candidates, default 2, hard max from config |
| input\_asset\_ids | string\[\] | extra inputs by asset\_id (resolved to approved files) |
| input\_image\_paths | string\[\] | extra inputs by path |
| prompt\_override | string | replaces the auto-built prompt body (style bible still applied unless `skip_style_bible` is true) |
| prompt\_append | string | appended to the auto-built prompt |
| negative\_prompt\_append | string\[\] |  |
| aspect\_ratio | string | overrides project value |
| model\_override | string |  |
| seed | integer | optional |
| video | object | for `motion_clip` only: `duration_sec`, `resolution`, `use_end_frame` (bool), `generate_audio` (bool) |
| status | enum | managed by app: `pending`, `generated`, `approved`, `failed`, `skipped` |

**`asset_type` enum:**

| Value | Meaning | Output |
| --- | --- | --- |
| `style_reference` | Look and mood board image | PNG |
| `character_reference` | Character identity image. Generates a main reference (neutral pose, clean background, full body) plus an optional turnaround and face close-up via `reference_views` | PNG(s) |
| `location_reference` | Establishing image of the set with no people | PNG |
| `prop_reference` | Isolated prop on a neutral background | PNG |
| `keyframe` | A shot's start or end frame, composed from shot data and references | PNG |
| `motion_clip` | 1 to 2 second image-to-video test from an approved keyframe | MP4 |
| `storyboard_sheet` | Contact sheet from approved keyframes, local only | PNG, optionally PDF |

If `assets[]` is omitted, the app auto-generates a default job list: one asset per character, location and prop, one `start` keyframe per shot, and a `storyboard_sheet`. Users add `end` keyframes and `motion_clip` jobs explicitly.

## 6. Example (abridged)

```json
{
  "schema_version": "0.1",
  "project": {
    "id": "rainy_cafe",
    "title": "Rainy Cafe",
    "aspect_ratio": "16:9",
    "target_video_model": "kling",
    "target_total_duration_sec": 30
  },
  "models": { "image_model": "<fill in>", "video_model": "<fill in>" },
  "style_bible": {
    "medium": "cinematic_film_still",
    "genre_mood": "quiet, melancholic, hopeful",
    "color_palette": ["muted teal", "warm amber", "charcoal"],
    "film_stock_or_look": "35mm, fine grain",
    "default_lens_mm": 35,
    "global_negative_prompt": ["text", "watermark", "extra fingers", "distorted face"]
  },
  "characters": [{
    "id": "mia", "name": "Mia", "gender": "female", "age": 28,
    "height_build": "170 cm, slim",
    "face": { "shape": "oval", "eyes": "dark brown, almond", "eyebrows": "straight, natural" },
    "hair": { "length": "shoulder", "style": "loose waves", "color": "dark brown" },
    "default_expression": "calm, slightly tired",
    "wardrobe": { "top": "mustard knit sweater", "outerwear": "beige trench coat", "bottom": "dark jeans" },
    "consistency_notes": "small mole under left eye, always"
  }],
  "locations": [{
    "id": "cafe", "name": "Corner cafe", "type": "interior",
    "description": "small wooden cafe, large rain-streaked front window",
    "default_time_of_day": "dusk"
  }],
  "shots": [{
    "id": "S01", "sequence_index": 1, "duration_sec": 4,
    "summary": "Mia looks out the window as rain falls",
    "location_id": "cafe",
    "camera": { "shot_size": "medium_close", "angle": "eye_level", "perspective": "three_quarter",
                "lens_mm": 50, "depth_of_field": "shallow", "movement": "push_in", "movement_speed": "very_slow" },
    "lighting": { "key_light": "window camera-right", "quality": "soft", "color_temperature": "cool" },
    "subjects": [{
      "character_id": "mia", "position_in_frame": "left third",
      "facing_direction": "three-quarter toward window",
      "pose": "seated, elbows on table", "hands": "both hands around a ceramic mug",
      "facial_expression": "pensive, eyes slightly unfocused", "gaze": "out the window"
    }],
    "background": { "description": "blurred street with passing cars and neon reflections", "focus_state": "bokeh" },
    "keyframes": { "start": { "description": "Mia mid-gaze, steam rising from mug" } },
    "motion": { "duration_sec": 2, "subject_motion": "slow blink, steam drifts", "environment_motion": "rain streaks down glass" },
    "chain_from_previous": false
  }],
  "assets": [
    { "asset_id": "char_mia", "asset_type": "character_reference", "target_id": "mia", "variants": 3 },
    { "asset_id": "loc_cafe", "asset_type": "location_reference", "target_id": "cafe", "variants": 2 },
    { "asset_id": "kf_S01_start", "asset_type": "keyframe", "target_id": "S01", "frame_role": "start", "variants": 3,
      "input_asset_ids": ["char_mia", "loc_cafe"] },
    { "asset_id": "clip_S01", "asset_type": "motion_clip", "target_id": "S01",
      "input_asset_ids": ["kf_S01_start"], "video": { "duration_sec": 2 } }
  ]
}
```

## 7. Prompt builder

The builder is a pure function: `(project, asset) -> {prompt_text, negative_prompt, input_images[]}`. It must be unit-testable without any API call, and a `--dry-run` flag prints its output.

**Prompt order for a `keyframe`** (natural-language paragraphs, not JSON dumps):

1. Medium and style sentence from `style_bible`.
2. Camera: shot size, angle, perspective, lens, depth of field.
3. Location and time of day, weather, key set elements.
4. Each subject: identity summary from the character entity (gender, age, face, hair, wardrobe), then position, facing, pose, action, hands, expression, gaze.
5. Props and their state.
6. Background layers and focus.
7. Lighting and atmosphere.
8. Composition and color grade.
9. Continuity or `prompt_append`.
10. A trailing line: `Avoid: <global + shot negatives>`.

**Input images** are attached in a fixed order, and the prompt includes a labelled legend so the model knows what each image is, for example: `Image 1 is the identity reference for Mia: keep her face, hair and build identical. Image 2 is the reference for the cafe location: keep layout and materials. Image 3 is the previous approved keyframe: match lighting and color.` Order: style, characters, location, props, previous keyframe, user-supplied extras.

For `character_reference`: neutral standing pose, full body, plain light-grey background, even lighting, facing camera, so the image is a clean identity anchor. If `reference_views` includes `turnaround`, also generate a front, three-quarter and side view on one sheet. For `location_reference`: no people. For `prop_reference`: isolated on a neutral background.

For an `end` keyframe: attach the approved start keyframe and instruct: `Same scene, same character, same lighting. Change only: <changes_from_start>.`

For `motion_clip`: the prompt is built only from `motion` fields plus a short note to keep the subject and scene identical to the first frame. Do not re-describe the image.

## 8. Generation engine

**Images**

- Use the Gemini image model through the `google-genai` SDK with text plus multiple input images.
- Request `variants` candidates per asset. If the API returns one image per call, loop with a small delay.
- Save the PNG exactly as returned, plus its sidecar meta file.
- If the model returns text with no image (a refusal or error), log it, mark the attempt failed, and show the message.

**Video (`motion_clip`)**

- Use Veo image-to-video through the SDK. This is a long-running operation: submit, poll every \~10 seconds, download the result on completion, with a timeout from config.
- First frame is the approved start keyframe. If `use_end_frame` is true and the selected model supports a last frame, pass the approved end keyframe.
- **Duration caveat:** current video models may have a minimum clip length longer than 2 seconds. The app should request the shortest allowed duration, then trim to the requested `duration_sec` with ffmpeg (`-t`). Keep the untrimmed original beside it. The builder should verify the real constraints in the current docs and put them in `config.yaml`.
- Default `generate_audio` to false to save cost where the model allows.

**Resolving inputs** `input_asset_ids` resolve to the file in that asset's `approved/` folder. If the asset is not approved, the job fails with a clear message (`Asset char_mia has no approved image. Run: storyteller approve char_mia`). Use `--allow-unapproved` to use the newest candidate instead.

## 9. CLI

```
storyteller init <project_id>                 # scaffold folder + template project.json
storyteller validate <project.json>           # schema + reference integrity check, prints errors with paths
storyteller plan <project.json>               # shows job list, dependency order, estimated number of API calls and cost
storyteller prompt <project.json> <asset_id>  # prints final prompt and input images (dry run)
storyteller generate <project.json> [--asset ID ...] [--type TYPE] [--shot ID] [--variants N] [--dry-run] [--yes]
storyteller review <project.json>             # builds storyboard/review.html gallery of candidates
storyteller approve <project.json> <asset_id> <candidate_filename>
storyteller reject <project.json> <asset_id>  # clears approval, keeps files
storyteller storyboard <project.json>         # builds contact sheet from approved keyframes
storyteller export <project.json>             # writes export/manifest.json with, per shot, the approved start/end keyframe, motion prompt and clip path, ready for Kling
storyteller status <project.json>             # table of all assets and their status
```

`generate` rules: skips assets already `generated` or `approved` unless `--force`; processes in dependency order; stops dependents if a dependency fails; asks for confirmation when the planned call count exceeds `confirm_above_calls`.

**Review gallery:** a static HTML file showing every asset's candidates side by side with prompt metadata. It also shows copy-paste `approve` commands under each image. (A later version can add a small local web server with click-to-approve.)

**Storyboard sheet:** a grid (default 3 columns) of approved start keyframes in `sequence_index` order, each labelled with shot ID, duration and `summary`, with total running time at the bottom. Optional PDF output.

**Export manifest:** a JSON file per project listing each shot in order with the paths of the approved start and end frames, the motion description, the `kling_prompt` (or an auto-composed one from `motion` fields), the duration and the transition. This is the handoff to the manual Kling step.

## 10. Config and safety

`config.yaml` (with sensible defaults):

```yaml
max_variants_per_asset: 4
max_retries: 2
confirm_above_calls: 10
max_calls_per_run: 40
request_delay_sec: 1.0
video_poll_interval_sec: 10
video_timeout_sec: 600
default_variants: 2
model_constraints:
  video_min_duration_sec: <fill in from docs>
  video_supports_last_frame: <fill in from docs>
```

- API key is read only from the `GEMINI_API_KEY` environment variable or `.env`. Never write it to logs, meta files or the project folder. `.env` must be in the generated `.gitignore`.
- Hard cap `max_calls_per_run` stops runaway loops. A failed call counts toward the cap.
- Retry only on transient errors (rate limit, 5xx, timeout) with exponential backoff. Do **not** retry on content-policy blocks or validation errors.
- A `state.json` write after every completed job, so a crashed run can resume.
- Log each API call with asset\_id and duration, never the key.

## 11. Validation rules (`validate`)

- All ids unique and slug-formatted (lowercase letters, digits, underscores).
- Every `location_id`, `character_id`, `prop_id` and `input_asset_ids` entry refers to something that exists.
- No dependency cycles among assets.
- `end` keyframe requires a `start` keyframe asset for the same shot.
- `motion_clip` requires a keyframe asset as input.
- Enum values checked against the lists in this spec, with a helpful error that lists allowed values.
- Input image paths exist and are PNG, JPG or WEBP under a size limit.
- Warn (not fail) if `branding_text` or on-screen text is requested, since image models render text unreliably.
- Warn if a shot's `subjects[]` has more than 3 people, because consistency drops quickly.

## 12. Code structure

```
storyteller/
  cli.py            # typer commands
  schema.py         # pydantic models and enums (single source of truth)
  prompt_builder.py # pure functions, unit tested
  resolver.py       # dependency graph and input image resolution
  gemini_client.py  # image generation wrapper with retries
  veo_client.py     # video generation wrapper, polling, download
  storage.py        # folder layout, sidecar meta, approvals, state.json
  review.py         # HTML gallery
  storyboard.py     # Pillow contact sheet
  export.py         # manifest for Kling
  config.py
tests/
  test_schema.py  test_prompt_builder.py  test_resolver.py
```

Generate the JSON Schema from the pydantic models (`storyteller schema > project.schema.json`) so editors and GLM can validate the input file.

## 13. Build phases

1. **Phase 1 (core, no API):** schema, validation, folder scaffolding, prompt builder, `prompt` and `plan` commands, unit tests. Dry-run output must look correct before spending anything.
2. **Phase 2 (images):** Gemini client, `generate` for references and keyframes, sidecar metadata, `approve`, `status`.
3. **Phase 3 (review and storyboard):** HTML gallery, contact sheet, `export`.
4. **Phase 4 (video):** Veo client, `motion_clip`, ffmpeg trimming, end-frame support if available.
5. **Phase 5 (optional):** local click-to-approve server, PDF storyboard, GLM helper command that turns a story idea into a draft `project.json`.

## 14. Acceptance criteria

- `validate` catches a missing character id, a bad enum and a missing input file, with readable messages.
- `prompt` for the example project prints a coherent prompt with a correct image legend and no API call.
- `generate --dry-run` lists jobs in the right order with an accurate call count.
- A full run on a 1-shot example produces candidates, sidecar files and an `index` that `review` can render.
- Generating a keyframe before approving its references fails with the clear message above (unless `--allow-unapproved`).
- Re-running `generate` does not repeat finished jobs.
- The API key never appears in any file under the project folder.
- Killing the process mid-run and restarting resumes without redoing completed jobs.

## 15. Notes for the builder

- Verify current model names, SDK method names, and supported video options against Google's official Gemini API docs before coding the clients. Keep these behind the two wrapper modules so changes are isolated.
- Keep prompt text in natural language. Do not pass raw JSON to the image model.
- Prefer clear errors over silent fallbacks. Every failure should say what to do next.
- Keep the dependency list short and do not add a database; files plus `state.json` are enough.
