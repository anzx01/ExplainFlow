import math
from .scene_builder_base import FallbackSceneBuilder
from .geometry import _point, _line_points, _curve_points, _rect_points, _circle_points, _arc_points


def build_railway_permission_gate(self, start: int) -> int:
    cursor = start
    b0 = self.beat_id_for(0)
    b1 = self.beat_id_for(1)
    b2 = self.beat_id_for(2)
    b3 = self.beat_id_for(3)
    icon_y = self.diagram_top + self.height * 0.12
    icon_w = self.width * 0.125
    icon_h = self.height * 0.145
    centers = [self.board_center_x - self.width * 0.29, self.board_center_x, self.board_center_x + self.width * 0.29]

    doc_x = centers[0] - icon_w * 0.5
    doc_y = icon_y
    self.add_stroke("railway_document", _rect_points(doc_x, doc_y, icon_w, icon_h), self.blue, 4, cursor, 16, close=True, beat_id=b0)
    self.add_stroke("railway_document_fold", [_point(doc_x + icon_w * 0.72, doc_y), _point(doc_x + icon_w, doc_y + icon_h * 0.24), _point(doc_x + icon_w * 0.72, doc_y + icon_h * 0.24), _point(doc_x + icon_w * 0.72, doc_y)], self.blue, 3, cursor + 10, 10, close=True, beat_id=b0)
    for line_index in range(3):
        self.add_stroke("railway_document_line", _line_points(doc_x + icon_w * 0.16, doc_y + icon_h * (0.30 + line_index * 0.18), doc_x + icon_w * 0.62, doc_y + icon_h * (0.30 + line_index * 0.18), count=4), self.ink, 3, cursor + 18 + line_index * 4, 6, beat_id=b0)
    self.draw_check_mark(doc_x + icon_w * 0.76, doc_y + icon_h * 0.68, self.green, cursor + 32, 10, 0.72, b0)
    self.add_text("作业计划", doc_x - self.width * 0.006, doc_y + icon_h + self.height * 0.030, self.body_size, self.blue, cursor + 38, 20, icon_w * 1.2, max_chars=4, beat_id=b0)

    scroll_x = centers[1] - icon_w * 0.50
    scroll_y = icon_y + self.height * 0.006
    self.add_stroke("railway_order_scroll", _arc_points(scroll_x + icon_w * 0.16, scroll_y + icon_h * 0.22, icon_w * 0.13, icon_h * 0.18, math.pi * 0.55, math.pi * 1.55, count=10), self.violet, 4, cursor + 10, 12, beat_id=b1)
    self.add_stroke("railway_order_scroll", _rect_points(scroll_x + icon_w * 0.15, scroll_y + icon_h * 0.10, icon_w * 0.70, icon_h * 0.70), self.violet, 4, cursor + 20, 16, close=False, beat_id=b1)
    self.add_stroke("railway_order_seal", _circle_points(scroll_x + icon_w * 0.66, scroll_y + icon_h * 0.59, icon_w * 0.080, icon_h * 0.080, count=14), self.red, 4, cursor + 38, 9, beat_id=b1)
    self.add_stroke("railway_radio_wave", _arc_points(scroll_x + icon_w * 0.92, scroll_y + icon_h * 0.35, icon_w * 0.12, icon_h * 0.20, -math.pi * 0.35, math.pi * 0.35, count=9), self.green, 3, cursor + 44, 8, beat_id=b1)
    self.add_text("调度命令", scroll_x - self.width * 0.006, scroll_y + icon_h + self.height * 0.030, self.body_size, self.violet, cursor + 50, 20, icon_w * 1.35, max_chars=4, beat_id=b1)

    track_x = centers[2] - icon_w * 0.52
    track_y = icon_y + self.height * 0.018
    for rail_offset in [0.20, 0.54]:
        self.add_stroke("railway_track", _line_points(track_x + icon_w * rail_offset, track_y, track_x + icon_w * (rail_offset + 0.12), track_y + icon_h * 0.82, count=8), self.ink, 4, cursor + 20, 16, beat_id=b2)
    for sleeper_index in range(6):
        sy = track_y + icon_h * (0.09 + sleeper_index * 0.13)
        self.add_stroke("railway_sleeper", _line_points(track_x + icon_w * 0.17, sy, track_x + icon_w * 0.73, sy + icon_h * 0.020, count=4), self.ink, 2, cursor + 34 + sleeper_index * 3, 5, beat_id=b2)
    self.add_stroke("railway_boundary", _line_points(track_x + icon_w * 0.80, track_y + icon_h * 0.08, track_x + icon_w * 0.93, track_y + icon_h * 0.86, count=7), self.red, 5, cursor + 54, 12, beat_id=b2)
    self.add_text("线路边界", track_x - self.width * 0.004, track_y + icon_h + self.height * 0.030, self.body_size, self.red, cursor + 64, 20, icon_w * 1.28, max_chars=4, beat_id=b2)
    cursor += 86

    gate_x = self.board_center_x
    gate_y = self.diagram_top + self.height * 0.48
    for center in centers:
        self.add_arrow(_curve_points(center, icon_y + icon_h + self.height * 0.060, gate_x, gate_y - self.height * 0.030, count=13, wave=self.height * 0.035), self.blue if center < gate_x else self.green, 4, cursor, 16, role="permission_merge", beat_id=b3)
        cursor += 9
    merge_label = self.annotation_label("short_arrow", "汇合")
    self.add_text(merge_label, gate_x - self.width * 0.040, gate_y - self.height * 0.135, self.body_size, self.blue, cursor, 18, self.width * 0.10, emphasis=True, max_chars=4, beat_id=b3)
    cursor += 20

    post_h = self.height * 0.19
    post_gap = self.width * 0.17
    self.add_stroke("permission_gate", _line_points(gate_x - post_gap * 0.5, gate_y, gate_x - post_gap * 0.5, gate_y + post_h, count=5), self.ink, 5, cursor, 10, beat_id=b3)
    self.add_stroke("permission_gate", _line_points(gate_x + post_gap * 0.5, gate_y, gate_x + post_gap * 0.5, gate_y + post_h, count=5), self.ink, 5, cursor + 7, 10, beat_id=b3)
    self.add_stroke("permission_gate_top", _arc_points(gate_x, gate_y + self.height * 0.020, post_gap * 0.52, self.height * 0.075, math.pi, math.pi * 2, count=16), self.green, 5, cursor + 16, 14, beat_id=b3)
    self.add_stroke("permission_gate_bar", _line_points(gate_x - post_gap * 0.42, gate_y + post_h * 0.58, gate_x + post_gap * 0.42, gate_y + post_h * 0.44, count=6), self.green, 5, cursor + 28, 10, beat_id=b3)
    self.add_text("许可闸门", gate_x - self.width * 0.060, gate_y + post_h + self.height * 0.020, self.body_size, self.green, cursor + 38, 20, self.width * 0.14, emphasis=True, max_chars=4, beat_id=b3)
    self.draw_wavy_underline(gate_x - self.width * 0.062, gate_y + post_h + self.height * 0.082, self.width * 0.135, self.yellow, cursor + 58, 12, b3)
    self.add_text(self.annotation_label("side_label", "缺一不可"), gate_x + self.width * 0.145, gate_y + self.height * 0.020, self.body_size, self.violet, cursor + 70, 20, self.width * 0.16, max_chars=5, beat_id=b3)
    self.draw_cross_mark(gate_x - self.width * 0.175, gate_y + post_h * 0.58, self.red, cursor + 74, 12, 0.95, b3)
    self.add_text(self.annotation_label("crossout", "禁止上道"), gate_x - self.width * 0.280, gate_y + post_h * 0.42, self.body_size, self.red, cursor + 82, 22, self.width * 0.17, emphasis=True, max_chars=5, beat_id=b3)
    self.add_teacher_takeaway("三项齐再上道", gate_x + self.width * 0.125, gate_y + post_h * 0.70, self.green, cursor + 104, b3, max_chars=7)
    return cursor + 142

