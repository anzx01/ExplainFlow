import logging

from src.core.llm import chat_json
from src.explain.models import ExplainGraph
from .models import (
    AnimationInstruction,
    AnimationType,
    GenerateStoryboardRequest,
    Scene,
    Storyboard,
)

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """你是专业的 Khan Academy 风格教学视频规划师。
根据 Explain Graph（概念图），规划一个中文白板讲解视频的分镜脚本。

规划原则：
1. 按 teach_order 顺序讲解，每个场景聚焦 1-2 个概念
2. 旁白用口语化中文，适合 B 站技术博主风格
3. 总时长控制在目标时长 ±20秒以内
4. 每场景时长 15-40 秒，开场和结尾可以稍短
5. animations 字段描述该场景的动画动作序列

动画类型说明：
- whiteboard_draw: 白板手写（文字、标题）
- formula_reveal: 公式逐步浮现（需要 latex 字段）
- concept_node: 概念卡片出现
- arrow_connect: 箭头连接两个概念
- highlight: 高亮强调某部分
- particle_flow: 粒子/数据流动（用于数据流、反向传播等）
- network_layer: 神经网络层（用于神经网络结构）
- text_narration: 纯文字讲解卡

输出格式为 JSON：
{
  "scenes": [
    {
      "id": "scene_0",
      "order": 0,
      "title": "场景标题",
      "narration": "旁白文案，口语化中文，完整句子，不要太长（50-120字）",
      "duration_estimate": 20,
      "node_ids": ["node_0"],
      "animations": [
        {
          "type": "whiteboard_draw",
          "duration": 2.0,
          "content": "显示的文字",
          "latex": null,
          "from_node": null,
          "to_node": null
        }
      ]
    }
  ]
}"""


async def generate_storyboard(req: GenerateStoryboardRequest) -> Storyboard:
    graph = req.graph
    nodes_desc = "\n".join(
        f"- [{n.node_type.value}] {n.label}（teach_order={n.teach_order}）: {n.description}"
        + (f" LaTeX: {n.latex}" if n.latex else "")
        for n in sorted(graph.nodes, key=lambda x: x.teach_order)
    )
    edges_desc = "\n".join(
        f"- {e.source} → {e.target}（{e.relation}）" for e in graph.edges
    )

    user_content = f"""主题：{graph.topic}
总结：{graph.summary}
目标时长：{req.target_duration}秒

概念节点（按教学顺序）：
{nodes_desc}

概念关系：
{edges_desc}

核心洞察：
{chr(10).join(f"- {i}" for i in graph.key_insights)}"""

    logger.info("Generating storyboard for: %s, target=%ds", graph.topic, req.target_duration)

    raw = await chat_json(
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]
    )

    scenes: list[Scene] = []
    total_duration = 0.0

    for s in raw.get("scenes", []):
        animations = [
            AnimationInstruction(
                type=AnimationType(a.get("type", "whiteboard_draw")),
                duration=float(a.get("duration", 2.0)),
                content=a.get("content") or "",
                latex=a.get("latex"),
                from_node=a.get("from_node"),
                to_node=a.get("to_node"),
            )
            for a in s.get("animations", [])
        ]
        dur = float(s.get("duration_estimate", 20))
        total_duration += dur
        scenes.append(
            Scene(
                id=s.get("id") or f"scene_{len(scenes)}",
                order=s.get("order", len(scenes)),
                title=s.get("title") or f"场景 {len(scenes) + 1}",
                narration=s.get("narration") or "",
                duration_estimate=dur,
                animations=animations,
                node_ids=s.get("node_ids") or [],
            )
        )

    storyboard = Storyboard(
        topic=graph.topic,
        total_duration_estimate=total_duration,
        scenes=scenes,
    )

    logger.info("Storyboard generated: %d scenes, %.1fs total", len(scenes), total_duration)
    return storyboard
