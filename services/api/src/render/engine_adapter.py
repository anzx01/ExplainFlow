"""Local adapter for Nikola's MIT stroke-story renderer."""

from __future__ import annotations

import asyncio
import base64
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path
from urllib.parse import unquote_to_bytes

import httpx


REPO_ROOT = Path(__file__).resolve().parents[4]
STROKE_ROOT = Path(os.getenv("EXPLAINFLOW_STROKE_STORY_DIR", r"D:\ck\hand-drawn-explainer-video-nikola\vendor\srt-whiteboard-animation"))
PREVIEW_DIR = REPO_ROOT / "outputs" / "engine-previews"
RENDER_SCRIPT = STROKE_ROOT / "scripts" / "render_stream_whiteboard.py"
HAND_ASSET = Path(os.getenv("EXPLAINFLOW_STROKE_HAND_ASSET", "")) if os.getenv("EXPLAINFLOW_STROKE_HAND_ASSET", "").strip() else STROKE_ROOT / "assets" / "drawing-hand.png"


def _python() -> Path:
    configured = os.getenv("EXPLAINFLOW_STROKE_STORY_PYTHON", "").strip()
    if configured:
        return Path(configured)
    bundled = STROKE_ROOT / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    return bundled if bundled.is_file() else Path(sys.executable)


def engine_status() -> dict:
    python = _python()
    return {
        "available": RENDER_SCRIPT.is_file() and HAND_ASSET.is_file() and python.is_file(),
        "engineRoot": str(STROKE_ROOT),
        "python": str(python),
        "renderer": "nikola-stroke-story",
        "localOnly": True,
    }


def _suffix_for_content_type(content_type: str, fallback: str = ".png") -> str:
    lowered = content_type.lower()
    if "jpeg" in lowered or "jpg" in lowered:
        return ".jpg"
    if "webp" in lowered:
        return ".webp"
    return fallback


async def stage_image(image_url: str, destination_base: Path) -> Path:
    destination_base.parent.mkdir(parents=True, exist_ok=True)
    if image_url.startswith("data:"):
        header, encoded = image_url.split(",", 1)
        destination = destination_base.with_suffix(_suffix_for_content_type(header))
        destination.write_bytes(base64.b64decode(encoded) if ";base64" in header else unquote_to_bytes(encoded))
        return destination
    if not image_url.startswith(("http://", "https://")):
        raise ValueError("image_url must be an http(s) URL or data URL")
    async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
        response = await client.get(image_url)
        response.raise_for_status()
        if len(response.content) > 20 * 1024 * 1024:
            raise ValueError("image exceeds 20MB preview limit")
        suffix = Path(response.url.path).suffix.lower()
        fallback = suffix if suffix in {".png", ".jpg", ".jpeg", ".webp"} else ".png"
        destination = destination_base.with_suffix(_suffix_for_content_type(response.headers.get("content-type", ""), fallback))
        destination.write_bytes(response.content)
    return destination


def _annotation(image_path: Path, duration: float) -> Path:
    from PIL import Image

    with Image.open(image_path) as image:
        width, height = image.size
    duration_ms = max(1500, round(duration * 1000))
    payload = {
        "sceneId": image_path.stem,
        "canvas": {"width": width, "height": height},
        "sceneDurationMs": duration_ms,
        "elements": [{
            "id": "scene", "label": "scene", "sequence": 1, "narrativeRole": "content", "subtitle": "",
            "region": {"x": 0, "y": 0, "width": width, "height": height},
            "reveal": {"startMs": 0, "durationMs": max(800, duration_ms - 600), "protectedRegions": []},
        }],
    }
    annotation = image_path.with_suffix(".annotation.json")
    annotation.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return annotation


def _render_story_preview(image_path: Path, output_path: Path, *, duration: float, fps: int, hand: str, hand_height: int, ink_path: str) -> None:
    """Render ordered canvas regions; labels and timings are supplied by the sidecar."""
    if not engine_status()["available"]:
        raise RuntimeError(f"Nikola stroke-story renderer not found at {STROKE_ROOT}")
    if image_path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
        raise ValueError("Nikola stroke-story preview requires a raster image")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    annotation = image_path.with_suffix(".annotation.json")
    args = [
        str(_python()), str(RENDER_SCRIPT), str(image_path), str(annotation), str(output_path), str(HAND_ASSET),
        "--total-ms", str(max(1500, round(duration * 1000))), "--fps", str(fps), "--hand-height", str(hand_height),
        "--cap-long-edge", "1080", "--ink-path", ink_path, "--color-fill", "brush", "--hand-follow", "0.6",
    ]
    if hand == "none":
        args.append("--bare-tip")
    process = subprocess.run(args, cwd=str(REPO_ROOT), capture_output=True, timeout=600, check=False)
    if process.returncode != 0 or not output_path.exists():
        detail = (process.stderr or process.stdout).decode("utf-8", errors="replace")[-4000:]
        raise RuntimeError(f"Nikola stroke-story preview failed: {detail}")


async def render_engine_preview_from_path(
    image_path: Path, output_path: Path, *, duration: float, fps: int, width: int, height: int,
    hand: str, stroke_detail: str, color_fill: str, color_fill_scope: str,
) -> Path:
    annotation = _annotation(image_path, duration)
    await asyncio.to_thread(
        _render_story_preview, image_path, output_path, duration=duration, fps=fps,
        hand=hand, hand_height=280, ink_path="skeleton" if stroke_detail == "rich" else "grid",
    )
    return output_path


async def render_engine_preview(image_url: str, **options) -> Path:
    token = uuid.uuid4().hex
    image_path = await stage_image(image_url, PREVIEW_DIR / token)
    return await render_engine_preview_from_path(image_path, PREVIEW_DIR / f"{token}.mp4", **options)
