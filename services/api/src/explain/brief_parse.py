import logging
import re

from src.core.text_utils import clean_text, as_str_list, contains_any_text, normalize_text
from src.core.topic_terms import CHALKBOARD_MATH_SIGNALS, MARKETING_SIGNALS
from .models import (
    EnhancedTeachingBrief,
    GenerateGraphRequest,
    TeachingBriefSceneOutline,
    TeachingCoverageUnit,
)
from .prompts import DEFAULT_AUDIENCE, WHITEBOARD_BOARD_RULES, WHITEBOARD_LAYOUT_PRINCIPLES

logger = logging.getLogger(__name__)


def _clean(value: object) -> str:
    from src.core.text_utils import localize_chinese_terms
    text = "" if value is None else str(value)
    text = re.sub(r"\x1b\[[0-9;]*m", "", text)
    return localize_chinese_terms(re.sub(r"\s+", " ", text).strip())


def _as_str_list(value: object, limit: int | None = None) -> list[str]:
    return as_str_list(value, limit)


def _norm(value: str) -> str:
    return normalize_text(value)


def _append_unique(items: list[str], additions: list[str], limit: int | None = None) -> list[str]:
    result = list(items)
    seen = {_norm(item) for item in result}
    for addition in additions:
        text = _clean(addition)
        key = _norm(text)
        if text and key not in seen:
            result.append(text)
            seen.add(key)
        if limit and len(result) >= limit:
            break
    return result


def _contains_any_text(text: str, terms: list[str]) -> bool:
    return contains_any_text(text, terms)


def _looks_corrupted_text(text: str) -> bool:
    if not text:
        return False
    question_runs = len(re.findall(r"\?{4,}", text))
    replacement_count = text.count("?")
    visible = max(1, len(re.sub(r"\s+", "", text)))
    return question_runs > 0 or replacement_count / visible > 0.01


def _request_blob(req: GenerateGraphRequest) -> str:
    return f"{req.prompt}\n{req.markdown or ''}"


def _outline_from_raw(value: object) -> list[TeachingBriefSceneOutline]:
    outlines: list[TeachingBriefSceneOutline] = []
    if not isinstance(value, list):
        return outlines
    for index, item in enumerate(value):
        if isinstance(item, dict):
            try:
                outlines.append(
                    TeachingBriefSceneOutline(
                        title=_clean(item.get("title")) or f"场景 {index + 1}",
                        learning_goal=_clean(item.get("learning_goal")) or _clean(item.get("goal")) or "解释该步骤的核心概念",
                        diagram_plan=_clean(item.get("diagram_plan")) or _clean(item.get("visual_plan")) or "whiteboard process diagram",
                        must_draw=_as_str_list(item.get("must_draw") or item.get("required_visuals")),
                        narration_focus=_clean(item.get("narration_focus")) or None,
                        board_mode=_clean(item.get("board_mode")) or None,
                        hand_usage=_clean(item.get("hand_usage")) or None,
                        visual_style=_clean(item.get("visual_style")) or None,
                    )
                )
            except Exception:
                logger.debug("Skipping invalid teaching brief scene outline: %r", item)
        elif isinstance(item, str) and item.strip():
            outlines.append(
                TeachingBriefSceneOutline(
                    title=f"场景 {index + 1}",
                    learning_goal=_clean(item),
                    diagram_plan=_clean(item),
                    must_draw=[],
                )
            )
    return outlines


def _coverage_units_from_raw(value: object) -> list[TeachingCoverageUnit]:
    units: list[TeachingCoverageUnit] = []
    if not isinstance(value, list):
        return units
    for index, item in enumerate(value):
        try:
            if isinstance(item, dict):
                label = _clean(item.get("label") or item.get("title") or item.get("name"))
                goal = _clean(item.get("teaching_goal") or item.get("learning_goal") or item.get("goal"))
                if not label and not goal:
                    continue
                units.append(
                    TeachingCoverageUnit(
                        id=_clean(item.get("id")) or f"unit_{index}",
                        label=label or f"教学单元 {index + 1}",
                        unit_type=_clean(item.get("unit_type") or item.get("type")) or "concept",
                        teaching_goal=goal,
                        visual_role=_clean(item.get("visual_role") or item.get("diagram_kind") or item.get("role")) or "structure",
                        must_show=_as_str_list(item.get("must_show") or item.get("required_labels") or item.get("must_draw"), limit=8),
                        narration_focus=_clean(item.get("narration_focus")) or None,
                        priority=int(item.get("priority") or 3),
                    )
                )
            elif isinstance(item, str) and item.strip():
                units.append(
                    TeachingCoverageUnit(
                        id=f"unit_{index}",
                        label=_clean(item),
                        unit_type="concept",
                        teaching_goal=f"讲清楚 {_clean(item)} 的含义、作用和使用场景。",
                        visual_role="structure",
                        must_show=[_clean(item)],
                        priority=3,
                    )
                )
        except Exception:
            logger.debug("Skipping invalid teaching coverage unit: %r", item)
    return units


