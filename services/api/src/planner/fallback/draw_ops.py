import math
import re

from ..models import Scene
from .geometry import _polyline_length
from ..storyboard_gen.normalizer import _clean_text


def _draw_op_group_key(op: dict, index: int) -> str:
    pair_id = op.get("pairedOpId")
    if not pair_id:
        return f"op:{index}"
    return f"pair:{min(str(op.get('id') or ''), str(pair_id))}"


def _retime_draw_ops_in_window(
    draw_ops: list[dict],
    start_frame: float,
    end_frame: float,
    beat_id: str | None = None,
) -> None:
    if not draw_ops:
        return
    grouped: dict[str, list[tuple[int, dict]]] = {}
    for index, op in enumerate(draw_ops):
        grouped.setdefault(_draw_op_group_key(op, index), []).append((index, op))
    ordered = sorted(
        grouped.values(),
        # Keep ink/color pairs atomic so retiming cannot make the fill lag the pen.
        key=lambda group: (
            min(float(op.get("startFrame", 0)) for _, op in group),
            0 if any(op.get("kind") == "path" for _, op in group) else 1,
            min(index for index, _ in group),
        ),
    )
    spans = [
        max(0.5, max(float(op.get("endFrame", 0)) - float(op.get("startFrame", 0)) for _, op in group))
        for group in ordered
    ]
    target_end = max(start_frame + 1.0, end_frame)
    target_span = max(1.0, target_end - start_frame)
    default_gap = 0.35 if len(ordered) > 80 else 0.65
    gap = min(default_gap, target_span * 0.18 / max(1, len(ordered) - 1))
    available = max(1.0, target_span - gap * max(0, len(ordered) - 1))
    min_span = min(1.0, max(0.08, available / max(1, len(ordered)) * 0.8))
    scale = available / max(1.0, sum(spans))
    cursor = start_frame
    for index, (group, span) in enumerate(zip(ordered, spans)):
        safe_start = min(cursor, max(start_frame, target_end - min_span))
        next_end = target_end if index == len(ordered) - 1 else min(target_end, safe_start + max(min_span, span * scale))
        op_start = round(safe_start, 2)
        op_end = round(max(safe_start + min_span, next_end), 2)
        for _, op in group:
            op["startFrame"] = op_start
            op["endFrame"] = op_end
            if len(group) == 2 and op.get("phase") in {"ink", "color"}:
                split = round(op_start + (op_end - op_start) * 0.7, 2)
                if op["phase"] == "ink":
                    op["endFrame"] = split
                else:
                    op["startFrame"] = split
            if beat_id:
                op["beatId"] = beat_id
        cursor = op_end + gap


def _retime_draw_ops_to_fill_scene(draw_ops: list[dict], duration: int) -> None:
    _retime_draw_ops_in_window(draw_ops, 0.0, max(1.0, duration - 4.0))


def _retime_draw_ops_to_subtitle_cues(draw_ops: list[dict], subtitle_cues: list[dict], duration: int) -> bool:
    """Retime explicitly bound drawings, never infer meaning from path count."""
    cues = [
        cue for cue in subtitle_cues
        if isinstance(cue, dict)
        and float(cue.get("endFrame", 0) or 0) > float(cue.get("startFrame", 0) or 0)
    ]
    if not draw_ops or not cues:
        return False

    if any(not any(op.get("beatId") == f"cue_{index}" for op in draw_ops) for index in range(len(cues))):
        return False
    if any(op.get("beatId") not in {f"cue_{index}" for index in range(len(cues))} for op in draw_ops):
        return False
    for cue_index, cue in enumerate(cues):
        bucket = [op for op in draw_ops if op.get("beatId") == f"cue_{cue_index}"]
        start = max(0.0, float(cue.get("startFrame", 0) or 0))
        end = min(float(duration), float(cue.get("endFrame", duration) or duration))
        _retime_draw_ops_in_window(bucket, start, max(start + 1.0, end), f"cue_{cue_index}")
    return True


def _audio_segment_groups_for_draw_ops(draw_ops: list[dict], segments: list[dict]) -> list[list[dict]]:
    grouped: dict[str, list[tuple[int, dict]]] = {}
    for index, op in enumerate(draw_ops):
        grouped.setdefault(_draw_op_group_key(op, index), []).append((index, op))
    ordered_groups = sorted(
        grouped.values(),
        key=lambda group: (
            min(float(op.get("startFrame", 0)) for _, op in group),
            0 if any(op.get("kind") == "path" for _, op in group) else 1,
            min(index for index, _ in group),
        ),
    )
    buckets: list[list[list[dict]]] = [[] for _ in segments]
    segment_index_by_id = {
        str(segment.get("id") or f"beat_{index}"): index
        for index, segment in enumerate(segments)
    }
    unassigned: list[list[dict]] = []
    for group in ordered_groups:
        ops = [op for _, op in group]
        existing_beat_id = next((str(op.get("beatId") or "") for op in ops if op.get("beatId")), "")
        segment_index = segment_index_by_id.get(existing_beat_id)
        if segment_index is None:
            unassigned.append(ops)
        else:
            buckets[segment_index].append(ops)

    weights = [max(1.0, float(segment.get("drawBudgetFrames") or segment.get("duration") or 1)) for segment in segments]
    total_weight = sum(weights) or float(len(segments))
    cursor = 0
    for index in range(len(segments)):
        remaining_ops = len(unassigned) - cursor
        remaining_segments = len(segments) - index
        if remaining_ops <= 0:
            break
        if index == len(segments) - 1:
            take = remaining_ops
        else:
            target = round(len(unassigned) * (weights[index] / total_weight))
            take = max(1, min(remaining_ops - (remaining_segments - 1), target))
        group = unassigned[cursor : cursor + take]
        cursor += take
        buckets[index].extend(group)

    if cursor < len(unassigned):
        buckets[-1].extend(unassigned[cursor:])

    return [[op for group in bucket for op in group] for bucket in buckets]


