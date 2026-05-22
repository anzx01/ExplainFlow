from ..models import Scene, Storyboard, AnnotationPlanItem
from .normalizer import (
    _clean_text,
    _clean_narration_text,
    _normalize_image_description_text,
    _annotation_template_types,
    _short_text,
    _parse_annotation_plan,
    TEACHING_RULES,
    ACTIVE_VIDEO_STYLE,
    ACTIVE_PEN_STYLE,
)
from ..coverage.corpus import _scene_corpus

def _scene_required_label_count(scene: Scene) -> int:
    labels: set[str] = set()
    if scene.diagram_plan:
        labels.update(label for label in scene.diagram_plan.required_labels if label)
    for beat in scene.visual_beats:
        labels.update(label for label in beat.required_labels if label)
    return len(labels)


def _is_simple_trace_scene(scene: Scene) -> bool:
    if (getattr(scene, "visual_mode", "") or "").lower() == "trace":
        return True
    return (
        (scene.render_strategy or "").lower() == "trace"
        and (scene.hand_usage or "").lower() == "trace"
        and (scene.board_mode or "").lower() == "whiteboard"
        and (scene.visual_style or "").lower() in {"", "teacher_whiteboard", "sharpie"}
        and (scene.visual_complexity or "").lower() in {"", "simple", "medium"}
    )


def _is_direct_reference_scene(scene: Scene) -> bool:
    if (getattr(scene, "visual_mode", "") or "").lower() in {"direct_reference", "hybrid"}:
        return True
    return (
        (scene.render_strategy or "").lower() in {"direct", "hybrid"}
        or (scene.hand_usage or "").lower() == "annotate"
        or (scene.board_mode or "").lower() in {"reference", "clean_canvas"}
        or (scene.visual_style or "").lower() in {"technical_reference", "marketing_doodle", "editorial", "playful"}
        or (scene.visual_complexity or "").lower() in {"dense", "reference"}
    )


def _append_image_description_rule(scene: Scene, rule: str) -> None:
    existing = scene.image_description or ""
    if rule.lower() not in existing.lower():
        scene.image_description = _normalize_image_description_text(f"{existing}. {rule}".strip(". "))


def _append_unique(existing: list[str], values: list[str], limit: int = 8) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in [*(existing or []), *(values or [])]:
        text = _clean_text(value)
        if not text or text.lower() in seen:
            continue
        seen.add(text.lower())
        result.append(text)
        if len(result) >= limit:
            break
    return result


def _scene_label_candidates(scene: Scene) -> list[str]:
    labels: list[str] = []
    if scene.diagram_plan:
        labels.extend(scene.diagram_plan.required_labels or [])
    for beat in scene.visual_beats:
        labels.extend(beat.required_labels or [])
    labels.extend([scene.title, scene.learning_goal or ""])
    cleaned: list[str] = []
    seen: set[str] = set()
    for label in labels:
        text = _short_text(_clean_text(label), 18)
        if not text or text.lower() in seen:
            continue
        seen.add(text.lower())
        cleaned.append(text)
    return cleaned


def _visual_mode_for_scene(scene: Scene) -> str:
    explicit = _clean_text(getattr(scene, "visual_mode", "")).lower()
    if explicit in {"trace", "direct_reference", "hybrid"}:
        return explicit
    strategy = (scene.render_strategy or "").lower()
    board_mode = (scene.board_mode or "").lower()
    hand_usage = (scene.hand_usage or "").lower()
    visual_style = (scene.visual_style or "").lower()
    complexity = (scene.visual_complexity or "").lower()
    if strategy == "direct":
        return "direct_reference"
    if strategy == "hybrid" and (complexity in {"dense", "reference"} or board_mode == "reference" or visual_style == "technical_reference"):
        return "direct_reference"
    if strategy == "hybrid":
        return "hybrid"
    if board_mode == "reference" or visual_style == "technical_reference" or hand_usage == "annotate":
        return "direct_reference" if complexity in {"dense", "reference"} else "hybrid"
    return "trace"


