import math
from .scene_builder_base import FallbackSceneBuilder
from .geometry import _point, _line_points, _curve_points, _rect_points, _circle_points, _arc_points


def build_seven_habits_overview(self, start: int) -> int:
    cursor = start
    b0 = self.beat_id_for(0)
    b1 = self.beat_id_for(1)
    x = self.board_center_x - self.width * 0.25
    y = self.diagram_top + self.height * 0.31
    step_w = self.width * 0.19
    step_h = self.height * 0.095
    step_points = [
        _point(x, y + step_h * 2),
        _point(x + step_w, y + step_h * 2),
        _point(x + step_w, y + step_h),
        _point(x + step_w * 2, y + step_h),
        _point(x + step_w * 2, y),
        _point(x + step_w * 3, y),
        _point(x + step_w * 3, y + step_h * 3),
        _point(x, y + step_h * 3),
        _point(x, y + step_h * 2),
    ]
    self.add_stroke("staircase", step_points, self.ink, 5, cursor, 34, beat_id=b0)
    cursor += 38
    step_labels = [
        ("\u4f9d\u8d56", x + step_w * 0.25, y + step_h * 2.18, self.red),
        ("\u72ec\u7acb", x + step_w * 1.22, y + step_h * 1.18, self.blue),
        ("\u4e92\u76f8\u4f9d\u8d56", x + step_w * 2.06, y + step_h * 0.18, self.green),
    ]
    for label, tx, ty, color in step_labels:
        self.add_text(label, tx, ty, self.body_size, color, cursor, 18, step_w * 0.80, emphasis=True, max_chars=4, beat_id=b0)
        cursor += 14
    self.add_arrow(_curve_points(x - self.width * 0.03, y + step_h * 2.80, x + step_w * 3.04, y - self.height * 0.02, count=20, wave=-self.height * 0.035), self.blue, 5, cursor, 26, role="growth_arrow", beat_id=b0)
    cursor += 30
    groups = [
        ("\u4e60\u60ef1-3", "\u4e3b\u52a8  \u7ec8\u5c40  \u8981\u4e8b", x - self.width * 0.16, y + step_h * 1.05, self.blue),
        ("\u4e60\u60ef4-6", "\u53cc\u8d62  \u503e\u542c  \u7edf\u5408", x + step_w * 2.25, y + step_h * 1.28, self.green),
    ]
    for title, detail, gx, gy, color in groups:
        cursor = self.add_node_box(title, gx, gy, self.width * 0.14, self.height * 0.070, cursor, color, role="habit_group", font_size=max(18, self.body_size - 8), beat_id=b1)
        self.add_text(detail, gx - self.width * 0.015, gy + self.height * 0.086, max(17, self.body_size - 11), color, cursor, 22, self.width * 0.20, max_chars=12, beat_id=b1)
        cursor += 24
    cx = x + step_w * 1.55
    cy = y - self.height * 0.080
    self.add_stroke("renew_badge", _circle_points(cx, cy, self.width * 0.050, self.height * 0.055, count=20), self.violet, 4, cursor, 12, beat_id=b1)
    self.add_text("\u4e60\u60ef7", cx - self.width * 0.030, cy - self.height * 0.018, max(18, self.body_size - 9), self.violet, cursor + 9, 16, self.width * 0.08, max_chars=4, beat_id=b1)
    self.add_arrow(_arc_points(cx, cy + self.height * 0.10, self.width * 0.34, self.height * 0.27, -math.pi * 0.80, math.pi * 0.10, count=24), self.violet, 4, cursor + 22, 26, role="renew_orbit", beat_id=b1)
    cursor += 55
    for index, (mx, my, color) in enumerate([(x - 32, y + step_h * 2.85, self.red), (x + step_w * 1.48, y + step_h * 1.06, self.yellow), (x + step_w * 3.10, y - 8, self.green)]):
        self.add_stroke("spark", _line_points(mx, my, mx + 18, my - 20, count=3), color, 3, cursor + index * 5, 5, beat_id=b1)
    return cursor + 24

