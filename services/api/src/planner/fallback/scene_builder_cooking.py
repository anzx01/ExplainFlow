"""Deterministic cooking diagrams with real draw-op paths."""
from __future__ import annotations

import math

from .geometry import _arc_points, _circle_points, _line_points, _rect_points


def _rounded_rect(x, y, w, h, radius=24, count=8):
    points = []
    for cx, cy, start in [(x + radius, y + radius, math.pi), (x + w - radius, y + radius, -math.pi / 2), (x + w - radius, y + h - radius, 0), (x + radius, y + h - radius, math.pi / 2)]:
        points.extend({"x": cx + math.cos(start + i * math.pi / 2 / count) * radius, "y": cy + math.sin(start + i * math.pi / 2 / count) * radius} for i in range(count + 1))
    return points


def _add_food_label(self, text, x, y, cursor, color=None):
    self.add_text(text, x, y, self.body_size, color or self.blue, cursor, 28, emphasis=True, max_width=self.width * 0.22, max_chars=12)
    return cursor + 32


def build_cooking_ingredients(self, start: int) -> int:
    cursor = start
    cx, cy = self.width * 0.28, self.height * 0.48
    self.add_stroke("bowl", _arc_points(cx, cy, self.width * .16, self.height * .10, 0, math.pi, count=20), self.ink, 5, cursor, 16); cursor += 16
    self.add_stroke("bowl_base", _line_points(cx - self.width*.16, cy, cx + self.width*.16, cy, count=8), self.ink, 5, cursor, 8); cursor += 8
    for i in range(5):
        self.add_stroke("flour", _circle_points(cx - self.width*.08 + i*self.width*.04, cy - self.height*.04 - (i%2)*10, self.width*.018, self.height*.014, count=10), self.ink, 3, cursor, 7); cursor += 6
    self.add_stroke("water", _line_points(cx + self.width*.28, cy - self.height*.20, cx + self.width*.28, cy - self.height*.05, count=8), self.blue, 5, cursor, 10); cursor += 10
    self.add_stroke("chopsticks", _line_points(cx - self.width*.08, cy - self.height*.13, cx + self.width*.10, cy - self.height*.02, count=10), self.ink, 4, cursor, 12); cursor += 10
    self.add_stroke("chopsticks", _line_points(cx - self.width*.02, cy - self.height*.15, cx + self.width*.13, cy - self.height*.01, count=10), self.ink, 4, cursor, 12); cursor += 10
    self.add_stroke("mixing", _arc_points(cx, cy - self.height*.02, self.width*.08, self.height*.045, 0, 2*math.pi, count=24), self.blue, 4, cursor, 14); cursor += 12
    self.add_stroke("dough", _circle_points(cx + self.width*.56, cy, self.width*.09, self.height*.065, count=18), self.yellow, 5, cursor, 14); cursor += 14
    self.add_stroke("dough_fold", _arc_points(cx + self.width*.56, cy, self.width*.055, self.height*.04, math.pi*.15, math.pi*1.2, count=16), self.green, 3, cursor, 8); cursor += 8
    cursor = _add_food_label(self, "面粉与水", self.width*.16, self.height*.25, cursor, self.blue)
    cursor = _add_food_label(self, "揉成面团", self.width*.57, self.height*.25, cursor, self.green)
    return cursor


def build_cooking_wrappers(self, start: int) -> int:
    cursor = start
    x, y = self.width*.25, self.height*.48
    self.add_stroke("dough_rope", _line_points(x, y, x + self.width*.42, y, count=18), self.ink, 8, cursor, 24); cursor += 24
    for i in range(5):
        px = x + self.width*.08 + i*self.width*.08
        self.add_stroke("dough_piece", _circle_points(px, y + self.height*.15, self.width*.035, self.height*.025, count=14), self.yellow, 4, cursor, 8); cursor += 7
        self.add_stroke("cut", _line_points(px - self.width*.018, y - self.height*.03, px - self.width*.018, y + self.height*.04, count=5), self.red, 3, cursor, 5); cursor += 4
    self.add_stroke("rolling_pin", _line_points(self.width*.60, self.height*.42, self.width*.82, self.height*.42, count=12), self.ink, 8, cursor, 18); cursor += 18
    self.add_stroke("rolling_pin_handle", _line_points(self.width*.57, self.height*.39, self.width*.60, self.height*.42, count=5), self.ink, 5, cursor, 6); cursor += 5
    self.add_stroke("rolling_pin_handle", _line_points(self.width*.82, self.height*.42, self.width*.86, self.height*.39, count=5), self.ink, 5, cursor, 6); cursor += 5
    self.add_stroke("wrapper", _circle_points(self.width*.71, self.height*.62, self.width*.12, self.height*.07, count=28), self.blue, 5, cursor, 20); cursor += 20
    cursor = _add_food_label(self, "搓条、切剂子", self.width*.16, self.height*.25, cursor, self.blue)
    return _add_food_label(self, "擀成圆面皮", self.width*.60, self.height*.25, cursor, self.green)


