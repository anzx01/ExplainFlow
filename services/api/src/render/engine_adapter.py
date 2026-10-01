"""Adapter for the optional local whiteboard-video-engine checkout."""

from __future__ import annotations

import asyncio
import base64
import os
import shutil
import sys
import uuid
from pathlib import Path
from urllib.parse import unquote_to_bytes

import httpx
import imageio_ffmpeg


REPO_ROOT = Path(__file__).resolve().parents[4]
ENGINE_ROOT = Path(os.getenv("EXPLAINFLOW_WHITEBOARD_ENGINE_DIR", r"D:\ck\whiteboard-video-engine"))
ENGINE_SRC = ENGINE_ROOT / "src"
PREVIEW_DIR = REPO_ROOT / "outputs" / "engine-previews"
TOOL_DIR = REPO_ROOT / "outputs" / ".tools"


def engine_status() -> dict:
    return {
        "available": (ENGINE_SRC / "whiteboard_skill" / "cli.py").exists(),
        "engineRoot": str(ENGINE_ROOT),
        "python": sys.executable,
        "ffmpeg": imageio_ffmpeg.get_ffmpeg_exe(),
    }


def _ensure_ffmpeg_alias() -> Path:
    source = Path(imageio_ffmpeg.get_ffmpeg_exe())
    TOOL_DIR.mkdir(parents=True, exist_ok=True)
    target = TOOL_DIR / ("ffmpeg.exe" if os.name == "nt" else "ffmpeg")
    if not target.exists() or target.stat().st_size != source.stat().st_size:
        shutil.copy2(source, target)
    return target


def _suffix_for_content_type(content_type: str, fallback: str = ".png") -> str:
    lowered = content_type.lower()
    if "svg" in lowered:
        return ".svg"
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
        data = base64.b64decode(encoded) if ";base64" in header else unquote_to_bytes(encoded)
        destination.write_bytes(data)
        return destination
    if not image_url.startswith(("http://", "https://")):
        raise ValueError("image_url must be an http(s) URL or data URL")
    async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
        response = await client.get(image_url)
        response.raise_for_status()
        if len(response.content) > 20 * 1024 * 1024:
            raise ValueError("image exceeds 20MB preview limit")
        url_suffix = Path(response.url.path).suffix.lower()
        fallback = url_suffix if url_suffix in {".png", ".jpg", ".jpeg", ".webp", ".svg"} else ".png"
        destination = destination_base.with_suffix(_suffix_for_content_type(response.headers.get("content-type", ""), fallback))
        destination.write_bytes(response.content)
    return destination


async def render_engine_preview_from_path(
    image_path: Path,
    output_path: Path,
    *,
    duration: float,
    fps: int,
    width: int,
    height: int,
    hand: str,
    stroke_detail: str,
    color_fill: str,
    color_fill_scope: str,
) -> Path:
    if not engine_status()["available"]:
        raise RuntimeError(f"whiteboard-video-engine not found at {ENGINE_ROOT}")
    ffmpeg = _ensure_ffmpeg_alias()
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ENGINE_SRC) + os.pathsep + env.get("PYTHONPATH", "")
    env["PATH"] = str(ffmpeg.parent) + os.pathsep + env.get("PATH", "")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    args = [
        sys.executable, "-m", "whiteboard_skill.cli", "render-image", str(image_path),
        "-o", str(output_path),
        "--duration", str(duration), "--fps", str(fps), "--width", str(width), "--height", str(height),
        "--tail-color", str(min(2.0, max(0.5, duration * 0.12))),
        "--stroke-detail", stroke_detail, "--hand", hand,
        "--color-fill", color_fill, "--color-fill-scope", color_fill_scope,
        "--animation-preset", "block-speedpaint",
    ]
    if image_path.suffix.lower() != ".svg":
        args.extend(["--source-image", str(image_path), "--source-fit", "exact"])
    process = await asyncio.create_subprocess_exec(
        *args,
        cwd=str(REPO_ROOT),
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=600)
    if process.returncode != 0 or not output_path.exists():
        detail = (stderr or stdout).decode("utf-8", errors="replace")[-4000:]
        raise RuntimeError(f"whiteboard engine preview failed: {detail}")
    return output_path


async def render_engine_preview(image_url: str, **options) -> Path:
    token = uuid.uuid4().hex
    image_base = PREVIEW_DIR / token
    output_path = PREVIEW_DIR / f"{token}.mp4"
    image_path = await stage_image(image_url, image_base)
    return await render_engine_preview_from_path(image_path, output_path, **options)
