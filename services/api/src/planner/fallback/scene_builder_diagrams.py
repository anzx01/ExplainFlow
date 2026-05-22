import re
import math
from .scene_builder_base import FallbackSceneBuilder
from .geometry import _point, _line_points, _curve_points, _rect_points, _circle_points, _arc_points, _diamond_points, _polyline_length, _path_from_points, _short_text
from ..coverage.corpus import _scene_corpus
from .scene_info import _contains_any


def build_comparison_transform(self, start: int) -> int:
    y = self.diagram_top + self.height * 0.16
    w = self.width * 0.19
    h = self.height * 0.18
    gap = self.width * 0.12
    left_x = self.board_center_x - (w * 2 + gap) * 0.5
    right_x = left_x + w + gap
    cursor = start
    cursor = self.add_node_box(self.fallback_label(0, "Before"), left_x, y, w, h, cursor, self.red)
    self.add_arrow(_curve_points(left_x + w + 8, y + h * 0.45, right_x - 20, y + h * 0.45, count=18, wave=self.height * 0.035), self.ink, 4, cursor, 22)
    self.add_text(self.fallback_label(2, "Change"), left_x + w + self.width * 0.035, y - self.height * 0.055, self.body_size, self.blue, cursor + 10, 24, self.width * 0.18)
    cursor += 34
    cursor = self.add_node_box(self.fallback_label(1, "After"), right_x, y, w, h, cursor, self.green)
    brace_x = right_x + w + self.width * 0.04
    self.add_stroke("change", _line_points(brace_x, y + 10, brace_x + 18, y + h * 0.5, count=5), self.violet, 4, cursor, 8)
    self.add_stroke("change", _line_points(brace_x + 18, y + h * 0.5, brace_x, y + h - 10, count=5), self.violet, 4, cursor + 7, 8)
    self.add_text(self.fallback_label(3, "Result"), brace_x + 28, y + h * 0.34, self.body_size, self.violet, cursor + 14, 22, self.width * 0.15)
    cursor += 42
    marks = [
        _line_points(left_x + 22, y - 26, left_x + 56, y - 10, count=4),
        _line_points(left_x + 60, y - 28, left_x + 25, y - 8, count=4),
        _line_points(right_x + w * 0.76, y - 24, right_x + w * 0.76, y - 4, count=3),
        _line_points(right_x + w * 0.68, y - 14, right_x + w * 0.84, y - 14, count=3),
        _curve_points(right_x + 12, y + h + 24, right_x + w - 8, y + h + 18, count=10, wave=self.height * 0.012),
    ]
    for points in marks:
        self.add_stroke("doodle", points, self.blue, 3, cursor, 7)
        cursor += 8
    return cursor

def build_formula_derivation(self, start: int) -> int:
    formulas = []
    for animation in self.scene.animations:
        raw_type = getattr(animation.type, "value", str(animation.type))
        if raw_type in {"write_formula", "formula_reveal"} and (animation.latex or animation.content):
            formulas.append(animation.latex or animation.content)
    formulas.extend(line for line in self.core_lines if line not in formulas)
    formulas = [_short_text(line, 30) for line in formulas if line][:3]
    while len(formulas) < 3:
        formulas.append(["Known", "Transform", "Conclusion"][len(formulas)])

    x = self.board_center_x - self.width * 0.22
    y = self.diagram_top + self.height * 0.08
    w = self.width * 0.44
    row_h = self.height * 0.115
    cursor = start
    for index, formula in enumerate(formulas[:3]):
        row_y = y + index * (row_h + self.height * 0.035)
        self.add_stroke("formula", _rect_points(x, row_y, w, row_h), [self.blue, self.violet, self.green][index % 3], 4, cursor, 16, close=True)
        self.add_text(formula, x + w * 0.06, row_y + row_h * 0.25, self.body_size, self.ink, cursor + 10, 28, w * 0.86)
        cursor += 38
        if index < 2:
            self.add_arrow(_line_points(x + w * 0.5, row_y + row_h + 6, x + w * 0.5, row_y + row_h + self.height * 0.035, count=5), self.ink, 4, cursor, 9)
            cursor += 16
    self.add_stroke("formula", _line_points(x - 26, y + 8, x - 42, y + row_h * 1.5, count=6), self.red, 4, cursor, 8)
    cursor += 8
    self.add_stroke("formula", _line_points(x - 42, y + row_h * 1.5, x - 26, y + row_h * 3.0, count=6), self.red, 4, cursor, 8)
    cursor += 10
    for tick in range(5):
        self.add_stroke(
            "doodle",
            _line_points(x + w + 38 + tick * 12, y + 20 + (tick % 2) * 18, x + w + 44 + tick * 12, y + 6 + (tick % 2) * 18, count=3),
            self.red,
            3,
            cursor,
            5,
        )
        cursor += 6
    return cursor