def build_proactive_circles(self, start: int) -> int:
    cursor = start
    b0 = self.beat_id_for(0)
    b1 = self.beat_id_for(1)
    cx = self.board_center_x + self.width * 0.12
    cy = self.diagram_top + self.height * 0.25
    self.add_stroke("concern_circle", _circle_points(cx, cy, self.width * 0.19, self.height * 0.22, count=34), self.ink, 4, cursor, 22, beat_id=b0)
    cursor += 24
    self.add_stroke("influence_circle", _circle_points(cx, cy, self.width * 0.105, self.height * 0.125, count=28), self.green, 5, cursor, 18, beat_id=b0)
    cursor += 22
    self.add_text("\u5f71\u54cd\u5708", cx - self.width * 0.052, cy - self.height * 0.030, self.body_size, self.green, cursor, 20, self.width * 0.14, emphasis=True, max_chars=4, beat_id=b0)
    self.add_text("\u5173\u6ce8\u5708", cx - self.width * 0.045, cy - self.height * 0.205, self.body_size, self.ink, cursor + 10, 20, self.width * 0.13, max_chars=4, beat_id=b0)
    cursor += 30
    self.add_text("\u6211\u80fd\u63a7\u5236", cx - self.width * 0.070, cy + self.height * 0.055, max(18, self.body_size - 8), self.green, cursor, 18, self.width * 0.14, max_chars=6, beat_id=b0)
    self.add_text("\u5173\u5fc3\u4f46\u63a7\u5236\u4e0d\u4e86", cx - self.width * 0.160, cy + self.height * 0.175, max(17, self.body_size - 10), self.red, cursor + 8, 20, self.width * 0.32, max_chars=10, beat_id=b0)
    cursor += 28
    y = cy + self.height * 0.33
    x0 = self.board_center_x - self.width * 0.31
    x1 = self.board_center_x + self.width * 0.31
    self.add_node_box("\u523a\u6fc0", x0, y, self.width * 0.105, self.height * 0.065, cursor, self.red, role="stimulus", font_size=max(18, self.body_size - 8), beat_id=b1)
    self.add_node_box("\u53cd\u5e94", x1 - self.width * 0.105, y, self.width * 0.105, self.height * 0.065, cursor + 8, self.green, role="response", font_size=max(18, self.body_size - 8), beat_id=b1)
    cursor += 24
    self.add_arrow(_line_points(x0 + self.width * 0.120, y + self.height * 0.033, x1 - self.width * 0.135, y + self.height * 0.033, count=12), self.ink, 4, cursor, 16, role="choice_line", beat_id=b1)
    cursor += 20
    choice_cx = self.board_center_x
    choice_cy = y + self.height * 0.033
    self.add_stroke("choice_space", _circle_points(choice_cx, choice_cy, self.width * 0.055, self.height * 0.052, count=20), self.blue, 4, cursor, 12, beat_id=b1)
    self.add_text("\u9009\u62e9", choice_cx - self.width * 0.030, choice_cy - self.height * 0.020, max(18, self.body_size - 8), self.blue, cursor + 8, 16, self.width * 0.08, emphasis=True, max_chars=4, beat_id=b1)
    cursor += 28
    self.draw_star(cx + self.width * 0.145, cy - self.height * 0.165, self.width * 0.023, self.yellow, cursor, 8, beat_id=b1)
    return cursor + 18

