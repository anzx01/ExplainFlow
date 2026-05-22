import math
import re

from .scene_builder_base import FallbackSceneBuilder
from .geometry import (
    _short_text,
    _text_visual_width,
    _point,
    _text_stroke_points,
    _curve_points,
    _rect_points,
    _circle_points,
    _line_points,
    _polyline_length,
    _path_from_points,
)
from .scene_info import _contains_any

_EMPHASIS_TERMS = [
    "V_G", "V_th", "V_DS", "I_D", "W_eff", "MOS", "FinFET",
    "Gate", "Source", "Drain", "Channel", "Loss", "gradient", "learning rate",
    "阈值", "沟道", "短沟道", "电流", "栅极", "学习率", "梯度", "损失",
]


def _add_text(
    self,
    text: str,
    x: float,
    y: float,
    font_size: int,
    color: str,
    start: int,
    frames: int,
    max_width: float | None = None,
    emphasis: bool | None = None,
    max_chars: int = 38,
    beat_id: str | None = None,
) -> None:
    op_id = f"s{self.scene_index}_text_{len(self.texts)}"
    safe_text = _short_text(text, max_chars)
    text_max_width = max_width if max_width is not None else self.width - x - 70
    text_max_width = max(font_size * 1.2, min(float(text_max_width), self.width * 0.88))
    safe_x, safe_y, text_box = self.resolve_text_position(safe_text, x, y, font_size, text_max_width, max_chars)
    self.text_boxes.append(text_box)
    safe_start, end = self.fit_timing(start, frames)
    draw_op: dict = {
        "id": op_id,
        "kind": "text",
        "startFrame": safe_start,
        "endFrame": end,
        "points": _text_stroke_points(safe_text, safe_x, safe_y, font_size, text_max_width),
    }
    if beat_id:
        draw_op["beatId"] = beat_id
    self.draw_ops.append(draw_op)
    has_cjk = bool(re.search(r"[㐀-鿿]", safe_text))
    has_many_latin = len(re.findall(r"[A-Za-z0-9]", safe_text)) >= 3
    marker_width = max(2.2, min(5.2, font_size * (0.052 if font_size >= 54 else 0.066)))
    if has_many_latin and not has_cjk:
        marker_width = max(2.0, min(4.2, font_size * 0.044))
    elif has_many_latin:
        marker_width = max(2.4, marker_width * 0.78)
    self.texts.append({
        "opId": op_id,
        "text": safe_text,
        "x": round(safe_x, 1),
        "y": round(safe_y, 1),
        "fontSize": font_size,
        "color": color,
        "maxWidth": round(text_max_width, 1),
        "markerStrokeWidth": round(marker_width, 1),
        "markerFillOpacity": (0.48 if has_many_latin else 0.74) if font_size >= 54 else (0.56 if has_many_latin else 0.86),
    })
    should_emphasize = (
        emphasis if emphasis is not None
        else len(safe_text) <= 28 and _contains_any(safe_text.lower(), [t.lower() for t in _EMPHASIS_TERMS])
    )
    if should_emphasize:
        estimated_width = min(
            text_max_width,
            max(font_size * 1.6, len(safe_text) * font_size * (0.72 if re.search(r"[㐀-鿿]", safe_text) else 0.48)),
        )
        underline_y = safe_y + font_size * 1.05
        self.add_stroke(
            "emphasis_underline",
            _curve_points(safe_x, underline_y, safe_x + estimated_width, underline_y, count=10, wave=max(2.0, font_size * 0.035)),
            self.yellow,
            max(3, round(font_size * 0.075)),
            end + 1,
            8,
            beat_id=beat_id,
        )


def _add_stroke(
    self,
    role: str,
    points: list[dict[str, float]],
    color: str,
    stroke_width: int,
    start: int,
    frames: int,
    close: bool = False,
    beat_id: str | None = None,
) -> None:
    op_id = f"s{self.scene_index}_stroke_{len(self.strokes)}"
    safe_start, end = self.fit_timing(start, frames)
    draw_op: dict = {
        "id": op_id,
        "kind": "path",
        "startFrame": safe_start,
        "endFrame": end,
        "points": points,
    }
    if beat_id:
        draw_op["beatId"] = beat_id
    self.draw_ops.append(draw_op)
    self.strokes.append({
        "opId": op_id,
        "role": role,
        "d": _path_from_points(points, close=close),
        "color": color,
        "strokeWidth": stroke_width,
        "dashLength": round(_polyline_length(points, close=close), 1),
    })


