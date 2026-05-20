#!/usr/bin/env python3
"""QA a rendered ExplainFlow/Golpo MP4 and optional storyboard JSON."""

from __future__ import annotations

import argparse
import json
import math
import statistics
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


def run(cmd: list[str], timeout: int = 60) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=timeout)


def check(ok: bool, check_id: str, severity: str, message: str, **extra: Any) -> dict[str, Any]:
    item = {"id": check_id, "ok": ok, "severity": severity, "message": message}
    item.update({k: v for k, v in extra.items() if v is not None})
    return item


def ffprobe(video_path: Path) -> dict[str, Any]:
    proc = run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration:stream=codec_type,codec_name,width,height",
            "-of",
            "json",
            str(video_path),
        ],
        timeout=30,
    )
    return json.loads(proc.stdout or "{}")


def extract_frame(video_path: Path, duration: float) -> Path:
    frame_path = Path(tempfile.gettempdir()) / f"explainflow_qa_{video_path.stem}.ppm"
    seek_at = max(0.2, min(max(duration * 0.5, 0.2), 3.0))
    run(
        [
            "ffmpeg",
            "-y",
            "-ss",
            f"{seek_at:.2f}",
            "-i",
            str(video_path),
            "-frames:v",
            "1",
            "-vf",
            "scale=160:-1",
            "-f",
            "image2",
            str(frame_path),
        ],
        timeout=60,
    )
    return frame_path


def read_ppm_brightness(frame_path: Path) -> dict[str, float]:
    raw = frame_path.read_bytes()
    tokens: list[bytes] = []
    idx = 0
    while len(tokens) < 4:
        while idx < len(raw) and raw[idx] in b" \t\r\n":
            idx += 1
        if idx < len(raw) and raw[idx : idx + 1] == b"#":
            while idx < len(raw) and raw[idx : idx + 1] not in b"\r\n":
                idx += 1
            continue
        start = idx
        while idx < len(raw) and raw[idx] not in b" \t\r\n":
            idx += 1
        tokens.append(raw[start:idx])
    magic, width_raw, height_raw, max_raw = tokens
    if magic != b"P6" or int(max_raw) != 255:
        raise ValueError("Unsupported ffmpeg QA frame format")
    while idx < len(raw) and raw[idx] in b" \t\r\n":
        idx += 1
    pixels = raw[idx:]
    values = [
        (pixels[i] + pixels[i + 1] + pixels[i + 2]) / 3
        for i in range(0, len(pixels) - 2, 3)
    ]
    mean = statistics.fmean(values) if values else 0.0
    stddev = statistics.pstdev(values) if len(values) > 1 else 0.0
    return {
        "width": float(int(width_raw)),
        "height": float(int(height_raw)),
        "meanBrightness": round(mean, 1),
        "brightnessStdDev": round(stddev, 1),
    }


def storyboard_text(storyboard: dict[str, Any]) -> str:
    return json.dumps(storyboard, ensure_ascii=False)


