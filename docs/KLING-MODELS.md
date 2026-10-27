# Kling API: Models, Pricing and pc_story Cost Estimate

> Verified from official docs 2026-10-27: https://kling.ai/document-api
> (JS-rendered site — append `.md` to URLs for LLM-readable versions;
> https://kling.ai/document-api/llms.txt lists every page.)

## Endpoint and auth

- Base URL: `https://api-singapore.klingai.com` (moved from api.klingai.com)
- Auth: `Authorization: Bearer <KLING_API_KEY>` header. Console → "Create a new
  API Key", shown once. Legacy AccessKey/SecretKey accounts instead sign a JWT
  (HS256, iss=ak, exp=+1800s) and send that as the Bearer token.
- Put it in `.env` as `KLING_API_KEY=...`. Never commit it.

## How generation works (async)

1. `POST /image-to-video/kling-3.0-turbo` (new-style API: the model version is
   in the path) with `contents` (a `prompt` item + a `first_frame` image URL or
   Base64) and `settings` (`resolution`: `720p`/`1080p`, `duration`: 3–15 s on
   3.x models). First-frame image: jpg/jpeg/png, ≤50 MB, ≥300 px wide, aspect
   1:2.5–2.5:1. Watermark off by default.
2. Response gives a task `id` (`status`: submitted/processing/succeeded/failed).
3. Poll `GET /tasks?task_ids=<id>` (batch with commas, or query by cursor).
4. On success, `outputs[].url` = video download URL — **results are deleted
   after 30 days; download immediately.** The `billing[]` block reports the
   actual deduction (cash CNY/USD or resource units) per task — log this for
   exact cost tracking.
5. `options.callback_url` available if you'd rather be notified than poll.

## Available video models (2026-10-20 capability map)

| Model | Generation range | Resolutions | Native audio | First/last frame | Notes |
|---|---|---|---|---|---|
| Kling 4.0 | 3–30 s | 720P, 1080P, 4K | yes | yes + multi-keyframes, video ref | **Coming soon** — prices listed are preview only, cannot submit yet |
| Kling 3.0 Turbo | 3–15 s | 720P, 1080P | yes | first frame only | Best value with audio; multi-shot prompts ("shot 1, 4s, ...; shot 2, ...") |
| Kling 3.0 | 3–15 s | 720P, 1080P, 4K | yes | yes | Motion control, video input, multi-shot |
| Kling 3.0 Omni | 3–15 s | 720P, 1080P, 4K | yes | yes | All-in-one multimodal, voice-driven characters, elements |
| Kling O1 | 3–10 s | 720P, 1080P | no | first frame only (5/10 s) | Strong consistency |
| Kling 2.6 | 5 s, 10 s | 720P, 1080P | yes, 1080P only | last frame: 1080P only | Voice reference support |
| Kling 2.5 Turbo | 5 s, 10 s | 720P, 1080P | no | last frame: 1080P only | Cheapest |

Legacy `model_name` values still in circulation: `kling-v1`, `kling-v1-5`,
`kling-v1-6`, `kling-v2-master`, `kling-v2-1`, `kling-v2-1-master`,
`kling-v2-5-turbo`, `kling-v2-6`, `kling-v3`.

**There is no 480p on the API.** Resolutions are 720P (floor), 1080P, 4K.
If you want 480p-sized files, generate 720p and downscale with ffmpeg —
this does not reduce the Kling bill (billing is per second at the generated
resolution).

## Official pricing (per second of output video)

Unit = resource-package unit, $0.157 per unit reference.

| Model / feature | 720P | 1080P | 4K |
|---|---|---|---|
| Kling 4.0 (preview) | $0.157/s | $0.235/s | - |
| Kling 3.0 Turbo (native audio) | $0.112/s | $0.14/s | - |
| Kling 3.0, no audio | $0.084/s | $0.112/s | $0.42/s |
| Kling 3.0, native audio | $0.126/s | $0.168/s | $0.42/s |
| Kling 3.0, motion control | $0.126/s | $0.168/s | - |
| Kling 3.0 Omni, no ref video, no audio | $0.084/s | $0.112/s | $0.42/s |
| Kling 3.0 Omni, no ref video, audio | $0.112/s | $0.14/s | $0.42/s |
| Kling 3.0 Omni, with ref video | $0.126/s | $0.168/s | $0.42/s |
| Kling O1, no ref video | $0.084/s | $0.112/s | - |
| Kling O1, with ref video | $0.126/s | $0.168/s | - |
| Kling 2.6, no audio | $0.042/s | $0.07/s | - |
| Kling 2.6, audio (no voice ref) | - | $0.14/s | - |
| Kling 2.5 Turbo, no audio | $0.042/s | $0.07/s | - |

Extras (any model version): Text-to-Audio / Video-to-Audio $0.035/call,
Lip Sync $0.07/5s, Avatar $0.056/s (720p), TTS $0.007/call.

## Cost estimate for pc_story

The story is 4 shots × 8 s = **32 s** total, image-to-video from the four
approved keyframes. Kling durations are flexible (3–15 s on 3.x), so each 8 s
shot is a single generation — no trimming needed.

| Plan | Per 8 s shot | Full 32 s story |
|---|---|---|
| Kling 2.5 Turbo, 720p, silent | $0.34 | **$1.34** |
| Kling 2.6, 720p, silent | $0.34 | **$1.34** |
| Kling 3.0, 720p, silent | $0.67 | **$2.69** |
| Kling 3.0 Turbo, 720p, native audio (dialogue) | $0.90 | **$3.58** |
| Kling 3.0, 720p, native audio (dialogue) | $1.01 | **$4.03** |

- A single hypothetical 15 s video at the cheapest rate (2.5 Turbo 720p) is
  15 × $0.042 = **$0.63**.
- Recommended for pc_story: **Kling 3.0 Turbo, 720p, native audio** — the
  script has spoken dialogue ("Eh! Still playing ah? Go study now, lah!") and
  3.0 Turbo is the cheapest model with native audio; dialogue goes in the
  prompt text. Silent 2.5 Turbo is the cheapest dry-run for motion only,
  then add audio later via Video-to-Audio ($0.035/call) if a clip's motion
  is good.
- One failed task is not billed (billing is only returned on success), but a
  task that succeeds while you dislike it is — the approve-before-video gate
  still saves money.
- Prices drift; re-check https://kling.ai/document-api/pricing/base/video.md
  before spending.

## Next steps for the app

- Add `KLING_API_KEY` to `.env` (same rules as `GEMINI_API_KEY`: env-only,
  never written to files).
- Video handoff today: `export/manifest.json` already contains per-shot
  `start_keyframe` path, `kling_prompt` and duration — a `kling_client.py`
  wrapper can submit these directly and log the `billing[]` deduction per
  task into `logs/run_*.log`.
- Keyframe files are local; Kling accepts Base64 first frames, so no upload
  step is needed.
