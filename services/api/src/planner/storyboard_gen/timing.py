import math
import re

from ..models import Scene, Storyboard, VisualBeat, AnimationInstruction
from .normalizer import _clean_narration_text, _clean_text, _trim_text_to_chars


def _label_token(value: object) -> str:
    return re.sub(r"\s+", "", _clean_text(value).lower())


def _label_is_covered(label: object, text: str) -> bool:
    token = _label_token(label)
    if len(token) < 2:
        return True
    return token in re.sub(r"\s+", "", _clean_text(text).lower())


def _ensure_required_labels_in_beat_narration(beats: list[VisualBeat]) -> list[VisualBeat]:
    for beat in beats:
        narration = _clean_narration_text(beat.narration)
        missing: list[str] = []
        seen: set[str] = set()
        for label in beat.required_labels or []:
            cleaned = _clean_text(label)
            token = _label_token(cleaned)
            if not cleaned or token in seen or _label_is_covered(cleaned, narration):
                continue
            seen.add(token)
            missing.append(cleaned)
            if len(missing) >= 3:
                break
        if missing:
            addition = f"关键词要点是：{'、'.join(missing)}。"
            beat.narration = _clean_narration_text(f"{narration} {addition}" if narration else addition)
        else:
            beat.narration = narration
    return beats

def _narration_from_beats(narration: str, beats: list[VisualBeat]) -> str:
    beats = _ensure_required_labels_in_beat_narration(beats)
    beat_text = " ".join(beat.narration for beat in beats if beat.narration).strip()
    narration = _clean_narration_text(narration)
    if not beat_text:
        return narration
    if len(narration) < max(80, len(beat_text) * 0.45):
        return beat_text
    missing = [
        beat.narration
        for beat in beats
        if beat.narration and beat.narration[:18] not in narration
    ]
    if missing and len(narration) < 180:
        return _clean_narration_text(f"{narration} {' '.join(missing[:3])}")
    return narration


def _compress_storyboard_narration_to_target(storyboard: Storyboard, target_duration: int) -> Storyboard:
    if not storyboard.scenes:
        return storyboard
    scene_count = max(1, len(storyboard.scenes))
    target = max(45.0, float(target_duration))
    speech_budget = max(30.0, target * 0.62)
    per_scene_budget = speech_budget / scene_count
    for scene in storyboard.scenes:
        beats = scene.visual_beats or []
        beat_count = max(1, len(beats))
        per_beat_seconds = max(4.0, min(9.0, per_scene_budget / beat_count))
        max_chars = max(18, int(per_beat_seconds * 3.0))
        for beat in beats:
            beat.narration = _trim_text_to_chars(beat.narration, max_chars)
            beat.duration_estimate = round(max(4.0, min(10.0, per_beat_seconds + 1.0)), 1)
        beat_narration = _clean_narration_text(" ".join(beat.narration for beat in beats if beat.narration))
        if beat_narration:
            scene.narration = beat_narration
        else:
            scene.narration = _trim_text_to_chars(scene.narration, int(per_scene_budget * 3.0))
        scene.duration_estimate = _estimate_scene_duration(min(scene.duration_estimate, per_scene_budget + 4.0), scene.narration, beats, scene.animations)
    storyboard.total_duration_estimate = round(sum(scene.duration_estimate for scene in storyboard.scenes), 1)
    return storyboard


def _estimate_narration_seconds(narration: str) -> float:
    cjk_chars = len(re.findall(r"[\u3400-\u9fff]", narration))
    total_chars = len(narration)
    # Edge TTS pauses on Chinese punctuation; this slower estimate prevents scene audio being clipped.
    return max(8.0, cjk_chars / 3.35 + max(0, total_chars - cjk_chars) / 7.2)


def _estimate_scene_duration(raw_duration: float, narration: str, beats: list[VisualBeat], animations: list[AnimationInstruction]) -> float:
    narration_seconds = _estimate_narration_seconds(narration)
    beat_seconds = sum(max(3.0, beat.duration_estimate) for beat in beats) + (4.0 if beats else 0.0)
    animation_seconds = sum(animation.duration for animation in animations) + (4.0 if animations else 0.0)
    minimum = 22.0 if beats else 16.0
    duration = max(float(raw_duration or 0), narration_seconds + 3.0, beat_seconds, animation_seconds, minimum)
    return round(min(duration, 55.0), 1)


