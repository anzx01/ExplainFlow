import json
import logging
import re

from src.core.llm import chat_json
from src.core.topic_terms import CHALKBOARD_MATH_SIGNALS, MARKETING_SIGNALS
from .models import EnhancedTeachingBrief, GenerateGraphRequest
from .prompts import (
    DEFAULT_AUDIENCE,
    ENHANCE_SYSTEM_PROMPT,
    WHITEBOARD_BOARD_RULES,
    WHITEBOARD_LAYOUT_PRINCIPLES,
    STYLE_STRATEGY_RULES,
)
from .brief_parse import (
    _append_unique,
    _clean,
    _coverage_unit,
    _fallback_brief,
    _norm,
    _request_blob,
    _split_teaching_items,
)

logger = logging.getLogger(__name__)


def _derive_teaching_coverage_units(brief: EnhancedTeachingBrief, req: GenerateGraphRequest) -> list:
    units = list(brief.teaching_coverage_units or [])
    source_items: list[tuple[str, str, str, int]] = []

    for index, item in enumerate(brief.recommended_scene_outline):
        source_items.append(
            (
                item.title,
                item.learning_goal or f"讲清楚 {item.title}。",
                item.diagram_plan or "whiteboard structure/process diagram",
                5 if index < 6 else 4,
            )
        )

    for point in brief.must_include_points:
        source_items.append((point, f"讲清楚 {point} 的含义、原因和结果。", "callout/process", 5))

    for objective in brief.learning_objectives:
        for item in _split_teaching_items(objective):
            source_items.append((item, objective, "concept_map", 3))

    for chain_item in brief.core_explanation_chain:
        source_items.append((chain_item, chain_item, "process", 4))

    topic = _clean(req.prompt)
    if topic:
        source_items.append((topic, f"让观众建立对 {topic} 的完整认知框架。", "overview", 5))

    seen = {_norm(unit.label) for unit in units}
    for label, goal, visual_role, priority in source_items:
        label = _clean(label)
        if not label:
            continue
        label = re.sub(r"^(?:理解|看懂|掌握|知道|说明|解释|通过|用)\s*", "", label)
        label = _clean(label.strip("：:，,。 "))
        if not label:
            continue
        if len(label) > 46:
            label = label[:46].rstrip() + "..."
        key = _norm(label)
        if not key or key in seen:
            continue
        seen.add(key)
        visual_text = f"{visual_role} {label}".lower()
        unit_type = "process" if any(term in visual_text for term in ["process", "simulation", "cycle", "goal_path", "interaction"]) else "concept"
        if any(term in visual_text for term in ["vs", "对比", "比较", "off/on", "before", "after", "comparison", "state"]):
            unit_type = "comparison"
            visual_role = "comparison"
        elif any(term in visual_text for term in ["tradeoff", "priority", "quadrant", "matrix", "取舍", "优先", "象限", "矩阵"]):
            unit_type = "comparison"
            visual_role = "tradeoff_matrix"
        elif any(term in visual_text for term in ["interaction", "relationship", "mutual", "communication", "collaboration", "互相", "互动", "关系", "沟通", "协作"]):
            unit_type = "process"
            visual_role = "interaction"
        elif any(term in visual_text for term in ["goal", "target", "path", "roadmap", "目标", "路径", "路线", "里程碑"]):
            unit_type = "process"
            visual_role = "goal_path"
        elif any(term in visual_text for term in ["cycle", "loop", "feedback", "iterate", "renew", "循环", "闭环", "反馈", "迭代", "更新"]):
            unit_type = "process"
            visual_role = "cycle"
        elif any(term in visual_text for term in ["公式", "=", "w_eff", "theta", "loss", "formula", "equation"]):
            unit_type = "formula"
            visual_role = "formula"
        units.append(
            _coverage_unit(
                len(units), label, unit_type, goal, visual_role,
                must_show=[label],
                narration_focus="按现象、原因、过程、结果讲清楚，不只给定义。",
                priority=priority,
            )
        )
        if len(units) >= 18:
            break

    return units


