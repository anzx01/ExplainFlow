from .scene_builder_base import FallbackSceneBuilder
from .scene_info import _contains_any
from ..coverage.corpus import _scene_corpus
from .scene_extra import _scene_extra
from .draw_ops import _retime_draw_ops_in_window, _retime_draw_ops_to_subtitle_cues, _stretch_audio_segments_for_draw_workload, _retime_draw_ops_to_audio_segments
from ..storyboard_gen.normalizer import _clean_text
import re


def _apply_render_contract(self) -> list[dict]:
    elements = sorted(
        (item for item in self.scene.render_elements
         if not self.raster_reveal_spec or item.source != "generated"),
        key=lambda item: (item.sequence, item.id),
    )
    if not elements:
        return []
    scene_ms = max(1, round(self.scene.duration_estimate * 1000))
    scale = self.duration / max(1, round(scene_ms * self.fps / 1000))
    region_sx = self.width / max(1, self.scene.canvas_width)
    region_sy = self.height / max(1, self.scene.canvas_height)

    def scaled_region(region) -> dict:
        return {
            "x": round(region.x * region_sx, 2),
            "y": round(region.y * region_sy, 2),
            "width": round(region.width * region_sx, 2),
            "height": round(region.height * region_sy, 2),
        }

    def point_in_region(point: dict, region: dict) -> bool:
        return (
            region["x"] <= float(point.get("x", -1)) < region["x"] + region["width"]
            and region["y"] <= float(point.get("y", -1)) < region["y"] + region["height"]
        )

    def path_weight(op: dict) -> float:
        points = op.get("points") or []
        length = 0.0
        for first, second in zip(points, points[1:]):
            dx = float(second.get("x", 0)) - float(first.get("x", 0))
            dy = float(second.get("y", 0)) - float(first.get("y", 0))
            length += (dx * dx + dy * dy) ** 0.5
        return max(1.0, length ** 0.5)

    def schedule_ops(ops: list[dict], start: int, end: int) -> None:
        if not ops:
            return
        weights = [path_weight(op) for op in ops]
        total = sum(weights) or float(len(ops))
        cursor = float(start)
        for index, (op, weight) in enumerate(zip(ops, weights)):
            next_cursor = float(end) if index == len(ops) - 1 else min(float(end), cursor + (end - start) * weight / total)
            op["startFrame"] = round(cursor, 2)
            op["endFrame"] = round(max(cursor + 0.01, next_cursor), 2)
            cursor = next_cursor

    specs: list[dict] = []
    for index, element in enumerate(elements):
        start = round(element.reveal.start_ms * self.fps / 1000 * scale)
        end = round((element.reveal.start_ms + element.reveal.duration_ms) * self.fps / 1000 * scale)
        # Authored time estimates must not override the actual spoken phrase.
        token = re.sub(r"[\W_]+", "", element.subtitle or "")
        cues = self.subtitle_cues
        if token and cues:
            cue_tokens = [re.sub(r"[\W_]+", "", cue["text"]) for cue in cues]
            spoken = "".join(cue_tokens)
            offset = spoken.find(token)
            if offset >= 0 and spoken.find(token, offset + 1) < 0:
                cursor = 0
                matching = []
                for cue, cue_token in zip(cues, cue_tokens):
                    if cursor < offset + len(token) and cursor + len(cue_token) > offset:
                        matching.append(cue)
                    cursor += len(cue_token)
                if matching:
                    start, end = matching[0]["startFrame"], matching[-1]["endFrame"]
        later = [scaled_region(item.region) for item in elements[index + 1 :]]
        specs.append(
            {
                "id": element.id,
                "sequence": element.sequence,
                "parallelGroup": element.parallel_group,
                "startFrame": max(0, start),
                "endFrame": max(start + 1, min(self.duration, end)),
                "region": scaled_region(element.region),
                "laterRegions": later,
                "protectedRegions": [
                    scaled_region(item) for item in element.reveal.protected_regions
                ],
            }
        )
    if not self.draw_ops:
        return specs

    spec_by_id = {spec["id"]: spec for spec in specs}
    op_by_id = {op.get("id"): op for op in self.draw_ops}
    raster_strokes = (self.raster_reveal_spec or {}).get("strokes", []) if self.raster_reveal_spec else []
    raster_op_ids = {
        op_id
        for stroke in raster_strokes
        for op_id in (stroke.get("opId"), stroke.get("colorOpId"))
        if op_id
    }

    # Keep paired ink/color paths on the same semantic element. For legacy
    # raster traces without an explicit assignment, choose the allowed region
    # containing the most sampled path points, preferring later elements in a
    # tie so an overlap cannot leak before its own turn.
    for stroke_index, stroke in enumerate(raster_strokes):
        ink_op = op_by_id.get(stroke.get("opId"))
        color_op = op_by_id.get(stroke.get("colorOpId"))
        assigned_id = next((
            op.get("contractElementId")
            for op in (ink_op, color_op)
            if op and op.get("contractElementId") in spec_by_id
        ), None)
        if not assigned_id and ink_op:
            scored: list[tuple[int, int, str]] = []
            for index, spec in enumerate(specs):
                allowed_points = sum(
                    1 for point in (ink_op.get("points") or [])
                    if point_in_region(point, spec["region"])
                    and not any(point_in_region(point, region) for region in [*spec["laterRegions"], *spec["protectedRegions"]])
                )
                scored.append((allowed_points, index, spec["id"]))
            score, _, candidate = max(scored, default=(0, 0, specs[min(len(specs) - 1, stroke_index * len(specs) // max(1, len(raster_strokes)))]["id"]))
            assigned_id = candidate if score > 0 else specs[min(len(specs) - 1, stroke_index * len(specs) // max(1, len(raster_strokes)))]["id"]
        if assigned_id:
            if ink_op:
                ink_op["contractElementId"] = assigned_id
            if color_op:
                color_op["contractElementId"] = assigned_id

    unassigned = [op for op in self.draw_ops if op.get("contractElementId") not in spec_by_id]
    for op_index, op in enumerate(unassigned):
        element_index = min(len(specs) - 1, op_index * len(specs) // max(1, len(unassigned)))
        op["contractElementId"] = specs[element_index]["id"]

    for spec in specs:
        assigned = [op for op in self.draw_ops if op.get("contractElementId") == spec["id"]]
        if not assigned:
            continue
        raster_ops = [op for op in assigned if op.get("id") in raster_op_ids]
        other = [op for op in assigned if op.get("id") not in raster_op_ids]
        if raster_ops:
            _retime_draw_ops_in_window(raster_ops, spec["startFrame"], spec["endFrame"])
            # Reveal the color with each painted stroke instead of waiting for
            # an entire object's black outlines to finish.
            by_id = {op["id"]: op for op in raster_ops}
            for ink in raster_ops:
                if ink.get("phase") != "ink":
                    continue
                color = by_id.get(ink.get("pairedOpId"))
                if not color:
                    continue
                start, end = ink["startFrame"], color["endFrame"]
                ink["endFrame"] = round(start + min(6, (end - start) * 0.12), 2)
                color["startFrame"] = ink["endFrame"]
        if other:
            schedule_ops(other, spec["startFrame"], spec["endFrame"])
    return specs


def _select_seven_habits_builder(self):
    corpus_local = _scene_corpus(self.scene)
    title_local = _clean_text(self.scene.title).lower()
    domain_markers = [
        "seven habits", "7 habits", "高效能人士的七个习惯", "七个习惯",
        "主动积极", "以终为始", "要事第一", "双赢", "知彼解己", "统合综效", "不断更新",
    ]
    if not _contains_any(corpus_local.lower(), domain_markers):
        return None
    habit_markers = [
        "七个习惯",
        "习惯1",
        "习惯2",
        "习惯3",
        "习惯4",
        "习惯5",
        "习惯6",
        "习惯7",
        "主动积极",
        "以终为始",
        "要事第一",
        "双赢",
        "知彼解己",
        "统合综效",
        "不断更新",
    ]
    if not any(marker in corpus_local for marker in habit_markers):
        return None
    if "不断更新" in title_local or "习惯7" in title_local:
        return self.build_renewal_summary_rich
    if "总览" in title_local or ("七个习惯" in corpus_local and "依赖" in corpus_local and ("互相依赖" in corpus_local or "互赖" in corpus_local)):
        return self.build_seven_habits_overview
    if "主动积极" in corpus_local or "影响圈" in corpus_local or "关注圈" in corpus_local:
        return self.build_proactive_circles
    if "以终为始" in corpus_local or "愿景" in corpus_local or "使命" in corpus_local:
        return self.build_begin_with_end
    if "要事第一" in corpus_local or "时间管理" in corpus_local or "四象限" in corpus_local:
        return self.build_time_matrix_rich
    if "双赢" in corpus_local or "知彼解己" in corpus_local or "统合综效" in corpus_local:
        return self.build_interdependence_rich
    if "不断更新" in corpus_local or "习惯7" in title_local or "总结" in corpus_local:
        return self.build_renewal_summary_rich
    return None


def _select_railway_builder(self):
    corpus_local = f"{_scene_corpus(self.scene)} {self.visual_anchor}".lower()
    domain_markers = [
        "railway", "railroad", "rail track", "station safety", "railway ppe",
        "铁路", "轨道", "车站", "道岔", "信号机", "防护员", "调度命令", "接触网",
    ]
    if not _contains_any(corpus_local, domain_markers):
        return None
    if not _contains_any(corpus_local, ["铁路", "上道", "站场", "道岔", "信号机", "防护员", "调度命令", "对讲机", "ppe"]):
        return None
    if _contains_any(corpus_local, ["ppe", "安全帽", "反光背心", "防护鞋", "对讲机", "工具清点"]):
        return self.build_railway_ppe_check
    if _contains_any(corpus_local, ["三方联络", "驻站联络员", "现场防护员", "复诵确认", "通信中断"]):
        return self.build_railway_contact_loop
    if _contains_any(corpus_local, ["一分钟复核", "六项复核", "复核路线", "铁律"]):
        return self.build_railway_minute_review
    if _contains_any(corpus_local, ["作业计划", "调度命令", "线路边界", "许可闸门", "命令和边界"]):
        return self.build_railway_permission_gate
    return None


def _build(self) -> dict:
    cursor = 0
    title_size = 58 if self.width >= 1600 else 44
    self.body_size = 32 if self.width >= 1600 else 26
    title_text = self.scene.title or f"Scene {self.scene_index + 1}"
    # The title is a safe-area overlay, not clipped handwritten glyphs.

    builders = {
        "process_flow": self.build_process_flow,
        "comparison_transform": self.build_comparison_transform,
        "formula_derivation": self.build_formula_derivation,
        "chalkboard_derivation": self.build_chalkboard_derivation,
        "optimization_curve": self.build_optimization_curve,
        "attention_network": self.build_attention_network,
        "matrix_transform": self.build_matrix_transform,
        "priority_matrix": self.build_priority_matrix,
        "feedback_loop": self.build_feedback_loop,
        "interaction_scenario": self.build_interaction_scenario,
        "goal_path": self.build_goal_path,
        "overview_map": self.build_overview_map,
        "teaching_board": self.build_teaching_board,
        "semiconductor_device": self.build_semiconductor_device,
    }
    cooking = _contains_any(_scene_corpus(self.scene).lower(), ["饺子", "面粉", "擀皮", "包制", "下锅", "包馅", "dumpling", "dough", "wrapper"])
    # A traced model image is authoritative; procedural cooking art is only a
    # fallback when image generation or line-art extraction is unavailable.
    spoken_recap = bool(_scene_extra(self.scene, "summaryPoints") and self.subtitle_cues)
    if spoken_recap:
        self.raster_reveal_spec = None
        self.reference_image_asset = None
        line_height = self.height * 0.50 / max(1, len(self.subtitle_cues))
        font_size = min(self.body_size, line_height * 0.70)
        for index, cue in enumerate(self.subtitle_cues):
            self.add_text(
                cue["text"], self.width * 0.12, self.height * 0.21 + index * line_height,
                font_size, self.ink, cue["startFrame"], cue["endFrame"] - cue["startFrame"],
                max_width=self.width * 0.76, max_chars=len(cue["text"]),
                emphasis=False, beat_id=f"cue_{index}",
            )
    elif cooking and not (self.raster_reveal and self.reference_image_asset):
        cooking_builders = {
            "ingredients": self.build_cooking_ingredients,
            "wrappers": self.build_cooking_wrappers,
            "wrapping": self.build_cooking_wrapping,
            "boiling": self.build_cooking_boiling,
        }
        title = f"{self.scene.title} {self.scene.narration}".lower()
        key = "boiling" if _contains_any(title, ["下锅", "煮", "浮起", "boil", "water"]) else "wrapping" if _contains_any(title, ["捏", "包", "馅", "fold", "wrap"]) else "wrappers" if _contains_any(title, ["擀", "切", "剂", "rolling", "wrapper"]) else "ingredients"
        # Put the main cooking action on the board at scene start. The title
        # can draw concurrently, but the hand must never begin on an empty
        # board while the narrated action is still waiting to appear.
        cursor = cooking_builders[key](0)
    elif self.raster_reveal and self.reference_image_asset:
        cursor = self.build_raster_reveal(cursor)
    elif self.trace_strokes:
        cursor = self.build_reference_trace(cursor)
    elif self.is_chalkboard:
        cursor = self.build_chalkboard_derivation(cursor)
    else:
        railway_builder = _select_railway_builder(self)
        seven_habits_builder = _select_seven_habits_builder(self)
        cursor = (railway_builder or seven_habits_builder or builders.get(self.diagram_kind, self.build_process_flow))(cursor)

    if not self.raster_reveal_spec and not self.subtitle_cues:
        self.duration = _stretch_audio_segments_for_draw_workload(
            self.draw_ops, self.texts, self.audio_segments, self.duration, self.fps
        )
    # Recap cue bindings are authoritative; contract scheduling must not overwrite them.
    if spoken_recap:
        _retime_draw_ops_to_subtitle_cues(self.draw_ops, self.subtitle_cues, self.duration)
        render_elements = []
    elif self.scene.render_elements and (
        not self.raster_reveal_spec
        or any(item.source != "generated" for item in self.scene.render_elements)
    ):
        render_elements = _apply_render_contract(self)
    else:
        if not _retime_draw_ops_to_subtitle_cues(self.draw_ops, self.subtitle_cues, self.duration):
            _retime_draw_ops_to_audio_segments(self.draw_ops, self.audio_segments, self.duration)
        render_elements = []
    return {
        "title": self.scene.title,
        "keywords": [] if self.raster_reveal_spec else list(dict.fromkeys(label for beat in self.scene.visual_beats for label in beat.required_labels))[:5],
        "subtitleCues": self.subtitle_cues,
        "summaryPoints": [] if spoken_recap else getattr(self.scene, "summaryPoints", []),
        "diagramKind": self.diagram_kind,
        "boardMode": self.board_mode,
        "handUsage": self.hand_usage,
        "videoStyle": self.video_style,
        "visualStyle": self.visual_style,
        "duration": self.duration,
        "audioUrl": _scene_extra(self.scene, "audioUrl") or _scene_extra(self.scene, "audio_url"),
        "audioSegments": self.audio_segments,
        "transitionFrames": self.transition_frames,
        "accent": self.accent,
        "drawOps": self.draw_ops,
        "texts": self.texts,
        "glyphPaths": [],
        "strokes": self.strokes,
        "referenceImageAsset": str(self.reference_image_asset) if self.reference_image_asset else None,
        "assetContract": self.asset_contract or None,
        "rasterReveal": self.raster_reveal_spec,
        "renderElements": render_elements,
    }


FallbackSceneBuilder.select_seven_habits_builder = _select_seven_habits_builder
FallbackSceneBuilder.select_railway_builder = _select_railway_builder
FallbackSceneBuilder.build = _build
