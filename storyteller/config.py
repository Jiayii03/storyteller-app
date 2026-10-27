"""Configuration: defaults, optional config.yaml overrides, model constraints."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .cost import IMAGE_PRICING, VIDEO_PRICING

DEFAULTS: dict[str, Any] = {
    "max_variants_per_asset": 4,
    "max_retries": 2,
    "confirm_above_calls": 10,
    "max_calls_per_run": 40,
    "request_delay_sec": 1.0,
    "video_poll_interval_sec": 10,
    "video_timeout_sec": 600,
    "default_variants": 2,
    # Verified against Google AI docs (Oct 2026):
    # Gemini Omni Flash video: duration 3s-10s (integer seconds), 720p,
    # audio always generated. Trim to requested length with ffmpeg.
    "model_constraints": {
        "video_allowed_durations_sec": [3, 4, 5, 6, 7, 8, 9, 10],
        "video_min_duration_sec": 3,
        "video_supports_last_frame": True,
    },
    "cost_per_image_usd": 0.04,
    "cost_per_video_sec_usd": 0.40,
    "storyboard_columns": 3,
}

_image_cost_hints = None  # placeholder to keep future per-model pricing tables


@dataclass
class Config:
    max_variants_per_asset: int = 4
    max_retries: int = 2
    confirm_above_calls: int = 10
    max_calls_per_run: int = 40
    request_delay_sec: float = 1.0
    video_poll_interval_sec: int = 10
    video_timeout_sec: int = 600
    default_variants: int = 2
    video_allowed_durations_sec: list[int] = field(default_factory=lambda: [4, 6, 8])
    video_min_duration_sec: int = 4
    video_supports_last_frame: bool = True
    cost_per_image_usd: float = 0.04
    cost_per_video_sec_usd: float = 0.40
    storyboard_columns: int = 3
    image_pricing: dict = field(default_factory=lambda: dict(IMAGE_PRICING))
    video_pricing: dict = field(default_factory=lambda: dict(VIDEO_PRICING))

    @property
    def video_max_duration_sec(self) -> int:
        return max(self.video_allowed_durations_sec)


def load_config(start_dir: Path | None = None) -> Config:
    """Defaults, overridden by config.yaml found in start_dir or cwd."""
    data: dict[str, Any] = {}
    for folder in (start_dir, Path.cwd()):
        if folder is None:
            continue
        candidate = folder / "config.yaml"
        if candidate.exists():
            import yaml

            loaded = yaml.safe_load(candidate.read_text(encoding="utf-8")) or {}
            if isinstance(loaded, dict):
                data.update(loaded)
            break
    merged = dict(DEFAULTS)
    constraints = dict(DEFAULTS["model_constraints"])
    constraints.update(data.pop("model_constraints", {}) or {})
    pricing_in = data.pop("pricing", {}) or {}
    data.pop("_image_cost_hints", None)
    merged.update(data)
    merged["model_constraints"] = constraints
    cfg = Config()
    cfg.max_variants_per_asset = int(merged["max_variants_per_asset"])
    cfg.max_retries = int(merged["max_retries"])
    cfg.confirm_above_calls = int(merged["confirm_above_calls"])
    cfg.max_calls_per_run = int(merged["max_calls_per_run"])
    cfg.request_delay_sec = float(merged["request_delay_sec"])
    cfg.video_poll_interval_sec = int(merged["video_poll_interval_sec"])
    cfg.video_timeout_sec = int(merged["video_timeout_sec"])
    cfg.default_variants = int(merged["default_variants"])
    cfg.video_allowed_durations_sec = list(constraints["video_allowed_durations_sec"])
    cfg.video_min_duration_sec = int(constraints["video_min_duration_sec"])
    cfg.video_supports_last_frame = bool(constraints["video_supports_last_frame"])
    cfg.cost_per_image_usd = float(merged["cost_per_image_usd"])
    cfg.cost_per_video_sec_usd = float(merged["cost_per_video_sec_usd"])
    cfg.storyboard_columns = int(merged["storyboard_columns"])
    if pricing_in:
        merged_pricing = {"image": dict(IMAGE_PRICING), "video": dict(VIDEO_PRICING)}
        merged_pricing["image"].update(pricing_in.get("image", {}) or {})
        merged_pricing["video"].update(pricing_in.get("video", {}) or {})
        cfg.image_pricing = merged_pricing["image"]
        cfg.video_pricing = merged_pricing["video"]
    return cfg


def api_key() -> str:
    """GEMINI_API_KEY from env or .env. Never logged, never written anywhere."""
    key = os.environ.get("GEMINI_API_KEY", "")
    if not key:
        try:
            from dotenv import load_dotenv

            load_dotenv()
            key = os.environ.get("GEMINI_API_KEY", "")
        except ImportError:
            pass
    return key
