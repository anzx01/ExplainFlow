import math
from .scene_builder_base import FallbackSceneBuilder
from .geometry import _point, _line_points, _curve_points, _polyline_length


def build_reference_trace(self, start: int) -> int:
    trace_x = self.width * 0.22
    trace_y = self.diagram_top + self.height * 0.045
    trace_w = self.width * 0.56
    trace_h = self.height * 0.48
    cursor = start
    drawn = 0
    for raw_path in self.trace_strokes[:80]:
        if not isinstance(raw_path, list) or len(raw_path) < 2:
            continue
        points: list[dict[str, float]] = []
        for raw_point in raw_path:
            if not isinstance(raw_point, dict):
                continue
            px = raw_point.get("x")
            py = raw_point.get("y")
            if not isinstance(px, (int, float)) or not isinstance(py, (int, float)):
                continue
            points.append(_point(trace_x + max(0.0, min(1.0, float(px))) * trace_w, trace_y + max(0.0, min(1.0, float(py))) * trace_h))
        if len(points) < 2:
            continue
        frames = max(7, min(22, round(_polyline_length(points) / max(18.0, self.width * 0.018))))
        self.add_stroke("reference_trace", points, self.ink, 4, cursor, frames)
        cursor += frames + 3
        drawn += 1
        if cursor > self.duration * 0.66:
            break
    if drawn == 0:
        return builders.get(self.diagram_kind, self.build_process_flow)(start)

    label = self.fallback_label(0, "Reference sketch")
    arrow_start = min(cursor, self.duration - 64)
    self.add_arrow(
        _curve_points(trace_x - self.width * 0.06, trace_y + trace_h * 0.44, trace_x + trace_w * 0.34, trace_y + trace_h * 0.46, count=16, wave=self.height * 0.025),
        self.blue,
        4,
        arrow_start,
        18,
    )
    self.add_text(label, trace_x - self.width * 0.145, trace_y + trace_h * 0.36, self.body_size, self.blue, arrow_start + 12, 28, self.width * 0.16, max_chars=14)
    cursor = arrow_start + 46
    for tick in range(5):
        self.add_stroke(
            "doodle",
            _line_points(
                trace_x + trace_w + 24 + tick * 16,
                trace_y + 22 + (tick % 2) * 20,
                trace_x + trace_w + 34 + tick * 16,
                trace_y + 6 + (tick % 2) * 20,
                count=3,
            ),
            self.red,
            3,
            cursor,
            5,
        )
        cursor += 6
    return cursor


def build_process_flow(self, start: int) -> int:
    y = self.diagram_top + self.height * 0.17
    box_w = self.width * 0.15
    box_h = self.height * 0.13
    gap = self.width * 0.055
    total_w = box_w * 3 + gap * 2
    x1 = self.board_center_x - total_w * 0.5
    x2 = x1 + box_w + gap
    x3 = x2 + box_w + gap
    cursor = start
    cursor = self.add_node_box(self.fallback_label(0, "Input"), x1, y, box_w, box_h, cursor, self.blue)
    self.add_arrow(_line_points(x1 + box_w + 6, y + box_h * 0.5, x2 - 16, y + box_h * 0.5, count=8), self.ink, 4, cursor, 16)
    cursor += 25
    cursor = self.add_node_box(self.fallback_label(1, "Process"), x2, y - self.height * 0.03, box_w, box_h, cursor, self.ink)
    self.add_arrow(_line_points(x2 + box_w + 6, y + box_h * 0.5, x3 - 16, y + box_h * 0.5, count=8), self.ink, 4, cursor, 16)
    cursor += 25
    cursor = self.add_node_box(self.fallback_label(2, "Output"), x3, y, box_w, box_h, cursor, self.green)
    if len(self.steps) > 3:
        self.add_stroke("note", _line_points(x2 + box_w * 0.5, y + box_h + 10, x2 + box_w * 0.5, y + box_h + self.height * 0.08), self.violet, 3, cursor, 9)
        self.add_text(self.fallback_label(3, "Key change"), x2 - box_w * 0.14, y + box_h + self.height * 0.09, self.body_size, self.violet, cursor + 8, 22, box_w * 1.35)
        cursor += 32
    return self.add_process_doodles(cursor, x3 + box_w * 0.30, y + box_h + self.height * 0.08)



FallbackSceneBuilder.build_reference_trace = build_reference_trace
FallbackSceneBuilder.build_process_flow = build_process_flow
