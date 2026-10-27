"""Video generation wrapper (Gemini Omni Flash, Interactions API).

Veo 3.1 Preview was shut down on 2026-10-22; the Gemini Developer API video
model is now `gemini-omni-1.1-flash` through `client.interactions.create`.
Kept behind this single module so future API changes stay isolated."""

from __future__ import annotations

import base64
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from . import cost as cost_mod
from .config import Config
from .storage import log_api_call


class VeoError(Exception):
    pass


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def trim_clip(src: Path, dst: Path, duration_sec: float) -> None:
    if not ffmpeg_available():
        raise VeoError(
            "ffmpeg not found on PATH. Install ffmpeg to trim motion clips, "
            "or keep the untrimmed original."
        )
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(src), "-t", f"{duration_sec:g}", "-c", "copy", str(dst)],
        check=True, capture_output=True,
    )


TERMINAL = {"completed", "failed", "cancelled", "succeeded"}


class VeoClient:
    """Named VeoClient for API compatibility; drives Gemini Omni Flash."""

    def __init__(self, api_key: str, cfg: Config, paths=None):
        from google import genai

        self._client = genai.Client(api_key=api_key)
        self.cfg = cfg
        self.paths = paths

    def generate_clip(
        self,
        model: str,
        prompt: str,
        first_image: Path,
        last_image: Path | None,
        requested_duration_sec: float,
        aspect_ratio: str | None,
        resolution: str,
        generate_audio: bool | None,
        asset_id: str = "",
        destination: Path | None = None,
    ) -> tuple[Path, Any, dict | None]:
        """Submit, poll, download. Returns (clip_path, usage, cost).
        Omni generates audio alongside video; silent rates no longer apply on
        the Developer API. Clips shorter than the 3 s minimum are generated at
        the minimum and trimmed with ffmpeg."""
        import mimetypes

        allowed = sorted(self.cfg.video_allowed_durations_sec)
        target = min((d for d in allowed if d >= requested_duration_sec), default=allowed[-1])
        if target < requested_duration_sec:
            target = allowed[-1]  # longest allowed; trim later
        if target > requested_duration_sec and self.paths is not None:
            log_api_call(self.paths,
                         f"video asset={asset_id}: requested {requested_duration_sec:g}s, "
                         f"generating {target}s (minimum), trimming after")

        def part_image(path: Path) -> dict[str, str]:
            mime = mimetypes.guess_type(str(path))[0] or "image/png"
            return {"type": "image", "data": base64.b64encode(Path(path).read_bytes()).decode(),
                    "mime_type": mime}

        video_config: dict[str, Any] = {
            "task": "image_to_video",
            "response_format": {
                "aspect_ratio": aspect_ratio or "16:9",
                "duration": f"{target:g}s",
            },
        }
        _ = resolution  # Omni outputs 720p on the Developer API

        input_parts: list[dict[str, str]] = [part_image(first_image)]
        if last_image is not None and self.cfg.video_supports_last_frame:
            # second image becomes the ending frame
            input_parts.append(part_image(last_image))
        input_parts.append({"type": "text", "text": prompt})

        started = time.time()
        interaction = self._client.interactions.create(
            model=model,
            input=input_parts,
            generation_config={"video_config": video_config},
        )
        if self.paths is not None:
            log_api_call(self.paths, f"video submitted asset={asset_id} model={model}")

        while getattr(interaction, "status", "completed") not in TERMINAL:
            if time.time() - started > self.cfg.video_timeout_sec:
                raise VeoError(
                    f"Video generation timed out after {self.cfg.video_timeout_sec}s "
                    f"for asset {asset_id}."
                )
            time.sleep(self.cfg.video_poll_interval_sec)
            interaction = self._client.interactions.get(interaction.id)

        if getattr(interaction, "status", "") == "failed":
            raise VeoError(f"Video generation failed for asset {asset_id}: {interaction}")

        usage = getattr(interaction, "usage_metadata", None) or getattr(
            interaction, "usage", None)
        audio = generate_audio is not False  # Omni always has audio
        clip_cost = cost_mod.video_cost(model, "720p", audio, target,
                                        pricing=self.cfg.video_pricing)
        if self.paths is not None:
            log_api_call(self.paths,
                         f"usage asset={asset_id} model={model} video_sec={target:g} "
                         f"cost_usd={clip_cost['cost_usd'] if clip_cost else 'unknown'}")

        if destination is None:
            destination = Path.cwd() / "omni_clip.mp4"
        destination.parent.mkdir(parents=True, exist_ok=True)
        out_bytes = self._extract_video(interaction)
        destination.write_bytes(out_bytes)
        if self.paths is not None:
            log_api_call(self.paths, f"video downloaded asset={asset_id} -> {destination}")

        if target > requested_duration_sec:
            if not ffmpeg_available():
                if self.paths is not None:
                    log_api_call(self.paths,
                                 f"warn asset={asset_id}: ffmpeg not found; kept untrimmed "
                                 f"{target:g}s clip (requested {requested_duration_sec:g}s)")
                return destination, usage, clip_cost
            trimmed = destination.with_name(destination.stem + "_trimmed.mp4")
            trim_clip(destination, trimmed, requested_duration_sec)
            # trimmed result becomes the approved artifact, original kept beside it
            return trimmed, usage, clip_cost
        return destination, usage, clip_cost

    def _extract_video(self, interaction: Any) -> bytes:
        data = getattr(interaction, "output_video", None)
        if data is not None and getattr(data, "data", None):
            return base64.b64decode(data.data)
        # fallback: collect model_output steps
        b64 = None
        for step in getattr(interaction, "steps", []) or []:
            if getattr(step, "type", "") in ("model_output", "MODEL_OUTPUT"):
                for part in getattr(step, "content", []) or []:
                    if getattr(part, "type", "") == "video" and getattr(part, "data", None):
                        b64 = part.data
                        break
            if b64:
                break
        if not b64:
            raise VeoError(f"No video data returned for the interaction: {interaction}")
        return base64.b64decode(b64)
