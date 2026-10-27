"""Gemini image generation wrapper with retries. SDK kept behind this module."""

from __future__ import annotations

import mimetypes
import time
from pathlib import Path
from typing import Any

from .config import Config
from .storage import log_api_call


class ContentBlocked(Exception):
    """Model returned text with no image (refusal or error). Message is user-facing."""


class TransientError(Exception):
    """Rate limit, 5xx or timeout: safe to retry."""


def _is_transient(exc: Exception) -> bool:
    msg = str(exc).lower()
    transient_words = ("rate", "429", "quota", "503", "500", "502", "timeout",
                       "timed out", "temporarily", "unavailable", "connection")
    return any(w in msg for w in transient_words)


class GeminiImageClient:
    def __init__(self, api_key: str, cfg: Config, paths=None):
        from google import genai

        self._client = genai.Client(api_key=api_key)
        self.cfg = cfg
        self.paths = paths

    def generate_image(
        self,
        model: str,
        prompt: str,
        input_images: list[tuple[Path, str]],
        aspect_ratio: str | None = None,
        seed: int | None = None,
        image_resolution: str | None = None,
        asset_id: str = "",
    ) -> tuple[bytes | None, str, Any]:
        """Returns (image_bytes|None, model_text, usage_metadata).
        Raises ContentBlocked on refusal."""
        from google.genai import types

        contents: list[Any] = []
        for path, _legend in input_images:
            mime = mimetypes.guess_type(str(path))[0] or "image/png"
            contents.append(types.Part.from_bytes(data=Path(path).read_bytes(), mime_type=mime))
        contents.append(prompt)

        kwargs: dict[str, Any] = {
            "response_modalities": ["IMAGE"],
        }
        image_cfg: dict[str, Any] = {}
        if aspect_ratio:
            image_cfg["aspect_ratio"] = aspect_ratio
        # Resolution support varies by model; passed only when set.
        if image_resolution and image_resolution not in ("1K", ""):
            image_cfg["image_size"] = image_resolution
        if image_cfg:
            kwargs["image_config"] = types.ImageConfig(**image_cfg)
        if seed is not None:
            kwargs["seed"] = seed

        attempts = 0
        last_exc: Exception | None = None
        while attempts <= self.cfg.max_retries:
            attempts += 1
            started = time.time()
            try:
                response = self._client.models.generate_content(
                    model=model,
                    contents=contents,
                    config=types.GenerateContentConfig(**kwargs),
                )
            except Exception as e:  # noqa: BLE001
                if _is_transient(e) and attempts <= self.cfg.max_retries:
                    last_exc = e
                    wait = 2.0 ** attempts
                    if self.paths is not None:
                        log_api_call(self.paths, f"transient error asset={asset_id} attempt={attempts}: {e}")
                    time.sleep(wait)
                    continue
                raise
            if self.paths is not None:
                log_api_call(self.paths,
                             f"image asset={asset_id} model={model} duration={time.time() - started:.1f}s")
            image_bytes: bytes | None = None
            text_parts: list[str] = []
            for cand in response.candidates or []:
                for part in cand.content.parts or []:
                    if part.inline_data and part.inline_data.data:
                        image_bytes = part.inline_data.data
                    elif part.text:
                        text_parts.append(part.text)
            if image_bytes is not None:
                usage = getattr(response, "usage_metadata", None)
                return image_bytes, "\n".join(text_parts), usage
            text = "\n".join(text_parts).strip()
            raise ContentBlocked(
                f"Model returned no image for asset {asset_id}. Model said: {text or '(no text)'}"
            )
        raise TransientError(f"Giving up on asset {asset_id} after {attempts} attempts: {last_exc}")