def _add_arrow(
    self,
    points: list[dict[str, float]],
    color: str,
    stroke_width: int,
    start: int,
    frames: int,
    role: str = "arrow",
    beat_id: str | None = None,
) -> None:
    self.add_stroke(role, points, color, stroke_width, start, frames, beat_id=beat_id)
    if len(points) < 2:
        return
    end = points[-1]
    prev = points[-2]
    angle = math.atan2(end["y"] - prev["y"], end["x"] - prev["x"])
    head_len = max(16.0, min(self.width, self.height) * 0.028)
    head_start = start + max(4, frames - 10)
    for sign in (-1, 1):
        theta = angle + math.pi + sign * 0.48
        side = _point(end["x"] + math.cos(theta) * head_len, end["y"] + math.sin(theta) * head_len)
        self.add_stroke("arrowhead", [side, _point(end["x"], end["y"])], color, stroke_width, head_start, 7, beat_id=beat_id)


def _add_node_box(
    self,
    label: str,
    x: float,
    y: float,
    w: float,
    h: float,
    start: int,
    color: str | None = None,
    role: str = "node",
    font_size: int | None = None,
    beat_id: str | None = None,
) -> int:
    c = color if color is not None else self.ink
    self.add_stroke(role, _rect_points(x, y, w, h), c, 4, start, 18, close=True, beat_id=beat_id)
    self.add_text(label, x + w * 0.14, y + h * 0.25, font_size or self.body_size, c, start + 12, 22, w * 0.78, beat_id=beat_id)
    return start + 36


def _add_node_circle(
    self,
    label: str,
    cx: float,
    cy: float,
    rx: float,
    ry: float,
    start: int,
    color: str | None = None,
    role: str = "node",
    font_size: int | None = None,
    beat_id: str | None = None,
) -> int:
    c = color if color is not None else self.ink
    self.add_stroke(role, _circle_points(cx, cy, rx, ry, count=24), c, 4, start, 18, beat_id=beat_id)
    self.add_text(label, cx - rx * 0.55, cy - ry * 0.28, font_size or self.body_size, c, start + 12, 22, rx * 1.1, beat_id=beat_id)
    return start + 36


def _draw_star(self, cx: float, cy: float, radius: float, color: str, start: int, frames: int, beat_id: str | None = None) -> int:
    points: list[dict[str, float]] = []
    for index in range(11):
        angle = -math.pi / 2 + index * math.pi / 5
        local_radius = radius if index % 2 == 0 else radius * 0.42
        points.append(_point(cx + math.cos(angle) * local_radius, cy + math.sin(angle) * local_radius))
    self.add_stroke("star", points, color, 4, start, frames, close=True, beat_id=beat_id)
    return start + frames + 3


def _draw_person_icon(self, cx: float, cy: float, color: str, start: int, scale: float = 1.0, beat_id: str | None = None) -> int:
    local = start
    self.add_stroke("person", _circle_points(cx, cy, self.width * 0.018 * scale, self.height * 0.028 * scale, count=14), color, 3, local, 7, beat_id=beat_id)
    local += 8
    self.add_stroke("person", _line_points(cx, cy + self.height * 0.030 * scale, cx, cy + self.height * 0.095 * scale, count=4), color, 3, local, 6, beat_id=beat_id)
    self.add_stroke("person", _line_points(cx - self.width * 0.030 * scale, cy + self.height * 0.055 * scale, cx + self.width * 0.030 * scale, cy + self.height * 0.055 * scale, count=4), color, 3, local + 4, 6, beat_id=beat_id)
    self.add_stroke("person", _line_points(cx, cy + self.height * 0.095 * scale, cx - self.width * 0.026 * scale, cy + self.height * 0.145 * scale, count=4), color, 3, local + 8, 6, beat_id=beat_id)
    self.add_stroke("person", _line_points(cx, cy + self.height * 0.095 * scale, cx + self.width * 0.026 * scale, cy + self.height * 0.145 * scale, count=4), color, 3, local + 12, 6, beat_id=beat_id)
    return local + 20


FallbackSceneBuilder.add_text = _add_text
FallbackSceneBuilder.add_stroke = _add_stroke
FallbackSceneBuilder.add_arrow = _add_arrow
FallbackSceneBuilder.add_node_box = _add_node_box
FallbackSceneBuilder.add_node_circle = _add_node_circle
FallbackSceneBuilder.draw_star = _draw_star
FallbackSceneBuilder.draw_person_icon = _draw_person_icon
