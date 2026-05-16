import json
import logging
import re

from src.core.llm import chat_json
from src.explain.models import ExplainGraph
from .models import (
    AnimationInstruction,
    AnimationType,
    GenerateRemotionCodeRequest,
    GenerateRemotionCodeResponse,
    GenerateStoryboardRequest,
    Scene,
    Storyboard,
)

logger = logging.getLogger(__name__)

ALLOWED_IMPORTS = {"react", "remotion"}
FORBIDDEN_CODE_TOKENS = (
    "from \"./",
    "from '../",
    "from \"../",
    "require(",
    "eval(",
    "new Function",
    "child_process",
    "node:",
    "fs",
    "process.",
    "document.",
    "window.",
    "localStorage",
    "sessionStorage",
    "XMLHttpRequest",
    "fetch(",
    "dangerouslySetInnerHTML",
)


def _strip_code_fence(value: str) -> str:
    text = value.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:tsx|ts|typescript|jsx|javascript)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _validate_generated_tsx(tsx: str) -> str:
    code = _strip_code_fence(tsx)
    if len(code) < 500:
        raise ValueError("Generated Remotion code is too short")

    export_ok = (
        "export const GeneratedVideo" in code
        or "export function GeneratedVideo" in code
    )
    if not export_ok:
        raise ValueError("Generated code must export GeneratedVideo")

    lowered = code.lower()
    for token in FORBIDDEN_CODE_TOKENS:
        if token.lower() in lowered:
            raise ValueError(f"Generated code contains forbidden token: {token}")

    for line in code.splitlines():
        stripped = line.strip()
        if not stripped.startswith("import "):
            continue
        match = re.search(r"from\s+['\"]([^'\"]+)['\"]", stripped)
        if not match or match.group(1) not in ALLOWED_IMPORTS:
            raise ValueError(f"Generated code has disallowed import: {stripped}")

    return code

SYSTEM_PROMPT = """你是专业的 Khan Academy / 3Blue1Brown 风格教学视频规划师。
根据概念图（Explain Graph），为中文白板动画视频规划分镜脚本。

视觉风格：米白纸张背景，黑色线条手绘插图，蓝色 Caveat 手写字体标题。

规划原则：
1. 按 teach_order 顺序讲解，每个场景聚焦 1-2 个核心要点
2. 旁白：口语化中文，B 站技术博主风格，50-120 字/场景
3. 总时长控制在目标时长 ±15 秒
4. 每场景时长 15-45 秒，animations 为 2-4 个动作
5. 动画动作要有层次感：先写标题或概念，再展开细节，最后总结
6. 每个场景必须提供 image_description（英文），描述该场景要生成的白板手绘插图

可用动画类型（重要！优先使用新类型）：

write_text — 逐字手写文本（标题、要点、说明）
  content: 要写的文字

write_formula — 公式框逐字显现（带紫色边框）
  content: 公式描述（如"均方误差"）
  latex: 公式文本（如"L(θ) = (1/n)·Σ(y - ŷ)²"）

concept_bubble — 概念气泡弹出（带颜色分类）
  content: 概念名称（简短，5-15 字）

bullet_list — 要点列表逐条展开
  content: 列表标题
  items: ["要点1", "要点2", "要点3"]（必填，3-5条）

step_reveal — 步骤序号依次显现
  content: 步骤组标题
  items: ["第一步：...", "第二步：...", "第三步：..."]（必填，2-5步）

draw_arrow — 画箭头（连接两个概念）
  content: 箭头标注文字（简短）

draw_box — 画矩形框高亮某区域
  content: 框的说明文字

highlight_region — 黄色高亮区域
  content: 说明（可为空）

旁白设计要点：
- 开场：直接点题，不废话
- 中间：解释每个动画的含义，语气自然
- 结尾：用一句话总结核心收获

image_description 设计要点：
- 必须是英文
- 描述一张白板手绘风格插图的内容（黑色线条，白色背景）
- 聚焦该场景的核心视觉概念，例如：
  "a simple diagram showing a neural network with input, hidden, and output layers connected by arrows"
  "a whiteboard sketch of gradient descent showing a ball rolling down a curved loss surface"
  "labeled anatomy diagram of a transformer attention mechanism with query, key, value boxes"

输出 JSON 格式（严格遵守）：
{
  "scenes": [
    {
      "id": "scene_0",
      "order": 0,
      "title": "场景标题（简短，5-15字）",
      "narration": "旁白文案，口语化中文，完整句子",
      "duration_estimate": 25,
      "node_ids": ["node_0"],
      "image_description": "English description of the whiteboard sketch illustration for this scene",
      "animations": [
        {
          "type": "write_text",
          "duration": 3.0,
          "content": "梯度下降",
          "latex": null,
          "items": null
        },
        {
          "type": "bullet_list",
          "duration": 8.0,
          "content": "核心概念",
          "items": ["损失函数：衡量误差", "梯度：指向增大方向", "学习率：控制步长"]
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
{chr(10).join(f"- {i}" for i in graph.key_insights)}

要求：
- 生成 {max(3, min(6, len(graph.nodes)))} 个场景
- 每个场景必须有 2-4 个 animations
- 优先使用 write_text + bullet_list/step_reveal 组合
- 公式场景必须用 write_formula（不要用 write_text 写公式）"""

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
        animations: list[AnimationInstruction] = []
        for a in s.get("animations", []):
            raw_type = a.get("type", "write_text")
            try:
                anim_type = AnimationType(raw_type)
            except ValueError:
                anim_type = AnimationType.WRITE_TEXT
            animations.append(
                AnimationInstruction(
                    type=anim_type,
                    duration=float(a.get("duration", 2.0)),
                    content=a.get("content") or "",
                    latex=a.get("latex"),
                    from_node=a.get("from_node"),
                    to_node=a.get("to_node"),
                    x=a.get("x"),
                    y=a.get("y"),
                    items=a.get("items"),
                )
            )
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
                image_description=s.get("image_description") or None,
            )
        )

    storyboard = Storyboard(
        topic=graph.topic,
        total_duration_estimate=total_duration,
        scenes=scenes,
    )

    logger.info("Storyboard generated: %d scenes, %.1fs total", len(scenes), total_duration)
    return storyboard