def build_railway_contact_loop(self, start: int) -> int:
    cursor = start
    b0 = self.beat_id_for(0)
    b1 = self.beat_id_for(1)
    b2 = self.beat_id_for(2)
    top_node = (self.board_center_x, self.diagram_top + self.height * 0.14, "驻站联络员", self.violet, b0)
    left_node = (self.board_center_x - self.width * 0.27, self.diagram_top + self.height * 0.43, "作业负责人", self.blue, b0)
    right_node = (self.board_center_x + self.width * 0.27, self.diagram_top + self.height * 0.43, "现场防护员", self.green, b0)
    nodes = [top_node, left_node, right_node]
    for x, y, label, color, beat in nodes:
        self.draw_person_icon(x, y, color, cursor, 1.25, beat)
        self.add_stroke("railway_headset", _arc_points(x + self.width * 0.020, y - self.height * 0.010, self.width * 0.025, self.height * 0.035, -math.pi * 0.45, math.pi * 0.45, count=9), color, 3, cursor + 25, 8, beat_id=beat)
        self.add_stroke("railway_radio_wave", _arc_points(x + self.width * 0.050, y + self.height * 0.020, self.width * 0.035, self.height * 0.055, -math.pi * 0.35, math.pi * 0.35, count=9), color, 3, cursor + 32, 8, beat_id=beat)
        self.add_text(label, x - self.width * 0.080, y + self.height * 0.185, self.body_size, color, cursor + 42, 20, self.width * 0.16, max_chars=5, beat_id=beat)
        cursor += 22

    arrow_start = cursor + 8
    confirm_label = self.annotation_label("short_arrow", "复诵确认")
    self.add_arrow(_curve_points(left_node[0] + self.width * 0.060, left_node[1] - self.height * 0.020, top_node[0] - self.width * 0.060, top_node[1] + self.height * 0.105, count=14, wave=-self.height * 0.035), self.blue, 5, arrow_start, 18, role="contact_loop", beat_id=b1)
    self.add_arrow(_curve_points(top_node[0] + self.width * 0.060, top_node[1] + self.height * 0.105, right_node[0] - self.width * 0.060, right_node[1] - self.height * 0.020, count=14, wave=-self.height * 0.035), self.violet, 5, arrow_start + 18, 18, role="contact_loop", beat_id=b1)
    self.add_arrow(_curve_points(right_node[0] - self.width * 0.070, right_node[1] + self.height * 0.130, left_node[0] + self.width * 0.070, left_node[1] + self.height * 0.130, count=16, wave=self.height * 0.050), self.green, 5, arrow_start + 36, 18, role="contact_loop", beat_id=b1)
    self.add_text(confirm_label, self.board_center_x - self.width * 0.058, self.diagram_top + self.height * 0.333, self.body_size, self.blue, arrow_start + 54, 20, self.width * 0.14, emphasis=True, max_chars=4, beat_id=b1)
    self.draw_wavy_underline(self.board_center_x - self.width * 0.060, self.diagram_top + self.height * 0.394, self.width * 0.125, self.yellow, arrow_start + 72, 12, b1)
    badge_y = self.diagram_top + self.height * 0.270
    self.add_step_badge("1", self.board_center_x - self.width * 0.175, badge_y, self.blue, arrow_start + 78, b1)
    self.add_text("报清", self.board_center_x - self.width * 0.150, badge_y - self.height * 0.025, max(18, self.body_size - 8), self.blue, arrow_start + 86, 14, self.width * 0.08, max_chars=2, beat_id=b1)
    self.add_step_badge("2", self.board_center_x + self.width * 0.105, badge_y, self.violet, arrow_start + 94, b1)
    self.add_text("复诵", self.board_center_x + self.width * 0.130, badge_y - self.height * 0.025, max(18, self.body_size - 8), self.violet, arrow_start + 102, 14, self.width * 0.08, max_chars=2, beat_id=b1)
    self.add_step_badge("3", self.board_center_x, self.diagram_top + self.height * 0.555, self.green, arrow_start + 110, b1)
    self.add_text("回传", self.board_center_x + self.width * 0.025, self.diagram_top + self.height * 0.530, max(18, self.body_size - 8), self.green, arrow_start + 118, 14, self.width * 0.08, max_chars=2, beat_id=b1)

    break_x = self.board_center_x + self.width * 0.18
    break_y = self.diagram_top + self.height * 0.28
    self.add_stroke("contact_broken_link", _line_points(break_x - self.width * 0.040, break_y, break_x + self.width * 0.036, break_y + self.height * 0.052, count=3), self.red, 4, arrow_start + 86, 8, beat_id=b2)
    self.draw_cross_mark(break_x + self.width * 0.012, break_y + self.height * 0.028, self.red, arrow_start + 94, 12, 0.95, b2)
    self.add_text(self.annotation_label("crossout", "通信中断"), break_x + self.width * 0.045, break_y - self.height * 0.020, self.body_size, self.red, arrow_start + 104, 22, self.width * 0.16, emphasis=True, max_chars=4, beat_id=b2)
    self.add_text(self.annotation_label("side_label", "立即停止"), self.board_center_x - self.width * 0.082, self.diagram_top + self.height * 0.640, self.body_size, self.red, arrow_start + 122, 22, self.width * 0.18, emphasis=True, max_chars=4, beat_id=b2)
    self.draw_risk_rays(self.board_center_x + self.width * 0.055, self.diagram_top + self.height * 0.660, self.red, arrow_start + 136, direction=1, beat_id=b2)
    self.add_teacher_takeaway("断联即停", self.board_center_x + self.width * 0.155, self.diagram_top + self.height * 0.615, self.red, arrow_start + 150, b2, max_chars=4)
    return arrow_start + 190

