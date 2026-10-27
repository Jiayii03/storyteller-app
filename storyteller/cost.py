"""Cost computation from published prices. Rates live in config.yaml `pricing`
so they can be updated when Google changes them; never hard-coded elsewhere.

Prices verified against Google AI pricing docs (2026-10-27, paid tier).
Image models: input tokens + per-image output (published per-image equivalent).
Video models: per second of generated video, audio vs silent rates differ.
"""

from __future__ import annotations

from typing import Any

# Per-image USD keyed by output resolution, as published by Google.
IMAGE_PRICING: dict[str, dict[str, Any]] = {
    "gemini-3.1-flash-image": {
        "input_per_mtok_usd": 0.50, "text_output_per_mtok_usd": 3.00,
        "per_image_usd": {"0.5K": 0.045, "1K": 0.067, "2K": 0.101, "4K": 0.151},
    },
    "gemini-3.1-flash-image-preview": {
        "input_per_mtok_usd": 0.50, "text_output_per_mtok_usd": 3.00,
        "per_image_usd": {"0.5K": 0.045, "1K": 0.067, "2K": 0.101, "4K": 0.151},
    },
    "gemini-nano-banana-2.1": {
        "input_per_mtok_usd": 0.50, "text_output_per_mtok_usd": 3.00,
        "per_image_usd": {"0.5K": 0.045, "1K": 0.067, "2K": 0.101, "4K": 0.151},
    },
    "gemini-3.1-flash-lite-image": {
        "input_per_mtok_usd": 0.25, "text_output_per_mtok_usd": 1.50,
        "per_image_usd": {"1K": 0.034},
    },
    "gemini-3-pro-image": {
        "input_per_mtok_usd": 2.00, "text_output_per_mtok_usd": 12.00,
        "per_image_usd": {"1K": 0.134, "2K": 0.134, "4K": 0.240},
    },
    "gemini-3-pro-image-preview": {
        "input_per_mtok_usd": 2.00, "text_output_per_mtok_usd": 12.00,
        "per_image_usd": {"1K": 0.134, "2K": 0.134, "4K": 0.240},
    },
    "nano-banana-pro-preview": {
        "input_per_mtok_usd": 2.00, "text_output_per_mtok_usd": 12.00,
        "per_image_usd": {"1K": 0.134, "2K": 0.134, "4K": 0.240},
    },
    "gemini-2.5-flash-image": {  # deprecated: shut down 2026-10-02
        "input_per_mtok_usd": 0.30, "text_output_per_mtok_usd": 2.50,
        "per_image_usd": {"1K": 0.039},
    },
}

# Per-second USD by resolution; audio and silent (no-audio) rates differ.
# Veo 3.1 Preview shut down 2026-10-22; Gemini Developer API video is now
# Gemini Omni Flash (Interactions API). Pricing: input $1.50/Mtok,
# video output $17.50/Mtok at ~5792 tokens/s of 720p -> ~$0.101/s.
VIDEO_PRICING: dict[str, dict[str, dict[str, float]]] = {
    "gemini-omni-1.1-flash": {
        "720p": {"audio": 0.1013, "silent": 0.1013},
    },
    "gemini-omni-flash-preview": {
        "720p": {"audio": 0.1013, "silent": 0.1013},
    },
    "veo-3.1-generate-preview": {  # shut down 2026-10-22 (Enterprise API only now)
        "720p": {"audio": 0.40, "silent": 0.20},
        "1080p": {"audio": 0.40, "silent": 0.20},
        "4k": {"audio": 0.60, "silent": 0.40},
    },
    "veo-3.1-generate-001": {
        "720p": {"audio": 0.40, "silent": 0.20},
        "1080p": {"audio": 0.40, "silent": 0.20},
        "4k": {"audio": 0.60, "silent": 0.40},
    },
}


def _match(table: dict, model: str) -> dict | None:
    if model in table:
        return table[model]
    for key in table:
        if model.startswith(key):
            return table[key]
    return None


def image_cost(
    model: str,
    resolution: str,
    usage: Any,
    images_returned: int,
    pricing: dict | None = None,
) -> dict | None:
    """Cost for one image API call. Returns {cost_usd, breakdown} or None
    when the model has no pricing entry (rate logged, cost unknown)."""
    table = pricing or IMAGE_PRICING
    entry = _match(table, model)
    if entry is None:
        return None
    per_image = entry["per_image_usd"]
    res = resolution if resolution in per_image else next(iter(per_image))
    image_out = per_image[res] * max(images_returned, 1)
    input_cost = 0.0
    prompt_tokens = 0
    if usage is not None:
        prompt_tokens = getattr(usage, "prompt_token_count", 0) or 0
        input_cost = prompt_tokens / 1e6 * entry.get("input_per_mtok_usd", 0.0)
    total = image_out + input_cost
    return {
        "cost_usd": round(total, 4),
        "breakdown": {
            "image_output": round(image_out, 4),
            "input_tokens": round(input_cost, 4),
        },
        "prompt_tokens": prompt_tokens,
    }


def video_cost(
    model: str,
    resolution: str,
    generate_audio: bool,
    duration_sec: float,
    pricing: dict | None = None,
) -> dict | None:
    table = pricing or VIDEO_PRICING
    entry = _match(table, model)
    if entry is None:
        return None
    rates = entry.get(resolution.lower()) or next(iter(entry.values()))
    rate = rates["audio" if generate_audio else "silent"]
    return {
        "cost_usd": round(rate * duration_sec, 4),
        "breakdown": {f"video_{resolution}_{duration_sec:g}s": round(rate * duration_sec, 4)},
        "rate_per_sec": rate,
    }