REMOTION_CODE_SYSTEM_PROMPT = """You are an expert Remotion engineer and motion designer.

Generate ONE self-contained TSX module for a complete educational whiteboard video.

Hard requirements:
- Export `GeneratedVideo` as a React component.
- Use only imports from "react" and "remotion".
- Do not import local files, component libraries, templates, CSS, npm packages, images, fonts, or helper modules.
- Do not use CSS animations/transitions. All motion must use Remotion frame APIs: useCurrentFrame(), interpolate(), Easing, spring(), Sequence, AbsoluteFill.
- Do not use fetch, eval, Function, require, filesystem APIs, browser globals, or dangerouslySetInnerHTML.
- Hardcode the provided storyboard content and audio URLs into the TSX.
- Use <Audio src="..."> from remotion for scene voiceover when audioUrl exists.
- Build visuals directly in TSX using HTML/CSS/SVG: hand-drawn lines, equations, arrows, curves, labels, diagrams, highlights.
- Avoid generic slide decks. Each scene must contain a meaningful visual explanation, not just bullets.
- Use a clean Chinese whiteboard teaching style: off-white background, black ink, limited accent colors, spacious layout, progressive reveal.
- Keep text inside safe bounds for 1920x1080.

Return JSON only:
{
  "tsx": "complete TSX module source",
  "duration_in_frames": integer,
  "notes": "short implementation note"
}
"""


async def generate_remotion_code(
    req: GenerateRemotionCodeRequest,
) -> GenerateRemotionCodeResponse:
    storyboard_data = req.storyboard.model_dump(mode="json")
    target_frames = max(
        req.fps * 10,
        round(req.storyboard.total_duration_estimate * req.fps),
    )
    style_prompt = req.style_prompt or (
        "Chinese AI/ML whiteboard lesson. Hand-drawn diagrams made in SVG, "
        "no stock images, no decorative template frames."
    )

    user_content = json.dumps(
        {
            "fps": req.fps,
            "width": req.width,
            "height": req.height,
            "target_duration_in_frames": target_frames,
            "style_prompt": style_prompt,
            "storyboard": storyboard_data,
        },
        ensure_ascii=False,
    )

    logger.info("Generating Remotion TSX for: %s", req.storyboard.topic)

    raw = await chat_json(
        messages=[
            {"role": "system", "content": REMOTION_CODE_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        model=None,
    )

    tsx = _validate_generated_tsx(raw.get("tsx") or raw.get("code") or "")
    duration = int(raw.get("duration_in_frames") or target_frames)
    duration = max(req.fps * 10, min(duration, req.fps * 240))

    return GenerateRemotionCodeResponse(
        tsx=tsx,
        duration_in_frames=duration,
        fps=req.fps,
        width=req.width,
        height=req.height,
        notes=raw.get("notes"),
    )