def build_railway_ppe_check(self, start: int) -> int:
    cursor = start
    b0 = self.beat_id_for(0)
    b1 = self.beat_id_for(1)
    b2 = self.beat_id_for(2)
    worker_x = self.board_center_x - self.width * 0.16
    head_y = self.diagram_top + self.height * 0.12
    torso_y = head_y + self.height * 0.115
    body_h = self.height * 0.265

    self.add_stroke("ppe_hardhat", _arc_points(worker_x, head_y, self.width * 0.070, self.height * 0.055, math.pi, math.pi * 2, count=15), self.yellow, 5, cursor, 14, beat_id=b0)
    self.add_stroke("ppe_hardhat_brim", _line_points(worker_x - self.width * 0.080, head_y + self.height * 0.004, worker_x + self.width * 0.080, head_y + self.height * 0.004, count=6), self.yellow, 5, cursor + 12, 8, beat_id=b0)
    self.add_stroke("ppe_head", _circle_points(worker_x, head_y + self.height * 0.055, self.width * 0.044, self.height * 0.052, count=18), self.ink, 4, cursor + 20, 12, beat_id=b0)
    vest = [
        _point(worker_x - self.width * 0.075, torso_y),
        _point(worker_x + self.width * 0.075, torso_y),
        _point(worker_x + self.width * 0.115, torso_y + body_h),
        _point(worker_x - self.width * 0.115, torso_y + body_h),
        _point(worker_x - self.width * 0.075, torso_y),
    ]
    self.add_stroke("ppe_vest", vest, self.green, 5, cursor + 34, 18, close=True, beat_id=b0)
    self.add_stroke("ppe_reflective_strip", _line_points(worker_x - self.width * 0.040, torso_y + self.height * 0.030, worker_x + self.width * 0.010, torso_y + body_h * 0.78, count=6), self.yellow, 4, cursor + 52, 10, beat_id=b0)
    self.add_stroke("ppe_reflective_strip", _line_points(worker_x + self.width * 0.040, torso_y + self.height * 0.030, worker_x - self.width * 0.010, torso_y + body_h * 0.78, count=6), self.yellow, 4, cursor + 58, 10, beat_id=b0)
    self.add_stroke("ppe_arm", _line_points(worker_x - self.width * 0.085, torso_y + self.height * 0.045, worker_x - self.width * 0.155, torso_y + self.height * 0.150, count=5), self.ink, 4, cursor + 66, 9, beat_id=b0)
    self.add_stroke("ppe_arm", _line_points(worker_x + self.width * 0.085, torso_y + self.height * 0.045, worker_x + self.width * 0.155, torso_y + self.height * 0.150, count=5), self.ink, 4, cursor + 72, 9, beat_id=b0)
    self.add_stroke("ppe_leg", _line_points(worker_x - self.width * 0.050, torso_y + body_h, worker_x - self.width * 0.080, torso_y + body_h + self.height * 0.150, count=5), self.ink, 5, cursor + 80, 9, beat_id=b0)
    self.add_stroke("ppe_leg", _line_points(worker_x + self.width * 0.050, torso_y + body_h, worker_x + self.width * 0.080, torso_y + body_h + self.height * 0.150, count=5), self.ink, 5, cursor + 86, 9, beat_id=b0)
    self.add_stroke("ppe_boot", _line_points(worker_x - self.width * 0.105, torso_y + body_h + self.height * 0.155, worker_x - self.width * 0.045, torso_y + body_h + self.height * 0.155, count=4), self.red, 5, cursor + 94, 8, beat_id=b0)
    self.add_stroke("ppe_boot", _line_points(worker_x + self.width * 0.045, torso_y + body_h + self.height * 0.155, worker_x + self.width * 0.105, torso_y + body_h + self.height * 0.155, count=4), self.red, 5, cursor + 99, 8, beat_id=b0)

    self.add_text(self.annotation_label("side_label", "安全帽"), worker_x - self.width * 0.265, head_y - self.height * 0.028, self.body_size, self.yellow, cursor + 108, 20, self.width * 0.13, emphasis=True, max_chars=4, beat_id=b0)
    self.add_arrow(_curve_points(worker_x - self.width * 0.130, head_y, worker_x - self.width * 0.055, head_y, count=8, wave=-self.height * 0.014), self.yellow, 4, cursor + 124, 12, role="ppe_callout", beat_id=b0)
    self.draw_check_mark(worker_x - self.width * 0.118, head_y - self.height * 0.010, self.green, cursor + 133, 9, 0.55, b0)
    self.add_text("反光背心", worker_x - self.width * 0.292, torso_y + self.height * 0.128, self.body_size, self.green, cursor + 136, 20, self.width * 0.16, max_chars=4, beat_id=b0)
    self.add_arrow(_curve_points(worker_x - self.width * 0.135, torso_y + self.height * 0.155, worker_x - self.width * 0.040, torso_y + self.height * 0.160, count=8, wave=self.height * 0.015), self.green, 4, cursor + 152, 12, role="ppe_callout", beat_id=b0)
    self.draw_check_mark(worker_x - self.width * 0.118, torso_y + self.height * 0.155, self.green, cursor + 161, 9, 0.55, b0)
    self.add_text("防护鞋", worker_x - self.width * 0.248, torso_y + body_h + self.height * 0.122, self.body_size, self.red, cursor + 164, 18, self.width * 0.12, max_chars=3, beat_id=b0)
    self.add_arrow(_curve_points(worker_x - self.width * 0.118, torso_y + body_h + self.height * 0.130, worker_x - self.width * 0.070, torso_y + body_h + self.height * 0.152, count=7, wave=-self.height * 0.010), self.red, 4, cursor + 178, 10, role="ppe_callout", beat_id=b0)
    self.draw_check_mark(worker_x - self.width * 0.118, torso_y + body_h + self.height * 0.132, self.green, cursor + 187, 9, 0.55, b0)
    cursor += 194

    tray_x = self.board_center_x + self.width * 0.120
    tray_y = self.diagram_top + self.height * 0.260
    tray_w = self.width * 0.270
    tray_h = self.height * 0.235
    self.add_stroke("tool_tray", _rect_points(tray_x, tray_y, tray_w, tray_h), self.ink, 5, cursor, 16, close=True, beat_id=b1)
    radio_x = tray_x + tray_w * 0.12
    radio_y = tray_y + tray_h * 0.18
    self.add_stroke("tool_radio", _rect_points(radio_x, radio_y, tray_w * 0.20, tray_h * 0.48), self.blue, 4, cursor + 16, 12, close=True, beat_id=b1)
    self.add_stroke("tool_radio_antenna", _line_points(radio_x + tray_w * 0.16, radio_y, radio_x + tray_w * 0.22, radio_y - tray_h * 0.18, count=4), self.blue, 3, cursor + 27, 7, beat_id=b1)
    self.add_stroke("tool_wrench", _line_points(tray_x + tray_w * 0.43, tray_y + tray_h * 0.58, tray_x + tray_w * 0.68, tray_y + tray_h * 0.28, count=7), self.violet, 5, cursor + 36, 12, beat_id=b1)
    self.add_stroke("tool_flashlight", _line_points(tray_x + tray_w * 0.70, tray_y + tray_h * 0.66, tray_x + tray_w * 0.88, tray_y + tray_h * 0.52, count=5), self.green, 7, cursor + 46, 10, beat_id=b1)
    self.add_text("对讲机", radio_x - self.width * 0.010, radio_y + tray_h * 0.58, max(18, self.body_size - 6), self.blue, cursor + 58, 16, tray_w * 0.27, max_chars=3, beat_id=b1)
    self.add_text("工具清点", tray_x + tray_w * 0.32, tray_y - self.height * 0.070, self.body_size, self.violet, cursor + 70, 20, self.width * 0.14, emphasis=True, max_chars=4, beat_id=b1)
    self.draw_check_mark(tray_x + tray_w * 0.88, tray_y - self.height * 0.043, self.green, cursor + 86, 12, 0.90, b1)
    self.add_text(self.annotation_label("checkmark", "齐全"), tray_x + tray_w * 0.88 + self.width * 0.025, tray_y - self.height * 0.070, self.body_size, self.green, cursor + 96, 18, self.width * 0.10, max_chars=2, beat_id=b1)
    self.add_teacher_takeaway("逐项点名", tray_x + tray_w * 0.48, tray_y + tray_h + self.height * 0.035, self.violet, cursor + 108, b1, max_chars=4)

    missing_x = tray_x + tray_w * 0.76
    missing_y = tray_y + tray_h * 0.77
    self.add_stroke("missing_slot", _line_points(missing_x - self.width * 0.035, missing_y, missing_x + self.width * 0.035, missing_y, count=4), self.red, 4, cursor + 142, 8, beat_id=b2)
    self.draw_cross_mark(missing_x + self.width * 0.058, missing_y, self.red, cursor + 150, 12, 0.85, b2)
    self.add_text(self.annotation_label("crossout", "缺项即停"), tray_x + tray_w * 0.42, tray_y + tray_h + self.height * 0.095, self.body_size, self.red, cursor + 162, 22, self.width * 0.18, emphasis=True, max_chars=4, beat_id=b2)
    self.draw_risk_rays(tray_x + tray_w * 0.36, tray_y + tray_h + self.height * 0.115, self.red, cursor + 180, direction=-1, beat_id=b2)
    return cursor + 202

