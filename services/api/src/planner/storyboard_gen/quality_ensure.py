import json

from src.explain.models import ExplainGraph
from ..models import Scene, Storyboard, VisualBeat
from .normalizer import (
    _clean_text,
    _clean_narration_text,
    _normalize_image_description_text,
    _canonical_video_style,
    _normalize_pen_style,
    _short_text,
    ACTIVE_VIDEO_STYLE,
    ACTIVE_PEN_STYLE,
)
from ..coverage.corpus import _scene_corpus, _storyboard_scene_corpus, _graph_source_corpus, _storyboard_corpus, _contains_terms, _graph_enhanced_brief
from ..coverage.appender import _append_missing_coverage_scenes, _sanitize_storyboard_narration
from ..coverage.generic_specs import _generic_relation_story_specs
from ..coverage.appender import _replace_with_specs
from ..fallback.scene_info import _cooking_prompt_suffix
from .timing import _estimate_scene_duration, _narration_from_beats
from .style_apply import _apply_video_style_to_scene, _apply_pen_style_to_scene
from .quality import (
    _append_image_description_rule,
    _ensure_core_teaching_fields,
    _is_direct_reference_scene,
    _is_simple_trace_scene,
    _scene_required_label_count,
)

def _best_scene_for_direct_reference(scenes: list[Scene]) -> Scene | None:
    candidates = [
        scene
        for scene in scenes
        if (scene.board_mode or "").lower() != "chalkboard"
        and (scene.hand_usage or "").lower() != "none"
        and (scene.visual_style or "").lower() != "math_chalkboard"
    ]
    if not candidates:
        return None

    priority_kinds = {
        "overview_map",
        "structure",
        "interaction",
        "comparison",
        "reference_callout",
        "cross_section",
        "process",
    }

    def score(scene: Scene) -> tuple[int, int]:
        kind = (scene.diagram_plan.kind if scene.diagram_plan else "").lower()
        labels = _scene_required_label_count(scene)
        complexity = (scene.visual_complexity or "").lower()
        strategy = (scene.render_strategy or "").lower()
        return (
            (8 if kind in priority_kinds else 0)
            + min(8, labels)
            + (5 if complexity in {"dense", "reference"} else 2 if complexity == "medium" else 0)
            + (3 if strategy in {"direct", "hybrid"} else 0),
            -scene.order,
        )

    return max(candidates, key=score)


def _best_scene_for_simple_trace(scenes: list[Scene]) -> Scene | None:
    candidates = [
        scene
        for scene in scenes
        if (scene.board_mode or "").lower() != "chalkboard"
        and (scene.hand_usage or "").lower() != "none"
        and (scene.visual_style or "").lower() != "math_chalkboard"
    ]
    if not candidates:
        return None

    simple_kinds = {"process", "comparison", "goal_path", "cycle", "formula", "simulation", "summary"}

    def score(scene: Scene) -> tuple[int, int]:
        kind = (scene.diagram_plan.kind if scene.diagram_plan else "").lower()
        labels = _scene_required_label_count(scene)
        complexity = (scene.visual_complexity or "").lower()
        return (
            (8 if kind in simple_kinds else 0)
            + (4 if labels <= 5 else 0)
            + (4 if complexity in {"", "simple", "medium"} else 0),
            scene.order,
        )

    return max(candidates, key=score)


def _has_complex_reference_subject(storyboard: Storyboard) -> bool:
    corpus = _storyboard_scene_corpus(storyboard).lower()
    complex_terms = [
        "railway",
        "rail yard",
        "trackside",
        "signal",
        "circuit",
        "mechanical",
        "equipment",
        "map",
        "anatomy",
        "cross-section",
        "3d",
        "dense",
        "reference",
        "multi-layer",
        "铁路",
        "站场",
        "轨道",
        "信号",
        "接触网",
        "设备",
        "电路",
        "机械",
        "地图",
        "人体",
        "剖面",
        "三维",
        "多层",
        "复杂",
        "密集",
    ]
    if any(term in corpus for term in complex_terms):
        return True
    return any((scene.visual_complexity or "").lower() in {"dense", "reference"} for scene in storyboard.scenes)