def _brief_from_raw(raw: dict, req: GenerateGraphRequest) -> EnhancedTeachingBrief:
    return EnhancedTeachingBrief(
        original_prompt=_clean(raw.get("original_prompt")) or req.prompt,
        audience_level=_clean(raw.get("audience_level")) or DEFAULT_AUDIENCE,
        topic_type=_clean(raw.get("topic_type")) or "technical_explanation",
        learning_objectives=_as_str_list(raw.get("learning_objectives"), limit=8),
        core_explanation_chain=_as_str_list(raw.get("core_explanation_chain"), limit=12),
        must_include_points=_as_str_list(raw.get("must_include_points"), limit=16),
        visual_metaphors=_as_str_list(raw.get("visual_metaphors"), limit=10),
        board_style_rules=_as_str_list(raw.get("board_style_rules"), limit=12),
        layout_principles=_as_str_list(raw.get("layout_principles"), limit=12),
        recommended_board_mode=_clean(raw.get("recommended_board_mode")) or "whiteboard",
        recommended_hand_usage=_clean(raw.get("recommended_hand_usage")) or "trace",
        recommended_visual_style=_clean(raw.get("recommended_visual_style")) or "teacher_whiteboard",
        recommended_scene_outline=_outline_from_raw(raw.get("recommended_scene_outline")),
        teaching_coverage_units=_coverage_units_from_raw(raw.get("teaching_coverage_units")),
        common_misconceptions=_as_str_list(raw.get("common_misconceptions"), limit=8),
    )


def _fallback_brief(req: GenerateGraphRequest) -> EnhancedTeachingBrief:
    topic = _clean(req.prompt)
    return EnhancedTeachingBrief(
        original_prompt=topic,
        audience_level=DEFAULT_AUDIENCE,
        topic_type="technical_explanation",
        learning_objectives=[
            f"理解 {topic} 的核心结构和关键变量。",
            f"理解 {topic} 的因果过程，而不只是记住名词。",
            f"能用一张过程图或对比图复述 {topic} 的工作原理。",
        ],
        core_explanation_chain=[
            "先给出直观现象或问题背景。",
            "再拆开结构、变量或步骤。",
            "用箭头说明原因如何导致结果。",
            "最后用类比或结论收束。",
        ],
        must_include_points=[topic],
        visual_metaphors=["用结构图、过程箭头和局部放大图代替纯文字列表。"],
        board_style_rules=list(WHITEBOARD_BOARD_RULES),
        layout_principles=list(WHITEBOARD_LAYOUT_PRINCIPLES),
        recommended_board_mode="whiteboard",
        recommended_hand_usage="trace",
        recommended_visual_style="teacher_whiteboard",
        recommended_scene_outline=[
            TeachingBriefSceneOutline(
                title="核心结构",
                learning_goal="建立观众对主题的第一张图像。",
                diagram_plan="A clear whiteboard structure diagram with labels and arrows.",
                must_draw=["核心对象", "关键关系", "方向箭头"],
                narration_focus="边画结构边解释每个部分的作用。",
                board_mode="whiteboard",
                hand_usage="trace",
                visual_style="teacher_whiteboard",
            )
        ],
        teaching_coverage_units=[
            TeachingCoverageUnit(
                id="unit_0",
                label=topic,
                unit_type="concept",
                teaching_goal=f"讲清楚 {topic} 的核心对象、关键关系和最终结论。",
                visual_role="structure",
                must_show=[topic, "关键关系", "结论"],
                narration_focus="按对象、关系、变化、结论的顺序讲清楚。",
                priority=5,
            )
        ],
        common_misconceptions=["把定义当成原理，忽略中间变化过程。"],
    )


def _scene_outline_from_dicts(items: list[dict]) -> list[TeachingBriefSceneOutline]:
    return [
        TeachingBriefSceneOutline(
            title=item["title"],
            learning_goal=item["learning_goal"],
            diagram_plan=item["diagram_plan"],
            must_draw=list(item["must_draw"]),
            narration_focus=item.get("narration_focus"),
            board_mode=item.get("board_mode"),
            hand_usage=item.get("hand_usage"),
            visual_style=item.get("visual_style"),
        )
        for item in items
    ]


def _coverage_unit(
    index: int,
    label: str,
    unit_type: str,
    teaching_goal: str,
    visual_role: str,
    must_show: list[str] | None = None,
    narration_focus: str | None = None,
    priority: int = 3,
) -> TeachingCoverageUnit:
    return TeachingCoverageUnit(
        id=f"unit_{index}",
        label=label,
        unit_type=unit_type,
        teaching_goal=teaching_goal,
        visual_role=visual_role,
        must_show=must_show or [],
        narration_focus=narration_focus,
        priority=priority,
    )


def _split_teaching_items(value: str) -> list[str]:
    text = _clean(value)
    if not text:
        return []
    text = re.sub(r"^\s*[\-•*]\s*", "", text)
    parts = re.split(r"[；;。.!?\n]+", text)
    items: list[str] = []
    for part in parts:
        part = _clean(part)
        if not part:
            continue
        subparts = re.split(r"(?:\s*[、,，]\s*)", part)
        if 2 <= len(subparts) <= 10 and all(2 <= len(item) <= 18 for item in subparts):
            items.extend(subparts)
        else:
            items.append(part)
    return [_clean(item) for item in items if _clean(item)]
