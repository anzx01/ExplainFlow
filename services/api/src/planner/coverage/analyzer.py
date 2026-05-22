import json
import re

from src.explain.models import ExplainGraph
from ..models import Scene, Storyboard, DiagramPlan
from .corpus import _storyboard_scene_corpus, _graph_source_corpus, _scene_corpus

def _brief_coverage_units(graph: ExplainGraph) -> list[dict]:
    brief = _graph_enhanced_brief(graph) or {}
    units = brief.get("teaching_coverage_units") if isinstance(brief, dict) else []
    if isinstance(units, list):
        return [unit for unit in units if isinstance(unit, dict) and _clean_text(unit.get("label"))]
    return []


def _coverage_unit_label(unit: dict) -> str:
    return _clean_text(unit.get("label") or unit.get("title") or unit.get("name"))


def _coverage_unit_tokens(unit: dict) -> list[str]:
    values: list[str] = []
    values.append(_coverage_unit_label(unit))
    values.extend(_planner_str_list(unit.get("must_show") or unit.get("required_labels") or unit.get("must_draw"), limit=8))
    values.append(_clean_text(unit.get("teaching_goal")))
    values.append(_clean_text(unit.get("narration_focus")))
    tokens: list[str] = []
    for value in values:
        value = _clean_text(value).strip(" ：:，,。")
        if not value:
            continue
        tokens.append(value)
        for piece in re.split(r"[、,，；;：:\s/]+", value):
            piece = _clean_text(piece).strip("（）()[]【】")
            if 2 <= len(piece) <= 24:
                tokens.append(piece)
    seen: set[str] = set()
    result: list[str] = []
    for token in tokens:
        key = re.sub(r"\s+", "", token).lower()
        if key and key not in seen:
            seen.add(key)
            result.append(token)
    return result


def _coverage_unit_fingerprint(unit: dict) -> set[str]:
    text = " ".join(_coverage_unit_tokens(unit)).lower()
    role = _clean_text(unit.get("visual_role") or unit.get("unit_type")).lower()
    labels = {_clean_text(token).lower() for token in _coverage_unit_tokens(unit) if _clean_text(token)}
    relation_kind = _diagram_kind_for_coverage_unit(unit)
    if relation_kind:
        labels.add(relation_kind)
    relation_terms = {
        "overview_map": ["overview", "map", "全局", "概览", "地图", "框架"],
        "comparison": ["comparison", "compare", "state", "before", "after", "对比", "比较", "状态", "方案"],
        "process": ["process", "flow", "mechanism", "cause", "effect", "过程", "流程", "机制", "因果"],
        "structure": ["structure", "component", "part", "结构", "拆解", "组成", "局部"],
        "tradeoff_matrix": ["tradeoff", "priority", "matrix", "quadrant", "取舍", "优先", "矩阵", "象限"],
        "interaction": ["interaction", "relationship", "mutual", "沟通", "互动", "关系", "协作"],
        "goal_path": ["goal", "path", "roadmap", "milestone", "目标", "路径", "路线", "倒推"],
        "cycle": ["cycle", "loop", "feedback", "iterate", "循环", "闭环", "反馈", "迭代"],
        "formula": ["formula", "equation", "公式", "="],
        "summary": ["summary", "checklist", "conclusion", "总结", "清单", "结论"],
    }
    for kind, terms in relation_terms.items():
        if kind in role or any(term in text for term in terms):
            labels.add(kind)
            labels.update(term.lower() for term in terms)
    return {label for label in labels if label}


def _coverage_unit_is_covered(unit: dict, scene_corpus: str) -> bool:
    tokens = _coverage_unit_tokens(unit)
    if not tokens:
        return True
    corpus = scene_corpus.lower()
    label = _coverage_unit_label(unit).lower()
    if label and label in corpus:
        return True
    strong_tokens = [token.lower() for token in tokens if len(token) >= 3]
    if not strong_tokens:
        return False
    hits = sum(1 for token in strong_tokens[:8] if token in corpus)
    return hits >= min(2, len(strong_tokens))


def _coverage_unit_is_redundant(unit: dict, kept_units: list[dict]) -> bool:
    current = _coverage_unit_fingerprint(unit)
    if not current:
        return False
    for kept in kept_units:
        other = _coverage_unit_fingerprint(kept)
        if not other:
            continue
        overlap = current & other
        if len(overlap) >= 2:
            return True
        label = _coverage_unit_label(unit).lower()
        kept_label = _coverage_unit_label(kept).lower()
        if label and kept_label and (label in kept_label or kept_label in label):
            return True
    return False


def _missing_coverage_units(storyboard: Storyboard, graph: ExplainGraph) -> list[dict]:
    scene_corpus = _storyboard_scene_corpus(storyboard)
    missing: list[dict] = []
    for unit in _brief_coverage_units(graph):
        priority = int(unit.get("priority") or 3)
        if priority < 3:
            continue
        if not _coverage_unit_is_covered(unit, scene_corpus):
            if _coverage_unit_is_redundant(unit, missing):
                continue
            missing.append(unit)
    return missing


def _diagram_kind_for_coverage_unit(unit: dict) -> str:
    role = _clean_text(unit.get("visual_role") or unit.get("unit_type")).lower()
    label = _coverage_unit_label(unit).lower()
    text = f"{role} {label}"
    if any(term in text for term in ["overview", "map", "whole", "landscape", "全局", "概览", "地图", "总览", "框架"]):
        return "overview_map"
    if any(term in text for term in ["formula", "equation", "公式", "="]):
        return "formula"
    if any(term in text for term in ["comparison", "compare", "versus", " vs ", "state", "对比", "状态"]):
        return "comparison"
    if any(term in text for term in ["tradeoff", "matrix", "quadrant", "priority", "2x2", "取舍", "矩阵", "象限", "优先", "分类"]):
        return "tradeoff_matrix"
    if any(term in text for term in ["interaction", "relationship", "communication", "collaboration", "exchange", "mutual", "互相", "互动", "关系", "沟通", "协作", "交换", "影响"]):
        return "interaction"
    if any(term in text for term in ["goal", "path", "journey", "roadmap", "milestone", "route", "目标", "路径", "路线", "旅程", "阶段", "里程碑"]):
        return "goal_path"
    if any(term in text for term in ["cycle", "loop", "feedback", "iterate", "renew", "循环", "闭环", "反馈", "迭代", "复盘", "更新"]):
        return "cycle"
    if any(term in text for term in ["process", "flow", "mechanism", "change", "step", "过程", "流程", "步骤", "变化", "机制"]):
        return "process"
    if any(term in text for term in ["summary", "conclusion", "checklist", "总结", "结论", "清单"]):
        return "summary"
    if any(term in text for term in ["structure", "object", "component", "结构", "对象", "组成"]):
        return "structure"
    return "concept"


