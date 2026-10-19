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


def _composition_metrics(image: Image.Image) -> dict:
    """Subject presence / clutter metrics on a downscaled foreground mask.

    Calibrated over the cached master corpus (subject_h 0.33-0.85, debris 0-33):
    a hand-drawn teaching illustration needs one dominant subject cluster;
    confetti-like images and noisy hatch textures trace badly and read as
    cheap AI output.
    """
    width = 256
    height = max(1, round(image.height * width / image.width))
    small = image.resize((width, height), Image.Resampling.BILINEAR)
    gray = np.asarray(small, dtype=np.float32).mean(axis=2)
    mask = gray < 235
    labels = np.zeros((height, width), dtype=np.int32)
    sizes: list[int] = []
    for y in range(height):
        for x in range(width):
            if not mask[y, x] or labels[y, x]:
                continue
            component = len(sizes) + 1
            stack = [(y, x)]
            labels[y, x] = component
            count = 0
            while stack:
                cy, cx = stack.pop()
                count += 1
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        ny, nx = cy + dy, cx + dx
                        if 0 <= ny < height and 0 <= nx < width and mask[ny, nx] and not labels[ny, nx]:
                            labels[ny, nx] = component
                            stack.append((ny, nx))
            sizes.append(count)
    if not sizes:
        return {"subjectHeightRatio": 0.0, "debrisCount": 0, "componentCount": 0}
    largest = int(np.argmax(sizes)) + 1
    ys, _ = np.where(labels == largest)
    subject_h = float((ys.max() - ys.min() + 1) / height) if len(ys) else 0.0
    small_area = width * height * 0.0004
    debris = int(sum(1 for size in sizes if size < small_area))
    return {
        "subjectHeightRatio": round(subject_h, 4),
        "debrisCount": debris,
        "componentCount": len(sizes),
    }


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

    composition = _composition_metrics(image)
    if composition["subjectHeightRatio"] < 0.24:
        errors.append("no_clear_subject")
    if composition["debrisCount"] > 60:
        errors.append("debris_too_many")

    ocr_text = ""
    tesseract = shutil.which("tesseract") if use_ocr else None
    if use_ocr and not tesseract:
        installed = Path("C:/Program Files/Tesseract-OCR/tesseract.exe")
        tesseract = str(installed) if installed.is_file() else None
        if not tesseract:
            warnings.append("ocr_unavailable")
    tsv_words: list[tuple[str, float]] = []
    if tesseract:
        with tempfile.TemporaryDirectory(prefix="explainflow-ocr-") as tmp:
            source = Path(tmp) / "image.png"
            image.save(source)
            try:
                result = subprocess.run(
                    [tesseract, str(source), "stdout", "-l", "eng", "--psm", "11", "tsv"],
                    capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=20, check=False,
                )
                rows = (result.stdout or "").splitlines()
                for row in rows[1:]:
                    cols = row.split("\t")
                    if len(cols) < 12:
                        continue
                    text = cols[11].strip()
                    try:
                        conf = float(cols[10])
                    except ValueError:
                        continue
                    if text and conf >= 0:
                        tsv_words.append((text, conf))
                ocr_text = " ".join(text for text, _ in tsv_words)[:200]
            except (OSError, subprocess.TimeoutExpired):
                warnings.append("ocr_unavailable")
        # Tesseract frequently hallucinates isolated short tokens from doodle
        # strokes (for example ``4 3) Yh``). Treat text as a signature only
        # when OCR has enough coherent evidence to indicate an actual label:
        # either several 4+ letter tokens, one very long token, or a single
        # confidently-read short word. Calibration over the generated-image
        # corpus: stroke hallucinations never exceed ~89 confidence while
        # actual drawn labels (``Safe``, ``GAS``) read at 94-97, so a single
        # word at >=90 confidence is safe to reject and closes the gap where
        # a lone short label (``GAS``) slipped past the multi-token rule.
        tokens = re.findall(r"[A-Za-zА-Яа-яЁё]{4,}|[A-Za-z0-9]{6,}", ocr_text)
        confident_words = [
            word for word, conf in tsv_words
            if conf >= 90 and re.fullmatch(r"[A-Za-z]{3,9}", word)
        ]
        if len(tokens) >= 2 or any(len(token) >= 10 for token in tokens) or confident_words:
            errors.append("possible_readable_text_or_signature")
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
            "subjectHeightRatio": composition["subjectHeightRatio"],
            "debrisCount": composition["debrisCount"],
            "componentCount": composition["componentCount"],
        },
        "ocrText": ocr_text,
    }