def build_optimization_curve(self, start: int) -> int:
    axis_x = self.board_center_x - self.width * 0.23
    axis_y = self.diagram_top + self.height * 0.44
    axis_w = self.width * 0.46
    axis_h = self.height * 0.30
    cursor = start
    self.add_arrow(_line_points(axis_x, axis_y, axis_x + axis_w, axis_y, count=8), self.ink, 4, cursor, 14, role="axis")
    cursor += 18
    self.add_arrow(_line_points(axis_x, axis_y, axis_x, axis_y - axis_h, count=8), self.ink, 4, cursor, 14, role="axis")
    cursor += 18
    self.add_text("theta", axis_x + axis_w * 0.88, axis_y + self.height * 0.025, self.body_size, self.ink, cursor, 16, self.width * 0.11)
    self.add_text("Loss", axis_x - self.width * 0.035, axis_y - axis_h - self.height * 0.055, self.body_size, self.ink, cursor + 8, 16, self.width * 0.12)
    cursor += 24

    curve = []
    for i in range(28):
        t = i / 27
        x = axis_x + axis_w * (0.08 + 0.84 * t)
        y = axis_y - axis_h * (0.88 * (1 - t) ** 2 + 0.12) + math.sin(t * math.pi * 3) * self.height * 0.01
        curve.append(_point(x, y))
    self.add_stroke("loss_curve", curve, self.blue, 5, cursor, 34)
    cursor += 38

    sample_indices = [3, 8, 14, 21]
    for prev_i, next_i in zip(sample_indices, sample_indices[1:]):
        p = curve[prev_i]
        q = curve[next_i]
        self.add_stroke("node", _circle_points(p["x"], p["y"], self.width * 0.012, self.height * 0.02, count=12), self.red, 4, cursor, 8)
        self.add_arrow(_line_points(p["x"] + 10, p["y"] + 8, q["x"] - 10, q["y"] + 5, count=6), self.red, 4, cursor + 7, 12)
        cursor += 23
    optimum = curve[-3]
    self.add_stroke("node", _circle_points(optimum["x"], optimum["y"], self.width * 0.013, self.height * 0.021, count=12), self.green, 4, cursor, 8)
    self.add_text(self.fallback_label(0, "Update"), axis_x + axis_w * 0.46, axis_y - axis_h * 0.82, self.body_size, self.violet, cursor + 8, 24, self.width * 0.22)
    cursor += 32
    flag_x = optimum["x"] + self.width * 0.035
    flag_y = optimum["y"] - self.height * 0.055
    self.add_stroke("doodle", _line_points(flag_x, flag_y, flag_x, flag_y + self.height * 0.09, count=5), self.green, 3, cursor, 8)
    cursor += 8
    self.add_stroke("doodle", [_point(flag_x, flag_y), _point(flag_x + self.width * 0.04, flag_y + self.height * 0.015), _point(flag_x, flag_y + self.height * 0.03)], self.green, 3, cursor, 8)
    cursor += 9
    for tick in range(3):
        self.add_stroke("doodle", _line_points(flag_x - 18 + tick * 22, flag_y + self.height * 0.11, flag_x - 8 + tick * 22, flag_y + self.height * 0.13, count=3), self.blue, 3, cursor, 5)
        cursor += 6
    return cursor

