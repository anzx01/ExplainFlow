from src.explain.models import ExplainGraph
from ..models import Scene, Storyboard
from .timing import _max_scene_count_for_target
from .normalizer import _clean_text
from ..coverage.analyzer import (
    _missing_coverage_units,
    _brief_coverage_units,
    _diagram_kind_for_coverage_unit,
    _coverage_unit_tokens,
    _coverage_unit_is_covered,
)
from ..coverage.corpus import _scene_corpus, _contains_terms, _graph_enhanced_brief


def _visual_relation_kind_for_scene(scene: Scene) -> str | None:
    """Infer visual relation kind from scene corpus (local copy to avoid fallback import cycle)."""
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
    patterns: list[tuple[str, list[str]]] = [
        ("priority_matrix", ["tradeoff", "quadrant", "2x2", "matrix", "priority", "取舍", "矩阵", "象限", "二维", "优先", "紧急", "重要", "分类"]),
        ("interaction_scenario", ["interaction", "relationship", "communication", "collaboration", "exchange", "互相", "互动", "关系", "沟通", "协作", "交换", "双方", "共同", "影响"]),
        ("goal_path", ["goal", "target", "vision", "path", "milestone", "route", "journey", "backcast", "目标", "愿景", "路径", "路线", "里程碑", "倒推", "阶段"]),
        ("feedback_loop", ["feedback", "loop", "cycle", "iterate", "iteration", "renewal", "闭环", "反馈", "循环", "迭代", "复盘", "更新", "重复"]),
        ("comparison_transform", ["comparison", "compare", "versus", " vs ", "before", "after", "contrast", "对比", "比较", "前后", "状态", "开关", "变化", "转换"]),
        ("process_flow", ["process", "flow", "mechanism", "cause", "effect", "step", "pipeline", "过程", "流程", "机制", "因果", "步骤", "原理"]),
        ("teaching_board", ["overview", "map", "framework", "structure", "component", "part", "whole", "概览", "框架", "结构", "组成", "部件", "整体"]),
    ]
    for result, terms in patterns:
        if any(t in text for t in terms):
            return result
    return None

def _scene_relation_key(scene: Scene) -> str:
    return _visual_relation_kind_for_scene(scene) or (
        _clean_text(scene.diagram_plan.kind if scene.diagram_plan else "") or "scene"
    )


def _reindex_storyboard_scenes(storyboard: Storyboard) -> Storyboard:
    for index, scene in enumerate(storyboard.scenes):
        scene.order = index
        scene.id = f"scene_{index}"
    storyboard.total_duration_estimate = round(sum(scene.duration_estimate for scene in storyboard.scenes), 1)
    return storyboard


def _is_opening_scene(scene: Scene) -> bool:
    title = (scene.title or "").lower()
    corpus = " ".join([scene.title or "", scene.learning_goal or "", scene.narration or ""]).lower()
    if _contains_terms(title, ["总结", "回顾", "复盘", "收尾", "summary", "conclusion"]):
        return False
    return _contains_terms(corpus, ["开场", "导入", "引入", "opening", "intro", "hook"])


def _ensure_opening_scene_first(storyboard: Storyboard) -> Storyboard:
    if len(storyboard.scenes) < 2:
        return storyboard
    opening_index = next((index for index, scene in enumerate(storyboard.scenes) if _is_opening_scene(scene)), None)
    if opening_index is None or opening_index == 0:
        return storyboard
    opening_scene = storyboard.scenes.pop(opening_index)
    storyboard.scenes.insert(0, opening_scene)
    return _reindex_storyboard_scenes(storyboard)


def _trim_storyboard_scene_count(storyboard: Storyboard, target_duration: int, graph: ExplainGraph | None = None) -> Storyboard:
    max_scenes = _max_scene_count_for_target(target_duration)
    if len(storyboard.scenes) <= max_scenes:
        return storyboard

    protected: list[Scene] = []
    if graph is not None:
        protected = _protected_coverage_scenes(storyboard, graph, max_scenes)

    unique: list[Scene] = []
    deferred: list[Scene] = []
    seen: set[str] = set()
    for scene in storyboard.scenes:
        kind = _scene_relation_key(scene)
        if kind in seen:
            deferred.append(scene)
            continue
        seen.add(kind)
        unique.append(scene)

    candidates = unique + deferred
    selected: list[Scene] = []
    for scene in protected + candidates:
        if scene not in selected:
            selected.append(scene)
        if len(selected) >= max_scenes:
            break

    summary_scene = next(
        (
            scene
            for scene in reversed(candidates)
            if (_visual_relation_kind_for_scene(scene) == "teaching_board_summary")
            or (_clean_text(scene.diagram_plan.kind if scene.diagram_plan else "").lower() in {"summary", "checklist", "conclusion"})
        ),
        None,
    )
    protected_set = set(id(scene) for scene in protected)
    if summary_scene and summary_scene not in selected and selected:
        replace_at = next((i for i in range(len(selected) - 1, -1, -1) if id(selected[i]) not in protected_set), None)
        if replace_at is None:
            replace_at = len(selected) - 1
        if id(selected[replace_at]) not in protected_set:
            selected[replace_at] = summary_scene

    if graph is not None:
        selected = _repair_missing_protected_scenes(selected, storyboard.scenes, graph, max_scenes)

    storyboard.scenes = selected[:max_scenes]
    return _reindex_storyboard_scenes(storyboard)


