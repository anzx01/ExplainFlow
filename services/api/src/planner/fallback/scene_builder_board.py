import re
import math
from .scene_builder_base import FallbackSceneBuilder
from .geometry import _point, _line_points, _curve_points, _rect_points, _circle_points, _arc_points, _short_text
from .scene_info import _contains_any
from ..coverage.corpus import _scene_corpus
from ..storyboard_gen.normalizer import _looks_like_mojibake


def build_teaching_board(self, start: int) -> int:
    cursor = start
    labels = self.core_lines[:]
    if self.scene.diagram_plan and self.scene.diagram_plan.required_labels:
        labels = [_short_text(label, 18) for label in self.scene.diagram_plan.required_labels if _short_text(label, 18)]
    for beat in getattr(self.scene, "visual_beats", []) or []:
        for label in beat.required_labels or []:
            short = _short_text(label, 18)
            if short and short not in labels:
                labels.append(short)
        if len(labels) >= 6:
            break
    if not labels:
        labels = [_short_text(self.scene.title, 18), "原因", "过程", "结果"]
    labels = labels[:6]
    corpus = _scene_corpus(self.scene)

    def build_visual_synthesis(start_frame: int) -> int:
        local_labels = [label for label in labels if label and not _looks_like_mojibake(label)]
        synthesis_defaults = ["\u5168\u5c40", "\u7ed3\u6784", "\u53d6\u820d", "\u884c\u52a8", "\u53cd\u9988"]
        for default in synthesis_defaults:
            if len(local_labels) >= 5:
                break
            if default not in local_labels:
                local_labels.append(default)
        local_labels = local_labels[:5]
        cursor_local = start_frame
        cx = self.board_center_x
        cy = self.diagram_top + self.height * 0.25
        hub_rx = self.width * 0.080
        hub_ry = self.height * 0.062
        cursor_local = self.add_node_circle(local_labels[0], cx, cy, hub_rx, hub_ry, cursor_local, self.blue, role="synthesis_hub", font_size=max(18, self.body_size - 5))
        positions = [
            (cx - self.width * 0.24, cy - self.height * 0.12, self.red, "warning_icon"),
            (cx + self.width * 0.24, cy - self.height * 0.12, self.violet, "gear_icon"),
            (cx + self.width * 0.23, cy + self.height * 0.15, self.green, "route_icon"),
            (cx - self.width * 0.23, cy + self.height * 0.15, self.yellow, "loop_icon"),
        ]
        for index, (px, py, color, role_name) in enumerate(positions):
            label = local_labels[index + 1] if index + 1 < len(local_labels) else synthesis_defaults[index + 1]
            self.add_arrow(
                _curve_points(cx + (hub_rx if px > cx else -hub_rx), cy, px + (self.width * 0.054 if px < cx else -self.width * 0.054), py, count=13, wave=self.height * 0.018 * (1 if index % 2 == 0 else -1)),
                self.ink,
                3,
                cursor_local,
                12,
                role="synthesis_link",
            )
            cursor_local += 14
            cursor_local = self.add_node_box(label, px - self.width * 0.060, py - self.height * 0.036, self.width * 0.12, self.height * 0.072, cursor_local, color if color != self.yellow else self.ink, role=role_name, font_size=max(17, self.body_size - 8))
            if index == 0:
                tri = [_point(px, py - self.height * 0.075), _point(px + self.width * 0.038, py - self.height * 0.010), _point(px - self.width * 0.038, py - self.height * 0.010), _point(px, py - self.height * 0.075)]
                self.add_stroke("warning_triangle", tri, self.red, 3, cursor_local, 9, close=True)
                cursor_local += 10
            elif index == 1:
                self.add_stroke("gear_ring", _circle_points(px, py - self.height * 0.070, self.width * 0.028, self.height * 0.032, count=18), self.violet, 3, cursor_local, 9)
                for spoke in range(4):
                    angle = spoke * math.pi / 2
                    self.add_stroke("gear_tooth", _line_points(px + math.cos(angle) * self.width * 0.032, py - self.height * 0.070 + math.sin(angle) * self.height * 0.036, px + math.cos(angle) * self.width * 0.047, py - self.height * 0.070 + math.sin(angle) * self.height * 0.050, count=3), self.violet, 3, cursor_local + 4, 5)
                cursor_local += 12
            elif index == 2:
                mini_path = _curve_points(px - self.width * 0.046, py + self.height * 0.066, px + self.width * 0.052, py + self.height * 0.044, count=9, wave=self.height * 0.020)
                self.add_arrow(mini_path, self.green, 3, cursor_local, 10, role="mini_route")
                cursor_local += 12
            else:
                self.add_arrow(_arc_points(px, py + self.height * 0.058, self.width * 0.044, self.height * 0.034, -math.pi * 0.2, math.pi * 1.25, count=12), self.blue, 3, cursor_local, 11, role="mini_loop")
                cursor_local += 13
        self.add_stroke("synthesis_orbit", _arc_points(cx, cy, self.width * 0.315, self.height * 0.235, -math.pi * 0.83, math.pi * 0.22, count=22), self.green, 4, cursor_local, 18)
        cursor_local += 22
        self.add_text(local_labels[-1], cx - self.width * 0.070, cy + self.height * 0.250, self.body_size, self.violet, cursor_local, 24, self.width * 0.20, emphasis=True, max_chars=10)
        cursor_local += 28
        self.add_stroke("synthesis_underline", _curve_points(cx - self.width * 0.08, cy + self.height * 0.325, cx + self.width * 0.09, cy + self.height * 0.318, count=10, wave=self.height * 0.005), self.yellow, 4, cursor_local, 9)
        return cursor_local + 10

    if _contains_any(corpus, ["summary", "checklist", "recap", "conclusion", "\u603b\u7ed3", "\u6e05\u5355", "\u590d\u76d8"]):
        return build_visual_synthesis(start)

    if _contains_any(corpus, ["summary", "checklist", "总结", "清单", "复盘"]):
        summary_defaults = ["看全局", "拆结构", "做取舍", "走目标", "跑反馈"]
        labels = [label for label in labels if label and not _looks_like_mojibake(label)]
        for default in summary_defaults:
            if len(labels) >= 5:
                break
            if default not in labels:
                labels.append(default)
        labels = labels[:5]
        x = self.board_center_x - self.width * 0.25
        y = self.diagram_top + self.height * 0.07
        row_gap = self.height * 0.078
        self.add_stroke("summary_frame", _rect_points(x - self.width * 0.025, y - self.height * 0.025, self.width * 0.50, row_gap * (len(labels) + 0.8)), self.ink, 4, cursor, 18, close=True)
        cursor += 20
        for index, label in enumerate(labels):
            row_y = y + index * row_gap
            check = [
                _point(x, row_y + self.body_size * 0.45),
                _point(x + self.width * 0.012, row_y + self.body_size * 0.72),
                _point(x + self.width * 0.038, row_y + self.body_size * 0.10),
            ]
            self.add_stroke("check", check, self.green, 4, cursor, 8)
            self.add_text(label, x + self.width * 0.055, row_y, self.body_size, self.ink if index % 2 else self.blue, cursor + 6, 24, self.width * 0.38, emphasis=index == len(labels) - 1, max_chars=18)
            cursor += 32
        self.add_stroke("summary_underline", _curve_points(x + self.width * 0.05, y + row_gap * len(labels) + 8, x + self.width * 0.40, y + row_gap * len(labels) + 4, count=12, wave=self.height * 0.006), self.yellow, 4, cursor, 10)
        return cursor + 14

    if _contains_any(corpus, ["comparison", "compare", "versus", " vs ", "before", "after", "对比", "状态"]):
        return self.build_comparison_transform(start)

    if _contains_any(corpus, ["process", "flow", "mechanism", "过程", "流程", "步骤", "变化", "机制"]):
        return self.build_process_flow(start)

    center_label = labels[0]
    cx = self.board_center_x
    cy = self.diagram_top + self.height * 0.24
    center_rx = self.width * 0.105
    center_ry = self.height * 0.070
    cursor = self.add_node_circle(center_label, cx, cy, center_rx, center_ry, cursor, self.blue, role="center", font_size=max(20, self.body_size - 2))
    branch_labels = labels[1:] if len(labels) > 1 else ["现象", "原因", "结果", "例子"]
    positions = [
        (cx - self.width * 0.24, cy - self.height * 0.13, self.red),
        (cx + self.width * 0.24, cy - self.height * 0.12, self.green),
        (cx - self.width * 0.22, cy + self.height * 0.16, self.violet),
        (cx + self.width * 0.22, cy + self.height * 0.16, self.yellow),
        (cx, cy + self.height * 0.24, self.blue),
    ]
    for index, label in enumerate(branch_labels[:5]):
        bx, by, color = positions[index]
        self.add_arrow(_curve_points(cx + (center_rx if bx > cx else -center_rx), cy, bx + (self.width * 0.055 if bx < cx else -self.width * 0.055), by, count=12, wave=self.height * 0.018 * (1 if index % 2 == 0 else -1)), self.ink, 3, cursor, 12, role="relation")
        cursor += 14
        cursor = self.add_node_box(label, bx - self.width * 0.055, by - self.height * 0.035, self.width * 0.11, self.height * 0.07, cursor, color if color != self.yellow else self.ink, role="branch", font_size=max(18, self.body_size - 7))
        if index in {0, len(branch_labels[:5]) - 1}:
            self.add_stroke("emphasis", _curve_points(bx - self.width * 0.045, by + self.height * 0.052, bx + self.width * 0.045, by + self.height * 0.052, count=8, wave=self.height * 0.004), self.yellow, 4, cursor, 8)
            cursor += 9
    self.add_stroke("teacher_mark", _circle_points(cx + center_rx * 0.06, cy, center_rx * 1.14, center_ry * 1.22, count=28), self.yellow, 4, cursor, 14)
    cursor += 16
    self.add_process_doodles(cursor, cx + self.width * 0.31, cy + self.height * 0.14)
    return min(self.duration - 8, cursor + 40)


FallbackSceneBuilder.build_teaching_board = build_teaching_board