def _ensure_mixed_visual_modes(storyboard: Storyboard, video_style: str, pen_style: str) -> Storyboard:
    if len(storyboard.scenes) < 2:
        return storyboard
    if _canonical_video_style(video_style) in {"chalkboard_bw", "chalkboard_color"}:
        return storyboard

    active_scenes = [
        scene
        for scene in storyboard.scenes
        if (scene.board_mode or "").lower() != "chalkboard"
        and (scene.hand_usage or "").lower() != "none"
        and (scene.visual_style or "").lower() != "math_chalkboard"
    ]
    if len(active_scenes) < 2:
        return storyboard

    has_simple_trace = any(_is_simple_trace_scene(scene) for scene in active_scenes)
    has_direct_reference = any(_is_direct_reference_scene(scene) for scene in active_scenes)

    if not has_simple_trace:
        scene = _best_scene_for_simple_trace(active_scenes)
        if scene:
            scene.board_mode = "whiteboard"
            scene.hand_usage = "trace"
            scene.visual_style = "teacher_whiteboard"
            scene.render_strategy = "trace"
            if (scene.visual_complexity or "").lower() not in {"simple", "medium"}:
                scene.visual_complexity = "simple"
            _append_image_description_rule(
                scene,
                "Simple teacher-whiteboard line diagram to be drawn by hand stroke by stroke; no finished reference image is needed for this scene.",
            )

    if not has_direct_reference and _has_complex_reference_subject(storyboard):
        scene = _best_scene_for_direct_reference(active_scenes)
        if scene:
            scene.board_mode = "reference"
            scene.hand_usage = "annotate"
            scene.visual_style = "technical_reference" if (scene.video_style or video_style) == "technical_blueprint" else "marketing_doodle"
            scene.render_strategy = "hybrid"
            scene.visual_complexity = "dense"
            scene.visual_mode = "direct_reference"
            _append_image_description_rule(
                scene,
                "Finished complex hand-drawn reference illustration shown directly, in the same marker/crayon whiteboard style as the rest of the video, with generous blank margins for varied renderer-added callouts.",
            )

    for scene in storyboard.scenes:
        _apply_pen_style_to_scene(scene, pen_style)
    return storyboard