def build_begin_with_end(self, start: int) -> int:
    cursor = start
    b0 = self.beat_id_for(0)
    b1 = self.beat_id_for(1)
    x0 = self.board_center_x - self.width * 0.30
    y0 = self.diagram_top + self.height * 0.39
    x1 = self.board_center_x + self.width * 0.31
    y1 = self.diagram_top + self.height * 0.17
    cursor = self.add_node_circle("\u73b0\u5728", x0, y0, self.width * 0.055, self.height * 0.050, cursor, self.blue, font_size=max(18, self.body_size - 7), beat_id=b0)
    path = _curve_points(x0 + self.width * 0.060, y0 - self.height * 0.010, x1 - self.width * 0.080, y1 + self.height * 0.050, count=24, wave=self.height * 0.09)
    self.add_arrow(path, self.green, 5, cursor, 28, role="vision_path", beat_id=b0)
    cursor += 32
    for index, point in enumerate([path[6], path[12], path[18]]):
        self.add_stroke("principle_milestone", _circle_points(point["x"], point["y"], self.width * 0.020, self.height * 0.028, count=14), self.violet if index % 2 else self.blue, 4, cursor, 8, beat_id=b0)
        self.add_text("\u539f\u5219", point["x"] - self.width * 0.027, point["y"] + self.height * 0.034, max(16, self.body_size - 11), self.violet, cursor + 5, 12, self.width * 0.07, max_chars=4, beat_id=b0)
        cursor += 15
    cursor = self.add_node_circle("\u613f\u666f/\u4f7f\u547d", x1, y1, self.width * 0.075, self.height * 0.060, cursor, self.red, font_size=max(18, self.body_size - 8), beat_id=b0)
    compass_cx = x1 - self.width * 0.02
    compass_cy = y1 - self.height * 0.18
    self.add_stroke("compass", _circle_points(compass_cx, compass_cy, self.width * 0.055, self.height * 0.060, count=24), self.ink, 4, cursor, 16, beat_id=b1)
    cursor += 18
    self.add_stroke("compass_needle", [_point(compass_cx, compass_cy - self.height * 0.045), _point(compass_cx + self.width * 0.022, compass_cy + self.height * 0.008), _point(compass_cx, compass_cy + self.height * 0.045), _point(compass_cx - self.width * 0.014, compass_cy - self.height * 0.006), _point(compass_cx, compass_cy - self.height * 0.045)], self.red, 4, cursor, 16, close=True, beat_id=b1)
    cursor += 18
    self.add_text("\u6307\u5357\u9488", compass_cx - self.width * 0.050, compass_cy - self.height * 0.115, max(18, self.body_size - 8), self.ink, cursor, 16, self.width * 0.12, max_chars=4, beat_id=b1)
    self.add_arrow(_curve_points(compass_cx - self.width * 0.060, compass_cy + self.height * 0.045, path[12]["x"], path[12]["y"], count=12, wave=-self.height * 0.025), self.violet, 4, cursor + 10, 16, role="principle_pointer", beat_id=b1)
    cursor += 34
    self.add_text("\u5148\u5b9a\u65b9\u5411", self.board_center_x - self.width * 0.070, self.diagram_top + self.height * 0.53, self.body_size, self.yellow, cursor, 20, self.width * 0.17, emphasis=True, max_chars=6, beat_id=b1)
    return cursor + 26

def build_time_matrix_rich(self, start: int) -> int:
    cursor = start
    b0 = self.beat_id_for(0)
    b1 = self.beat_id_for(1)
    x = self.board_center_x - self.width * 0.27
    y = self.diagram_top + self.height * 0.06
    w = self.width * 0.54
    h = self.height * 0.46
    mid_x = x + w * 0.5
    mid_y = y + h * 0.5
    self.add_stroke("matrix_frame", _rect_points(x, y, w, h), self.ink, 5, cursor, 20, close=True, beat_id=b0)
    cursor += 22
    self.add_stroke("matrix_axis", _line_points(mid_x, y, mid_x, y + h, count=7), self.ink, 4, cursor, 12, beat_id=b0)
    self.add_stroke("matrix_axis", _line_points(x, mid_y, x + w, mid_y, count=7), self.ink, 4, cursor + 7, 12, beat_id=b0)
    cursor += 24
    self.add_text("\u91cd\u8981", x - self.width * 0.065, y + h * 0.14, self.body_size, self.blue, cursor, 16, self.width * 0.08, max_chars=4, beat_id=b0)
    self.add_text("\u4e0d\u91cd\u8981", x - self.width * 0.080, y + h * 0.68, max(18, self.body_size - 7), self.ink, cursor + 6, 16, self.width * 0.10, max_chars=4, beat_id=b0)
    self.add_text("\u7d27\u6025", x + w * 0.18, y + h + self.height * 0.030, self.body_size, self.red, cursor + 12, 16, self.width * 0.08, max_chars=4, beat_id=b0)
    self.add_text("\u4e0d\u7d27\u6025", x + w * 0.68, y + h + self.height * 0.030, max(18, self.body_size - 7), self.green, cursor + 18, 16, self.width * 0.10, max_chars=4, beat_id=b0)
    cursor += 38
    quadrants = [
        ("\u5371\u673a", x + w * 0.14, y + h * 0.18, self.red, "alarm"),
        ("\u9884\u9632/\u89c4\u5212", x + w * 0.60, y + h * 0.18, self.green, "star"),
        ("\u5e72\u6270", x + w * 0.16, y + h * 0.66, self.yellow, "noise"),
        ("\u6d6a\u8d39", x + w * 0.66, y + h * 0.66, self.violet, "waste"),
    ]
    for index, (label, tx, ty, color, role_name) in enumerate(quadrants):
        self.add_text(label, tx, ty, max(21, self.body_size - 4), color, cursor, 20, w * 0.28, emphasis=index == 1, max_chars=8, beat_id=b1)
        if role_name == "star":
            self.draw_star(tx + w * 0.18, ty + self.height * 0.020, self.width * 0.028, self.yellow, cursor + 16, 10, beat_id=b1)
            self.add_stroke("focus_circle", _circle_points(tx + w * 0.10, ty + self.height * 0.030, w * 0.18, h * 0.16, count=22), self.green, 4, cursor + 26, 12, beat_id=b1)
        elif role_name == "alarm":
            self.add_stroke("alarm", _line_points(tx + w * 0.11, ty - self.height * 0.035, tx + w * 0.11, ty - self.height * 0.070, count=3), self.red, 4, cursor + 15, 6, beat_id=b1)
            self.add_stroke("alarm", _line_points(tx + w * 0.09, ty - self.height * 0.057, tx + w * 0.13, ty - self.height * 0.057, count=3), self.red, 4, cursor + 19, 6, beat_id=b1)
        cursor += 24
    self.add_arrow(_curve_points(x + w * 0.22, y + h * 0.78, x + w * 0.70, y + h * 0.30, count=15, wave=-self.height * 0.025), self.blue, 4, cursor, 18, role="priority_shift", beat_id=b1)
    cursor += 24
    self.add_text("\u8981\u4e8b\u7b2c\u4e00", x + w * 0.58, y + h * 0.49, self.body_size, self.violet, cursor, 22, self.width * 0.18, emphasis=True, max_chars=6, beat_id=b1)
    return cursor + 30

