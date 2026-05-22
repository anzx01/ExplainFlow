import re
import math
from .scene_builder_base import FallbackSceneBuilder
from .geometry import _point, _line_points, _curve_points, _rect_points, _circle_points, _arc_points, _short_text, _text_visual_width
from .scene_info import _contains_any
from ..coverage.corpus import _scene_corpus


def build_chalkboard_derivation(self, start: int) -> int:
    cursor = start
    x = self.width * 0.12
    y = self.height * 0.18
    line_gap = self.height * 0.087
    chalk_size = max(30, int(self.body_size * 1.05))
    lines: list[str] = []
    if scene.diagram_plan and scene.diagram_plan.required_labels:
        lines.extend(scene.diagram_plan.required_labels[:5])
    for animation in scene.animations:
        raw_type = getattr(animation.type, "value", str(animation.type))
        if raw_type in {"write_formula", "formula_reveal"} and (animation.latex or animation.content):
            lines.append(animation.latex or animation.content)
        elif animation.items:
            lines.extend(animation.items[:4])
        elif animation.content:
            lines.append(animation.content)
    for beat in getattr(self.scene, "visual_beats", []) or []:
        if beat.required_labels:
            lines.extend(beat.required_labels[:3])
        elif beat.draw_intent:
            pieces = re.split(r"[。；;,.，、]", beat.draw_intent)
            lines.extend(piece for piece in pieces[:2] if piece.strip())
    if not lines:
        lines = re.split(r"[。；;]", scene.narration)[:6]
    lines = [_short_text(line, 34) for line in lines if _short_text(line, 34)]
    if not lines:
        lines = [_short_text(scene.title, 24), "Known", "Derive", "Conclusion"]
    color_cycle = [self.ink, self.blue, self.green, self.yellow, self.red]
    cursor = max(cursor, 12)
    for index, line in enumerate(lines[:7]):
        line_y = y + index * line_gap
        color = color_cycle[index % len(color_cycle)]
        frames = max(24, min(54, int(len(line) * 2.2)))
        self.add_text(line, x + (self.width * 0.035 if index % 2 else 0), line_y, chalk_size, color, cursor, frames, self.width * 0.78, emphasis=index in {0, len(lines[:7]) - 1}, max_chars=34)
        cursor += frames + 10
        if index in {0, 2, 4} and cursor + 10 < self.duration - 10:
            underline_y = line_y + chalk_size * 1.05
            self.add_stroke(
                "chalk_underline",
                _line_points(x, underline_y, min(self.width * 0.86, x + _text_visual_width(line, chalk_size) * 0.62), underline_y, count=8),
                self.yellow if index == 0 else self.green,
                3,
                cursor,
                8,
            )
            cursor += 10
    return cursor