def _ensure_storyboard_quality(storyboard: Storyboard, graph: ExplainGraph, target_duration: int) -> Storyboard:
    corpus = _storyboard_corpus(storyboard, graph)
    source_corpus = _graph_source_corpus(graph)
    video_style = _canonical_video_style(storyboard.video_style)
    storyboard.video_style = video_style
    pen_style = _normalize_pen_style(storyboard.pen_style)
    storyboard.pen_style = pen_style
    brief = _graph_enhanced_brief(graph) or {}
    default_board_mode = _clean_text(brief.get("recommended_board_mode") if isinstance(brief, dict) else "") or "whiteboard"
    default_hand_usage = _clean_text(brief.get("recommended_hand_usage") if isinstance(brief, dict) else "") or "trace"
    default_visual_style = _clean_text(brief.get("recommended_visual_style") if isinstance(brief, dict) else "") or "teacher_whiteboard"
    framework_terms = ["通用问题解决框架", "问题解决框架", "全局地图", "取舍矩阵", "目标路径", "反馈闭环"]
    framework_terms.extend(["通用问题解决框架", "问题解决框架", "全局地图", "取舍矩阵", "目标路径", "反馈闭环"])
    is_problem_framework = _contains_terms(source_corpus, framework_terms)
    if is_problem_framework:
        storyboard = _replace_with_specs(storyboard, _generic_relation_story_specs(graph, target_duration))
        corpus = _storyboard_corpus(storyboard, graph)

    if not is_problem_framework:
        storyboard = _append_missing_coverage_scenes(storyboard, graph, target_duration)
        corpus = _storyboard_corpus(storyboard, graph)

    for scene in storyboard.scenes:
        if not scene.visual_beats:
            labels = []
            if scene.diagram_plan:
                labels = scene.diagram_plan.required_labels
            scene.visual_beats = [
                VisualBeat(
                    id="beat_0",
                    draw_intent=scene.image_description or scene.title,
                    narration=_clean_narration_text(scene.narration or scene.title),
                    required_labels=labels,
                    duration_estimate=max(5.0, min(10.0, scene.duration_estimate * 0.35)),
                )
            ]
        for beat in scene.visual_beats:
            beat.narration = _clean_narration_text(beat.narration)
        scene.narration = _narration_from_beats(scene.narration, scene.visual_beats)
        if not scene.board_mode:
            scene.board_mode = default_board_mode
        if not scene.hand_usage:
            scene.hand_usage = default_hand_usage
        if not scene.video_style and video_style != "auto":
            scene.video_style = video_style
        if not scene.visual_style:
            scene.visual_style = default_visual_style
        scene.title = _clean_text(scene.title)
        scene.learning_goal = _clean_text(scene.learning_goal)
        scene.image_description = _normalize_image_description_text(scene.image_description)
        if scene.diagram_plan:
            scene.diagram_plan.kind = _clean_text(scene.diagram_plan.kind)
            scene.diagram_plan.layout = _clean_text(scene.diagram_plan.layout)
            scene.diagram_plan.required_labels = [_clean_text(label) for label in scene.diagram_plan.required_labels if _clean_text(label)]
        for beat in scene.visual_beats:
            beat.draw_intent = _clean_text(beat.draw_intent)
            beat.required_labels = [_clean_text(label) for label in beat.required_labels if _clean_text(label)]
        for animation in scene.animations:
            animation.content = _clean_text(animation.content)
            if animation.items:
                animation.items = [_clean_text(item) for item in animation.items if _clean_text(item)]
        scene_corpus = _scene_corpus(scene)
        cooking_suffix = _cooking_prompt_suffix(scene_corpus)
        if cooking_suffix and cooking_suffix not in (scene.image_description or ""):
            scene.image_description = f"{scene.image_description}. {cooking_suffix}".strip(". ")
            scene.image_description = _normalize_image_description_text(scene.image_description)
        is_math_board = (
            video_style in {"auto", "chalkboard_bw", "chalkboard_color"}
            and default_visual_style == "math_chalkboard"
        ) or _contains_terms(
            scene_corpus,
            ["数学解题", "数学证明", "公式推导", "plane normal", "perpendicular", "parametric", "iit"],
        )
        if is_math_board:
            scene.board_mode = "chalkboard"
            scene.hand_usage = "none"
            scene.visual_style = "math_chalkboard"
        _apply_video_style_to_scene(scene, video_style)
        if scene.board_mode == "chalkboard" or scene.visual_style == "math_chalkboard":
            scene.hand_usage = "none"
            scene.render_strategy = scene.render_strategy or "trace"
            scene.visual_complexity = scene.visual_complexity or "medium"
        if scene.hand_usage == "annotate" and not scene.render_strategy:
            scene.render_strategy = "hybrid"
        _apply_pen_style_to_scene(scene, pen_style)
        if scene.board_mode == "chalkboard" or scene.visual_style == "math_chalkboard":
            scene.hand_usage = "none"
            scene.pen_style = "no_hand"
            scene.render_strategy = scene.render_strategy or "trace"
        scene.duration_estimate = _estimate_scene_duration(
            scene.duration_estimate,
            scene.narration,
            scene.visual_beats,
            scene.animations,
        )
    storyboard = _ensure_mixed_visual_modes(storyboard, video_style, pen_style)
    storyboard = _ensure_core_teaching_fields(storyboard)
    storyboard.total_duration_estimate = round(sum(scene.duration_estimate for scene in storyboard.scenes), 1)
    return _sanitize_storyboard_narration(storyboard)