def _repair_missing_protected_scenes(selected: list[Scene], all_scenes: list[Scene], graph: ExplainGraph, max_scenes: int) -> list[Scene]:
    selected_storyboard = Storyboard(topic=graph.topic, total_duration_estimate=0, scenes=list(selected))
    missing = _missing_coverage_units(selected_storyboard, graph)
    if not missing:
        return selected
    result = list(selected)
    for unit in missing:
        replacement = _best_scene_for_coverage_unit(all_scenes, unit, result)
        if replacement is None or replacement in result:
            continue
        replace_at = _replaceable_scene_index(result)
        if replace_at is None and len(result) < max_scenes:
            result.append(replacement)
        elif replace_at is not None:
            result[replace_at] = replacement
    return result[:max_scenes]


def _replaceable_scene_index(scenes: list[Scene], protected_ids: set[int] | None = None) -> int | None:
    protected_ids = protected_ids or set()
    for index in range(len(scenes) - 1, -1, -1):
        if id(scenes[index]) in protected_ids:
            continue
        kind = _scene_relation_key(scenes[index]).lower()
        if kind in {"summary", "teaching_board_summary", "checklist", "conclusion"}:
            return index
    for index in range(len(scenes) - 1, -1, -1):
        if id(scenes[index]) not in protected_ids:
            return index
    return None


def _protected_coverage_scenes(storyboard: Storyboard, graph: ExplainGraph, limit: int) -> list[Scene]:
    protected: list[Scene] = []
    for unit in _high_priority_coverage_units(graph):
        scene = _best_scene_for_coverage_unit(storyboard.scenes, unit, protected)
        if scene is not None and scene not in protected:
            protected.append(scene)
        if len(protected) >= limit:
            break
    return protected


def _best_scene_for_coverage_unit(scenes: list[Scene], unit: dict, excluded: list[Scene] | None = None) -> Scene | None:
    excluded_ids = {id(scene) for scene in excluded or []}
    expected_kind = _diagram_kind_for_coverage_unit(unit)
    tokens = [token.lower() for token in _coverage_unit_tokens(unit) if len(token) >= 2]
    best_score: tuple[int, int] | None = None
    best_scene: Scene | None = None
    for index, scene in enumerate(scenes):
        if id(scene) in excluded_ids:
            continue
        corpus = _scene_corpus(scene).lower()
        score = 0
        if _coverage_unit_is_covered(unit, corpus):
            score += 8
        if expected_kind and expected_kind in {_clean_text(scene.diagram_plan.kind if scene.diagram_plan else "").lower(), _scene_relation_key(scene).lower()}:
            score += 6
        score += min(5, sum(1 for token in tokens[:10] if token in corpus))
        if score <= 0:
            continue
        candidate_score = (score, -index)
        if best_score is None or candidate_score > best_score:
            best_score = candidate_score
            best_scene = scene
    return best_scene


def _high_priority_coverage_units(graph: ExplainGraph) -> list[dict]:
    units = []
    for unit in _brief_coverage_units(graph):
        priority = int(unit.get("priority") or 3)
        if priority >= 3:
            units.append(unit)
    return sorted(units, key=lambda item: int(item.get("priority") or 3), reverse=True)


def _desired_scene_count(graph: ExplainGraph, target_duration: int) -> int:
    brief = _graph_enhanced_brief(graph) or {}
    outline = brief.get("recommended_scene_outline") if isinstance(brief, dict) else None
    outline_count = len(outline) if isinstance(outline, list) else 0
    coverage_count = len(_brief_coverage_units(graph))
    scene_cap = _max_scene_count_for_target(target_duration)
    topic_blob = " ".join(
        [
            graph.topic,
            graph.summary,
            " ".join(graph.key_insights),
            json.dumps(brief, ensure_ascii=False) if brief else "",
        ]
    ).lower()
    if coverage_count >= 7:
        return max(6, min(scene_cap, 7))
    if coverage_count >= 4:
        return max(4, min(scene_cap, 6))
    if outline_count:
        return max(3, min(scene_cap, outline_count))
    node_count = len(graph.nodes)
    duration_based = max(3, target_duration // 20)
    if node_count >= 7 and target_duration >= 100:
        return max(6, min(scene_cap, node_count))
    if node_count > 0:
        return max(3, min(scene_cap, node_count, duration_based))
    return max(3, min(scene_cap, duration_based))