def build_semiconductor_device(self, start: int) -> int:
    cursor = start
    corpus = _scene_corpus(self.scene)
    x = self.board_center_x - self.width * 0.30
    y = self.diagram_top + self.height * 0.12
    panel_w = self.width * 0.22
    panel_h = self.height * 0.30

    def draw_planar_mos(px: float, py: float, label: str, on_state: bool, start_frame: int) -> int:
        local = start_frame
        self.add_text(label, px, py - self.height * 0.065, max(22, self.body_size - 4), self.green if on_state else self.red, local, 18, panel_w, max_chars=18)
        local += 20
        substrate_y = py + panel_h * 0.58
        self.add_stroke("substrate", _rect_points(px, substrate_y, panel_w, panel_h * 0.18), self.ink, 4, local, 14, close=True)
        local += 16
        source_x = px + panel_w * 0.08
        drain_x = px + panel_w * 0.68
        self.add_stroke("terminal", _rect_points(source_x, py + panel_h * 0.35, panel_w * 0.20, panel_h * 0.21), self.blue, 4, local, 12, close=True)
        self.add_stroke("terminal", _rect_points(drain_x, py + panel_h * 0.35, panel_w * 0.20, panel_h * 0.21), self.blue, 4, local + 8, 12, close=True)
        local += 22
        oxide_y = py + panel_h * 0.28
        self.add_stroke("oxide", _line_points(px + panel_w * 0.32, oxide_y, px + panel_w * 0.68, oxide_y, count=8), self.violet, 4, local, 10)
        self.add_stroke("gate", _rect_points(px + panel_w * 0.38, py + panel_h * 0.12, panel_w * 0.24, panel_h * 0.12), self.ink, 4, local + 8, 12, close=True)
        local += 22
        self.add_text("S", source_x + panel_w * 0.06, py + panel_h * 0.39, max(18, self.body_size - 6), self.blue, local, 10, panel_w * 0.10)
        self.add_text("D", drain_x + panel_w * 0.06, py + panel_h * 0.39, max(18, self.body_size - 6), self.blue, local + 4, 10, panel_w * 0.10)
        self.add_text("G", px + panel_w * 0.45, py + panel_h * 0.13, max(18, self.body_size - 6), self.ink, local + 8, 10, panel_w * 0.10)
        local += 18
        channel_y = py + panel_h * 0.51
        if on_state:
            self.add_stroke("channel", _line_points(px + panel_w * 0.29, channel_y, px + panel_w * 0.73, channel_y, count=12), self.green, 7, local, 16)
            self.add_arrow(_line_points(px + panel_w * 0.30, channel_y + 24, px + panel_w * 0.72, channel_y + 24, count=8), self.red, 4, local + 15, 16, role="current")
            self.add_text("I_D", px + panel_w * 0.47, channel_y + 38, max(16, self.body_size - 10), self.red, local + 28, 12, panel_w * 0.20)
            local += 44
        else:
            self.add_stroke("no_channel", _line_points(px + panel_w * 0.34, channel_y, px + panel_w * 0.65, channel_y, count=5), self.red, 3, local, 8)
            self.add_stroke("no_channel", _line_points(px + panel_w * 0.48, channel_y - 18, px + panel_w * 0.55, channel_y + 18, count=4), self.red, 4, local + 8, 8)
            self.add_stroke("no_channel", _line_points(px + panel_w * 0.55, channel_y - 18, px + panel_w * 0.48, channel_y + 18, count=4), self.red, 4, local + 15, 8)
            local += 28
        return local

    if _contains_any(corpus, ["w_eff", "2h_fin", "cross-section", "cross section", "截面", "有效宽度"]):
        fin_x = x + panel_w * 0.86
        fin_y = y + panel_h * 0.18
        fin_w = self.width * 0.10
        fin_h = self.height * 0.34
        self.add_stroke("fin", _rect_points(fin_x, fin_y, fin_w, fin_h), self.green, 5, cursor, 18, close=True)
        cursor += 20
        gate_points = [
            _point(fin_x - self.width * 0.045, fin_y - self.height * 0.025),
            _point(fin_x - self.width * 0.045, fin_y + fin_h + self.height * 0.025),
            _point(fin_x + fin_w + self.width * 0.045, fin_y + fin_h + self.height * 0.025),
            _point(fin_x + fin_w + self.width * 0.045, fin_y - self.height * 0.025),
        ]
        self.add_stroke("gate_wrap", gate_points, self.violet, 6, cursor, 22)
        cursor += 26
        self.add_arrow(_line_points(fin_x - self.width * 0.10, fin_y + fin_h * 0.48, fin_x - 8, fin_y + fin_h * 0.48, count=7), self.blue, 3, cursor, 12)
        self.add_arrow(_line_points(fin_x + fin_w + self.width * 0.10, fin_y + fin_h * 0.52, fin_x + fin_w + 8, fin_y + fin_h * 0.52, count=7), self.blue, 3, cursor + 8, 12)
        self.add_arrow(_line_points(fin_x + fin_w * 0.5, fin_y - self.height * 0.10, fin_x + fin_w * 0.5, fin_y - 6, count=7), self.blue, 3, cursor + 16, 12)
        cursor += 34
        self.add_text("H_fin", fin_x - self.width * 0.105, fin_y + fin_h * 0.42, self.body_size, self.blue, cursor, 20, self.width * 0.12)
        self.add_text("W_fin", fin_x + fin_w * 0.10, fin_y - self.height * 0.085, self.body_size, self.blue, cursor + 8, 20, self.width * 0.13)
        self.add_text("W_eff = 2H_fin + W_fin", x, y + panel_h + self.height * 0.10, self.body_size, self.violet, cursor + 18, 36, self.width * 0.42)
        cursor += 60
        for offset in [0.18, 0.5, 0.82]:
            self.add_stroke("charge", _circle_points(fin_x + fin_w * offset, fin_y + fin_h * 0.10, 8, 8, count=10), self.red, 3, cursor, 6)
            cursor += 7
        return cursor

    if _contains_any(corpus, ["finfet", "fin channel", "wrap", "三面", "包住", "鳍"]):
        base_y = y + panel_h * 0.64
        fin_x = x + panel_w * 0.55
        fin_y = y + panel_h * 0.18
        self.add_stroke("source", _rect_points(x + panel_w * 0.05, base_y - 40, panel_w * 0.30, 80), self.blue, 4, cursor, 16, close=True)
        self.add_stroke("drain", _rect_points(x + panel_w * 1.15, base_y - 40, panel_w * 0.30, 80), self.blue, 4, cursor + 10, 16, close=True)
        cursor += 28
        self.add_stroke("fin", _rect_points(fin_x, fin_y, panel_w * 0.45, panel_h * 0.55), self.green, 5, cursor, 18, close=True)
        cursor += 22
        self.add_stroke("gate_wrap", _rect_points(fin_x - 28, fin_y + 20, panel_w * 0.56, panel_h * 0.34), self.violet, 6, cursor, 20, close=True)
        cursor += 26
        self.add_text("Source", x + panel_w * 0.06, base_y + 54, self.body_size, self.blue, cursor, 18, self.width * 0.12)
        self.add_text("Drain", x + panel_w * 1.17, base_y + 54, self.body_size, self.blue, cursor + 7, 18, self.width * 0.12)
        self.add_text("Gate wraps 3 sides", fin_x - self.width * 0.04, fin_y - self.height * 0.08, self.body_size, self.violet, cursor + 16, 28, self.width * 0.28)
        cursor += 50
        for side_x in [fin_x - 48, fin_x + panel_w * 0.22, fin_x + panel_w * 0.50]:
            self.add_arrow(_line_points(side_x, fin_y - self.height * 0.06, fin_x + panel_w * 0.22, fin_y + panel_h * 0.20, count=7), self.red, 3, cursor, 12)
            cursor += 13
        return cursor

    if _contains_any(corpus, ["short-channel", "short channel", "短沟道"]):
        left_end = draw_planar_mos(x, y, "Long channel", False, cursor)
        right_x = x + panel_w * 1.25
        cursor = max(left_end, cursor + 70)
        self.add_arrow(_curve_points(x + panel_w + 8, y + panel_h * 0.40, right_x - 24, y + panel_h * 0.40, count=12, wave=self.height * 0.03), self.ink, 4, cursor, 18)
        cursor += 24
        right_end = draw_planar_mos(right_x, y, "Short channel", False, cursor)
        cursor = max(cursor, right_end)
        self.add_arrow(_line_points(right_x + panel_w * 0.12, y + panel_h * 0.50, right_x + panel_w * 0.45, y + panel_h * 0.50, count=7), self.red, 4, cursor, 12)
        self.add_arrow(_line_points(right_x + panel_w * 0.88, y + panel_h * 0.50, right_x + panel_w * 0.55, y + panel_h * 0.50, count=7), self.red, 4, cursor + 8, 12)
        self.add_text("field intrusion", right_x + panel_w * 0.22, y + panel_h * 0.74, self.body_size, self.red, cursor + 18, 24, panel_w * 0.70)
        return cursor + 50

    if _contains_any(corpus, ["off", "on", "v_g", "vth", "v_th", "阈值"]):
        left_end = draw_planar_mos(x, y, "OFF: V_G < V_th", False, cursor)
        right_x = x + panel_w * 1.30
        cursor = max(left_end, cursor + 70)
        self.add_arrow(_curve_points(x + panel_w + 6, y + panel_h * 0.40, right_x - 22, y + panel_h * 0.40, count=16, wave=self.height * 0.035), self.ink, 4, cursor, 18)
        cursor += 24
        right_end = draw_planar_mos(right_x, y, "ON: V_G > V_th", True, cursor)
        return max(cursor, right_end)

    cursor = draw_planar_mos(x + panel_w * 0.35, y, self.fallback_label(0, "MOS structure"), True, cursor)
    self.add_text(self.fallback_label(1, "Gate controls channel"), x, y + panel_h + self.height * 0.09, self.body_size, self.violet, cursor, 30, self.width * 0.42)
    return cursor + 36


FallbackSceneBuilder.build_chalkboard_derivation = build_chalkboard_derivation
FallbackSceneBuilder.build_semiconductor_device = build_semiconductor_device