def build_attention_network(self, start: int) -> int:
    cursor = start
    x0 = self.board_center_x - self.width * 0.29
    y0 = self.diagram_top + self.height * 0.08
    token_gap = self.height * 0.105
    token_positions = [(x0, y0 + i * token_gap) for i in range(3)]
    qkv_x = x0 + self.width * 0.15
    mix_x = x0 + self.width * 0.34
    out_x = x0 + self.width * 0.49
    labels = ["Q", "K", "V"]
    for index, (x, y) in enumerate(token_positions):
        cursor = self.add_node_circle(f"T{index + 1}", x, y, self.width * 0.035, self.height * 0.045, cursor, self.blue, font_size=max(18, self.body_size - 5))
        qy = y
        cursor = self.add_node_box(labels[index], qkv_x, qy - self.height * 0.04, self.width * 0.08, self.height * 0.075, cursor, self.violet if index == 0 else self.ink, font_size=max(18, self.body_size - 4))
        self.add_arrow(_line_points(x + self.width * 0.04, y, qkv_x - 12, qy, count=5), self.ink, 3, cursor, 10)
        cursor += 14
    soft_y = y0 + token_gap
    cursor = self.add_node_circle("Softmax", mix_x, soft_y, self.width * 0.055, self.height * 0.06, cursor, self.red, font_size=max(16, self.body_size - 8))
    for qy in [pos[1] for pos in token_positions]:
        self.add_arrow(_line_points(qkv_x + self.width * 0.085, qy, mix_x - self.width * 0.065, soft_y, count=6), self.ink, 3, cursor, 9)
        cursor += 11
    cursor = self.add_node_circle(self.fallback_label(0, "Output"), out_x, soft_y, self.width * 0.048, self.height * 0.055, cursor, self.green, font_size=max(16, self.body_size - 8))
    self.add_arrow(_line_points(mix_x + self.width * 0.06, soft_y, out_x - self.width * 0.055, soft_y, count=5), self.green, 4, cursor, 12)
    cursor += 18

    eye_cx = out_x + self.width * 0.09
    eye_cy = soft_y - self.height * 0.12
    self.add_stroke("doodle", _circle_points(eye_cx, eye_cy, self.width * 0.032, self.height * 0.022, count=18), self.blue, 3, cursor, 8)
    cursor += 8
    self.add_stroke("doodle", _circle_points(eye_cx, eye_cy, self.width * 0.008, self.height * 0.012, count=10), self.ink, 3, cursor, 6)
    cursor += 7
    for offset in [-1, 0, 1]:
        self.add_stroke("doodle", _line_points(eye_cx + offset * self.width * 0.028, eye_cy - self.height * 0.035, eye_cx + offset * self.width * 0.036, eye_cy - self.height * 0.058, count=3), self.blue, 3, cursor, 5)
        cursor += 6
    return cursor

def build_matrix_transform(self, start: int) -> int:
    cursor = start
    x = self.board_center_x - self.width * 0.29
    y = self.diagram_top + self.height * 0.12
    w = self.width * 0.12
    h = self.height * 0.20
    cursor = self.add_node_box("W", x, y, w, h, cursor, self.blue, role="matrix", font_size=self.body_size + 6)
    plus_x = x + w + self.width * 0.055
    self.add_text("+", plus_x, y + h * 0.34, self.body_size + 18, self.ink, cursor, 15, self.width * 0.05)
    cursor += 18
    a_x = plus_x + self.width * 0.06
    cursor = self.add_node_box("A", a_x, y + h * 0.34, w * 0.74, h * 0.42, cursor, self.violet, role="matrix", font_size=self.body_size)
    b_x = a_x + w * 0.86
    cursor = self.add_node_box("B", b_x, y, w * 0.48, h, cursor, self.red, role="matrix", font_size=self.body_size)
    result_x = b_x + self.width * 0.13
    self.add_arrow(_line_points(b_x + w * 0.55, y + h * 0.5, result_x - 18, y + h * 0.5, count=6), self.ink, 4, cursor, 14)
    cursor += 20
    cursor = self.add_node_box("W'", result_x, y, w, h, cursor, self.green, role="matrix", font_size=self.body_size + 4)
    self.add_text(self.fallback_label(0, "Low rank update"), a_x - self.width * 0.03, y + h + self.height * 0.055, self.body_size, self.ink, cursor, 24, self.width * 0.28)
    cursor += 30
    for offset in [0.28, 0.5, 0.72]:
        self.add_stroke("matrix_grid", _line_points(x + w * offset, y + 8, x + w * offset, y + h - 8, count=4), self.blue, 2, cursor, 5)
        cursor += 5
    for tick in range(5):
        self.add_stroke("doodle", _line_points(a_x + tick * 18, y - 28 + (tick % 2) * 8, a_x + tick * 18 + 8, y - 40 + (tick % 2) * 8, count=3), self.violet, 3, cursor, 5)
        cursor += 6
    return cursor

