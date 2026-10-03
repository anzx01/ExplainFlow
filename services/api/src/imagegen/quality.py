"""Deterministic quality checks for generated storyboard artwork."""
from __future__ import annotations

import io
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image


def normalize_whiteboard_image(image_bytes: bytes) -> bytes:
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    width, height = image.size
    pixels = np.asarray(image).copy()
    border = max(4, round(min(width, height) * 0.07))
    pixels[:border, :, :] = 255
    pixels[-border:, :, :] = 255
    pixels[:, :border, :] = 255
    pixels[:, -border:, :] = 255
    cleaned = Image.fromarray(pixels)
    gray = pixels.mean(axis=2)
    search = np.zeros_like(gray, dtype=bool)
    search[round(height * 0.15):round(height * 0.82), round(width * 0.05):round(width * 0.95)] = True
    foreground = (gray < 225) & search
    ys, xs = np.where(foreground)
    if len(xs) >= 32:
        pad_x = max(8, round((xs.max() - xs.min() + 1) * 0.08))
        pad_y = max(8, round((ys.max() - ys.min() + 1) * 0.08))
        left, right = max(0, int(xs.min()) - pad_x), min(width, int(xs.max()) + pad_x + 1)
        top, bottom = max(0, int(ys.min()) - pad_y), min(height, int(ys.max()) + pad_y + 1)
        cleaned = cleaned.crop((left, top, right, bottom))
    max_width, max_height = round(width * 0.82), round(height * 0.76)
    scale = min(max_width / cleaned.width, max_height / cleaned.height)
    target = (max(1, round(cleaned.width * scale)), max(1, round(cleaned.height * scale)))
    cleaned = cleaned.resize(target, Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (width, height), "white")
    canvas.paste(cleaned, ((width - target[0]) // 2, (height - target[1]) // 2))
    output = io.BytesIO()
    canvas.save(output, format="PNG", optimize=True)
    return output.getvalue()


def inspect_generated_image(image_bytes: bytes, *, use_ocr: bool = True) -> dict:
    errors: list[str] = []
    warnings: list[str] = []
    try:
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    except Exception as exc:
        return {"ok": False, "errors": ["invalid_image"], "warnings": [], "message": str(exc)}
    pixels = np.asarray(image, dtype=np.float32)
    gray = pixels.mean(axis=2)
    height, width = gray.shape
    stddev = float(gray.std())
    foreground_ratio = float((gray < 238).mean())
    dx = np.abs(np.diff(gray, axis=1))
    dy = np.abs(np.diff(gray, axis=0))
    edge_density = float(((dx > 24).sum() + (dy > 24).sum()) / max(1, dx.size + dy.size))
    border = max(8, round(min(width, height) * 0.07))
    border_mask = np.zeros_like(gray, dtype=bool)
    border_mask[:border, :] = True
    border_mask[-border:, :] = True
    border_mask[:, :border] = True
    border_mask[:, -border:] = True
    border_foreground_ratio = float(((gray < 180) & border_mask).sum() / max(1, border_mask.sum()))
    if width < 256 or height < 256:
        errors.append("resolution_too_small")
    if stddev < 5:
        errors.append("blank_or_flat")
    if foreground_ratio < 0.008:
        errors.append("foreground_too_sparse")
    if foreground_ratio > 0.72:
        errors.append("foreground_too_dense")
    if edge_density < 0.002:
        errors.append("insufficient_edges")
    if border_foreground_ratio > 0.002:
        errors.append("border_signature_or_watermark")

    ocr_text = ""
    tesseract = shutil.which("tesseract") if use_ocr else None
    if tesseract:
        with tempfile.TemporaryDirectory(prefix="explainflow-ocr-") as tmp:
            source = Path(tmp) / "image.png"
            image.save(source)
            try:
                result = subprocess.run(
                    [tesseract, str(source), "stdout", "-l", "eng", "--psm", "11"],
                    capture_output=True, text=True, timeout=20, check=False,
                )
                ocr_text = " ".join((result.stdout or "").split())[:200]
            except (OSError, subprocess.TimeoutExpired):
                warnings.append("ocr_unavailable")
        tokens = re.findall(r"[A-Za-z0-9]{3,}", ocr_text)
        if tokens:
            errors.append("readable_text_or_signature")
    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "metrics": {
            "width": width,
            "height": height,
            "brightnessStdDev": round(stddev, 2),
            "foregroundRatio": round(foreground_ratio, 4),
            "edgeDensity": round(edge_density, 4),
            "borderForegroundRatio": round(border_foreground_ratio, 4),
        },
        "ocrText": ocr_text,
    }
