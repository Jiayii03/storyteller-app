"""Higgsfield video client: thin wrapper over the official Python SDK.

Handles reference-to-video only: uploads the first-frame keyframe plus
identity references, submits to the model's catalog workflow, polls with a
hard timeout, downloads the MP4 immediately (outputs are kept server-side
for only ~7 days). Credentials are passed to the SDK explicitly and are
never logged."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import httpx

from .config import Config
from .storage import ProjectPaths, log_api_call


class HiggsfieldError(Exception):
    pass


def download(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with httpx.stream("GET", url, timeout=120.0, follow_redirects=True) as r:
        r.raise_for_status()
        with open(destination, "wb") as f:
            for chunk in r.iter_bytes():
                f.write(chunk)


class HiggsfieldClient:
    def __init__(self, key_id: str, key_secret: str, cfg: Config,
                 paths: ProjectPaths | None = None, sdk: Any = None):
        from higgsfield_client import SyncClient

        self.cfg = cfg
        self.paths = paths
        self._client = SyncClient(api_key=f"{key_id}:{key_secret}",
                                  base_url=cfg.higgsfield_base_url)
        # tests inject a fake SDK object; production uses SyncClient methods
        self._sdk = sdk or self._client

    def generate_clip(
        self,
        model: str,
        prompt: str,
        first_image: Path,
        references: list[Path],
        duration_sec: int,
        resolution: str,
        aspect_ratio: str,
        destination: Path,
        asset_id: str,
        request_id: str | None = None,
        on_submitted: Any = None,
    ) -> tuple[Path, dict | None, str]:
        entry = self.cfg.higgsfield_models.get(model)
        if entry is None:
            known = ", ".join(sorted(self.cfg.higgsfield_models))
            raise HiggsfieldError(
                f"Unknown Higgsfield model {model!r}. Catalog entries: {known}. "
                "Add it under `higgsfield.models` in config.yaml.")
        if request_id:
            controller = self._sdk.get_request_controller(request_id)
            if self.paths is not None:
                log_api_call(self.paths,
                             f"video resume asset={asset_id} request_id={request_id}")
        else:
            urls = [self._sdk.upload_file(str(first_image))]
            max_refs = int(entry.get("max_references", 10))
            if len(references) > max_refs:
                if self.paths is not None:
                    log_api_call(self.paths,
                                 f"warn asset={asset_id}: {len(references)} references "
                                 f"exceed max_references={max_refs}; truncating")
                references = references[:max_refs]
            urls += [self._sdk.upload_file(str(r)) for r in references]
            arguments = self._build_arguments(entry, model, prompt, urls,
                                              duration_sec, resolution, aspect_ratio)
            if self.paths is not None:
                log_api_call(self.paths,
                             f"video submitted asset={asset_id} model={model} "
                             f"refs={len(urls) - 1}")
            controller = self._sdk.submit(entry["workflow"], arguments)
            request_id = str(getattr(controller, "request_id", "") or "")
            if on_submitted is not None and request_id:
                # persist before polling: a kill mid-poll must resume, never re-submit
                on_submitted(request_id)

        result, usage = self._wait(controller, asset_id, model)
        url = (result.get("video") or {}).get("url") if isinstance(result, dict) else None
        if not url:
            raise HiggsfieldError(
                f"Video generation completed without a video URL for {asset_id}: {result}")
        if self.paths is not None:
            log_api_call(self.paths,
                         f"usage asset={asset_id} model={model} video_sec={duration_sec:g} "
                         f"cost_entry=estimate download=start")
        download(url, destination)
        if self.paths is not None:
            log_api_call(self.paths,
                         f"video downloaded asset={asset_id} -> {destination}")
        return destination, usage, request_id

    def _build_arguments(self, entry: dict, model: str, prompt: str, urls: list[str],
                         duration_sec: int, resolution: str,
                         aspect_ratio: str) -> dict[str, Any]:
        params = entry.get("params") or []
        values: dict[str, Any] = {
            "prompt": prompt,
            "image_urls": urls,
            "duration": int(duration_sec),
            "resolution": resolution,
            "aspect_ratio": aspect_ratio,
            "generate_audio": True,
        }
        for name in params:
            if name not in values:
                raise HiggsfieldError(
                    f"Model {model}: catalog parameter {name!r} is not supported "
                    "by this client; remove it from `higgsfield.models` params "
                    "in config.yaml or extend the client.")
        return {k: v for k, v in values.items() if k in params}

    def _wait(self, controller: Any, asset_id: str, model: str) -> tuple[dict, dict | None]:
        from higgsfield_client import (Cancelled, Completed, Failed, InProgress,
                                       NSFW, Queued)

        started = time.time()
        result: dict | None = None
        for status in controller.poll_request_status(delay=self.cfg.video_poll_interval_sec):
            if isinstance(status, Completed):
                result = controller.get()
                break
            if isinstance(status, (Failed, NSFW, Cancelled)):
                kind = type(status).__name__.lower()
                raise HiggsfieldError(
                    f"Video generation {kind} for asset {asset_id} (model {model}). "
                    "Higgsfield refunds failed generations automatically.")
            if not isinstance(status, (Queued, InProgress)):
                raise HiggsfieldError(
                    f"Unexpected poll status for asset {asset_id}: {status!r}")
            if time.time() - started > self.cfg.video_timeout_sec:
                raise HiggsfieldError(
                    f"Video generation timed out after {self.cfg.video_timeout_sec}s "
                    f"for asset {asset_id}. Resume with the same command; the "
                    "request keeps running server-side.")
        if result is None:
            raise HiggsfieldError(
                f"Video generation ended without completion for asset {asset_id}.")
        usage = result.get("usage") if isinstance(result, dict) else None
        return result, usage if isinstance(usage, dict) else None
