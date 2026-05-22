import re
import math
from .scene_builder_base import FallbackSceneBuilder
from .geometry import _point, _line_points, _curve_points, _circle_points, _short_text, _text_visual_width
from .scene_info import _contains_any
from ..storyboard_gen.normalizer import _clean_text


def fallback_label(self, index: int, value: str) -> str:
    pool = self.steps or self.core_lines
    return _short_text(pool[index], 16) if index < len(pool) else value

def annotation_label(self, annotation_type: str, fallback: str, index: int = 0) -> str:
    matches = [
        _short_text(getattr(item, "label", ""), 12)
        for item in self.annotation_plan
        if _clean_text(getattr(item, "type", "")) == annotation_type and _clean_text(getattr(item, "label", ""))
    ]
    return matches[index] if index < len(matches) else fallback

def annotation_items(self, limit: int = 5) -> list[tuple[str, str, str | None]]:
    items: list[tuple[str, str, str | None]] = []
    for item in self.annotation_plan:
        label = _short_text(getattr(item, "label", ""), 12)
        annotation_type = _clean_text(getattr(item, "type", "")) or "side_label"
        beat_id = _clean_text(getattr(item, "beat_id", "") or "beat_0")
        if label and label not in [existing[1] for existing in items]:
            items.append((annotation_type, label, beat_id))
        if len(items) >= limit:
            break
    return items

def draw_check_mark(
    self,
    cx: float,
    cy: float,
    color: str,
    start: int,
    frames: int = 10,
    scale: float = 1.0,
    beat_id: str | None = None,
) -> int:
    self.add_stroke(
        "annotation_checkmark",
        [
            _point(cx - self.width * 0.020 * scale, cy),
            _point(cx - self.width * 0.006 * scale, cy + self.height * 0.020 * scale),
            _point(cx + self.width * 0.034 * scale, cy - self.height * 0.028 * scale),
        ],
        color,
        max(4, round(5 * scale)),
        start,
        frames,
        beat_id=beat_id,
    )
    return start + frames + 3