def _draw_op_workload_frames(op: dict, text_by_op_id: dict[str, dict], fps: int) -> float:
    start = float(op.get("startFrame", 0) or 0)
    end = float(op.get("endFrame", start + 1) or (start + 1))
    span = max(1.0, end - start)
    if op.get("kind") == "text":
        text_spec = text_by_op_id.get(str(op.get("id") or "")) or {}
        raw_text = _clean_text(text_spec.get("text") or "")
        compact_text = re.sub(r"\s+", "", raw_text)
        char_count = max(1, len(compact_text))
        cjk_count = len(re.findall(r"[\u3400-\u9fff]", compact_text))
        font_size = float(text_spec.get("fontSize") or 32)
        per_char = 4.8 if font_size < 40 else 5.7
        if cjk_count >= max(1, char_count // 2):
            per_char += 0.8
        if font_size >= 54:
            per_char += 0.7
        return max(18.0, min(float(fps) * 3.0, 10.0 + char_count * per_char + font_size * 0.08))

    raw_points = op.get("points")
    points = raw_points if isinstance(raw_points, list) else []
    length = _polyline_length(points) if points else span * 10.0
    return max(5.0, min(float(fps), max(span * 0.62, 4.0 + length / 95.0)))


def _stretch_audio_segments_for_draw_workload(
    draw_ops: list[dict],
    texts: list[dict],
    audio_segments: list[dict],
    duration: int,
    fps: int,
) -> int:
    if not draw_ops or not audio_segments:
        return duration
    segments = [
        segment
        for segment in audio_segments
        if isinstance(segment, dict)
        and float(segment.get("endFrame", 0) or 0) > float(segment.get("startFrame", 0) or 0)
    ]
    if not segments:
        return duration

    text_by_op_id = {
        str(text.get("opId")): text
        for text in texts
        if isinstance(text, dict) and text.get("opId")
    }
    groups = _audio_segment_groups_for_draw_ops(draw_ops, segments)
    cursor = 0
    for index, (segment, group) in enumerate(zip(segments, groups)):
        original_start = float(segment.get("startFrame", 0) or 0)
        original_end = float(segment.get("endFrame", original_start + 1) or (original_start + 1))
        original_duration = max(1, int(round(original_end - original_start)))
        audio_duration = max(1, int(round(float(segment.get("audioDurationFrames") or segment.get("audioSequenceDuration") or original_duration))))
        workload = sum(_draw_op_workload_frames(op, text_by_op_id, fps) for op in group)
        workload_target = int(math.ceil(workload + (fps * 0.35 if group else 0)))
        audio_target = int(math.ceil(audio_duration + fps * (0.70 if index == len(segments) - 1 else 0.45)))
        expansion_cap = int(
            math.ceil(
                max(original_duration, audio_duration)
                + fps * (2.4 if workload > audio_duration else 1.2)
                + min(fps * 1.4, len(group) * 1.1)
            )
        )
        target_duration = max(original_duration, audio_target, min(workload_target, expansion_cap))
        segment["startFrame"] = cursor
        segment["endFrame"] = cursor + target_duration
        segment["duration"] = target_duration
        segment["audioStartFrame"] = cursor
        segment["audioEndFrame"] = cursor + audio_duration
        segment["audioSequenceDuration"] = audio_duration
        segment["drawBudgetFrames"] = max(1, target_duration - 6)
        cursor += target_duration

    final_hold = max(18, int(round(fps * 0.65)))
    return max(duration, cursor + final_hold)


def _retime_draw_ops_to_audio_segments(draw_ops: list[dict], audio_segments: list[dict], duration: int) -> None:
    if not draw_ops:
        return
    segments = [
        segment
        for segment in audio_segments
        if isinstance(segment, dict)
        and float(segment.get("endFrame", 0) or 0) > float(segment.get("startFrame", 0) or 0)
    ]
    if not segments:
        _retime_draw_ops_to_fill_scene(draw_ops, duration)
        return
    buckets = _audio_segment_groups_for_draw_ops(draw_ops, segments)

    for index, segment in enumerate(segments):
        group = buckets[index]
        if not group:
            continue
        start = float(segment.get("startFrame", 0) or 0)
        end = float(segment.get("endFrame", duration) or duration)
        audio_start = float(segment.get("audioStartFrame", start) or start)
        audio_end = float(segment.get("audioEndFrame", end) or end)
        # Spoken beats and their drawing must share one window: no narration
        # over a static board, and no pre-drawn explanation.
        window_start = max(0.0, start, audio_start)
        window_end = min(audio_end, max(1.0, duration - 1.0))
        window_end = max(window_start + 1.0, window_end)
        _retime_draw_ops_in_window(group, window_start, window_end, str(segment.get("id") or f"beat_{index}"))