def build_railway_minute_review(self, start: int) -> int:
    cursor = start
    b0 = self.beat_id_for(0)
    b1 = self.beat_id_for(1)
    b2 = self.beat_id_for(2)
    route_label = self.annotation_label("route_trace", "复核路径")
    route_points = _curve_points(
        self.board_center_x - self.width * 0.36,
        self.diagram_top + self.height * 0.43,
        self.board_center_x + self.width * 0.18,
        self.diagram_top + self.height * 0.25,
        count=28,
        wave=-self.height * 0.090,
    )
    self.add_arrow(route_points, self.green, 6, cursor, 28, role="minute_review_route", beat_id=b0)
    self.add_text(route_label, self.board_center_x - self.width * 0.365, self.diagram_top + self.height * 0.315, self.body_size, self.green, cursor + 26, 20, self.width * 0.16, emphasis=True, max_chars=4, beat_id=b0)
    cursor += 50
    labels = ["人", "证", "令", "物", "路", "护"]
    checkpoint_indices = [1, 6, 11, 16, 21, 26]
    for index, label in enumerate(labels):
        point = route_points[checkpoint_indices[index]]
        color = [self.blue, self.violet, self.red, self.green, self.blue, self.violet][index]
        self.add_stroke("review_checkpoint", _circle_points(point["x"], point["y"], self.width * 0.030, self.height * 0.040, count=16), color, 4, cursor, 10, beat_id=b0)
        self.add_text(label, point["x"] - self.width * 0.012, point["y"] - self.height * 0.024, self.body_size, color, cursor + 8, 12, self.width * 0.04, max_chars=1, beat_id=b0)
        cursor += 13
    self.add_text("人证令物路护", self.board_center_x - self.width * 0.330, self.diagram_top + self.height * 0.555, max(22, self.body_size - 4), self.violet, cursor + 4, 18, self.width * 0.20, emphasis=True, max_chars=6, beat_id=b0)
    self.add_arrow(_curve_points(self.board_center_x - self.width * 0.195, self.diagram_top + self.height * 0.555, self.board_center_x - self.width * 0.075, self.diagram_top + self.height * 0.485, count=10, wave=-self.height * 0.016), self.violet, 4, cursor + 18, 12, role="review_legend_link", beat_id=b0)
    cursor += 38

    split_x = route_points[-1]["x"] + self.width * 0.035
    split_y = route_points[-1]["y"]
    go_x = split_x + self.width * 0.190
    go_y = split_y - self.height * 0.095
    stop_x = split_x + self.width * 0.190
    stop_y = split_y + self.height * 0.130
    self.add_arrow(_curve_points(split_x, split_y, go_x - self.width * 0.045, go_y, count=12, wave=-self.height * 0.040), self.green, 5, cursor, 16, role="review_go", beat_id=b1)
    self.add_stroke("go_gate", _rect_points(go_x - self.width * 0.040, go_y - self.height * 0.045, self.width * 0.105, self.height * 0.090), self.green, 4, cursor + 14, 12, close=True, beat_id=b1)
    self.add_text(self.annotation_label("short_arrow", "上道"), go_x - self.width * 0.022, go_y - self.height * 0.026, self.body_size, self.green, cursor + 24, 16, self.width * 0.08, max_chars=2, beat_id=b1)
    self.draw_check_mark(go_x + self.width * 0.090, go_y, self.green, cursor + 36, 10, 0.75, b1)
    cursor += 52

    self.add_arrow(_curve_points(split_x, split_y + self.height * 0.020, stop_x - self.width * 0.048, stop_y, count=12, wave=self.height * 0.044), self.red, 5, cursor, 16, role="review_stop", beat_id=b2)
    self.add_stroke("stop_bar", _line_points(stop_x - self.width * 0.055, stop_y - self.height * 0.045, stop_x + self.width * 0.055, stop_y + self.height * 0.045, count=6), self.red, 6, cursor + 14, 10, beat_id=b2)
    self.add_text(self.annotation_label("risk_ray", "停止上道"), stop_x + self.width * 0.010, stop_y + self.height * 0.060, self.body_size, self.red, cursor + 24, 18, self.width * 0.16, emphasis=True, max_chars=4, beat_id=b2)
    self.draw_risk_rays(stop_x + self.width * 0.115, stop_y + self.height * 0.020, self.red, cursor + 40, direction=1, beat_id=b2)
    self.add_text(self.annotation_label("side_label", "不符即停"), self.board_center_x - self.width * 0.055, self.diagram_top + self.height * 0.655, self.body_size + 2, self.blue, cursor + 56, 22, self.width * 0.15, emphasis=True, max_chars=4, beat_id=b2)
    self.draw_wavy_underline(self.board_center_x - self.width * 0.056, self.diagram_top + self.height * 0.720, self.width * 0.135, self.yellow, cursor + 76, 12, b2)
    self.add_teacher_takeaway("一分钟内说清", self.board_center_x - self.width * 0.185, self.diagram_top + self.height * 0.690, self.violet, cursor + 88, b2, max_chars=6)
    return cursor + 128



FallbackSceneBuilder.build_railway_permission_gate = build_railway_permission_gate
FallbackSceneBuilder.build_railway_contact_loop = build_railway_contact_loop
FallbackSceneBuilder.build_railway_ppe_check = build_railway_ppe_check
FallbackSceneBuilder.build_railway_minute_review = build_railway_minute_review
