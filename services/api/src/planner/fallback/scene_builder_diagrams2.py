import math
from .scene_builder_base import FallbackSceneBuilder
from .geometry import _point, _line_points, _curve_points, _rect_points, _circle_points
from ..coverage.corpus import _scene_corpus
from .scene_info import _contains_any
from .scene_diagram import _visual_relation_kind_for_scene
from ..storyboard_gen.normalizer import _clean_text


def build_interaction_scenario(self, start: int) -> int:
    cursor = start
    corpus_local = _scene_corpus(self.scene)
    relation_kind = _visual_relation_kind_for_scene(self.scene)
    x = self.board_center_x - self.width * 0.30
    y = self.diagram_top + self.height * 0.12
    panel_w = self.width * 0.22
    panel_h = self.height * 0.25

    def draw_person(cx: float, cy: float, color: str, label: str, start_frame: int) -> int:
        local = start_frame
        self.add_stroke("person", _circle_points(cx, cy, self.width * 0.028, self.height * 0.045, count=18), color, 4, local, 10)
        local += 11
        self.add_stroke("person", _line_points(cx, cy + self.height * 0.045, cx, cy + self.height * 0.14, count=5), color, 4, local, 8)
        self.add_stroke("person", _line_points(cx - self.width * 0.045, cy + self.height * 0.085, cx + self.width * 0.045, cy + self.height * 0.085, count=5), color, 4, local + 5, 8)
        self.add_stroke("person", _line_points(cx, cy + self.height * 0.14, cx - self.width * 0.040, cy + self.height * 0.20, count=4), color, 4, local + 10, 8)
        self.add_stroke("person", _line_points(cx, cy + self.height * 0.14, cx + self.width * 0.040, cy + self.height * 0.20, count=4), color, 4, local + 15, 8)
        self.add_text(label, cx - self.width * 0.060, cy + self.height * 0.225, max(18, self.body_size - 6), color, local + 18, 18, self.width * 0.14, max_chars=8)
        return local + 42

    relation_mode = relation_kind == "interaction_scenario" or _contains_any(
        corpus_local,
        [
            "collabor",
            "communication",
            "team",
            "沟通",
            "合作",
            "协作",
            "交流",
            "互相",
            "互动",
            "关系",
            "交换",
            "共同",
            "双方",
        ],
    )
    renewal_mode = relation_kind == "feedback_loop" or _contains_any(corpus_local, ["renew", "growth", "sharpen", "improve", "更新", "成长", "复盘", "精进", "循环", "闭环", "迭代"])
    goal_mode = relation_kind == "goal_path" or _contains_any(corpus_local, ["goal", "end", "target", "vision", "目标", "愿景", "路径", "路线", "里程碑", "倒推"])

    if relation_mode:
        left_end = draw_person(x + panel_w * 0.40, y + panel_h * 0.26, self.blue, self.fallback_label(0, "A"), cursor)
        right_end = draw_person(x + panel_w * 1.75, y + panel_h * 0.26, self.green, self.fallback_label(1, "B"), cursor + 10)
        cursor = max(left_end, right_end)
        bubble_y = y + panel_h * 0.06
        self.add_stroke("speech", _circle_points(x + panel_w * 0.63, bubble_y, self.width * 0.070, self.height * 0.052, count=20), self.blue, 3, cursor, 12)
        self.add_text(self.fallback_label(2, "输入"), x + panel_w * 0.55, bubble_y - self.height * 0.020, max(18, self.body_size - 7), self.blue, cursor + 8, 16, self.width * 0.14, max_chars=8)
        self.add_stroke("speech", _circle_points(x + panel_w * 1.47, bubble_y, self.width * 0.070, self.height * 0.052, count=20), self.green, 3, cursor + 14, 12)
        self.add_text(self.fallback_label(3, "反馈"), x + panel_w * 1.39, bubble_y - self.height * 0.020, max(18, self.body_size - 7), self.green, cursor + 22, 16, self.width * 0.14, max_chars=8)
        cursor += 42
        self.add_arrow(_curve_points(x + panel_w * 0.70, y + panel_h * 0.50, x + panel_w * 1.48, y + panel_h * 0.50, count=14, wave=self.height * 0.030), self.red, 4, cursor, 16, role="mutual_path")
        self.add_arrow(_curve_points(x + panel_w * 1.42, y + panel_h * 0.59, x + panel_w * 0.76, y + panel_h * 0.59, count=14, wave=-self.height * 0.022), self.violet, 4, cursor + 12, 16, role="mutual_path")
        cursor += 34
        self.add_text(self.fallback_label(4, "共同结果"), x + panel_w * 0.83, y + panel_h * 0.78, self.body_size, self.violet, cursor, 24, self.width * 0.22, emphasis=True, max_chars=12)
        self.add_stroke("emphasis", _curve_points(x + panel_w * 0.83, y + panel_h * 0.92, x + panel_w * 1.25, y + panel_h * 0.92, count=10, wave=self.height * 0.005), self.yellow, 4, cursor + 20, 8)
        return cursor + 40

    if renewal_mode:
        cx = self.board_center_x
        cy = y + panel_h * 0.36
        nodes = [
            (self.fallback_label(0, "身体"), cx, cy - self.height * 0.15, self.blue),
            (self.fallback_label(1, "智力"), cx + self.width * 0.18, cy, self.green),
            (self.fallback_label(2, "情感"), cx, cy + self.height * 0.15, self.violet),
            (self.fallback_label(3, "精神"), cx - self.width * 0.18, cy, self.red),
        ]
        for label, nx, ny, color in nodes:
            cursor = self.add_node_circle(label, nx, ny, self.width * 0.055, self.height * 0.048, cursor, color, font_size=max(18, self.body_size - 7))
        for start_angle, end_angle in [(-math.pi * 0.45, math.pi * 0.05), (math.pi * 0.05, math.pi * 0.55), (math.pi * 0.55, math.pi * 1.05), (math.pi * 1.05, math.pi * 1.55)]:
            self.add_arrow(_arc_points(cx, cy, self.width * 0.22, self.height * 0.19, start_angle, end_angle, count=12), self.ink, 4, cursor, 12, role="renew_loop")
            cursor += 15
        self.add_text(self.fallback_label(4, "持续更新"), cx - self.width * 0.075, cy - self.height * 0.020, self.body_size, self.violet, cursor, 24, self.width * 0.18, emphasis=True, max_chars=10)
        return cursor + 34

    if goal_mode:
        person_end = draw_person(x + panel_w * 0.28, y + panel_h * 0.34, self.blue, self.fallback_label(0, "现在"), cursor)
        cursor = max(cursor + 36, person_end)
        target_x = x + panel_w * 1.55
        target_y = y + panel_h * 0.32
        self.add_stroke("target", _circle_points(target_x, target_y, self.width * 0.085, self.height * 0.085, count=24), self.red, 4, cursor, 12)
        self.add_stroke("target", _circle_points(target_x, target_y, self.width * 0.050, self.height * 0.050, count=18), self.red, 3, cursor + 10, 10)
        self.add_stroke("target", _circle_points(target_x, target_y, self.width * 0.018, self.height * 0.018, count=12), self.red, 3, cursor + 18, 8)
        self.add_text(self.fallback_label(1, "目标"), target_x - self.width * 0.050, target_y + self.height * 0.105, self.body_size, self.red, cursor + 20, 18, self.width * 0.12, max_chars=8)
        cursor += 40
        self.add_arrow(_curve_points(x + panel_w * 0.44, y + panel_h * 0.48, target_x - self.width * 0.095, target_y, count=14, wave=self.height * 0.040), self.green, 4, cursor, 18, role="path")
        self.add_text(self.fallback_label(2, "倒推行动"), x + panel_w * 0.80, y + panel_h * 0.12, self.body_size, self.violet, cursor + 12, 24, self.width * 0.20, emphasis=True, max_chars=10)
        return cursor + 44

    left_x = x
    mid_x = x + panel_w * 0.98
    right_x = x + panel_w * 1.96
    cursor = self.add_node_box(self.fallback_label(0, "输入"), left_x, y + panel_h * 0.20, panel_w * 0.62, panel_h * 0.28, cursor, self.red, font_size=max(18, self.body_size - 6))
    self.add_arrow(_line_points(left_x + panel_w * 0.66, y + panel_h * 0.34, mid_x - 16, y + panel_h * 0.34, count=6), self.ink, 4, cursor, 12)
    cursor += 18
    cursor = self.add_node_circle(self.fallback_label(1, "转换"), mid_x + panel_w * 0.15, y + panel_h * 0.34, self.width * 0.065, self.height * 0.060, cursor, self.blue, font_size=max(18, self.body_size - 6))
    self.add_arrow(_line_points(mid_x + panel_w * 0.30, y + panel_h * 0.34, right_x - 16, y + panel_h * 0.34, count=6), self.green, 4, cursor, 12)
    cursor += 18
    cursor = self.add_node_box(self.fallback_label(2, "输出"), right_x, y + panel_h * 0.20, panel_w * 0.62, panel_h * 0.28, cursor, self.green, font_size=max(18, self.body_size - 6))
    self.add_text(self.fallback_label(3, "关键关系"), mid_x + panel_w * 0.02, y + panel_h * 0.60, self.body_size, self.violet, cursor, 24, self.width * 0.20, emphasis=True, max_chars=10)
    return cursor + 40


FallbackSceneBuilder.build_interaction_scenario = build_interaction_scenario
