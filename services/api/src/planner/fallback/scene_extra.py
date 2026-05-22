import re

from ..models import Scene
from ..storyboard_gen.normalizer import _clean_text, _subtitle_text


def _scene_extra(scene: Scene, name: str, default: object = None) -> object:
    aliases = [name]
    if "_" in name:
        parts = name.split("_")
        aliases.append(parts[0] + "".join(part.capitalize() for part in parts[1:]))
    else:
        aliases.append(re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower())
    aliases = list(dict.fromkeys(alias for alias in aliases if alias))

    for alias in aliases:
        value = getattr(scene, alias, default)
        if value is not default and value is not None:
            return value

    extra = getattr(scene, "model_extra", None)
    if isinstance(extra, dict):
        for alias in aliases:
            if alias in extra:
                return extra[alias]
    return default


def _audio_segments_for_scene(scene: Scene, fps: int) -> tuple[list[dict], int, int]:
    raw_segments = (
        _scene_extra(scene, "audioSegments")
        or _scene_extra(scene, "audio_segments")
        or _scene_extra(scene, "audio_segments_json")
        or []
    )
    raw_timing = _scene_extra(scene, "timingPlan") or _scene_extra(scene, "timing_plan") or {}
    transition_frames = 0
    if isinstance(raw_timing, dict):
        transition_frames = max(0, min(18, int(raw_timing.get("transitionFrames") or raw_timing.get("transition_frames") or 0)))
    segments: list[dict] = []
    if isinstance(raw_segments, list):
        for index, raw in enumerate(raw_segments):
            if not isinstance(raw, dict):
                continue
            start = max(0, int(round(float(raw.get("startFrame") or raw.get("start_frame") or 0))))
            duration = int(round(float(raw.get("duration") or 0)))
            end = int(round(float(raw.get("endFrame") or raw.get("end_frame") or 0)))
            if duration <= 0 and end > start:
                duration = end - start
            if duration <= 0:
                duration = max(fps * 3, int(round(float(raw.get("audioDurationFrames") or fps * 3))) + 12)
            end = max(start + 1, start + duration)
            audio_duration = max(1, int(round(float(raw.get("audioDurationFrames") or raw.get("audio_duration_frames") or duration))))
            audio_start = int(round(float(raw.get("audioStartFrame") or raw.get("audio_start_frame") or start)))
            audio_start = max(start, min(end - 1, audio_start))
            audio_end = int(round(float(raw.get("audioEndFrame") or raw.get("audio_end_frame") or (audio_start + audio_duration))))
            audio_end = max(audio_start + 1, min(end, audio_end))
            segments.append(
                {
                    "id": _clean_text(raw.get("id")) or f"beat_{index}",
                    "index": index,
                    "startFrame": start,
                    "endFrame": end,
                    "duration": end - start,
                    "audioStartFrame": audio_start,
                    "audioEndFrame": audio_end,
                    # Use audioDurationFrames as audioSequenceDuration to prevent audio overlap
                    # Don't use end - audio_start which would extend beyond audio duration
                    "audioSequenceDuration": max(1, audio_duration),
                    "audioUrl": raw.get("audioUrl") or raw.get("audio_url"),
                    "audioDurationFrames": audio_duration,
                    "drawBudgetFrames": max(1, int(round(float(raw.get("drawBudgetFrames") or raw.get("draw_budget_frames") or (end - start - 8))))),
                    "subtitleText": _subtitle_text(raw.get("subtitleText") or raw.get("subtitle_text") or raw.get("narration")),
                    "drawIntent": _clean_text(raw.get("drawIntent") or raw.get("draw_intent")),
                }
            )
    duration_frames = 0
    if isinstance(raw_timing, dict):
        duration_frames = int(round(float(raw_timing.get("durationFrames") or raw_timing.get("duration_frames") or 0)))
    if segments:
        duration_frames = max(duration_frames, max(segment["endFrame"] for segment in segments) + transition_frames)
    return segments, duration_frames, transition_frames