def build_priority_matrix(self, start: int) -> int:
    cursor = start
    x = self.board_center_x - self.width * 0.25
    y = self.diagram_top + self.height * 0.08
    w = self.width * 0.50
    h = self.height * 0.42
    mid_x = x + w * 0.5
    mid_y = y + h * 0.5
    self.add_stroke("matrix_frame", _rect_points(x, y, w, h), self.ink, 4, cursor, 18, close=True)
    cursor += 20
    self.add_stroke("matrix_axis", _line_points(mid_x, y, mid_x, y + h, count=6), self.ink, 3, cursor, 10)
    self.add_stroke("matrix_axis", _line_points(x, mid_y, x + w, mid_y, count=6), self.ink, 3, cursor + 6, 10)
    cursor += 20
    self.add_text("重要", x - self.width * 0.065, y + h * 0.18, self.body_size, self.blue, cursor, 16, self.width * 0.08)
    self.add_text("紧急", x + w * 0.72, y + h + self.height * 0.035, self.body_size, self.red, cursor + 8, 16, self.width * 0.10)
    cursor += 24
    quadrant_labels = [
        (self.fallback_label(0, "计划"), x + w * 0.10, y + h * 0.16, self.blue),
        (self.fallback_label(1, "危机"), x + w * 0.62, y + h * 0.16, self.red),
        (self.fallback_label(2, "授权"), x + w * 0.62, y + h * 0.62, self.violet),
        (self.fallback_label(3, "减少"), x + w * 0.10, y + h * 0.62, self.green),
    ]
    for index, (label, tx, ty, color) in enumerate(quadrant_labels):
        self.add_text(label, tx, ty, max(20, self.body_size - 2), color, cursor, 20, w * 0.30, emphasis=index == 0, max_chars=10)
        if index == 0:
            self.add_stroke("focus_circle", _circle_points(tx + w * 0.11, ty + self.body_size * 0.45, w * 0.15, h * 0.16, count=22), self.yellow, 4, cursor + 18, 12)
        cursor += 25
    self.add_arrow(_curve_points(x + w * 0.25, y + h * 0.77, x + w * 0.25, y + h * 0.32, count=12, wave=self.height * 0.018), self.blue, 4, cursor, 14, role="priority_arrow")
    self.add_arrow(_curve_points(x + w * 0.77, y + h * 0.28, x + w * 0.36, y + h * 0.28, count=12, wave=self.height * 0.016), self.green, 4, cursor + 12, 14, role="priority_arrow")
    cursor += 34
    self.add_text(self.fallback_label(4, "把时间留给真正重要的事"), x + w * 0.10, y + h + self.height * 0.085, self.body_size, self.violet, cursor, 28, w * 0.70, emphasis=True, max_chars=18)
    return cursor + 38

def build_feedback_loop(self, start: int) -> int:
    cursor = start
    cx = self.board_center_x
    cy = self.diagram_top + self.height * 0.24
    rx = self.width * 0.17
    ry = self.height * 0.17
    nodes = [
        (self.fallback_label(0, "Observe"), cx, cy - ry),
        (self.fallback_label(1, "Update"), cx + rx, cy + ry * 0.38),
        (self.fallback_label(2, "Improve"), cx - rx, cy + ry * 0.38),
    ]
    for index, (label, x, y) in enumerate(nodes):
        cursor = self.add_node_circle(label, x, y, self.width * 0.065, self.height * 0.055, cursor, self.blue if index % 2 == 0 else self.green, font_size=max(16, self.body_size - 8))
    angles = [-math.pi / 2, 0.3, math.pi - 0.3]
    for start_angle, end_angle in [(angles[0] + 0.38, angles[1] - 0.38), (angles[1] + 0.45, angles[2] - 0.45), (angles[2] + 0.45, angles[0] + math.pi * 2 - 0.45)]:
        self.add_arrow(_arc_points(cx, cy, rx, ry, start_angle, end_angle, count=14), self.ink, 4, cursor, 16, role="loop")
        cursor += 23
    self.add_text(self.fallback_label(3, "Repeat"), cx - self.width * 0.06, cy - self.height * 0.025, self.body_size, self.violet, cursor, 22, self.width * 0.17)
    cursor += 26
    for tick in range(5):
        angle = -0.2 + tick * 0.22
        x0 = cx + math.cos(angle) * (rx + self.width * 0.08)
        y0 = cy + math.sin(angle) * (ry + self.height * 0.05)
        self.add_stroke("doodle", _line_points(x0, y0, x0 + math.cos(angle) * 24, y0 + math.sin(angle) * 18, count=3), self.red, 3, cursor, 5)
        cursor += 6
    return cursor

