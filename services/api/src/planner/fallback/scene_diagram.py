import re

from ..models import Scene
from ..storyboard_gen.normalizer import _clean_text
from .scene_info import _scene_corpus, _contains_any, _animation_type_values


def _visual_relation_kind_for_scene(scene: Scene) -> str | None:
    corpus = _scene_corpus(scene)
    explicit_kind = _clean_text(scene.diagram_plan.kind if scene.diagram_plan else "").lower().replace("-", "_")
    layout = _clean_text(scene.diagram_plan.layout if scene.diagram_plan else "").lower()
    text = f"{explicit_kind} {layout} {corpus}"

    aliases = {
        "overview_map": {"overview_map", "overview", "map", "concept_map", "framework_map", "roadmap"},
        "comparison_transform": {"comparison", "compare", "state_comparison", "before_after", "two_panel", "vs"},
        "process_flow": {"process", "flow", "mechanism", "pipeline", "journey", "sequence"},
        "interaction_scenario": {"interaction", "relationship", "mutual", "communication", "collaboration", "exchange", "scenario"},
        "priority_matrix": {"tradeoff_matrix", "priority_matrix", "matrix", "quadrant", "2x2", "classification"},
        "goal_path": {"goal_path", "goal", "path", "roadmap", "milestone", "backcasting"},
        "feedback_loop": {"cycle", "loop", "feedback", "iteration", "iterate", "renewal"},
        "formula_derivation": {"formula", "equation", "derivation"},
        "teaching_board_summary": {"summary", "checklist", "conclusion"},
        "teaching_board": {"structure", "component", "part_whole", "concept", "framework"},
    }
    for result, values in aliases.items():
        if explicit_kind in values:
            return result

    relation_patterns: list[tuple[str, list[str]]] = [
        ("priority_matrix", ["tradeoff", "quadrant", "2x2", "matrix", "priority", "urgent", "important", "取舍", "矩阵", "象限", "二维", "优先", "紧急", "重要", "分类"]),
        ("interaction_scenario", ["interaction", "relationship", "mutual", "communication", "collaboration", "exchange", "stakeholder", "actor", "between", "互相", "互动", "关系", "沟通", "协作", "交换", "双方", "共同", "影响"]),
        ("goal_path", ["goal", "target", "vision", "path", "roadmap", "milestone", "route", "journey", "backcast", "目标", "愿景", "路径", "路线", "里程碑", "倒推", "阶段"]),
        ("feedback_loop", ["feedback", "loop", "cycle", "iterate", "iteration", "renewal", "repeat", "闭环", "反馈", "循环", "迭代", "复盘", "更新", "重复"]),
        ("comparison_transform", ["comparison", "compare", "versus", " vs ", "before", "after", "state", "switch", "contrast", "对比", "比较", "前后", "状态", "开关", "变化", "转换"]),
        ("process_flow", ["process", "flow", "mechanism", "cause", "effect", "step", "pipeline", "过程", "流程", "机制", "因果", "原因", "结果", "步骤", "原理"]),
        ("teaching_board_summary", ["summary", "checklist", "recap", "conclusion", "总结", "清单", "复盘", "结论", "收束"]),
        ("teaching_board", ["overview", "map", "framework", "structure", "component", "part", "whole", "概览", "地图", "框架", "结构", "组成", "部件", "整体", "局部"]),
    ]
    for result, terms in relation_patterns:
        if _contains_any(text, terms):
            return result
    return None


def _scene_steps(scene: Scene) -> list[str]:
    steps: list[str] = []
    if scene.diagram_plan and scene.diagram_plan.required_labels:
        steps.extend(scene.diagram_plan.required_labels[:5])
    for beat in getattr(scene, "visual_beats", []) or []:
        if beat.required_labels:
            steps.extend(beat.required_labels[:2])
        if len(steps) >= 5:
            break
    for animation in scene.animations:
        if animation.items:
            steps.extend(animation.items[:5])
        elif animation.content:
            steps.append(animation.content)
        if len(steps) >= 5:
            break
    if not steps and scene.narration:
        steps = re.split(r"[，。；;,.!?？、\s]+", scene.narration)[:5]
    return [_short_text(step, 18) for step in steps if _short_text(step, 18)][:5]


def _diagram_kind_for_scene(scene: Scene, scene_index: int) -> str:
    corpus = _scene_corpus(scene)
    types = _animation_type_values(scene)
    visual_relation_kind = _visual_relation_kind_for_scene(scene)
    if visual_relation_kind:
        return "teaching_board" if visual_relation_kind == "teaching_board_summary" else visual_relation_kind
    if scene.diagram_plan and scene.diagram_plan.kind in {"semiconductor_device", "mos_device", "finfet_device"}:
        return "semiconductor_device"
    if _contains_any(corpus, ["v_g", "v_ds", "w_eff", "阈值", "短沟道"]):
        return "semiconductor_device"
    has_formula = "write_formula" in types or "formula_reveal" in types or bool(
        re.search(r"(=|∇|Σ|softmax|theta|\\theta|\bloss\b|\battention\s*\()", corpus, flags=re.IGNORECASE)
    )

    if _contains_any(
        corpus,
        [
            "attention",
            "self-attention",
            "transformer",
            "query",
            "key",
            "value",
            "softmax",
            "qkv",
            "token",
            "注意力",
            "自注意力",
            "键值",
            "向量",
        ],
    ):
        return "attention_network"
    if _contains_any(
        corpus,
        [
            "urgent",
            "important",
            "priority",
            "quadrant",
            "eisenhower",
            "time management",
            "紧急",
            "重要",
            "优先",
            "四象限",
        ],
    ):
        return "priority_matrix"
    if _contains_any(
        corpus,
        [
            "lora",
            "low rank",
            "low-rank",
            "rank update",
            "weight matrix",
            "matrix decomposition",
            "matrix multiplication",
            "linear layer",
            "矩阵",
            "低秩",
            "分解",
            "微调",
        ],
    ):
        return "matrix_transform"
    if _contains_any(
        corpus,
        [
            "gradient",
            "descent",
            "loss",
            "learning rate",
            "converge",
            "optimum",
            "梯度",
            "损失",
            "学习率",
            "收敛",
            "最优",
            "参数更新",
        ],
    ):
        return "optimization_curve"
    if _contains_any(corpus, ["feedback", "loop", "cycle", "iterate", "iteration", "反馈", "循环", "迭代"]):
        return "feedback_loop"
    if has_formula:
        return "formula_derivation"
    if _contains_any(corpus, ["checklist", "summary", "recap", "conclusion", "娓呭崟", "鎬荤粨"]):
        return "teaching_board"
    if _contains_any(
        corpus,
        [
            "framework",
            "method",
            "checklist",
            "overview",
            "summary",
            "概览",
            "框架",
            "方法",
            "清单",
            "总结",
        ],
    ):
        return "overview_map"
    if "step_reveal" in types or _contains_any(corpus, ["process", "pipeline", "workflow", "过程", "步骤", "流程", "原理"]):
        return "process_flow"
    if _contains_any(corpus, ["compare", "versus", " vs ", "change", "transform", "before", "after", "对比", "比较", "变化", "变换", "转换"]):
        return "comparison_transform"

    return ["process_flow", "comparison_transform", "feedback_loop"][scene_index % 3]