def build_interdependence_rich(self, start: int) -> int:
    cursor = start
    b0 = self.beat_id_for(0)
    b1 = self.beat_id_for(1)
    b2 = self.beat_id_for(2)
    sx = self.board_center_x - self.width * 0.31
    sy = self.diagram_top + self.height * 0.15
    self.add_stroke("scale_base", _line_points(sx, sy + self.height * 0.145, sx + self.width * 0.18, sy + self.height * 0.145, count=5), self.ink, 4, cursor, 8, beat_id=b0)
    self.add_stroke("scale_stem", _line_points(sx + self.width * 0.09, sy + self.height * 0.145, sx + self.width * 0.09, sy + self.height * 0.015, count=5), self.ink, 4, cursor + 6, 8, beat_id=b0)
    self.add_stroke("scale_bar", _line_points(sx + self.width * 0.015, sy + self.height * 0.035, sx + self.width * 0.165, sy + self.height * 0.035, count=5), self.ink, 4, cursor + 12, 8, beat_id=b0)
    self.add_stroke("scale_pan", _arc_points(sx + self.width * 0.025, sy + self.height * 0.055, self.width * 0.045, self.height * 0.035, 0.05, math.pi - 0.05, count=10), self.blue, 4, cursor + 19, 9, beat_id=b0)
    self.add_stroke("scale_pan", _arc_points(sx + self.width * 0.155, sy + self.height * 0.055, self.width * 0.045, self.height * 0.035, 0.05, math.pi - 0.05, count=10), self.green, 4, cursor + 25, 9, beat_id=b0)
    cursor += 40
    self.add_text("\u6211", sx + self.width * 0.004, sy + self.height * 0.084, max(18, self.body_size - 8), self.blue, cursor, 10, self.width * 0.05, max_chars=2, beat_id=b0)
    self.add_text("\u4f60", sx + self.width * 0.137, sy + self.height * 0.084, max(18, self.body_size - 8), self.green, cursor + 4, 10, self.width * 0.05, max_chars=2, beat_id=b0)
    self.add_text("\u53cc\u8d62", sx + self.width * 0.060, sy - self.height * 0.035, self.body_size, self.green, cursor + 8, 18, self.width * 0.10, emphasis=True, max_chars=4, beat_id=b0)
    cursor += 28
    seesaw_x = sx + self.width * 0.22
    self.add_stroke("seesaw", _line_points(seesaw_x, sy + self.height * 0.12, seesaw_x + self.width * 0.18, sy + self.height * 0.045, count=6), self.red, 4, cursor, 10, beat_id=b0)
    self.add_stroke("seesaw_base", [_point(seesaw_x + self.width * 0.09, sy + self.height * 0.085), _point(seesaw_x + self.width * 0.07, sy + self.height * 0.14), _point(seesaw_x + self.width * 0.11, sy + self.height * 0.14), _point(seesaw_x + self.width * 0.09, sy + self.height * 0.085)], self.ink, 3, cursor + 8, 8, close=True, beat_id=b0)
    self.add_text("\u8f93\u8d62", seesaw_x + self.width * 0.055, sy + self.height * 0.150, max(18, self.body_size - 8), self.red, cursor + 15, 14, self.width * 0.08, max_chars=4, beat_id=b0)
    cursor += 32
    px = self.board_center_x + self.width * 0.10
    py = self.diagram_top + self.height * 0.09
    self.draw_person_icon(px, py + self.height * 0.06, self.blue, cursor, 1.1, b1)
    self.draw_person_icon(px + self.width * 0.22, py + self.height * 0.06, self.green, cursor + 8, 1.1, b1)
    self.add_stroke("big_ear", _arc_points(px + self.width * 0.042, py + self.height * 0.045, self.width * 0.025, self.height * 0.040, -math.pi * 0.55, math.pi * 0.65, count=12), self.blue, 5, cursor + 28, 10, beat_id=b1)
    self.add_stroke("mouth", _arc_points(px + self.width * 0.205, py + self.height * 0.055, self.width * 0.025, self.height * 0.018, 0, math.pi, count=8), self.green, 4, cursor + 36, 8, beat_id=b1)
    self.add_text("\u503e\u542c", px - self.width * 0.020, py + self.height * 0.225, max(18, self.body_size - 8), self.blue, cursor + 42, 14, self.width * 0.08, max_chars=4, beat_id=b1)
    self.add_text("\u8868\u8fbe", px + self.width * 0.185, py + self.height * 0.225, max(18, self.body_size - 8), self.green, cursor + 48, 14, self.width * 0.08, max_chars=4, beat_id=b1)
    self.add_arrow(_curve_points(px + self.width * 0.070, py + self.height * 0.08, px + self.width * 0.180, py + self.height * 0.08, count=10, wave=-self.height * 0.015), self.violet, 4, cursor + 54, 12, role="understand_arrow", beat_id=b1)
    self.add_text("\u7406\u89e3", px + self.width * 0.096, py + self.height * 0.025, max(18, self.body_size - 8), self.violet, cursor + 62, 14, self.width * 0.08, max_chars=4, beat_id=b1)
    cursor += 86
    bx = self.board_center_x - self.width * 0.21
    by = self.diagram_top + self.height * 0.45
    self.add_stroke("puzzle_circle", _circle_points(bx, by, self.width * 0.045, self.height * 0.050, count=18), self.blue, 4, cursor, 12, beat_id=b2)
    self.add_stroke("puzzle_square", _rect_points(bx + self.width * 0.055, by - self.height * 0.045, self.width * 0.090, self.height * 0.090), self.green, 4, cursor + 8, 12, close=True, beat_id=b2)
    self.draw_star(bx + self.width * 0.205, by, self.width * 0.046, self.yellow, cursor + 18, 12, beat_id=b2)
    self.add_arrow(_line_points(bx + self.width * 0.145, by, bx + self.width * 0.160, by, count=3), self.ink, 3, cursor + 22, 8, beat_id=b2)
    self.add_text("1+1>2", bx + self.width * 0.160, by + self.height * 0.070, self.body_size, self.green, cursor + 32, 18, self.width * 0.12, emphasis=True, max_chars=5, beat_id=b2)
    self.add_node_box("\u59a5\u534f", bx + self.width * 0.36, by - self.height * 0.046, self.width * 0.11, self.height * 0.080, cursor + 12, self.violet, role="compromise", font_size=max(18, self.body_size - 8), beat_id=b2)
    cursor += 64
    return cursor

