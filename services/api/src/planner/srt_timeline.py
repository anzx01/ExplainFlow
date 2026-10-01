"""Deterministic SRT parsing and scene grouping for storyboard planning."""
from __future__ import annotations

import re
from dataclasses import dataclass


_TIME = re.compile(r"(?P<h>\d+):(?P<m>\d{2}):(?P<s>\d{2})[,.](?P<ms>\d{1,3})")


@dataclass(frozen=True)
class SrtCue:
    index: int
    start_ms: int
    end_ms: int
    text: str

    @property
    def duration_ms(self) -> int:
        return self.end_ms - self.start_ms


class SrtParseError(ValueError):
    def __init__(self, message: str, *, block: int | None = None):
        self.block = block
        super().__init__(message if block is None else f"block {block}: {message}")


def _to_ms(match: re.Match[str]) -> int:
    parts = {key: int(value) for key, value in match.groupdict().items()}
    return ((parts["h"] * 60 + parts["m"]) * 60 + parts["s"]) * 1000 + parts["ms"] * (10 ** (3 - len(match.group("ms"))))


def parse_srt(text: str) -> list[SrtCue]:
    if not isinstance(text, str) or not text.strip():
        raise SrtParseError("SRT text is empty")
    normalized = text.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
    cues: list[SrtCue] = []
    for block_number, raw_block in enumerate(re.split(r"\n\s*\n", normalized.strip()), 1):
        lines = [line.strip() for line in raw_block.split("\n")]
        if not any(line for line in lines):
            continue
        time_index = next((i for i, line in enumerate(lines) if "-->" in line), None)
        if time_index is None:
            raise SrtParseError("missing time range", block=block_number)
        times = _TIME.findall(lines[time_index])
        if len(times) < 2:
            raise SrtParseError("invalid time range", block=block_number)
        matches = list(_TIME.finditer(lines[time_index]))
        start_ms, end_ms = _to_ms(matches[0]), _to_ms(matches[1])
        if end_ms <= start_ms:
            raise SrtParseError("end time must be after start time", block=block_number)
        body = " ".join(line for line in lines[time_index + 1 :] if line).strip()
        if not body:
            raise SrtParseError("subtitle text is empty", block=block_number)
        cues.append(SrtCue(len(cues) + 1, start_ms, end_ms, body))
    if not cues:
        raise SrtParseError("no subtitle cues found")
    for previous, current in zip(cues, cues[1:]):
        if current.start_ms < previous.start_ms:
            raise SrtParseError(f"cue {current.index} starts before cue {previous.index}")
    return cues


def group_scenes(
    cues: list[SrtCue],
    *,
    target_sec: float = 30.0,
    min_sec: float = 25.0,
    max_sec: float = 35.0,
) -> list[dict]:
    if not cues:
        return []
    if not (0 < min_sec <= target_sec <= max_sec):
        raise ValueError("scene duration must satisfy 0 < min_sec <= target_sec <= max_sec")
    target_ms, min_ms, max_ms = target_sec * 1000, min_sec * 1000, max_sec * 1000
    scenes: list[dict] = []
    bucket: list[SrtCue] = []

    def flush() -> None:
        if not bucket:
            return
        start_ms, end_ms = bucket[0].start_ms, bucket[-1].end_ms
        scenes.append({
            "sceneIndex": len(scenes) + 1,
            "startMs": start_ms,
            "endMs": end_ms,
            "sceneDurationMs": end_ms - start_ms,
            "cueIds": [cue.index for cue in bucket],
            "cueRange": [bucket[0].index, bucket[-1].index],
            "text": " ".join(cue.text for cue in bucket),
        })
        bucket.clear()

    for cue in cues:
        if bucket and cue.end_ms - bucket[0].start_ms > max_ms:
            flush()
        bucket.append(cue)
        span = bucket[-1].end_ms - bucket[0].start_ms
        if span >= target_ms and span >= min_ms:
            flush()
    flush()
    return scenes


def build_srt_timeline(text: str, *, target_sec: float = 30.0, min_sec: float = 25.0, max_sec: float = 35.0) -> dict:
    cues = parse_srt(text)
    scenes = group_scenes(cues, target_sec=target_sec, min_sec=min_sec, max_sec=max_sec)
    return {
        "cues": [
            {"index": cue.index, "startMs": cue.start_ms, "endMs": cue.end_ms, "durMs": cue.duration_ms, "text": cue.text}
            for cue in cues
        ],
        "scenes": scenes,
        "totalDurationMs": max(cue.end_ms for cue in cues) - min(cue.start_ms for cue in cues),
    }
