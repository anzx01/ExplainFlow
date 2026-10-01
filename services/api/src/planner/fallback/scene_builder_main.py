from .scene_builder_base import FallbackSceneBuilder
from .scene_info import _contains_any
from ..coverage.corpus import _scene_corpus
from .scene_extra import _scene_extra
from .draw_ops import _stretch_audio_segments_for_draw_workload, _retime_draw_ops_to_audio_segments
from ..storyboard_gen.normalizer import _clean_text


def _apply_render_contract(self) -> list[dict]:
    elements = sorted(self.scene.render_elements, key=lambda item: (item.sequence, item.id))
    if not elements:
        return []
    scene_ms = max(1, round(self.scene.duration_estimate * 1000))
    scale = self.duration / max(1, round(scene_ms * self.fps / 1000))
    specs: list[dict] = []
    for index, element in enumerate(elements):
        start = round(element.reveal.start_ms * self.fps / 1000 * scale)
        end = round((element.reveal.start_ms + element.reveal.duration_ms) * self.fps / 1000 * scale)
        later = [item.region.model_dump(mode="json") for item in elements[index + 1 :]]
        specs.append(
            {
                "id": element.id,
                "sequence": element.sequence,
                "parallelGroup": element.parallel_group,
                "startFrame": max(0, start),
                "endFrame": max(start + 1, min(self.duration, end)),
                "region": element.region.model_dump(mode="json"),
                "laterRegions": later,
                "protectedRegions": [
                    item.model_dump(mode="json") for item in element.reveal.protected_regions
                ],
            }
        )
    if not self.draw_ops:
        return specs
    for op_index, op in enumerate(self.draw_ops):
        element_index = min(len(specs) - 1, op_index * len(specs) // len(self.draw_ops))
        op["contractElementId"] = specs[element_index]["id"]
    for spec in specs:
        assigned = [op for op in self.draw_ops if op.get("contractElementId") == spec["id"]]
        if not assigned:
            continue
        window = max(1, spec["endFrame"] - spec["startFrame"])
        for index, op in enumerate(assigned):
            start = spec["startFrame"] + round(index * window / len(assigned))
            end = spec["startFrame"] + round((index + 1) * window / len(assigned))
            op["startFrame"] = start
            op["endFrame"] = max(start + 1, end)
    return specs


def _select_seven_habits_builder(self):
    corpus_local = _scene_corpus(self.scene)
    title_local = _clean_text(self.scene.title).lower()
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
    self.add_text(
        title_text,
        self.title_x_for_text(title_text, title_size),
        self.top,
        title_size,
        self.blue,
        cursor,
        44,
        emphasis=True,
        max_width=self.width * 0.78,
        max_chars=24,
    )
    cursor += 54

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
    if self.raster_reveal and self.reference_image_asset:
        cursor = self.build_raster_reveal(cursor)
    elif self.trace_strokes:
        cursor = self.build_reference_trace(cursor)
    elif self.is_chalkboard:
        cursor = self.build_chalkboard_derivation(cursor)
    else:
        railway_builder = _select_railway_builder(self)
        seven_habits_builder = _select_seven_habits_builder(self)
        cursor = (railway_builder or seven_habits_builder or builders.get(self.diagram_kind, self.build_process_flow))(cursor)

    self.duration = _stretch_audio_segments_for_draw_workload(
        self.draw_ops, self.texts, self.audio_segments, self.duration, self.fps
    )
    _retime_draw_ops_to_audio_segments(self.draw_ops, self.audio_segments, self.duration)
    render_elements = _apply_render_contract(self)
    return {
        "title": self.scene.title,
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
        "rasterReveal": self.raster_reveal_spec,
        "renderElements": render_elements,
    }


FallbackSceneBuilder.select_seven_habits_builder = _select_seven_habits_builder
FallbackSceneBuilder.select_railway_builder = _select_railway_builder
FallbackSceneBuilder.build = _build
