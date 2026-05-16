import logging

from src.core.llm import chat_json
from .models import (
    ConceptEdge,
    ConceptNode,
    ExplainGraph,
    GenerateGraphRequest,
    NodeType,
)

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """你是一位专业的 AI/ML 教学规划专家。
用户会给你一个 AI/ML 概念或主题，你需要：
1. 提取该主题涉及的核心概念、公式、过程
2. 分析概念之间的逻辑依赖关系
3. 规划最优的教学顺序（teach_order 从 0 开始）
4. 生成适合 Khan Academy 白板动画风格的讲解结构

要求：
- 节点数量：5-10 个（不要太少也不要太多）
- 每个节点必须有清晰的一句话描述
- teach_order 必须按教学逻辑排序（0 = 最先讲）
- 公式节点的 latex 字段用标准 LaTeX 语法
- edges 的 relation 用中文描述（如："依赖于"、"推导出"、"是...的特例"）

输出格式为 JSON，严格遵守以下结构：
{
  "topic": "主题名称",
  "summary": "本次讲解的一句话总结（面向初学者）",
  "nodes": [
    {
      "id": "node_0",
      "label": "显示名称（简短）",
      "node_type": "concept|formula|example|conclusion|process",
      "description": "一句话说明这个概念",
      "latex": "LaTeX公式字符串（仅formula类型需要，其他为null）",
      "teach_order": 0
    }
  ],
  "edges": [
    {
      "source": "node_0",
      "target": "node_1",
      "relation": "关系描述"
    }
  ],
  "key_insights": ["核心洞察1", "核心洞察2", "核心洞察3"]
}"""


async def generate_explain_graph(req: GenerateGraphRequest) -> ExplainGraph:
    user_content = f"主题：{req.prompt}"
    if req.markdown:
        user_content += f"\n\n参考材料：\n{req.markdown}"

    logger.info("Generating explain graph for: %s", req.prompt[:50])

    raw = await chat_json(
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]
    )

    nodes = [
        ConceptNode(
            id=n.get("id") or f"node_{i}",
            label=n.get("label") or f"概念{i}",
            node_type=NodeType(n.get("node_type") or "concept"),
            description=n.get("description") or "",
            latex=n.get("latex"),
            teach_order=n.get("teach_order", i),
        )
        for i, n in enumerate(raw.get("nodes", []))
    ]

    edges = [
        ConceptEdge(
            source=e.get("source", ""),
            target=e.get("target", ""),
            relation=e.get("relation") or "关联",
        )
        for e in raw.get("edges", [])
        if e.get("source") and e.get("target")
    ]

    import re
    _ansi = re.compile(r"\x1b\[[0-9;]*m")

    def clean(s: str) -> str:
        return _ansi.sub("", s).strip()

    graph = ExplainGraph(
        topic=clean(raw.get("topic") or req.prompt),
        summary=clean(raw.get("summary") or ""),
        nodes=nodes,
        edges=edges,
        key_insights=raw.get("key_insights", []),
    )

    logger.info("Graph generated: %d nodes, %d edges", len(nodes), len(edges))
    return graph