def build_cooking_wrapping(self, start: int) -> int:
    cursor = start
    cx, cy = self.width*.52, self.height*.55
    wrapper_rx, wrapper_ry = self.width*.28, self.height*.17
    self.add_stroke("wrapper", _circle_points(cx, cy, wrapper_rx, wrapper_ry, count=30), self.blue, 6, cursor, 18); cursor += 18
    self.add_stroke("filling", _circle_points(cx, cy, self.width*.075, self.height*.05, count=18), self.red, 5, cursor, 12); cursor += 12
    self.add_stroke("spoon", _line_points(cx - self.width*.28, cy - self.height*.24, cx - self.width*.07, cy - self.height*.04, count=10), self.ink, 4, cursor, 12); cursor += 10
    self.add_stroke("spoon_bowl", _circle_points(cx - self.width*.28, cy - self.height*.24, self.width*.045, self.height*.028, count=14), self.ink, 3, cursor, 7); cursor += 6
    fold = _arc_points(cx, cy, wrapper_rx, wrapper_ry, math.pi, 2*math.pi, count=22)
    self.add_stroke("folded_wrapper", fold, self.ink, 6, cursor, 20); cursor += 20
    for i in range(6):
        px = cx - self.width*.18 + i*self.width*.072
        self.add_stroke("pleat", _line_points(px, cy - self.height*.07, px + self.width*.018, cy - self.height*.095, count=4), self.green, 4, cursor, 6); cursor += 5
        self.add_stroke("finger", _arc_points(px + self.width*.012, cy - self.height*.11, self.width*.022, self.height*.012, 0, math.pi, count=8), self.red, 3, cursor, 5); cursor += 4
    cursor = _add_food_label(self, "放馅", self.width*.23, self.height*.28, cursor, self.red)
    cursor = _add_food_label(self, "对折", self.width*.46, self.height*.28, cursor, self.blue)
    return _add_food_label(self, "捏紧边缘", self.width*.66, self.height*.28, cursor, self.green)


def build_cooking_boiling(self, start: int) -> int:
    cursor = start
    x, y, w, h = self.width*.25, self.height*.48, self.width*.50, self.height*.25
    self.add_stroke("pot", _rounded_rect(x, y, w, h, 30, 8), self.ink, 6, cursor, 24); cursor += 24
    self.add_stroke("water", _arc_points(x+w/2, y+h*.25, w*.43, h*.18, math.pi, 2*math.pi, count=24), self.blue, 6, cursor, 18); cursor += 18
    for i in range(5):
        px = x + w*.18 + i*w*.16
        self.add_stroke("dumpling", _circle_points(px, y+h*.28+(i%2)*h*.08, w*.06, h*.045, count=18), self.ink, 4, cursor, 10); cursor += 8
        self.add_stroke("pleat", _line_points(px-w*.025, y+h*.22+(i%2)*h*.08, px, y+h*.18+(i%2)*h*.08, count=4), self.yellow, 3, cursor, 5); cursor += 4
    self.add_stroke("steam", _arc_points(x+w*.32, y-h*.05, w*.03, h*.12, math.pi, 2*math.pi, count=12), self.blue, 3, cursor, 8); cursor += 7
    self.add_stroke("steam", _arc_points(x+w*.52, y-h*.07, w*.03, h*.14, math.pi, 2*math.pi, count=12), self.blue, 3, cursor, 8); cursor += 7
    cursor = _add_food_label(self, "ˮ���¹�", self.width*.22, self.height*.28, cursor, self.blue)
    cursor = _add_food_label(self, "��ˮ��ճ", self.width*.48, self.height*.28, cursor, self.yellow)
    cursor = _add_food_label(self, "�������", self.width*.70, self.height*.28, cursor, self.green)
    return cursor


# Register deterministic cooking builders on the shared fallback builder.
from .scene_builder_base import FallbackSceneBuilder

FallbackSceneBuilder.build_cooking_ingredients = build_cooking_ingredients
FallbackSceneBuilder.build_cooking_wrappers = build_cooking_wrappers
FallbackSceneBuilder.build_cooking_wrapping = build_cooking_wrapping
FallbackSceneBuilder.build_cooking_boiling = build_cooking_boiling