def build_goal_path(self, start: int) -> int:
    cursor = start
    x0 = self.board_center_x - self.width * 0.30
    y0 = self.diagram_top + self.height * 0.37
    x1 = self.board_center_x + self.width * 0.30
    y1 = self.diagram_top + self.height * 0.18
    path_points = _curve_points(x0, y0, x1, y1, count=18, wave=self.height * 0.08)
    cursor = self.add_node_circle(self.fallback_label(0, "现在"), x0, y0, self.width * 0.055, self.height * 0.050, cursor, self.blue, font_size=max(18, self.body_size - 7))
    self.add_arrow(path_points, self.green, 5, cursor, 24, role="goal_path")
    cursor += 30
    milestones = [path_points[5], path_points[10], path_points[14]]
    for index, point in enumerate(milestones):
        self.add_stroke("milestone", _circle_points(point["x"], point["y"], self.width * 0.020, self.height * 0.028, count=14), self.violet if index % 2 else self.blue, 4, cursor, 8)
        self.add_text(self.fallback_label(index + 2, f"阶段{index + 1}"), point["x"] - self.width * 0.045, point["y"] + self.height * 0.035, max(17, self.body_size - 9), self.ink, cursor + 6, 14, self.width * 0.12, max_chars=8)
        cursor += 18
    cursor = self.add_node_circle(self.fallback_label(1, "目标"), x1, y1, self.width * 0.065, self.height * 0.060, cursor, self.red, font_size=max(19, self.body_size - 6))
    self.add_arrow(_curve_points(x1 - self.width * 0.03, y1 + self.height * 0.08, x0 + self.width * 0.08, y0 - self.height * 0.06, count=16, wave=-self.height * 0.055), self.violet, 4, cursor, 18, role="backcast")
    cursor += 24
    self.add_text(self.fallback_label(5, "从终点倒推"), self.board_center_x - self.width * 0.11, self.diagram_top + self.height * 0.48, self.body_size, self.violet, cursor, 26, self.width * 0.28, emphasis=True, max_chars=12)
    return cursor + 34

def build_overview_map(self, start: int) -> int:
    cursor = start
    labels = self.steps or self.core_lines or [_short_text(self.scene.title, 18), "现象", "机制", "结果", "总结"]
    labels = labels[:5]
    cx = self.board_center_x
    cy = self.diagram_top + self.height * 0.24
    cursor = self.add_node_circle(labels[0], cx, cy, self.width * 0.090, self.height * 0.065, cursor, self.blue, role="overview_center", font_size=max(18, self.body_size - 5))
    positions = [
        (cx - self.width * 0.24, cy - self.height * 0.14, self.red),
        (cx + self.width * 0.24, cy - self.height * 0.13, self.green),
        (cx + self.width * 0.22, cy + self.height * 0.15, self.violet),
        (cx - self.width * 0.22, cy + self.height * 0.16, self.yellow),
    ]
    for index, label in enumerate(labels[1:5]):
        px, py, color = positions[index]
        self.add_arrow(_curve_points(cx + (self.width * 0.085 if px > cx else -self.width * 0.085), cy, px + (self.width * 0.065 if px < cx else -self.width * 0.065), py, count=12, wave=self.height * 0.020), self.ink, 3, cursor, 12, role="overview_link")
        cursor += 14
        cursor = self.add_node_box(label, px - self.width * 0.065, py - self.height * 0.034, self.width * 0.13, self.height * 0.068, cursor, color if color != self.yellow else self.ink, role="overview_unit", font_size=max(17, self.body_size - 8))
    self.add_stroke("route", _arc_points(cx, cy, self.width * 0.30, self.height * 0.23, -math.pi * 0.82, math.pi * 0.12, count=18), self.green, 4, cursor, 18)
    cursor += 22
    self.add_text(self.fallback_label(5, "学习路线"), cx - self.width * 0.07, cy + self.height * 0.25, self.body_size, self.violet, cursor, 22, self.width * 0.20, emphasis=True, max_chars=10)
    return cursor + 30

FallbackSceneBuilder.build_comparison_transform = build_comparison_transform
FallbackSceneBuilder.build_formula_derivation = build_formula_derivation
FallbackSceneBuilder.build_optimization_curve = build_optimization_curve
FallbackSceneBuilder.build_attention_network = build_attention_network
FallbackSceneBuilder.build_matrix_transform = build_matrix_transform
FallbackSceneBuilder.build_priority_matrix = build_priority_matrix
FallbackSceneBuilder.build_feedback_loop = build_feedback_loop
FallbackSceneBuilder.build_goal_path = build_goal_path
FallbackSceneBuilder.build_overview_map = build_overview_map