def build_renewal_summary_rich(self, start: int) -> int:
    cursor = start
    b0 = self.beat_id_for(0)
    b1 = self.beat_id_for(1)
    cx = self.board_center_x
    cy = self.diagram_top + self.height * 0.22
    rx = self.width * 0.19
    ry = self.height * 0.18
    labels = [
        ("\u8eab\u4f53", cx, cy - ry, self.blue, "run"),
        ("\u5fc3\u667a", cx + rx, cy, self.green, "book"),
        ("\u7cbe\u795e", cx, cy + ry, self.violet, "med"),
        ("\u793e\u4f1a\u60c5\u611f", cx - rx, cy, self.red, "hand"),
    ]
    for index, (label, nx, ny, color, icon) in enumerate(labels):
        cursor = self.add_node_circle(label, nx, ny, self.width * 0.066, self.height * 0.055, cursor, color, font_size=max(17, self.body_size - 8), beat_id=b0)
        if icon == "run":
            self.add_arrow(_line_points(nx - 22, ny + self.height * 0.060, nx + 24, ny + self.height * 0.045, count=4), color, 3, cursor, 6, role="mini_icon", beat_id=b0)
        elif icon == "book":
            self.add_stroke("book_icon", _rect_points(nx - 24, ny + self.height * 0.055, 48, 34), color, 3, cursor, 6, close=True, beat_id=b0)
        elif icon == "med":
            self.add_stroke("med_icon", _arc_points(nx, ny + self.height * 0.070, 40, 22, 0, math.pi, count=9), color, 3, cursor, 6, beat_id=b0)
        else:
            self.add_stroke("handshake", _line_points(nx - 36, ny + self.height * 0.070, nx + 36, ny + self.height * 0.070, count=5), color, 3, cursor, 6, beat_id=b0)
        cursor += 8
    for start_angle, end_angle in [(-math.pi * 0.46, math.pi * 0.05), (math.pi * 0.05, math.pi * 0.55), (math.pi * 0.55, math.pi * 1.05), (math.pi * 1.05, math.pi * 1.55)]:
        self.add_arrow(_arc_points(cx, cy, rx * 0.96, ry * 0.95, start_angle, end_angle, count=13), self.ink, 4, cursor, 12, role="renew_loop", beat_id=b0)
        cursor += 14
    self.add_text("\u66f4\u65b0", cx - self.width * 0.038, cy - self.height * 0.026, self.body_size, self.violet, cursor, 18, self.width * 0.09, emphasis=True, max_chars=4, beat_id=b0)
    cursor += 24
    sx = self.board_center_x - self.width * 0.20
    sy = self.diagram_top + self.height * 0.51
    mini_w = self.width * 0.13
    mini_h = self.height * 0.050
    mini = [
        ("\u4f9d\u8d56", sx, sy + mini_h * 1.8, self.red),
        ("\u72ec\u7acb", sx + mini_w, sy + mini_h * 0.9, self.blue),
        ("\u4e92\u76f8\u4f9d\u8d56", sx + mini_w * 2, sy, self.green),
    ]
    prev = None
    for label, tx, ty, color in mini:
        cursor = self.add_node_box(label, tx, ty, mini_w * 0.92, mini_h * 1.05, cursor, color, role="mini_step", font_size=max(16, self.body_size - 12), beat_id=b1)
        if prev:
            self.add_arrow(_line_points(prev[0] + mini_w * 0.82, prev[1] + mini_h * 0.50, tx - 10, ty + mini_h * 0.50, count=5), self.ink, 3, cursor, 8, beat_id=b1)
            cursor += 8
        prev = (tx, ty)
    self.add_text("\u4ece\u88ab\u52a8\u5230\u5171\u8d62", sx + mini_w * 0.55, sy + mini_h * 2.95, self.body_size, self.yellow, cursor, 22, self.width * 0.24, emphasis=True, max_chars=8, beat_id=b1)
    return cursor + 28



FallbackSceneBuilder.build_seven_habits_overview = build_seven_habits_overview
FallbackSceneBuilder.build_proactive_circles = build_proactive_circles
FallbackSceneBuilder.build_begin_with_end = build_begin_with_end
FallbackSceneBuilder.build_time_matrix_rich = build_time_matrix_rich
FallbackSceneBuilder.build_interdependence_rich = build_interdependence_rich
FallbackSceneBuilder.build_renewal_summary_rich = build_renewal_summary_rich