def storyboard_checks(storyboard: dict[str, Any]) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    scenes = storyboard.get("scenes") if isinstance(storyboard.get("scenes"), list) else []
    missing_style = [
        scene.get("id") or scene.get("title") or f"scene_{idx}"
        for idx, scene in enumerate(scenes)
        if not scene.get("video_style") and not scene.get("videoStyle")
    ]
    missing_pen = [
        scene.get("id") or scene.get("title") or f"scene_{idx}"
        for idx, scene in enumerate(scenes)
        if not scene.get("pen_style") and not scene.get("penStyle")
    ]
    checks.append(
        check(
            not missing_style,
            "scene_video_style",
            "warning" if missing_style else "info",
            "Every scene has video_style" if not missing_style else f"{len(missing_style)} scene(s) missing video_style",
            details={"scenes": missing_style[:8]} if missing_style else None,
            suggestion="Regenerate storyboard or normalize scenes with the selected Golpo video_style.",
        )
    )
    checks.append(
        check(
            not missing_pen,
            "scene_pen_style",
            "warning" if missing_pen else "info",
            "Every scene has pen_style" if not missing_pen else f"{len(missing_pen)} scene(s) missing pen_style",
            details={"scenes": missing_pen[:8]} if missing_pen else None,
            suggestion="Apply the selected Pen-in-hand style to all non-chalkboard scenes.",
        )
    )

    prompt_missing = []
    for idx, scene in enumerate(scenes):
        desc = str(scene.get("image_description") or scene.get("imageDescription") or "").lower()
        if desc and "text-free" not in desc and "no readable" not in desc:
            prompt_missing.append(scene.get("id") or scene.get("title") or f"scene_{idx}")
    checks.append(
        check(
            not prompt_missing,
            "text_free_image_prompts",
            "warning" if prompt_missing else "info",
            "All image prompts ask for text-free artwork"
            if not prompt_missing
            else f"{len(prompt_missing)} image prompt(s) missing text-free wording",
            details={"scenes": prompt_missing[:8]} if prompt_missing else None,
            suggestion="Add text-free/no-readable-words constraints to image_description.",
        )
    )

    text = storyboard_text(storyboard)
    hard_terms = ["互赖", "相互依赖赖", "interdependence 的"]
    bad_terms = [term for term in hard_terms if term in text]
    checks.append(
        check(
            not bad_terms,
            "natural_chinese_blacklist",
            "error" if bad_terms else "info",
            "No hard-translation blacklist terms found"
            if not bad_terms
            else f"Hard-translation terms found: {', '.join(bad_terms)}",
            details={"terms": bad_terms} if bad_terms else None,
            suggestion="Edit or regenerate narration/labels with natural Chinese wording.",
        )
    )

    topic = str(storyboard.get("topic") or "").lower()
    if any(term in topic for term in ["mapo", "麻婆", "豆腐", "tofu"]):
        prompt_blob = " ".join(
            str(scene.get("title") or "")
            + " "
            + str(scene.get("image_description") or scene.get("imageDescription") or "")
            for scene in scenes
        ).lower()
        required = ["wok", "red", "tofu", "minced", "scallion"]
        missing = [term for term in required if term not in prompt_blob]
        checks.append(
            check(
                not missing,
                "mapo_visual_terms",
                "warning" if missing else "info",
                "Mapo tofu prompts include key visual terms"
                if not missing
                else f"Mapo tofu prompts missing: {', '.join(missing)}",
                details={"missing": missing} if missing else None,
                suggestion="Use red chili oil, tofu cubes, minced meat, scallions, steam, and a wide wok.",
            )
        )
    return checks


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("video", type=Path, help="Path to rendered MP4")
    parser.add_argument("--storyboard", type=Path, help="Optional storyboard JSON")
    parser.add_argument("--min-bytes", type=int, default=50_000)
    parser.add_argument("--min-frame-stddev", type=float, default=2.5)
    args = parser.parse_args()

    checks: list[dict[str, Any]] = []
    suggestions: list[str] = []
    video = args.video
    exists = video.exists()
    size = video.stat().st_size if exists else 0
    checks.append(
        check(
            exists and size >= args.min_bytes,
            "output_file",
            "error",
            f"Output file size is {size} bytes" if exists else "Output file missing",
            details={"fileSizeBytes": size, "minBytes": args.min_bytes},
            suggestion="Render again and inspect Remotion/ffmpeg logs.",
        )
    )

    media_info: dict[str, Any] | None = None
    if exists:
        try:
            media_info = ffprobe(video)
            streams = media_info.get("streams") or []
            duration = float(media_info.get("format", {}).get("duration") or 0)
            has_video = any(s.get("codec_type") == "video" for s in streams)
            has_audio = any(s.get("codec_type") == "audio" for s in streams)
            checks.append(
                check(
                    has_video and duration > 0,
                    "video_stream",
                    "error",
                    f"Video duration is {duration:.1f}s",
                    details={"durationSeconds": duration, "hasVideo": has_video},
                    suggestion="Regenerate Remotion output; no playable video stream was found.",
                )
            )
            checks.append(
                check(
                    has_audio,
                    "audio_stream",
                    "error",
                    "Audio stream exists" if has_audio else "Rendered MP4 has no audio stream",
                    suggestion="Retry TTS and render; silent videos are blocked.",
                )
            )
            if duration > 0:
                frame = extract_frame(video, duration)
                try:
                    stats = read_ppm_brightness(frame)
                    nonblank = stats["brightnessStdDev"] >= args.min_frame_stddev
                    checks.append(
                        check(
                            nonblank,
                            "nonblank_frame",
                            "error",
                            f"Frame brightness stddev {stats['brightnessStdDev']}",
                            details={**stats, "minStdDev": args.min_frame_stddev},
                            suggestion="Regenerate scene images/code; the sampled frame looks blank or flat.",
                        )
                    )
                finally:
                    frame.unlink(missing_ok=True)
        except Exception as exc:
            checks.append(
                check(
                    False,
                    "media_probe",
                    "error",
                    f"ffprobe/ffmpeg QA failed: {exc}",
                    suggestion="Check local ffprobe/ffmpeg installation.",
                )
            )

    if args.storyboard:
        try:
            storyboard = json.loads(args.storyboard.read_text(encoding="utf-8"))
            checks.extend(storyboard_checks(storyboard))
        except Exception as exc:
            checks.append(
                check(
                    False,
                    "storyboard_json",
                    "error",
                    f"Could not read storyboard JSON: {exc}",
                    suggestion="Pass a valid storyboard JSON file.",
                )
            )

    for item in checks:
        if not item["ok"] and item.get("suggestion"):
            suggestions.append(item["suggestion"])

    blocking = [item for item in checks if not item["ok"] and item["severity"] == "error"]
    result = {
        "ok": not blocking,
        "checks": checks,
        "suggestions": sorted(set(suggestions)),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if blocking else 0


if __name__ == "__main__":
    sys.exit(main())