def _scene_floor_duration(scene: Scene, target_scene_seconds: float | None = None) -> float:
    beat_floor = sum(max(2.4, beat.duration_estimate * 0.75) for beat in scene.visual_beats)
    animation_floor = sum(max(1.0, animation.duration * 0.8) for animation in scene.animations)
    narration_floor = _estimate_narration_seconds(scene.narration) + 2.0
    required = max(10.0, narration_floor, beat_floor + 1.0, animation_floor + 1.0)
    cap = 32.0 if target_scene_seconds is None else max(12.0, target_scene_seconds * 1.18)
    return round(min(cap, required), 1)


def _fit_storyboard_to_target(storyboard: Storyboard, target_duration: int) -> Storyboard:
    """Use the UI duration as a pacing hint: stretch short lessons, never trim required content."""
    target = float(max(30, min(300, target_duration)))
    if not storyboard.scenes:
        storyboard.total_duration_estimate = target
        return storyboard

    target_scene_seconds = target / max(1, len(storyboard.scenes))
    floors = [_scene_floor_duration(scene, target_scene_seconds) for scene in storyboard.scenes]
    for scene, floor in zip(storyboard.scenes, floors):
        scene.duration_estimate = round(max(0.1, scene.duration_estimate, floor), 1)

    current = sum(max(0.1, scene.duration_estimate) for scene in storyboard.scenes)
    floor_total = sum(floors)
    if current >= target:
        if floor_total >= target:
            for scene, floor in zip(storyboard.scenes, floors):
                old_duration = max(0.1, scene.duration_estimate)
                ratio = floor / old_duration
                scene.duration_estimate = round(floor, 1)
                for beat in scene.visual_beats:
                    beat.duration_estimate = round(max(1.0, beat.duration_estimate * ratio), 1)
                for animation in scene.animations:
                    animation.duration = round(min(15.0, max(0.5, animation.duration * ratio)), 1)
            storyboard.total_duration_estimate = round(sum(scene.duration_estimate for scene in storyboard.scenes), 1)
            return storyboard
        compressible = max(0.1, current - floor_total)
        ratio = max(0.0, min(1.0, (target - floor_total) / compressible))
        for scene, floor in zip(storyboard.scenes, floors):
            old_duration = max(0.1, scene.duration_estimate)
            duration = floor + (old_duration - floor) * ratio
            beat_ratio = duration / old_duration
            scene.duration_estimate = round(duration, 1)
            for beat in scene.visual_beats:
                beat.duration_estimate = round(max(1.0, beat.duration_estimate * beat_ratio), 1)
            for animation in scene.animations:
                animation.duration = round(min(15.0, max(0.5, animation.duration * beat_ratio)), 1)
        storyboard.total_duration_estimate = round(sum(scene.duration_estimate for scene in storyboard.scenes), 1)
        return storyboard

    remaining = target - current
    weights = [max(1.0, scene.duration_estimate) for scene in storyboard.scenes]
    weight_total = sum(weights) or float(len(storyboard.scenes))

    for scene, weight in zip(storyboard.scenes, weights):
        old_duration = max(0.1, scene.duration_estimate)
        duration = old_duration + remaining * (weight / weight_total)
        ratio = duration / old_duration
        scene.duration_estimate = round(duration, 1)
        for beat in scene.visual_beats:
            beat.duration_estimate = round(max(1.0, beat.duration_estimate * ratio), 1)
        for animation in scene.animations:
            animation.duration = round(min(15.0, max(0.5, animation.duration * ratio)), 1)

    rounded_total = round(sum(scene.duration_estimate for scene in storyboard.scenes), 1)
    delta = round(target - rounded_total, 1)
    if storyboard.scenes and abs(delta) >= 0.1:
        storyboard.scenes[-1].duration_estimate = round(max(1.0, storyboard.scenes[-1].duration_estimate + delta), 1)
        old_total_without_last = sum(scene.duration_estimate for scene in storyboard.scenes[:-1])
        last = storyboard.scenes[-1]
        last.duration_estimate = round(max(_scene_floor_duration(last, target_scene_seconds), target - old_total_without_last), 1)
    storyboard.total_duration_estimate = round(sum(scene.duration_estimate for scene in storyboard.scenes), 1)
    return storyboard


def _max_scene_count_for_target(target_duration: int) -> int:
    return max(3, min(7, math.ceil(max(60, target_duration) / 22)))