def draw_cross_mark(
    self,
    cx: float,
    cy: float,
    color: str,
    start: int,
    frames: int = 10,
    scale: float = 1.0,
    beat_id: str | None = None,
) -> int:
    self.add_stroke(
        "annotation_crossout",
        _line_points(cx - self.width * 0.026 * scale, cy - self.height * 0.030 * scale, cx + self.width * 0.026 * scale, cy + self.height * 0.030 * scale, count=4),
        color,
        max(4, round(5 * scale)),
        start,
        max(5, frames // 2),
        beat_id=beat_id,
    )
    self.add_stroke(
        "annotation_crossout",
        _line_points(cx + self.width * 0.026 * scale, cy - self.height * 0.030 * scale, cx - self.width * 0.026 * scale, cy + self.height * 0.030 * scale, count=4),
        color,
        max(4, round(5 * scale)),
        start + max(4, frames // 2),
        max(5, frames // 2),
        beat_id=beat_id,
    )
    return start + frames + 3

def draw_wavy_underline(
    self,
    x: float,
    y: float,
    w: float,
    color: str,
    start: int,
    frames: int = 12,
    beat_id: str | None = None,
) -> int:
    self.add_stroke(
        "annotation_wavy_underline",
        _curve_points(x, y, x + w, y, count=12, wave=self.height * 0.007),
        color,
        5,
        start,
        frames,
        beat_id=beat_id,
    )
    return start + frames + 3

def draw_risk_rays(
    self,
    x: float,
    y: float,
    color: str,
    start: int,
    direction: int = 1,
    beat_id: str | None = None,
) -> int:
    for ray_index, offset in enumerate([-0.035, 0.0, 0.035]):
        self.add_stroke(
            "annotation_risk_ray",
            _line_points(
                x,
                y + self.height * offset,
                x + direction * self.width * 0.050,
                y + self.height * (offset - 0.030),
                count=3,
            ),
            color,
            4,
            start + ray_index * 4,
            6,
            beat_id=beat_id,
        )
    return start + 17

def semantic_annotation_color(self, annotation_type: str, label: str, default: str | None = None) -> str:
    if default is None:
        default = self.blue
    annotation_type = _clean_text(annotation_type).lower()
    label_text = _clean_text(label).lower()
    if annotation_type in {"risk_ray", "crossout"} or _contains_any(
        label_text,
        ["风险", "禁止", "停止", "停", "断", "缺", "错", "不可", "邻线", "危险", "超界"],
    ):
        return self.red
    if annotation_type in {"checkmark", "route_trace"} or _contains_any(
        label_text,
        ["齐全", "确认", "许可", "安全", "上道", "闭环", "复核", "通过", "正确"],
    ):
        return self.green
    if annotation_type in {"wavy_underline", "edge_tick"} or _contains_any(label_text, ["重点", "边界", "铁律", "命令"]):
        return self.blue
    return default

def add_step_badge(
    self,
    label: str,
    cx: float,
    cy: float,
    color: str,
    start: int,
    beat_id: str | None = None,
) -> int:
    self.add_stroke("teacher_step_badge", _circle_points(cx, cy, self.width * 0.018, self.height * 0.026, count=12), color, 3, start, 8, beat_id=beat_id)
    self.add_text(label, cx - self.width * 0.006, cy - self.height * 0.020, max(16, self.body_size - 12), color, start + 5, 10, self.width * 0.035, max_chars=1, beat_id=beat_id)
    return start + 17

def add_teacher_takeaway(
    self,
    label: str,
    x: float,
    y: float,
    color: str,
    start: int,
    beat_id: str | None = None,
    max_chars: int = 9,
) -> int:
    safe_label = _short_text(label, max_chars)
    marker_x = max(self.width * 0.040, x - self.width * 0.030)
    marker_y = y + self.body_size * 0.45
    self.draw_star(marker_x, marker_y, self.width * 0.014, self.yellow, start, 10, beat_id=beat_id)
    self.add_text(
        safe_label,
        x,
        y,
        max(24, self.body_size - 2),
        color,
        start + 8,
        22,
        self.width * 0.22,
        emphasis=True,
        max_chars=max_chars,
        beat_id=beat_id,
    )
    return start + 36

def direct_callout_labels(self) -> list[str]:
    labels: list[str] = []
    for item in self.annotation_plan:
        short = _short_text(getattr(item, "label", ""), 14)
        if short and short not in labels:
            labels.append(short)
        if len(labels) >= 5:
            break
    for beat in getattr(self.scene, "visual_beats", []) or []:
        for label in beat.required_labels or []:
            short = _short_text(label, 14)
            if short and short not in labels:
                labels.append(short)
        if len(labels) >= 4:
            break
    for step in self.steps:
        short = _short_text(step, 14)
        if short and short not in labels:
            labels.append(short)
        if len(labels) >= 4:
            break
    defaults = ["关键结构", "控制关系", "变化路径", "重点结论"]
    for default in defaults:
        if len(labels) >= 4:
            break
        labels.append(default)
    return labels[:4]

def title_x_for_text(self, text: str, font_size: int, max_chars: int = 24) -> float:
    safe_text = _short_text(text, max_chars)
    estimated = min(self.width * 0.78, max(font_size * 2.4, _text_visual_width(safe_text, font_size) * 0.84))
    return max(self.width * 0.06, (self.width - estimated) * 0.5)

def add_process_doodles(self, start: int, x: float, y: float) -> int:
    cursor = start
    route = _curve_points(x, y + 20, x + 118, y - 18, count=14, wave=self.height * 0.030)
    self.add_arrow(route, self.blue, 3, cursor, 16, role="route_doodle")
    cursor += 18
    marker_specs = [
        (route[0], self.green, "\u8d77\u70b9"),
        (route[len(route) // 2], self.violet, "\u8c03\u6574"),
        (route[-1], self.red, "\u7ed3\u8bba"),
    ]
    for point, color, label in marker_specs:
        self.add_stroke("route_marker", _circle_points(point["x"], point["y"], self.width * 0.010, self.height * 0.016, count=10), color, 3, cursor, 6)
        cursor += 7
        self.add_text(label, point["x"] - self.width * 0.018, point["y"] + self.height * 0.022, max(15, self.body_size - 12), color, cursor, 10, self.width * 0.08, emphasis=False, max_chars=4)
        cursor += 11
    for index in range(3):
        ray_x = x + 132 + index * 16
        self.add_stroke("spark", _line_points(ray_x, y - 38, ray_x + 8, y - 54 - index * 2, count=3), self.yellow, 3, cursor, 5)
        cursor += 6
    return cursor



FallbackSceneBuilder.fallback_label = fallback_label
FallbackSceneBuilder.annotation_label = annotation_label
FallbackSceneBuilder.annotation_items = annotation_items
FallbackSceneBuilder.draw_check_mark = draw_check_mark
FallbackSceneBuilder.draw_cross_mark = draw_cross_mark
FallbackSceneBuilder.draw_wavy_underline = draw_wavy_underline
FallbackSceneBuilder.draw_risk_rays = draw_risk_rays
FallbackSceneBuilder.semantic_annotation_color = semantic_annotation_color
FallbackSceneBuilder.add_step_badge = add_step_badge
FallbackSceneBuilder.add_teacher_takeaway = add_teacher_takeaway
FallbackSceneBuilder.direct_callout_labels = direct_callout_labels
FallbackSceneBuilder.title_x_for_text = title_x_for_text
FallbackSceneBuilder.add_process_doodles = add_process_doodles