def _default_annotation_types(scene: Scene, visual_mode: str) -> list[str]:
    if visual_mode in {"direct_reference", "hybrid"}:
        return ["side_label", "short_arrow", "edge_tick", "risk_ray", "wavy_underline"]
    kind = (scene.diagram_plan.kind if scene.diagram_plan else "").lower()
    if kind in {"process", "goal_path", "cycle", "simulation"}:
        return ["side_label", "route_trace", "short_arrow", "wavy_underline", "checkmark"]
    if kind in {"comparison", "tradeoff_matrix"}:
        return ["side_label", "short_arrow", "checkmark", "crossout", "wavy_underline"]
    return ["side_label", "short_arrow", "wavy_underline", "checkmark", "labeled_zoom"]


def _ensure_scene_annotation_plan(scene: Scene) -> None:
    allowed = _annotation_template_types()
    allowed_set = set(allowed)
    visual_mode = _visual_mode_for_scene(scene)
    existing = [
        item
        for item in (scene.annotation_plan or [])
        if item.type in allowed_set and item.label and item.target
    ]
    labels = _scene_label_candidates(scene)
    if not labels:
        labels = [_short_text(scene.title, 18) or "重点", "风险点", "正确做法"]
    beat_ids = [beat.id or f"beat_{index}" for index, beat in enumerate(scene.visual_beats)] or ["beat_0"]
    used_types = {item.type for item in existing}
    defaults = [item for item in _default_annotation_types(scene, visual_mode) if item in allowed_set]
    target_count = 4 if visual_mode in {"direct_reference", "hybrid"} else 3
    for index, annotation_type in enumerate(defaults):
        if len(existing) >= target_count and len({item.type for item in existing}) >= 3:
            break
        if annotation_type in used_types and len(existing) >= 3:
            continue
        label = labels[index % len(labels)]
        existing.append(
            AnnotationPlanItem(
                type=annotation_type,
                label=label,
                target=label,
                beat_id=beat_ids[index % len(beat_ids)],
                layer="renderer",
            )
        )
        used_types.add(annotation_type)
    scene.annotation_plan = existing[:6]


def _ensure_core_teaching_fields(storyboard: Storyboard) -> Storyboard:
    for scene in storyboard.scenes:
        scene.video_style = ACTIVE_VIDEO_STYLE
        scene.pen_style = ACTIVE_PEN_STYLE
        scene.teaching_density = scene.teaching_density or str(TEACHING_RULES.get("mode_policy", {}).get("default_density") or "rich")
        scene.visual_mode = _visual_mode_for_scene(scene)
        if scene.visual_mode == "trace":
            scene.board_mode = "whiteboard"
            scene.hand_usage = "trace"
            scene.visual_style = "teacher_whiteboard"
            scene.render_strategy = "trace"
            scene.visual_mode = "trace"
        elif scene.visual_mode == "direct_reference":
            scene.board_mode = "reference"
            scene.hand_usage = "annotate"
            scene.visual_style = "technical_reference"
            scene.render_strategy = "hybrid"
        else:
            scene.board_mode = scene.board_mode or "reference"
            scene.hand_usage = "annotate"
            scene.visual_style = scene.visual_style or "technical_reference"
            scene.render_strategy = "hybrid"
        if not scene.visual_anchor:
            if scene.diagram_plan and scene.diagram_plan.layout:
                scene.visual_anchor = _short_text(scene.diagram_plan.layout, 36)
            else:
                scene.visual_anchor = _short_text(scene.title, 36)
        _ensure_scene_annotation_plan(scene)
        plan_labels = [item.label for item in scene.annotation_plan if item.label]
        if scene.visual_beats and plan_labels:
            for index, beat in enumerate(scene.visual_beats):
                needed = [
                    item.label
                    for item in scene.annotation_plan
                    if item.beat_id == (beat.id or f"beat_{index}") and item.label
                ]
                if not needed and index == 0:
                    needed = plan_labels[:3]
                beat.required_labels = _append_unique(beat.required_labels, needed, limit=8)
        scene.image_description = _normalize_image_description_text(scene.image_description)
    storyboard.video_style = ACTIVE_VIDEO_STYLE
    storyboard.pen_style = ACTIVE_PEN_STYLE
    return storyboard



