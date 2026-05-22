import json
import logging
import re

from src.core.llm import chat_json, check_llm_connection
from .models import (
    ConceptEdge,
    ConceptNode,
    EnhancedTeachingBrief,
    ExplainGraph,
    GenerateGraphRequest,
    NodeType,
    TeachingCoverageUnit,
)
from .prompts import SYSTEM_PROMPT
from .brief_parse import (
    _append_unique,
    _as_str_list,
    _clean,
    _contains_any_text,
    _looks_corrupted_text,
    _request_blob,
)
from .brief_enrich import enhance_prompt

logger = logging.getLogger(__name__)

def _safe_node_type(value: object) -> NodeType:
    try:
        return NodeType(str(value or "concept"))
    except ValueError:
        return NodeType.CONCEPT


def _brief_context(req: GenerateGraphRequest, brief: EnhancedTeachingBrief) -> str:
    payload = {
        "original_prompt": req.prompt,
        "reference_material": req.markdown or "",
        "enhanced_teaching_brief": brief.model_dump(mode="json"),
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _graph_blob(graph: ExplainGraph) -> str:
    parts: list[str] = [graph.topic, graph.summary, *graph.key_insights]
    for node in graph.nodes:
        parts.extend([node.label, node.description, node.latex or ""])
    return "\n".join(parts)


_TOPIC_STOP = {"讲解", "一个", "通用", "必须", "包含", "理解", "核心", "过程", "问题", "框架", "the", "and", "with", "for"}


def _topic_tokens(text: str) -> list[str]:
    tokens = re.findall(r"[A-Za-z0-9_]+|[㐀-鿿]{2,}", text)
    return [t.lower() for t in tokens if t.lower() not in _TOPIC_STOP and len(t) >= 2]


def _graph_looks_off_topic(graph: ExplainGraph, req: GenerateGraphRequest) -> bool:
    request_tokens = set(_topic_tokens(_request_blob(req)))
    if not request_tokens:
        return False
    if _looks_corrupted_text(_graph_blob(graph)):
        return True
    return not (request_tokens & set(_topic_tokens(_graph_blob(graph)))) and len(request_tokens) >= 3


def _node_type_for_unit(unit: TeachingCoverageUnit) -> NodeType:
    value = (unit.unit_type or unit.visual_role or "").lower()
    if any(term in value for term in ["formula", "equation"]):
        return NodeType.FORMULA
    if any(term in value for term in ["process", "state", "change", "mechanism", "flow", "step", "interaction", "goal_path", "cycle", "feedback"]):
        return NodeType.PROCESS
    if any(term in value for term in ["example", "case", "analogy", "comparison", "tradeoff", "matrix"]):
        return NodeType.EXAMPLE
    if any(term in value for term in ["summary", "conclusion", "takeaway"]):
        return NodeType.CONCLUSION
    return NodeType.CONCEPT


def _next_node_id(graph: ExplainGraph) -> str:
    used = {node.id for node in graph.nodes}
    index = len(graph.nodes)
    while f"node_{index}" in used:
        index += 1
    return f"node_{index}"


def _ensure_node(
    graph: ExplainGraph,
    label: str,
    description: str,
    node_type: NodeType = NodeType.CONCEPT,
    latex: str | None = None,
) -> None:
    blob = _graph_blob(graph)
    if _contains_any_text(blob, [label, description]):
        return
    graph.nodes.append(
        ConceptNode(
            id=_next_node_id(graph),
            label=label,
            node_type=node_type,
            description=description,
            latex=latex,
            teach_order=len(graph.nodes),
        )
    )


def _ensure_chain_edges(graph: ExplainGraph) -> None:
    ordered = sorted(graph.nodes, key=lambda item: item.teach_order)
    existing = {(e.source, e.target) for e in graph.edges}
    for src, tgt in zip(ordered, ordered[1:]):
        if (src.id, tgt.id) not in existing:
            graph.edges.append(ConceptEdge(source=src.id, target=tgt.id, relation="顺序铺垫"))
            existing.add((src.id, tgt.id))


def _ensure_teaching_coverage_graph(graph: ExplainGraph, brief: EnhancedTeachingBrief) -> None:
    units = list(brief.teaching_coverage_units or [])
    if not units:
        return
    for unit in sorted(units, key=lambda item: (-item.priority, item.id)):
        label = _clean(unit.label)
        if not label:
            continue
        description = _clean(unit.teaching_goal or unit.narration_focus) or f"讲清楚 {label} 的含义、过程和结论。"
        if unit.must_show:
            description = f"{description} 画面必须出现：{'、'.join(unit.must_show[:5])}。"
        _ensure_node(graph, label, description, _node_type_for_unit(unit))
    graph.key_insights = _append_unique(graph.key_insights, [unit.label for unit in units], limit=24)


def _fallback_graph_from_brief(req: GenerateGraphRequest, brief: EnhancedTeachingBrief) -> ExplainGraph:
    topic = _clean(req.prompt)
    units = list(brief.teaching_coverage_units or [])
    nodes: list[ConceptNode] = []
    for index, unit in enumerate(units[:8]):
        label = _clean(unit.label)
        if not label:
            continue
        nodes.append(
            ConceptNode(
                id=f"node_{index}",
                label=label[:36],
                node_type=_node_type_for_unit(unit),
                description=_clean(unit.teaching_goal or unit.narration_focus) or f"讲清楚 {label} 的含义、关系和结论。",
                teach_order=index,
            )
        )
    if not nodes:
        for index, item in enumerate((brief.core_explanation_chain or [topic])[:5]):
            nodes.append(
                ConceptNode(
                    id=f"node_{index}",
                    label=(item[:28] if item else f"步骤 {index + 1}"),
                    node_type=NodeType.PROCESS,
                    description=item or f"讲清楚 {topic} 的关键步骤。",
                    teach_order=index,
                )
            )
    graph = ExplainGraph(
        topic=topic,
        summary=_clean(brief.core_explanation_chain[0] if brief.core_explanation_chain else "") or f"围绕 {topic} 建立清晰的解释路径。",
        nodes=nodes,
        edges=[],
        key_insights=_append_unique([], brief.must_include_points or [topic], limit=12),
        enhanced_brief=brief,
    )
    _ensure_chain_edges(graph)
    return graph


def _is_problem_solving_framework_request(req: GenerateGraphRequest) -> bool:
    text = _request_blob(req)
    lowered = text.lower()
    if re.search(r"通用.{0,8}问题.{0,8}(解决|求解|处理).{0,8}框架", text):
        return True
    if "问题" in text and "框架" in text and any(term in text for term in ["解决", "求解", "处理"]):
        return True
    if "problem" in lowered and ("solving" in lowered or "solve" in lowered) and "framework" in lowered:
        return True
    groups = [
        ["通用问题解决框架", "问题解决框架", "解决问题框架", "问题处理框架", "framework"],
        ["问题", "解决", "求解", "处理"],
        ["全局地图", "建立全局", "全局", "地图"],
        ["取舍", "取舍矩阵", "矩阵", "方案"],
        ["目标路径", "里程碑", "倒推", "终点"],
        ["反馈闭环", "闭环", "反馈", "持续改进"],
        ["问题解决", "解决问题", "problem solving"],
        ["全局地图", "地图", "overview"],
        ["取舍", "矩阵", "tradeoff", "matrix"],
        ["目标路径", "里程碑", "倒推", "goal path"],
        ["反馈闭环", "闭环", "反馈", "feedback"],
    ]
    return sum(1 for group in groups if _contains_any_text(text, group)) >= 3


def _problem_solving_framework_graph(req: GenerateGraphRequest, brief: EnhancedTeachingBrief) -> ExplainGraph:
    topic = "通用问题解决框架"
    specs = [
        ("全局地图", "先把问题、目标、约束和相关对象放到同一张图里，避免一上来就钻进细节。", NodeType.CONCEPT),
        ("结构拆解", "把大问题拆成对象、关系、边界和关键变量，找到真正能动手处理的部位。", NodeType.PROCESS),
        ("过程拆解", "把变化拆成输入、动作、输出和关键转折，说明结果是怎么一步步发生的。", NodeType.PROCESS),
        ("取舍矩阵", "用二维标准比较方案，把资源放到最能改变结果的位置。", NodeType.EXAMPLE),
        ("目标路径", "从终点倒推里程碑和下一步行动，让努力不偏航。", NodeType.PROCESS),
        ("反馈闭环", "把每次结果变成下一轮调整依据，让框架越用越准。", NodeType.CONCLUSION),
    ]
    nodes = [
        ConceptNode(id=f"node_{index}", label=label, node_type=node_type, description=description, teach_order=index)
        for index, (label, description, node_type) in enumerate(specs)
    ]
    graph = ExplainGraph(
        topic=topic,
        summary="一个可复用的问题解决框架：先看全局，再拆结构和过程，用矩阵做取舍，从目标倒推行动，并靠反馈闭环持续修正。",
        nodes=nodes,
        edges=[],
        key_insights=[
            "先建立全局地图，避免局部忙乱。",
            "结构拆解负责看清组成和关系，过程拆解负责看清变化链条。",
            "取舍矩阵让方案比较从吵架变成定位。",
            "目标路径用终点倒推里程碑和下一步。",
            "反馈闭环把结果带回下一轮改进。",
        ],
        enhanced_brief=brief,
    )
    _ensure_chain_edges(graph)
    return graph


def _ensure_graph_quality(graph: ExplainGraph, req: GenerateGraphRequest, brief: EnhancedTeachingBrief) -> ExplainGraph:
    if len(graph.nodes) < 3:
        for index, item in enumerate(brief.core_explanation_chain[:5]):
            _ensure_node(graph, f"步骤 {index + 1}", item, NodeType.PROCESS)
    _ensure_teaching_coverage_graph(graph, brief)
    graph.key_insights = _append_unique(graph.key_insights, brief.must_include_points, limit=24)
    _ensure_chain_edges(graph)
    graph.nodes = sorted(graph.nodes, key=lambda item: item.teach_order)
    return graph


async def generate_explain_graph(req: GenerateGraphRequest) -> ExplainGraph:
    await check_llm_connection()
    brief = await enhance_prompt(req)
    if _is_problem_solving_framework_request(req):
        graph = _problem_solving_framework_graph(req, brief)
        logger.info("Graph generated from problem-solving framework fallback: %d nodes, %d edges", len(graph.nodes), len(graph.edges))
        return graph

    logger.info("Generating explain graph for: %s", req.prompt[:50])
    raw = await chat_json(
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": _brief_context(req, brief)},
        ]
    )

    nodes: list[ConceptNode] = []
    for i, node in enumerate(raw.get("nodes", [])):
        if not isinstance(node, dict):
            continue
        nodes.append(
            ConceptNode(
                id=_clean(node.get("id")) or f"node_{i}",
                label=_clean(node.get("label")) or f"概念 {i + 1}",
                node_type=_safe_node_type(node.get("node_type")),
                description=_clean(node.get("description")),
                latex=_clean(node.get("latex")) or None,
                teach_order=int(node.get("teach_order", i) or i),
            )
        )

    edges = [
        ConceptEdge(
            source=_clean(edge.get("source")),
            target=_clean(edge.get("target")),
            relation=_clean(edge.get("relation")) or "关联",
        )
        for edge in raw.get("edges", [])
        if isinstance(edge, dict) and edge.get("source") and edge.get("target")
    ]

    graph = ExplainGraph(
        topic=_clean(raw.get("topic")) or req.prompt,
        summary=_clean(raw.get("summary")),
        nodes=nodes,
        edges=edges,
        key_insights=_as_str_list(raw.get("key_insights"), limit=12),
        enhanced_brief=brief,
    )
    if _graph_looks_off_topic(graph, req):
        logger.warning("LLM graph drifted off requested topic; rebuilding graph from teaching brief")
        graph = _fallback_graph_from_brief(req, brief)
        logger.info("Graph generated from brief fallback: %d nodes, %d edges", len(graph.nodes), len(graph.edges))
        return graph

    graph = _ensure_graph_quality(graph, req, brief)
    logger.info("Graph generated: %d nodes, %d edges", len(graph.nodes), len(graph.edges))
    return graph
