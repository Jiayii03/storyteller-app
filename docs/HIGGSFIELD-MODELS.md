# Higgsfield API: Models, Pricing and pc_story Cost Estimate

> Verified from official docs 2026-10-27: https://docs.higgsfield.ai/docs
> (Mintlify-hosted — append `.md` to URLs for LLM-readable pages; index at
> https://docs.higgsfield.ai/docs/llms.txt. Live model catalog and playground
> pricing at https://open.higgsfield.ai/pricing.)

Higgsfield is an aggregator: **one API key, one request lifecycle, 22 model
families / 67 catalog entries** — Seedance 2.5/2.0 (ByteDance), Kling 2.5–4.0 /
O1 / Omni (Kling AI), Wan 2.6–3.0 Prime (Alibaba), MiniMax H3, Hailuo 2.3,
LTX-2.5 (Fast/Pro), PixVerse V6, Happy Horse 1.0/1.1, Grok Imagine Video 1.5,
Cinema Studio 4.0, plus image models (FLUX.2, Nano Banana Pro, Soul, Ideogram,
Recraft, Qwen, Z-Image Turbo).

## Endpoint and auth

- Base URL: `https://api.higgsfield.ai`
- Auth header: `Authorization: Key ${HF_API_KEY_ID}:${HF_API_KEY_SECRET}`
  (two credentials, created at https://console.higgsfield.ai)
- Env vars in practice: `HF_API_KEY_ID` / `HF_API_KEY_SECRET` (or
  `HF_KEY="KEY_ID:KEY_SECRET"` for the SDKs / cURL). Put them in `.env`,
  never commit.
- Official SDKs: `@higgsfield/client` (TypeScript, server-side only) and
  Python; both poll automatically via `subscribe(..., withPolling=True)`.

## Request lifecycle (async, same for every model)

1. `POST https://api.higgsfield.ai/<model-path>` with the model's JSON body.
   Response: `{"status": "queued", "request_id": ..., "status_url": ...,
   "cancel_url": ...}`.
2. Poll `GET /requests/<request_id>/status` (or receive webhook).
3. Output files are available **at least 7 days** — download promptly.
   Inputs can be uploaded to Higgsfield storage first (`file-uploads.md`)
   or passed as public URLs/Base64.
4. Failed generations: credits are usually returned automatically. Completed
   generations are never refunded even if you dislike the result.

## Video models and pricing

Billing for Seedance-family models is per video token:
`tokens = ceil(h × w × (input + output duration) × 24 / 1024)`, priced
$0.0214/1k tokens at 480p/720p and $0.0234/1k at 1080p (Seedance 2.5; ×0.6
when video references are used). Prices below are **list** vs **max-discount**
(list + pick-4 promo). List per second at 16:9:

| Model | Resolutions | Duration | 480p | 720p | 1080p | Notes |
|---|---|---|---|---|---|---|
| **Seedance 2.5** (t2v, i2v) | 480p–1080p | 4–30 s | $0.206 / $0.144 | $0.462 / $0.324 | $1.137 / $0.796 | Native audio (default on), mp4/mov, one take up to 30 s |
| Seedance 2.5 (ref-to-video, video edit/extend) | 480p–1080p | 4–30 s | $0.174 / $0.123 (×0.6 rate with video input) | — | — | Multimodal references |
| Seedance 2.0 (t2v, i2v) | 480p–4K | 4–15 s | $0.141 / $0.099 | ~triples 720p→1080p | ≈5× 720p | 4K support |
| Seedance 2.0 (ref-to-video) | 480p–4K | 4–15 s | $0.168 / $0.118 | — | — | |
| Wan 3.0 / 3.0 Prime | up to 1080p | 2–30 s | ? | $0.050 / $0.020 | (Prime $0.068 / $0.027) | Cheapest per second; check per-model page for 480p |
| Kling 4.0 | up to 1080p | 3–30 s | ? | $0.094 / $0.066 | — | Via Higgsfield (Kling 4.0 is preview on Kling's own API) |
| Kling 3.0 (Standard i2v / Pro) | up to 1080p | 3–15 s | ? | $0.063 i2v-std, $0.084 pro | $0.21 4K | 50% off promo |
| Kling 2.6 / 2.5 | 5s/10s | ? | $0.070 / $0.035, $0.042 / $0.021 | — | |
| MiniMax H3 | up to 1080p | 3–15 s | ? | $0.065 / $0.033 | — | |
| Hailuo 2.3 Standard | up to 1080p | 6/10 s | ? | $0.0467 / $0.0117 | — | 75% off |
| LTX-2.5 Fast / Pro | up to 1080p | ? | ? | $0.09 / $0.12 | — | |
| PixVerse V6 | up to 1080p | 5/8 s | ? | $0.0978 / $0.083 | — | 15% off |
| Happy Horse 1.0 / 1.1 | up to 1080p | ? | ? | $0.07 / $0.035 | — | |
| Grok Imagine Video 1.5 | up to 1080p | ? | ? | $0.08 | — | |
| Cinema Studio 4.0 | 1080p | ? | ? | $0.2057 | — | Camera/style controls |

Image models (per image): Grok Imagine 2.0 $0.04, Qwen Image 3 $0.04,
Ideogram 4.0 $0.03, Recraft 4.1 $0.035, Z-Image Turbo $0.015, Soul 2 $0.0032,
Nano Banana Pro 2 credits, FLUX.2 Pro 1 credit.

## Seedance 2.5 API details (the model we care about)

Model ID: `bytedance/seedance-2.5/text-to-video` (and sibling workflows
`image-to-video`, `reference-to-video`, `video-edit`, `video-extend`).

```
POST https://api.higgsfield.ai/bytedance/seedance-2.5/image-to-video
Authorization: Key ${HF_API_KEY_ID}:${HF_API_KEY_SECRET}
{
  "prompt": "...",            // required, ≥1 char
  "duration": 8,              // 4–30 s, default 5
  "resolution": "480p",       // 480p | 720p | 1080p, default 720p
  "aspect_ratio": "16:9",     // 16:9 | 4:3 | 1:1 | 3:4 | 9:16 | 21:9
  "output_format": "mp4",     // mp4 | mov
  "generate_audio": true      // default true
}
```

First frame comes from our approved keyframe image. 480p is a first-class
output resolution here (unlike Kling's own API, which floors at 720p).

## Cost estimate for pc_story

4 shots × 8 s = **32 s**, image-to-video, 16:9.

| Plan | Per 8 s shot | Full 32 s story |
|---|---|---|
| Seedance 2.5 i2v, **480p**, list | $1.64 | **$6.58** |
| Seedance 2.5 i2v, 480p, 30% off | $1.15 | **$4.61** |
| Seedance 2.0 i2v, 480p, 30% off | $0.79 | **$3.16** |
| Seedance 2.5 i2v, 720p, list | $3.70 | $14.79 |
| Seedance 2.5 i2v, 720p, 30% off | $2.59 | **$10.35** |
| Kling 3.0 Standard i2v, 720p (via Higgsfield) | $0.50 | **$2.02** |

- A single 15 s video at 480p: Seedance 2.5 i2v list $3.08, discounted $2.16;
  Seedance 2.0 i2v discounted $1.48.
- Native audio is default-on and bills the same token rate — but for accurate
  dialogue audio check whether Seedance 2.5 renders speech from the prompt
  (the promo material says audio generation, not necessarily lip-synced
  dialogue; test one cheap 480p clip first).
- Recommended first test: one **Seedance 2.5 i2v 480p 8 s** clip (~$1.15–1.64)
  on S01, review motion and dialogue behavior, then batch the other 3.
- Completed generations are not refunded — the approve-before-video gate still
  matters. Failed generations refund automatically.
- Prices drift; re-check https://open.higgsfield.ai/pricing before spending.

## Next steps for the app

- Add `HF_API_KEY_ID` / `HF_API_KEY_SECRET` to `.env` (never written to files).
- `export/manifest.json` already has per-shot keyframe path, `kling_prompt`
  and duration — a `higgsfield_client.py` wrapper can submit these and log
  the billed amount per task into `logs/run_*.log`, same pattern as the
  Gemini cost lines.
- Output retention is only 7 days: download to `assets/shots/<id>/motion/`
  immediately.