def _ensure_teaching_coverage_brief(brief: EnhancedTeachingBrief, req: GenerateGraphRequest) -> EnhancedTeachingBrief:
    units = _derive_teaching_coverage_units(brief, req)
    brief.teaching_coverage_units = units
    if units:
        brief.must_include_points = _append_unique(
            brief.must_include_points,
            [unit.label for unit in units if unit.priority >= 4],
            limit=24,
        )
    brief.visual_metaphors = _append_unique(
        brief.visual_metaphors,
        [
            "通用课堂结构：全局地图、状态对比、因果流程、结构拆解、交互关系、优先级矩阵、目标路径、反馈闭环、公式 callout 和总结清单按教学关系选择。",
            "不要根据题材词套专门图形；同一种关系在技术、商业、管理、医学、数学等主题中都用同一套可迁移视觉语法。",
            "英文术语要先做中文本地化转译：优先使用中文语境中自然、常用、好懂的说法；没有固定译名时用自然短语解释，不要逐词硬翻。",
            "复杂主体直接呈现清晰图，老师只用手写箭头、圈选、下划线和短标签强调重点。",
            "如果主题包含多个单元、状态、对象或阶段，每个单元都必须有独立画面或明确视觉 beat 覆盖。",
        ],
        limit=14,
    )
    return brief


def _ensure_brief_minimums(brief: EnhancedTeachingBrief, req: GenerateGraphRequest) -> EnhancedTeachingBrief:
    topic = _clean(req.prompt)
    if not brief.original_prompt:
        brief.original_prompt = topic
    if not brief.audience_level:
        brief.audience_level = DEFAULT_AUDIENCE
    if len(brief.learning_objectives) < 3:
        brief.learning_objectives = _append_unique(
            brief.learning_objectives,
            [
                f"理解 {topic} 的核心对象和关键变量。",
                f"能按因果顺序解释 {topic} 的工作过程。",
                f"能通过图形、箭头和对比复述 {topic} 的主要结论。",
            ],
            limit=6,
        )
    if not brief.core_explanation_chain:
        brief.core_explanation_chain = [
            "先画直观结构或现象。",
            "再解释关键原因如何发生。",
            "接着画出变化过程和结果。",
            "最后用对比或类比总结。",
        ]
    if not brief.must_include_points:
        brief.must_include_points = [topic]
    if not brief.visual_metaphors:
        brief.visual_metaphors = ["结构图 + 过程箭头 + 局部放大 + 状态对比。"]
    brief.board_style_rules = _append_unique(brief.board_style_rules, WHITEBOARD_BOARD_RULES + STYLE_STRATEGY_RULES, limit=20)
    brief.layout_principles = _append_unique(brief.layout_principles, WHITEBOARD_LAYOUT_PRINCIPLES, limit=16)
    if brief.recommended_board_mode not in {"whiteboard", "chalkboard", "clean_canvas", "reference"}:
        brief.recommended_board_mode = "whiteboard"
    if brief.recommended_hand_usage not in {"trace", "annotate", "none"}:
        brief.recommended_hand_usage = "trace"
    if brief.recommended_visual_style not in {
        "teacher_whiteboard", "marketing_doodle", "math_chalkboard", "technical_reference",
    }:
        brief.recommended_visual_style = "teacher_whiteboard"
    if not brief.recommended_scene_outline:
        brief.recommended_scene_outline = _fallback_brief(req).recommended_scene_outline

    blob = _request_blob(req)
    blob_lower = blob.lower()
    if any(signal in blob_lower for signal in CHALKBOARD_MATH_SIGNALS):
        brief.recommended_board_mode = "chalkboard"
        brief.recommended_hand_usage = "none"
        brief.recommended_visual_style = "math_chalkboard"
    elif any(signal in blob_lower for signal in MARKETING_SIGNALS):
        brief.recommended_board_mode = "clean_canvas"
        brief.recommended_hand_usage = "annotate"
        brief.recommended_visual_style = "marketing_doodle"
    brief = _ensure_teaching_coverage_brief(brief, req)
    return brief


async def enhance_prompt(req: GenerateGraphRequest) -> EnhancedTeachingBrief:
    from .brief_parse import _brief_from_raw
    user_content = {
        "original_prompt": req.prompt,
        "reference_material": req.markdown or "",
        "default_audience": DEFAULT_AUDIENCE,
    }
    logger.info("Enhancing teaching prompt for: %s", req.prompt[:50])
    raw = await chat_json(
        messages=[
            {"role": "system", "content": ENHANCE_SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(user_content, ensure_ascii=False)},
        ]
    )
    try:
        brief = _brief_from_raw(raw, req)
    except Exception as exc:
        logger.warning("Prompt enhancement JSON was incomplete; using deterministic brief: %s", exc)
        brief = _fallback_brief(req)
    return _ensure_brief_minimums(brief, req)
