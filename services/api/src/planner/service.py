import json
import logging
import math
import re
from copy import deepcopy

from src.core.llm import chat_json, check_llm_connection
from src.core.config import settings
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
HAND_ASSET = "hand-real-pen.png"
REMOTION_CODE_CACHE: dict[str, GenerateRemotionCodeResponse] = {}
REMOTION_CODE_CACHE_MAX_ITEMS = 16
FORBIDDEN_CODE_TOKENS = (
    "from \"./",
    "from './",
    "from '../",
    "from \"../",
    "require(",
    "eval(",
    "new Function",
    "child_process",
    "node:",
    "process.",
    "document.",
    "window.",
    "localStorage",
    "sessionStorage",
    "XMLHttpRequest",
    "fetch(",
    "dangerouslySetInnerHTML",
)
FORBIDDEN_CODE_PATTERNS = (
    r"\bfs\.",
    r"\bfs/promises\b",
    r"\bimport\s*\(",
    r"<\s*animate\b",
    r"\btransition\s*:",
    r"\banimation(?:Name|Duration|TimingFunction|Delay|IterationCount|Direction|FillMode|PlayState)?\s*:",
    r"@keyframes\b",
    r"\bclassName\s*=\s*['\"][^'\"]*\banimate-",
    r"\bsetTimeout\s*\(",
    r"\bsetInterval\s*\(",
    r"\brequestAnimationFrame\s*\(",
    r"\bDate\.now\s*\(",
    r"\bMath\.random\s*\(",
)


def _has_watercolor_accent(code: str) -> bool:
    for value in re.findall(r"#[0-9a-fA-F]{6}\b", code):
        if value.lower() in {"#000000", "#ffffff"}:
            continue
        r = int(value[1:3], 16)
        g = int(value[3:5], 16)
        b = int(value[5:7], 16)
        is_neutral = max(r, g, b) - min(r, g, b) < 24
        is_too_light = min(r, g, b) > 238
        is_too_dark = max(r, g, b) < 48
        if not is_neutral and not is_too_light and not is_too_dark:
            return True
    return bool(re.search(r"\brgba?\s*\(", code, flags=re.IGNORECASE))


def _validate_stroke_following_timeline(code: str) -> None:
    """Require one stroke timeline to drive both drawings and the visible hand."""
    required_tokens = (
        "drawOps",
        "startFrame",
        "endFrame",
        "points",
        "pointOnPolyline",
        "getActiveDrawOp",
        "getPenPosition",
    )
    for token in required_tokens:
        if not re.search(rf"\b{token}\b", code):
            raise ValueError(
                "Generated Remotion code must define drawOps with points plus "
                "getPenPosition() so the hand follows the active text/path stroke"
            )

    if not re.search(r"\b['\"]?kind['\"]?\s*:\s*['\"]text['\"]", code):
        raise ValueError("drawOps must include text operations with kind: 'text'")
    if not re.search(r"\b['\"]?kind['\"]?\s*:\s*['\"](?:path|stroke|shape|arrow|box)['\"]", code):
        raise ValueError("drawOps must include path/stroke operations for diagrams")

    point_count = len(
        re.findall(
            r"\{\s*['\"]?x['\"]?\s*:\s*-?\d+(?:\.\d+)?\s*,\s*['\"]?y['\"]?\s*:\s*-?\d+(?:\.\d+)?\s*\}",
            code,
        )
    )
    if point_count < 16:
        raise ValueError(
            "drawOps must contain at least 16 explicit {x, y} points so the pen traces strokes smoothly"
        )

    if not re.search(r"\bgetPenPosition\s*\(\s*frame\s*\)", code):
        raise ValueError("Generated Remotion code must call getPenPosition(frame) for the hand position")

    coarse_tip = (
        r"\bconst\s+(?:tipX|tipY|penX|penY)\s*=\s*interpolate\s*"
        r"\(\s*frame\s*,\s*\[[^\]]+\]\s*,\s*\[[^\]]+\]"
    )
    if re.search(coarse_tip, code):
        raise ValueError(
            "Pen tip coordinates must not use coarse scene-level interpolate(frame, [...]); "
            "derive the tip from active drawOp points"
        )

    if re.search(r"<\s*text\b", code, flags=re.IGNORECASE):
        raise ValueError(
            "Do not use static SVG <text>; render handwriting text with glyphPaths driven by drawOps"
        )


def _validate_glyph_outline_text(code: str) -> None:
    if not (
        re.search(r"\bglyphPaths\b", code)
        and re.search(r"\b(DrawGlyphPath|GlyphText)\b", code)
    ):
        raise ValueError(
            "Generated Remotion code must render Chinese text through preprocessed "
            "glyphPaths/GlyphText, not HTML text reveal only"
        )
    if re.search(r"\bHandText\b", code) and not re.search(r"\bGlyphText\b", code):
        raise ValueError(
            "Generated Remotion code must replace HandText slice rendering with GlyphText outline path drawing"
        )


def _validate_handwritten_anime_style(code: str) -> None:
    if not re.search(
        r"\b(STXingkai|Xingkai|KaiTi|STKaiti|Kaiti|楷体|华文行楷|华文楷体)\b",
        code,
        flags=re.IGNORECASE,
    ):
        raise ValueError(
            "Generated Remotion code must use an explicit Chinese handwriting font stack "
            "such as STXingkai/华文行楷/KaiTi/STKaiti"
        )
    if re.search(r"\bfontWeight\s*:\s*['\"]?(?:700|800|900|bold)\b", code, flags=re.IGNORECASE):
        raise ValueError("Handwritten text must not use bold sans-serif styling")
    if not re.search(
        r"\b(AnimeDoodle|CartoonDiagram|CartoonMascot|DoodleCharacter|anime|cartoon|doodle)\b",
        code,
        flags=re.IGNORECASE,
    ):
        raise ValueError(
            "Generated Remotion code must include anime/cartoon whiteboard doodle graphics, "
            "not only charts or slide labels"
        )


def _strip_code_fence(value: str) -> str:
    text = value.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:tsx|ts|typescript|jsx|javascript)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _has_generated_video_named_export(code: str) -> bool:
    return bool(
        re.search(r"export\s+const\s+GeneratedVideo\b", code)
        or re.search(r"export\s+function\s+GeneratedVideo\b", code)
        or re.search(r"export\s*\{\s*GeneratedVideo\s*\}", code)
    )


def _normalize_generated_video_export(code: str) -> str:
    if _has_generated_video_named_export(code):
        return code

    code = re.sub(
        r"export\s+default\s+function\s+GeneratedVideo\s*\(",
        "export function GeneratedVideo(",
        code,
        count=1,
    )
    if _has_generated_video_named_export(code):
        return code

    if re.search(r"\b(function|const|let|var)\s+GeneratedVideo\b", code):
        code = re.sub(r"export\s+default\s+GeneratedVideo\s*;?", "", code, count=1)
        return f"{code.rstrip()}\n\nexport {{ GeneratedVideo }};\n"

    default_function = re.search(r"export\s+default\s+function\s+([A-Z]\w*)\s*\(", code)
    if default_function:
        name = default_function.group(1)
        code = re.sub(
            rf"export\s+default\s+function\s+{name}\s*\(",
            f"function {name}(",
            code,
            count=1,
        )
        return f"{code.rstrip()}\n\nexport const GeneratedVideo = {name};\n"

    default_identifier = re.search(r"export\s+default\s+([A-Z]\w*)\s*;?", code)
    if default_identifier:
        name = default_identifier.group(1)
        code = re.sub(rf"export\s+default\s+{name}\s*;?", "", code, count=1)
        return f"{code.rstrip()}\n\nexport const GeneratedVideo = {name};\n"

    return code


def _remotion_codegen_cache_key(req: GenerateRemotionCodeRequest, mode: str) -> str:
    return json.dumps(
        {
            "mode": mode,
            "fps": req.fps,
            "width": req.width,
            "height": req.height,
            "style_prompt": req.style_prompt,
            "storyboard": req.storyboard.model_dump(mode="json"),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _cache_remotion_response(key: str, response: GenerateRemotionCodeResponse) -> GenerateRemotionCodeResponse:
    if len(REMOTION_CODE_CACHE) >= REMOTION_CODE_CACHE_MAX_ITEMS:
        REMOTION_CODE_CACHE.pop(next(iter(REMOTION_CODE_CACHE)))
    REMOTION_CODE_CACHE[key] = deepcopy(response)
    return response


def _cached_remotion_response(key: str) -> GenerateRemotionCodeResponse | None:
    cached = REMOTION_CODE_CACHE.get(key)
    return deepcopy(cached) if cached else None


def _compile_fast_remotion_response(
    req: GenerateRemotionCodeRequest,
    note: str,
) -> GenerateRemotionCodeResponse:
    fallback_tsx, fallback_duration = _build_fallback_remotion_tsx(
        req.storyboard,
        req.fps,
        req.width,
        req.height,
    )
    return GenerateRemotionCodeResponse(
        tsx=_validate_generated_tsx(fallback_tsx),
        duration_in_frames=max(req.fps * 10, min(fallback_duration, req.fps * 240)),
        fps=req.fps,
        width=req.width,
        height=req.height,
        notes=note,
    )


def _validate_generated_tsx(tsx: str) -> str:
    code = _normalize_generated_video_export(_strip_code_fence(tsx))
    if len(code) < 500:
        raise ValueError("Generated Remotion code is too short")

    if not _has_generated_video_named_export(code):
        raise ValueError("Generated code must export GeneratedVideo")

    if not re.search(r"\buseCurrentFrame\b", code):
        raise ValueError("Generated Remotion code must use useCurrentFrame()")
    if not (re.search(r"\binterpolate\s*\(", code) or re.search(r"\bspring\s*\(", code)):
        raise ValueError("Generated Remotion code must animate with interpolate() or spring()")
    if not re.search(r"\bSequence\b", code):
        raise ValueError("Generated Remotion code must use Sequence for scene timing")
    if not re.search(r"\bstrokeDasharray\b", code) or not re.search(r"\bstrokeDashoffset\b", code):
        raise ValueError("Generated Remotion code must draw SVG strokes with strokeDasharray/strokeDashoffset")
    has_text_reveal = (
        re.search(r"\bglyphPaths\b", code)
        or re.search(r"\bspec\.text\.(?:slice|substring)\s*\(", code)
        or re.search(r"\bclipPath\b", code)
    )
    if not has_text_reveal:
        raise ValueError("Generated Remotion code must reveal text progressively")
    _validate_stroke_following_timeline(code)
    _validate_glyph_outline_text(code)
    _validate_handwritten_anime_style(code)
    if not re.search(r"\b(KaiTi|STKaiti|Kaiti|楷体)\b", code, flags=re.IGNORECASE):
        raise ValueError("Generated Remotion code must use a Chinese handwriting-style font family such as KaiTi/STKaiti")
    if not _has_watercolor_accent(code):
        raise ValueError("Generated Remotion code must include muted watercolor-style accent colors, not only black and white")
    if HAND_ASSET not in code:
        raise ValueError(f"Generated Remotion code must use staticFile('{HAND_ASSET}') for the visible hand holding a pen")
    if not re.search(r"\bstaticFile\s*\(", code):
        raise ValueError("Generated Remotion code must reference the hand asset with staticFile()")
    if not re.search(r"\bImg\b", code):
        raise ValueError("Generated Remotion code must render the visible hand with Remotion <Img>")
    if not re.search(r"\bHandPen\b", code):
        raise ValueError("Generated Remotion code must define and render a HandPen component")
    if not re.search(r"\b(tip|pen)(X|Y)\b", code):
        raise ValueError("Generated Remotion code must compute pen tip coordinates for the hand overlay")
    if not re.search(r"\bvisible\b", code):
        raise ValueError("HandPen must receive a visible flag and hide during non-drawing holds")
    if not re.search(r"\bHAND_WIDTH\s*=\s*(?:2[2-9]\d|[3-9]\d\d)\b", code):
        raise ValueError("Generated Remotion code must size the hand image with HAND_WIDTH >= 220")
    if not re.search(r"\bPEN_TIP_(?:X|Y)\b", code):
        raise ValueError("Generated Remotion code must use fixed PEN_TIP_X/PEN_TIP_Y offsets to align the marker tip")
    if re.search(r"<svg(?:(?!</svg>).)*<HandPen(?:(?!</svg>).)*</svg>", code, flags=re.IGNORECASE | re.DOTALL):
        raise ValueError("Generated Remotion code must render HandPen outside SVG as an HTML overlay sibling")
    if not re.search(r"HandPen[\s\S]*?<div[\s\S]*?<Img", code, flags=re.IGNORECASE):
        raise ValueError("Generated Remotion code must wrap the hand <Img> in an absolutely positioned HTML <div>")
    if re.search(r"<path(?=[^>]*strokeDash)(?=[^>]*fill=['\"](?!none['\"])[^'\"]+['\"])[^>]*>", code, flags=re.IGNORECASE):
        raise ValueError("Generated Remotion code must not fill animated stroke paths; use separate closed wash shapes behind strokes")

    lowered = code.lower()
    for token in FORBIDDEN_CODE_TOKENS:
        if token.lower() in lowered:
            raise ValueError(f"Generated code contains forbidden token: {token}")
    for pattern in FORBIDDEN_CODE_PATTERNS:
        if re.search(pattern, code, flags=re.IGNORECASE):
            raise ValueError(f"Generated code contains forbidden pattern: {pattern}")

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
    await check_llm_connection()

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


def _short_text(value: str | None, max_chars: int = 30) -> str:
    text = re.sub(r"\s+", " ", value or "").strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3].rstrip() + "..."


def _point(x: float, y: float) -> dict[str, float]:
    return {"x": round(float(x), 1), "y": round(float(y), 1)}


def _text_stroke_points(
    text: str,
    x: float,
    y: float,
    font_size: float,
    max_width: float,
) -> list[dict[str, float]]:
    char_count = max(1, min(len(text), 20))
    cjk_count = len(re.findall(r"[\u3400-\u9fff]", text))
    char_w = font_size * (0.92 if cjk_count >= max(1, char_count // 2) else 0.58)
    char_w = max(12.0, min(char_w, max_width / max(char_count, 1)))
    baseline = y + font_size * 0.82
    high = y + font_size * 0.18
    mid = y + font_size * 0.52
    low = y + font_size * 0.92
    points: list[dict[str, float]] = []
    for i in range(char_count):
        left = x + i * char_w
        wobble = (i % 3) * font_size * 0.04
        points.extend(
            [
                _point(left, baseline),
                _point(left + char_w * 0.18, high + wobble),
                _point(left + char_w * 0.42, low - wobble),
                _point(left + char_w * 0.66, mid + wobble),
                _point(left + char_w * 0.96, baseline - wobble),
            ]
        )
    return points


def _curve_points(
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    count: int = 20,
    wave: float = 34.0,
) -> list[dict[str, float]]:
    points: list[dict[str, float]] = []
    for i in range(count):
        t = i / max(count - 1, 1)
        x = x0 + (x1 - x0) * t
        y = y0 + (y1 - y0) * t - math.sin(math.pi * t) * wave + math.sin(math.pi * 3 * t) * wave * 0.18
        points.append(_point(x, y))
    return points


def _rect_points(x: float, y: float, width: float, height: float) -> list[dict[str, float]]:
    return [
        _point(x, y),
        _point(x + width * 0.34, y - 4),
        _point(x + width, y),
        _point(x + width + 5, y + height * 0.46),
        _point(x + width, y + height),
        _point(x + width * 0.42, y + height + 4),
        _point(x, y + height),
        _point(x - 4, y + height * 0.42),
        _point(x, y),
    ]


def _circle_points(cx: float, cy: float, rx: float, ry: float, count: int = 24) -> list[dict[str, float]]:
    return [
        _point(cx + math.cos((math.pi * 2 * i) / count) * rx, cy + math.sin((math.pi * 2 * i) / count) * ry)
        for i in range(count + 1)
    ]


def _line_points(x0: float, y0: float, x1: float, y1: float, count: int = 5) -> list[dict[str, float]]:
    return [_point(x0 + (x1 - x0) * i / max(count - 1, 1), y0 + (y1 - y0) * i / max(count - 1, 1)) for i in range(count)]


def _smile_points(cx: float, cy: float, width: float, height: float, count: int = 10) -> list[dict[str, float]]:
    points: list[dict[str, float]] = []
    for i in range(count):
        t = i / max(count - 1, 1)
        x = cx - width / 2 + width * t
        y = cy + math.sin(math.pi * t) * height
        points.append(_point(x, y))
    return points


def _polyline_length(points: list[dict[str, float]], close: bool = False) -> float:
    if len(points) < 2:
        return 1.0
    total = 0.0
    pairs = zip(points, points[1:])
    for start, end in pairs:
        total += math.hypot(end["x"] - start["x"], end["y"] - start["y"])
    if close and points[0] != points[-1]:
        total += math.hypot(points[-1]["x"] - points[0]["x"], points[-1]["y"] - points[0]["y"])
    return max(1.0, total + 12.0)


def _path_from_points(points: list[dict[str, float]], close: bool = False) -> str:
    if not points:
        return ""
    commands = [f"M {points[0]['x']} {points[0]['y']}"]
    commands.extend(f"L {p['x']} {p['y']}" for p in points[1:])
    if close:
        commands.append("Z")
    return " ".join(commands)


def _animation_lines(scene: Scene) -> list[str]:
    lines: list[str] = []
    for animation in scene.animations:
        raw_type = getattr(animation.type, "value", str(animation.type))
        if raw_type in {"write_formula", "formula_reveal"}:
            value = animation.latex or animation.content
            if value:
                lines.append(value)
        elif animation.items:
            if animation.content:
                lines.append(animation.content)
            lines.extend(animation.items[:3])
        elif animation.content:
            lines.append(animation.content)
    if not lines and scene.narration:
        lines = re.split(r"[，。,.]", scene.narration)[:3]
    return [_short_text(line, 34) for line in lines if _short_text(line, 34)][:4]


def _scene_corpus(scene: Scene) -> str:
    parts: list[str] = [scene.title, scene.narration, scene.image_description or ""]
    for animation in scene.animations:
        parts.append(getattr(animation.type, "value", str(animation.type)))
        parts.extend(
            [
                animation.content or "",
                animation.latex or "",
                animation.from_node or "",
                animation.to_node or "",
            ]
        )
        if animation.items:
            parts.extend(animation.items)
    return " ".join(part for part in parts if part).lower()


def _animation_type_values(scene: Scene) -> set[str]:
    return {getattr(animation.type, "value", str(animation.type)) for animation in scene.animations}


def _contains_any(corpus: str, terms: list[str]) -> bool:
    return any(term.lower() in corpus for term in terms)


def _scene_steps(scene: Scene) -> list[str]:
    steps: list[str] = []
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
    if _contains_any(corpus, ["lora", "low rank", "rank", "matrix", "矩阵", "低秩", "分解", "微调"]):
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
    if _contains_any(corpus, ["feedback", "loop", "iterate", "iteration", "反馈", "循环", "迭代", "更新"]):
        return "feedback_loop"
    if has_formula:
        return "formula_derivation"
    if "step_reveal" in types or _contains_any(corpus, ["process", "pipeline", "workflow", "过程", "步骤", "流程", "原理"]):
        return "process_flow"
    if _contains_any(corpus, ["compare", "versus", " vs ", "change", "transform", "before", "after", "对比", "比较", "变化", "变换", "转换"]):
        return "comparison_transform"

    return ["process_flow", "comparison_transform", "feedback_loop"][scene_index % 3]


def _arc_points(
    cx: float,
    cy: float,
    rx: float,
    ry: float,
    start_angle: float,
    end_angle: float,
    count: int = 18,
) -> list[dict[str, float]]:
    return [
        _point(
            cx + math.cos(start_angle + (end_angle - start_angle) * i / max(count - 1, 1)) * rx,
            cy + math.sin(start_angle + (end_angle - start_angle) * i / max(count - 1, 1)) * ry,
        )
        for i in range(count)
    ]


def _diamond_points(cx: float, cy: float, width: float, height: float) -> list[dict[str, float]]:
    return [
        _point(cx, cy - height / 2),
        _point(cx + width / 2 + 4, cy),
        _point(cx, cy + height / 2 + 3),
        _point(cx - width / 2 - 3, cy),
        _point(cx, cy - height / 2),
    ]


def _build_fallback_scene_spec(scene: Scene, scene_index: int, fps: int, width: int, height: int) -> dict:
    duration = max(fps * 8, round(scene.duration_estimate * fps))
    left = width * 0.07
    top = height * 0.08
    diagram_left = width * 0.40
    diagram_top = height * 0.22
    accent_colors = ["#F7D77E", "#A8D8F0", "#F4A7A1", "#BFE3C0", "#D7C5F7"]
    accent = accent_colors[scene_index % len(accent_colors)]
    ink = "#1D1D1F"
    blue = "#2F6FB2"
    red = "#D85C4A"
    green = "#3F8F68"
    violet = "#6E58B5"
    draw_ops: list[dict] = []
    texts: list[dict] = []
    strokes: list[dict] = []
    diagram_kind = _diagram_kind_for_scene(scene, scene_index)
    core_lines = _animation_lines(scene)
    steps = _scene_steps(scene)
    raw_trace_strokes = getattr(scene, "trace_strokes", None) or getattr(scene, "traceStrokes", None) or []
    trace_strokes = raw_trace_strokes if isinstance(raw_trace_strokes, list) else []

    def fit_timing(start: int, frames: int) -> tuple[int, int]:
        safe_start = min(max(0, start), max(0, duration - 8))
        safe_end = min(duration - 4, safe_start + max(4, frames))
        if safe_end <= safe_start:
            safe_end = min(duration - 1, safe_start + 1)
        return safe_start, safe_end

    def add_text(
        text: str,
        x: float,
        y: float,
        font_size: int,
        color: str,
        start: int,
        frames: int,
        max_width: float | None = None,
    ) -> None:
        op_id = f"s{scene_index}_text_{len(texts)}"
        safe_text = _short_text(text, 38)
        text_max_width = max_width if max_width is not None else width - x - 70
        safe_start, end = fit_timing(start, frames)
        draw_ops.append(
            {
                "id": op_id,
                "kind": "text",
                "startFrame": safe_start,
                "endFrame": end,
                "points": _text_stroke_points(safe_text, x, y, font_size, text_max_width),
            }
        )
        texts.append(
            {
                "opId": op_id,
                "text": safe_text,
                "x": round(x, 1),
                "y": round(y, 1),
                "fontSize": font_size,
                "color": color,
                "maxWidth": round(text_max_width, 1),
            }
        )

    def add_stroke(
        role: str,
        points: list[dict[str, float]],
        color: str,
        stroke_width: int,
        start: int,
        frames: int,
        close: bool = False,
    ) -> None:
        op_id = f"s{scene_index}_stroke_{len(strokes)}"
        safe_start, end = fit_timing(start, frames)
        draw_ops.append(
            {
                "id": op_id,
                "kind": "path",
                "startFrame": safe_start,
                "endFrame": end,
                "points": points,
            }
        )
        strokes.append(
            {
                "opId": op_id,
                "role": role,
                "d": _path_from_points(points, close=close),
                "color": color,
                "strokeWidth": stroke_width,
                "dashLength": round(_polyline_length(points, close=close), 1),
            }
        )

    def add_arrow(
        points: list[dict[str, float]],
        color: str,
        stroke_width: int,
        start: int,
        frames: int,
        role: str = "arrow",
    ) -> None:
        add_stroke(role, points, color, stroke_width, start, frames)
        if len(points) < 2:
            return
        end = points[-1]
        prev = points[-2]
        angle = math.atan2(end["y"] - prev["y"], end["x"] - prev["x"])
        head_len = max(16.0, min(width, height) * 0.028)
        head_start = start + max(4, frames - 10)
        for sign in (-1, 1):
            theta = angle + math.pi + sign * 0.48
            side = _point(end["x"] + math.cos(theta) * head_len, end["y"] + math.sin(theta) * head_len)
            add_stroke("arrowhead", [side, _point(end["x"], end["y"])], color, stroke_width, head_start, 7)

    def add_node_box(
        label: str,
        x: float,
        y: float,
        w: float,
        h: float,
        start: int,
        color: str = ink,
        role: str = "node",
        font_size: int | None = None,
    ) -> int:
        add_stroke(role, _rect_points(x, y, w, h), color, 4, start, 18, close=True)
        add_text(label, x + w * 0.14, y + h * 0.25, font_size or body_size, color, start + 12, 22, w * 0.78)
        return start + 36

    def add_node_circle(
        label: str,
        cx: float,
        cy: float,
        rx: float,
        ry: float,
        start: int,
        color: str = ink,
        role: str = "node",
        font_size: int | None = None,
    ) -> int:
        add_stroke(role, _circle_points(cx, cy, rx, ry, count=24), color, 4, start, 18)
        add_text(label, cx - rx * 0.55, cy - ry * 0.28, font_size or body_size, color, start + 12, 22, rx * 1.1)
        return start + 36

    def fallback_label(index: int, value: str) -> str:
        pool = steps or core_lines
        return _short_text(pool[index], 16) if index < len(pool) else value

    def add_process_doodles(start: int, x: float, y: float) -> int:
        checks = [
            [_point(x, y), _point(x + 10, y + 12), _point(x + 30, y - 14)],
            [_point(x + 8, y + 44), _point(x + 20, y + 56), _point(x + 42, y + 28)],
            [_point(x + 20, y + 84), _point(x + 30, y + 98), _point(x + 54, y + 68)],
        ]
        cursor = start
        for points in checks:
            add_stroke("doodle", points, green, 4, cursor, 8)
            cursor += 9
        add_stroke("doodle", _line_points(x + 70, y - 12, x + 108, y - 28, count=4), blue, 3, cursor, 7)
        cursor += 8
        add_stroke("doodle", _line_points(x + 70, y + 4, x + 112, y + 4, count=4), blue, 3, cursor, 7)
        return cursor + 8

    def build_reference_trace(start: int) -> int:
        trace_x = diagram_left + width * 0.025
        trace_y = diagram_top + height * 0.055
        trace_w = width * 0.43
        trace_h = height * 0.38
        cursor = start
        drawn = 0
        for raw_path in trace_strokes[:80]:
            if not isinstance(raw_path, list) or len(raw_path) < 2:
                continue
            points: list[dict[str, float]] = []
            for raw_point in raw_path:
                if not isinstance(raw_point, dict):
                    continue
                px = raw_point.get("x")
                py = raw_point.get("y")
                if not isinstance(px, (int, float)) or not isinstance(py, (int, float)):
                    continue
                points.append(_point(trace_x + max(0.0, min(1.0, float(px))) * trace_w, trace_y + max(0.0, min(1.0, float(py))) * trace_h))
            if len(points) < 2:
                continue
            frames = max(7, min(22, round(_polyline_length(points) / max(18.0, width * 0.018))))
            add_stroke("reference_trace", points, ink, 4, cursor, frames)
            cursor += frames + 3
            drawn += 1
            if cursor > duration * 0.66:
                break
        if drawn == 0:
            return builders.get(diagram_kind, build_process_flow)(start)

        label = fallback_label(0, "Reference sketch")
        arrow_start = min(cursor, duration - 64)
        add_arrow(
            _curve_points(left + width * 0.26, top + height * 0.34, trace_x + trace_w * 0.42, trace_y + trace_h * 0.46, count=16, wave=height * 0.035),
            blue,
            4,
            arrow_start,
            18,
        )
        add_text(label, left + 34, top + height * 0.30, body_size, blue, arrow_start + 12, 28, width * 0.30)
        cursor = arrow_start + 46
        for tick in range(5):
            add_stroke(
                "doodle",
                _line_points(
                    trace_x + trace_w + 24 + tick * 16,
                    trace_y + 22 + (tick % 2) * 20,
                    trace_x + trace_w + 34 + tick * 16,
                    trace_y + 6 + (tick % 2) * 20,
                    count=3,
                ),
                red,
                3,
                cursor,
                5,
            )
            cursor += 6
        return cursor

    def build_process_flow(start: int) -> int:
        y = diagram_top + height * 0.18
        box_w = width * 0.16
        box_h = height * 0.13
        gap = width * 0.055
        x1 = diagram_left
        x2 = x1 + box_w + gap
        x3 = x2 + box_w + gap
        cursor = start
        cursor = add_node_box(fallback_label(0, "Input"), x1, y, box_w, box_h, cursor, blue)
        add_arrow(_line_points(x1 + box_w + 6, y + box_h * 0.5, x2 - 16, y + box_h * 0.5, count=8), ink, 4, cursor, 16)
        cursor += 25
        cursor = add_node_box(fallback_label(1, "Process"), x2, y - height * 0.03, box_w, box_h, cursor, ink)
        add_arrow(_line_points(x2 + box_w + 6, y + box_h * 0.5, x3 - 16, y + box_h * 0.5, count=8), ink, 4, cursor, 16)
        cursor += 25
        cursor = add_node_box(fallback_label(2, "Output"), x3, y, box_w, box_h, cursor, green)
        if len(steps) > 3:
            add_stroke("note", _line_points(x2 + box_w * 0.5, y + box_h + 10, x2 + box_w * 0.5, y + box_h + height * 0.08), violet, 3, cursor, 9)
            add_text(fallback_label(3, "Key change"), x2 - box_w * 0.14, y + box_h + height * 0.09, body_size, violet, cursor + 8, 22, box_w * 1.35)
            cursor += 32
        return add_process_doodles(cursor, diagram_left + width * 0.34, y + box_h + height * 0.08)

    def build_comparison_transform(start: int) -> int:
        y = diagram_top + height * 0.16
        left_x = diagram_left + width * 0.02
        right_x = diagram_left + width * 0.32
        w = width * 0.18
        h = height * 0.18
        cursor = start
        cursor = add_node_box(fallback_label(0, "Before"), left_x, y, w, h, cursor, red)
        add_arrow(_curve_points(left_x + w + 8, y + h * 0.45, right_x - 20, y + h * 0.45, count=18, wave=height * 0.035), ink, 4, cursor, 22)
        add_text(fallback_label(2, "Change"), left_x + w + width * 0.035, y - height * 0.055, body_size, blue, cursor + 10, 24, width * 0.18)
        cursor += 34
        cursor = add_node_box(fallback_label(1, "After"), right_x, y, w, h, cursor, green)
        brace_x = right_x + w + width * 0.04
        add_stroke("change", _line_points(brace_x, y + 10, brace_x + 18, y + h * 0.5, count=5), violet, 4, cursor, 8)
        add_stroke("change", _line_points(brace_x + 18, y + h * 0.5, brace_x, y + h - 10, count=5), violet, 4, cursor + 7, 8)
        add_text(fallback_label(3, "Result"), brace_x + 28, y + h * 0.34, body_size, violet, cursor + 14, 22, width * 0.15)
        cursor += 42
        marks = [
            _line_points(left_x + 22, y - 26, left_x + 56, y - 10, count=4),
            _line_points(left_x + 60, y - 28, left_x + 25, y - 8, count=4),
            _line_points(right_x + w * 0.76, y - 24, right_x + w * 0.76, y - 4, count=3),
            _line_points(right_x + w * 0.68, y - 14, right_x + w * 0.84, y - 14, count=3),
            _curve_points(right_x + 12, y + h + 24, right_x + w - 8, y + h + 18, count=10, wave=height * 0.012),
        ]
        for points in marks:
            add_stroke("doodle", points, blue, 3, cursor, 7)
            cursor += 8
        return cursor

    def build_formula_derivation(start: int) -> int:
        formulas = []
        for animation in scene.animations:
            raw_type = getattr(animation.type, "value", str(animation.type))
            if raw_type in {"write_formula", "formula_reveal"} and (animation.latex or animation.content):
                formulas.append(animation.latex or animation.content)
        formulas.extend(line for line in core_lines if line not in formulas)
        formulas = [_short_text(line, 30) for line in formulas if line][:3]
        while len(formulas) < 3:
            formulas.append(["Known", "Transform", "Conclusion"][len(formulas)])

        x = diagram_left + width * 0.02
        y = diagram_top + height * 0.08
        w = width * 0.38
        row_h = height * 0.115
        cursor = start
        for index, formula in enumerate(formulas[:3]):
            row_y = y + index * (row_h + height * 0.035)
            add_stroke("formula", _rect_points(x, row_y, w, row_h), [blue, violet, green][index % 3], 4, cursor, 16, close=True)
            add_text(formula, x + w * 0.06, row_y + row_h * 0.25, body_size, ink, cursor + 10, 28, w * 0.86)
            cursor += 38
            if index < 2:
                add_arrow(_line_points(x + w * 0.5, row_y + row_h + 6, x + w * 0.5, row_y + row_h + height * 0.035, count=5), ink, 4, cursor, 9)
                cursor += 16
        add_stroke("formula", _line_points(x - 26, y + 8, x - 42, y + row_h * 1.5, count=6), red, 4, cursor, 8)
        cursor += 8
        add_stroke("formula", _line_points(x - 42, y + row_h * 1.5, x - 26, y + row_h * 3.0, count=6), red, 4, cursor, 8)
        cursor += 10
        for tick in range(5):
            add_stroke(
                "doodle",
                _line_points(x + w + 38 + tick * 12, y + 20 + (tick % 2) * 18, x + w + 44 + tick * 12, y + 6 + (tick % 2) * 18, count=3),
                red,
                3,
                cursor,
                5,
            )
            cursor += 6
        return cursor

    def build_optimization_curve(start: int) -> int:
        axis_x = diagram_left + width * 0.02
        axis_y = diagram_top + height * 0.44
        axis_w = width * 0.40
        axis_h = height * 0.30
        cursor = start
        add_arrow(_line_points(axis_x, axis_y, axis_x + axis_w, axis_y, count=8), ink, 4, cursor, 14, role="axis")
        cursor += 18
        add_arrow(_line_points(axis_x, axis_y, axis_x, axis_y - axis_h, count=8), ink, 4, cursor, 14, role="axis")
        cursor += 18
        add_text("theta", axis_x + axis_w * 0.88, axis_y + height * 0.025, body_size, ink, cursor, 16, width * 0.11)
        add_text("Loss", axis_x - width * 0.035, axis_y - axis_h - height * 0.055, body_size, ink, cursor + 8, 16, width * 0.12)
        cursor += 24

        curve = []
        for i in range(28):
            t = i / 27
            x = axis_x + axis_w * (0.08 + 0.84 * t)
            y = axis_y - axis_h * (0.88 * (1 - t) ** 2 + 0.12) + math.sin(t * math.pi * 3) * height * 0.01
            curve.append(_point(x, y))
        add_stroke("loss_curve", curve, blue, 5, cursor, 34)
        cursor += 38

        sample_indices = [3, 8, 14, 21]
        for prev_i, next_i in zip(sample_indices, sample_indices[1:]):
            p = curve[prev_i]
            q = curve[next_i]
            add_stroke("node", _circle_points(p["x"], p["y"], width * 0.012, height * 0.02, count=12), red, 4, cursor, 8)
            add_arrow(_line_points(p["x"] + 10, p["y"] + 8, q["x"] - 10, q["y"] + 5, count=6), red, 4, cursor + 7, 12)
            cursor += 23
        optimum = curve[-3]
        add_stroke("node", _circle_points(optimum["x"], optimum["y"], width * 0.013, height * 0.021, count=12), green, 4, cursor, 8)
        add_text(fallback_label(0, "Update"), axis_x + axis_w * 0.46, axis_y - axis_h * 0.82, body_size, violet, cursor + 8, 24, width * 0.22)
        cursor += 32
        flag_x = optimum["x"] + width * 0.035
        flag_y = optimum["y"] - height * 0.055
        add_stroke("doodle", _line_points(flag_x, flag_y, flag_x, flag_y + height * 0.09, count=5), green, 3, cursor, 8)
        cursor += 8
        add_stroke("doodle", [_point(flag_x, flag_y), _point(flag_x + width * 0.04, flag_y + height * 0.015), _point(flag_x, flag_y + height * 0.03)], green, 3, cursor, 8)
        cursor += 9
        for tick in range(3):
            add_stroke("doodle", _line_points(flag_x - 18 + tick * 22, flag_y + height * 0.11, flag_x - 8 + tick * 22, flag_y + height * 0.13, count=3), blue, 3, cursor, 5)
            cursor += 6
        return cursor

    def build_attention_network(start: int) -> int:
        cursor = start
        x0 = diagram_left + width * 0.02
        y0 = diagram_top + height * 0.08
        token_gap = height * 0.105
        token_positions = [(x0, y0 + i * token_gap) for i in range(3)]
        qkv_x = x0 + width * 0.15
        mix_x = x0 + width * 0.34
        out_x = x0 + width * 0.49
        labels = ["Q", "K", "V"]
        for index, (x, y) in enumerate(token_positions):
            cursor = add_node_circle(f"T{index + 1}", x, y, width * 0.035, height * 0.045, cursor, blue, font_size=max(18, body_size - 5))
            qy = y
            cursor = add_node_box(labels[index], qkv_x, qy - height * 0.04, width * 0.08, height * 0.075, cursor, violet if index == 0 else ink, font_size=max(18, body_size - 4))
            add_arrow(_line_points(x + width * 0.04, y, qkv_x - 12, qy, count=5), ink, 3, cursor, 10)
            cursor += 14
        soft_y = y0 + token_gap
        cursor = add_node_circle("Softmax", mix_x, soft_y, width * 0.055, height * 0.06, cursor, red, font_size=max(16, body_size - 8))
        for qy in [pos[1] for pos in token_positions]:
            add_arrow(_line_points(qkv_x + width * 0.085, qy, mix_x - width * 0.065, soft_y, count=6), ink, 3, cursor, 9)
            cursor += 11
        cursor = add_node_circle(fallback_label(0, "Output"), out_x, soft_y, width * 0.048, height * 0.055, cursor, green, font_size=max(16, body_size - 8))
        add_arrow(_line_points(mix_x + width * 0.06, soft_y, out_x - width * 0.055, soft_y, count=5), green, 4, cursor, 12)
        cursor += 18

        eye_cx = out_x + width * 0.09
        eye_cy = soft_y - height * 0.12
        add_stroke("doodle", _circle_points(eye_cx, eye_cy, width * 0.032, height * 0.022, count=18), blue, 3, cursor, 8)
        cursor += 8
        add_stroke("doodle", _circle_points(eye_cx, eye_cy, width * 0.008, height * 0.012, count=10), ink, 3, cursor, 6)
        cursor += 7
        for offset in [-1, 0, 1]:
            add_stroke("doodle", _line_points(eye_cx + offset * width * 0.028, eye_cy - height * 0.035, eye_cx + offset * width * 0.036, eye_cy - height * 0.058, count=3), blue, 3, cursor, 5)
            cursor += 6
        return cursor

    def build_matrix_transform(start: int) -> int:
        cursor = start
        x = diagram_left + width * 0.02
        y = diagram_top + height * 0.12
        w = width * 0.12
        h = height * 0.20
        cursor = add_node_box("W", x, y, w, h, cursor, blue, role="matrix", font_size=body_size + 6)
        plus_x = x + w + width * 0.055
        add_text("+", plus_x, y + h * 0.34, body_size + 18, ink, cursor, 15, width * 0.05)
        cursor += 18
        a_x = plus_x + width * 0.06
        cursor = add_node_box("A", a_x, y + h * 0.34, w * 0.74, h * 0.42, cursor, violet, role="matrix", font_size=body_size)
        b_x = a_x + w * 0.86
        cursor = add_node_box("B", b_x, y, w * 0.48, h, cursor, red, role="matrix", font_size=body_size)
        result_x = b_x + width * 0.13
        add_arrow(_line_points(b_x + w * 0.55, y + h * 0.5, result_x - 18, y + h * 0.5, count=6), ink, 4, cursor, 14)
        cursor += 20
        cursor = add_node_box("W'", result_x, y, w, h, cursor, green, role="matrix", font_size=body_size + 4)
        add_text(fallback_label(0, "Low rank update"), a_x - width * 0.03, y + h + height * 0.055, body_size, ink, cursor, 24, width * 0.28)
        cursor += 30
        for offset in [0.28, 0.5, 0.72]:
            add_stroke("matrix_grid", _line_points(x + w * offset, y + 8, x + w * offset, y + h - 8, count=4), blue, 2, cursor, 5)
            cursor += 5
        for tick in range(5):
            add_stroke("doodle", _line_points(a_x + tick * 18, y - 28 + (tick % 2) * 8, a_x + tick * 18 + 8, y - 40 + (tick % 2) * 8, count=3), violet, 3, cursor, 5)
            cursor += 6
        return cursor

    def build_feedback_loop(start: int) -> int:
        cursor = start
        cx = diagram_left + width * 0.28
        cy = diagram_top + height * 0.24
        rx = width * 0.17
        ry = height * 0.17
        nodes = [
            (fallback_label(0, "Observe"), cx, cy - ry),
            (fallback_label(1, "Update"), cx + rx, cy + ry * 0.38),
            (fallback_label(2, "Improve"), cx - rx, cy + ry * 0.38),
        ]
        for index, (label, x, y) in enumerate(nodes):
            cursor = add_node_circle(label, x, y, width * 0.065, height * 0.055, cursor, blue if index % 2 == 0 else green, font_size=max(16, body_size - 8))
        angles = [-math.pi / 2, 0.3, math.pi - 0.3]
        for start_angle, end_angle in [(angles[0] + 0.38, angles[1] - 0.38), (angles[1] + 0.45, angles[2] - 0.45), (angles[2] + 0.45, angles[0] + math.pi * 2 - 0.45)]:
            add_arrow(_arc_points(cx, cy, rx, ry, start_angle, end_angle, count=14), ink, 4, cursor, 16, role="loop")
            cursor += 23
        add_text(fallback_label(3, "Repeat"), cx - width * 0.06, cy - height * 0.025, body_size, violet, cursor, 22, width * 0.17)
        cursor += 26
        for tick in range(5):
            angle = -0.2 + tick * 0.22
            x0 = cx + math.cos(angle) * (rx + width * 0.08)
            y0 = cy + math.sin(angle) * (ry + height * 0.05)
            add_stroke("doodle", _line_points(x0, y0, x0 + math.cos(angle) * 24, y0 + math.sin(angle) * 18, count=3), red, 3, cursor, 5)
            cursor += 6
        return cursor

    cursor = 8
    title_size = 62 if width >= 1600 else 46
    body_size = 39 if width >= 1600 else 29
    add_text(scene.title or f"Scene {scene_index + 1}", left, top, title_size, blue, cursor, 52)
    cursor += 60

    builders = {
        "process_flow": build_process_flow,
        "comparison_transform": build_comparison_transform,
        "formula_derivation": build_formula_derivation,
        "optimization_curve": build_optimization_curve,
        "attention_network": build_attention_network,
        "matrix_transform": build_matrix_transform,
        "feedback_loop": build_feedback_loop,
    }
    if trace_strokes:
        cursor = build_reference_trace(cursor)
    else:
        cursor = builders.get(diagram_kind, build_process_flow)(cursor)

    note_y = top + height * 0.28
    for note_index, line in enumerate(core_lines[:3]):
        if cursor + 42 > duration - 8:
            break
        add_text(line, left + 34, note_y + note_index * (body_size + 16), body_size, ink, cursor, 34, width * 0.34)
        cursor += 47

    if len(texts) < 2 and cursor + 42 <= duration - 8:
        add_text(_short_text(scene.narration, 32), left + 34, top + height * 0.38, body_size, ink, cursor, 42)

    wash_points = _rect_points(diagram_left - 28, diagram_top + height * 0.02, width * 0.48, height * 0.48)
    return {
        "title": scene.title,
        "diagramKind": diagram_kind,
        "duration": duration,
        "audioUrl": getattr(scene, "audioUrl", None) or getattr(scene, "audio_url", None),
        "accent": accent,
        "washD": _path_from_points(wash_points, close=True),
        "drawOps": draw_ops,
        "texts": texts,
        "glyphPaths": [],
        "strokes": strokes,
    }


def _build_fallback_remotion_tsx(
    storyboard: Storyboard,
    fps: int,
    width: int,
    height: int,
) -> tuple[str, int]:
    scene_specs = [
        _build_fallback_scene_spec(scene, index, fps, width, height)
        for index, scene in enumerate(storyboard.scenes[:6])
    ]
    if not scene_specs:
        raise ValueError("Cannot build fallback Remotion TSX without storyboard scenes")
    duration = sum(scene["duration"] for scene in scene_specs)
    scenes_json = json.dumps(scene_specs, ensure_ascii=False, separators=(",", ":"))
    template = r'''
import React from "react";
import { AbsoluteFill, Audio, Easing, Img, interpolate, Sequence, staticFile, useCurrentFrame } from "remotion";

const HAND_WIDTH = 260;
const HAND_HEIGHT = 289;
const PEN_TIP_X = 15;
const PEN_TIP_Y = 78;
const VIDEO_WIDTH = __VIDEO_WIDTH__;
const VIDEO_HEIGHT = __VIDEO_HEIGHT__;
const FONT_FAMILY = "'STXingkai', '华文行楷', KaiTi, STKaiti, 'Kaiti SC', cursive";

type Point = { x: number; y: number };
type DrawOp = { id: string; kind: "text" | "path"; startFrame: number; endFrame: number; points: Point[]; pace?: "glyph" | "ease" };
type TextSpec = { opId: string; text: string; x: number; y: number; fontSize: number; color: string; maxWidth: number };
type GlyphPathSpec = { opId: string; sourceOpId: string; d: string; color: string; strokeWidth: number; dashLength: number; fontOutline: boolean };
type StrokeSpec = { opId: string; role: string; d: string; color: string; strokeWidth: number; dashLength: number };
type SceneSpec = {
  title: string;
  diagramKind?: string;
  duration: number;
  audioUrl?: string | null;
  accent: string;
  washD: string;
  drawOps: DrawOp[];
  texts: TextSpec[];
  glyphPaths?: GlyphPathSpec[];
  strokes: StrokeSpec[];
};

const scenes = __SCENES_JSON__ as SceneSpec[];

const clamp01 = (value: number) => Math.max(0, Math.min(1, value));

const progressForOp = (frame: number, op: DrawOp) => {
  const baseConfig = {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  } as const;
  if (op.pace === "glyph") {
    return interpolate(frame, [op.startFrame, op.endFrame], [0, 1], baseConfig);
  }
  return interpolate(frame, [op.startFrame, op.endFrame], [0, 1], {
    ...baseConfig,
    easing: Easing.bezier(0.2, 0.8, 0.2, 1),
  });
};

const pointOnPolyline = (points: Point[], progress: number): Point => {
  if (points.length === 0) return { x: -400, y: -400 };
  if (points.length === 1) return points[0];
  const lengths = points.slice(1).map((point, index) => {
    const prev = points[index];
    return Math.sqrt((point.x - prev.x) ** 2 + (point.y - prev.y) ** 2);
  });
  const total = lengths.reduce((sum, value) => sum + value, 0) || 1;
  let walked = clamp01(progress) * total;
  for (let i = 0; i < lengths.length; i += 1) {
    if (walked <= lengths[i]) {
      const prev = points[i];
      const next = points[i + 1];
      const t = lengths[i] === 0 ? 0 : walked / lengths[i];
      return {
        x: interpolate(t, [0, 1], [prev.x, next.x]),
        y: interpolate(t, [0, 1], [prev.y, next.y]),
      };
    }
    walked -= lengths[i];
  }
  return points[points.length - 1];
};

const HandPen = ({ tipX, tipY, visible }: { tipX: number; tipY: number; visible: boolean }) => (
  <div
    style={{
      position: "absolute",
      left: tipX - PEN_TIP_X,
      top: tipY - PEN_TIP_Y,
      width: HAND_WIDTH,
      height: HAND_HEIGHT,
      opacity: visible ? 1 : 0,
      pointerEvents: "none",
      zIndex: 20,
    }}
  >
    <Img src={staticFile("hand-real-pen.png")} style={{ width: HAND_WIDTH, height: HAND_HEIGHT }} />
  </div>
);

const DrawGlyphPath = ({ spec, op }: { spec: GlyphPathSpec; op: DrawOp }) => {
  const frame = useCurrentFrame();
  const progress = progressForOp(frame, op);
  const length = spec.dashLength;
  return (
    <path
      d={spec.d}
      fill="none"
      stroke={spec.color}
      strokeWidth={spec.strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeDasharray={length}
      strokeDashoffset={length * (1 - progress)}
    />
  );
};

const GlyphText = ({ scene }: { scene: SceneSpec }) => (
  <g data-font-family={FONT_FAMILY}>
    {(scene.glyphPaths ?? []).map((glyphPath) => {
      const op = scene.drawOps.find((drawOp) => drawOp.id === glyphPath.opId);
      return op ? <DrawGlyphPath key={glyphPath.opId} spec={glyphPath} op={op} /> : null;
    })}
  </g>
);

const DrawStroke = ({ spec, op }: { spec: StrokeSpec; op: DrawOp }) => {
  const frame = useCurrentFrame();
  const progress = progressForOp(frame, op);
  const length = spec.dashLength;
  return (
    <path
      d={spec.d}
      fill="none"
      stroke={spec.color}
      strokeWidth={spec.strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeDasharray={length}
      strokeDashoffset={length * (1 - progress)}
    />
  );
};

const AnimeDoodle = ({ scene }: { scene: SceneSpec }) => {
  return (
    <>
      {scene.strokes
        .filter((stroke) => stroke.role === "doodle")
        .map((stroke) => {
          const op = scene.drawOps.find((drawOp) => drawOp.id === stroke.opId);
          return op ? <DrawStroke key={stroke.opId} spec={stroke} op={op} /> : null;
        })}
    </>
  );
};

const CartoonDiagram = ({ scene }: { scene: SceneSpec }) => (
  <>
    {scene.strokes
      .filter((stroke) => stroke.role !== "doodle")
      .map((stroke) => {
        const op = scene.drawOps.find((drawOp) => drawOp.id === stroke.opId);
        return op ? <DrawStroke key={stroke.opId} spec={stroke} op={op} /> : null;
      })}
  </>
);

const WhiteboardScene = ({ scene }: { scene: SceneSpec }) => {
  const frame = useCurrentFrame();
  const drawOps = scene.drawOps;
  const getActiveDrawOp = (frame: number) =>
    drawOps.find((op) => frame >= op.startFrame && frame <= op.endFrame);
  const getPenPosition = (frame: number) => {
    const active = getActiveDrawOp(frame);
    if (!active) return { x: -400, y: -400, visible: false };
    const progress = progressForOp(frame, active);
    const point = pointOnPolyline(active.points, progress);
    return { x: point.x, y: point.y, visible: true };
  };
  const pen = getPenPosition(frame);

  return (
    <AbsoluteFill style={{ backgroundColor: "#FBFAF5", overflow: "hidden" }}>
      {scene.audioUrl ? <Audio src={scene.audioUrl} /> : null}
      <svg style={{ position: "absolute", inset: 0, width: "100%", height: "100%" }} viewBox={`0 0 ${VIDEO_WIDTH} ${VIDEO_HEIGHT}`}>
        <path d={scene.washD} fill={scene.accent} opacity={0.24} />
        <AnimeDoodle scene={scene} />
        <CartoonDiagram scene={scene} />
        <GlyphText scene={scene} />
      </svg>
      <HandPen tipX={pen.x} tipY={pen.y} visible={pen.visible} />
    </AbsoluteFill>
  );
};

export function GeneratedVideo() {
  let from = 0;
  return (
    <>
      {scenes.map((scene, index) => {
        const start = from;
        from += scene.duration;
        return (
          <Sequence key={`${scene.title}-${index}`} from={start} durationInFrames={scene.duration}>
            <WhiteboardScene scene={scene} />
          </Sequence>
        );
      })}
    </>
  );
}
'''
    return (
        template.replace("__SCENES_JSON__", scenes_json)
        .replace("__VIDEO_WIDTH__", str(width))
        .replace("__VIDEO_HEIGHT__", str(height))
        .strip(),
        duration,
    )


REMOTION_CODE_SYSTEM_PROMPT = """You are an expert Remotion engineer and motion designer.

Generate ONE self-contained TSX module for a complete educational whiteboard video.

Target visual reference:
- A sparse white canvas where a real visible hand holds a marker and writes/draws every visible element live.
- The hand must be on screen during drawing, with the pen tip touching the active text stroke, line, arrow, box, equation, or diagram.
- Use black marker outlines with limited blue marker text. Use very light fill washes only as separate closed shapes behind strokes, never as fill on an open animated path.
- Text should feel handwritten: irregular but readable, large, dark/blue marker strokes, revealed character-by-character or word-by-word while the hand follows the reveal.
- For Chinese text, fontFamily must start with a handwriting-style Chinese font stack like "KaiTi, STKaiti, Kaiti SC, cursive". Do not rely on default bold sans-serif Chinese.
- Graphics should feel hand-sketched: speech bubbles, arrows, boxes, curves, icons, charts, characters, objects, and concept diagrams are revealed by strokes being drawn.
- Preserve lots of empty white space. Avoid slide-deck cards, polished UI panels, gradients, stock images, and decorative template layouts.
- Prefer one meaningful illustrated explanation per scene over dense bullet lists.

Hard requirements:
- Export exactly one named component, either `export const GeneratedVideo = ...` or `export function GeneratedVideo() ...`.
- Do not use default exports.
- Use only imports from "react" and "remotion".
- Do not import local files, component libraries, templates, CSS, npm packages, images, fonts, or helper modules. The only asset exception is `staticFile("hand-real-pen.png")` rendered via Remotion <Img>.
- Do not use CSS animations/transitions. All motion must use Remotion frame APIs: useCurrentFrame(), interpolate(), Easing, spring(), Sequence, AbsoluteFill.
- The TSX must explicitly use useCurrentFrame(), Sequence, and at least one of interpolate() or spring().
- Every scene must draw text and shapes over time. Define inline helper components such as HandText, DrawPath, SketchBubble, SketchArrow, or DiagramStroke inside the same TSX module.
- The central animation model must be a `drawOps` array. Each op must have `kind`, `startFrame`, `endFrame`, and a `points: {x:number; y:number}[]` polyline that represents the actual stroke path the marker tip follows.
- Define `pointOnPolyline(points, progress)`, `getActiveDrawOp(frame)`, and `getPenPosition(frame)`. The rendered `<HandPen>` must use `const pen = getPenPosition(frame)` and pass `tipX={pen.x}` and `tipY={pen.y}`. Hand visibility must come from whether an active draw op exists.
- The pen must move up, down, left, and right inside words and drawings. Do not make the hand travel along a single straight baseline for text. Text ops must include zig-zag or stroke-like points for each word/phrase so the marker visibly writes within glyph shapes.
- Never define `const tipX = interpolate(frame, [...])` or `const tipY = interpolate(frame, [...])` at scene level. Pen coordinates must be sampled from active `drawOps.points`.
- Every animated SVG path/arrow/box/diagram stroke must have a matching drawOp with similar points. The hand tip should be near the visible end of the stroke as strokeDashoffset reveals it.
- Handwritten text must use a real Chinese handwriting stack like `"STXingkai, 华文行楷, KaiTi, STKaiti, Kaiti SC, cursive"`. Do not use bold sans-serif text.
- The visual language must be anime/cartoon whiteboard: add at least one simple cartoon/doodle character, face, mascot, or expressive icon in each video, drawn with SVG strokes and synced drawOps. Use helper names like AnimeDoodle, CartoonDiagram, CartoonMascot, or DoodleCharacter.
- Import Img and staticFile from "remotion" and render the visible hand using <Img src={staticFile("hand-real-pen.png")} />.
- Define a HandPen component in the same TSX module. It must receive `tipX`, `tipY` coordinates and position the hand image so the actual marker tip follows the currently drawn element.
- Use these exact hand alignment constants in TSX: `const HAND_WIDTH = 260; const HAND_HEIGHT = 289; const PEN_TIP_X = 15; const PEN_TIP_Y = 78;`. Render the hand with width HAND_WIDTH and height HAND_HEIGHT, and position it with `left: tipX - PEN_TIP_X`, `top: tipY - PEN_TIP_Y`.
- HandPen must return an absolutely positioned HTML `<div>` wrapping `<Img>`. Never render `<HandPen>` inside `<svg>`; render it as a sibling overlay after the SVG so Remotion's Img stays in HTML, not SVG namespace.
- The hand cannot be decorative. It must move across the canvas during every draw/write operation and be hidden only during pauses or completed static holds.
- Create a deterministic drawing timeline array or helper function that maps frame ranges to pen tip coordinates. Use interpolate() to move the hand between points; never jump instantly.
- The hand should be large enough to resemble the reference video, roughly 240-300 px wide on a 1920x1080 canvas, not a tiny cursor.
- SVG line drawings must use strokeDasharray and strokeDashoffset driven by useCurrentFrame()/interpolate().
- Animated dashed paths must have `fill="none"`. If a wash/fill is needed, draw a separate closed shape behind the animated stroke without strokeDasharray/strokeDashoffset.
- Text must be progressively revealed with slice(), substring(), or a frame-driven clipPath. Do not show full paragraphs instantly.
- For Chinese text, define a `glyphPaths` array and render it with inline `GlyphText` / `DrawGlyphPath` helpers using SVG `<path>` plus strokeDasharray/strokeDashoffset. The render server will preprocess these glyph paths from a local Chinese font with opentype.js, so include text specs and matching text drawOps instead of static SVG `<text>`.
- Do not use an HTML `HandText` slice-only renderer as the final text drawing path. The pen must follow glyph outline/path points that can be replaced by the renderer.
- Opacity fade may be used only as a secondary polish, never as the main animation for text or diagrams.
- Do not use SVG SMIL tags such as <animate>. Even SVG details must be driven by Remotion frame values.
- Include at least one non-black/white muted watercolor accent fill or wash in each scene, such as warm yellow, red, blue, tan, or gray.
- Do not use transition, animation, @keyframes, Tailwind animate-* class names, setTimeout, setInterval, requestAnimationFrame, Date.now(), or Math.random().
- Do not use fetch, eval, Function, require, filesystem APIs, browser globals, or dangerouslySetInnerHTML.
- Hardcode the provided storyboard content and audio URLs into the TSX.
- Use <Audio src="..."> from remotion for scene voiceover when audioUrl exists.
- Build visuals directly in TSX using HTML/CSS/SVG: hand-drawn lines, equations, arrows, curves, labels, diagrams, highlights.
- Avoid generic slide decks. Each scene must contain a meaningful visual explanation, not just bullets.
- Use a clean Chinese whiteboard teaching style: off-white background, black ink outlines, loose muted color fills, spacious layout, progressive reveal.
- Keep text inside safe bounds for 1920x1080.
- Keep helpers deterministic. If you need hand-drawn jitter, compute it from indexes or fixed arrays, never Math.random().

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
    await check_llm_connection()

    storyboard_data = req.storyboard.model_dump(mode="json")
    target_frames = max(
        req.fps * 10,
        round(req.storyboard.total_duration_estimate * req.fps),
    )
    style_prompt = req.style_prompt or (
        "Chinese educational whiteboard animation with a real visible hand holding a marker. "
        "The hand must write every text label and draw every SVG line by following drawOps stroke points, "
        "moving up/down/left/right inside glyphs like real handwriting, "
        "using glyphPaths/GlyphText/DrawGlyphPath so the renderer can replace Chinese text with opentype.js font outlines, "
        "using staticFile('hand-real-pen.png'), <Img>, and getPenPosition(frame) coordinates. "
        "Use Chinese handwritten fonts and anime/cartoon whiteboard doodles. "
        "No stock images, no templates, no decorative component frames."
    )
    codegen_mode = settings.remotion_codegen_mode.strip().lower()
    cache_key = _remotion_codegen_cache_key(req, codegen_mode)
    cached = _cached_remotion_response(cache_key)
    if cached:
        cached.notes = f"{cached.notes or 'Generated Remotion TSX'} (cache hit)"
        return cached

    if codegen_mode not in {"llm", "llm-first", "llm_repair"}:
        logger.info("Compiling Remotion TSX with fast local compiler for: %s", req.storyboard.topic)
        return _cache_remotion_response(
            cache_key,
            _compile_fast_remotion_response(
                req,
                (
                    "Fast Remotion compiler path: ExplainFlow used the storyboard produced by the LLM "
                    "and generated validated glyph-outline Remotion TSX locally."
                ),
            ),
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

    messages = [
        {"role": "system", "content": REMOTION_CODE_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]
    try:
        raw = await chat_json(messages=messages, model=settings.coder_model)
    except Exception as llm_error:
        logger.warning("Remotion TSX LLM call failed before validation: %s", llm_error)
        return _cache_remotion_response(
            cache_key,
            _compile_fast_remotion_response(
                req,
                (
                    "LLM TSX generation failed before validation, so ExplainFlow "
                    "compiled a self-contained Remotion whiteboard module from the storyboard."
                ),
            ),
        )

    try:
        tsx = _validate_generated_tsx(raw.get("tsx") or raw.get("code") or "")
    except ValueError as first_error:
        logger.warning("Generated Remotion TSX failed validation: %s", first_error)
        if not settings.remotion_llm_repair and codegen_mode != "llm_repair":
            return _cache_remotion_response(
                cache_key,
                _compile_fast_remotion_response(
                    req,
                    (
                        "LLM TSX failed validation, so ExplainFlow skipped the repair round "
                        "and compiled a validated Remotion whiteboard module locally."
                    ),
                ),
            )
        repair_messages = [
            *messages,
            {
                "role": "assistant",
                "content": json.dumps(raw, ensure_ascii=False),
            },
            {
                "role": "user",
                "content": (
                    "The TSX failed validation with this error: "
                    f"{first_error}. Return corrected JSON only. Keep it self-contained, "
                    "use only react/remotion imports, export named GeneratedVideo, "
                    "use useCurrentFrame(), Sequence, and interpolate() or spring(), "
                    "draw SVG lines with strokeDasharray/strokeDashoffset, reveal text progressively, "
                    "render Chinese text through glyphPaths with GlyphText/DrawGlyphPath so the renderer can "
                    "preprocess font outline paths using opentype.js, "
                    "use STXingkai/华文行楷/KaiTi/STKaiti for Chinese handwriting, never bold sans-serif, "
                    "include muted watercolor accent colors and anime/cartoon whiteboard doodles, "
                    f"render a moving HandPen with <Img src={{staticFile('{HAND_ASSET}')}} />, "
                    "use HAND_WIDTH >= 220 and PEN_TIP_X/PEN_TIP_Y offsets so the marker tip touches the active stroke, "
                    "define drawOps with kind/startFrame/endFrame/points, pointOnPolyline(), getActiveDrawOp(), "
                    "and getPenPosition(frame); pass getPenPosition(frame) to HandPen, "
                    "make text points move up/down/left/right inside words instead of sliding on a baseline, "
                    "avoid coarse scene-level tipX/tipY interpolation and avoid SVG <animate>, "
                    "and do not use CSS transitions/animations or nondeterministic timers."
                ),
            },
        ]
        try:
            raw = await chat_json(messages=repair_messages, model=settings.coder_model)
        except Exception as repair_error:
            logger.warning("Repaired Remotion TSX LLM call failed before validation: %s", repair_error)
            response = _compile_fast_remotion_response(
                req,
                (
                    "LLM TSX repair failed before validation, so ExplainFlow "
                    "compiled a self-contained Remotion whiteboard module from the storyboard."
                ),
            )
            tsx = response.tsx
            raw = {
                "duration_in_frames": response.duration_in_frames,
                "notes": response.notes,
            }
        candidate_tsx = raw.get("tsx") or raw.get("code")
        if candidate_tsx:
            try:
                tsx = _validate_generated_tsx(candidate_tsx)
            except ValueError as second_error:
                logger.warning("Repaired Remotion TSX failed validation: %s", second_error)
                response = _compile_fast_remotion_response(
                    req,
                    (
                        "LLM TSX failed stroke-following validation, so ExplainFlow "
                        "compiled a self-contained Remotion whiteboard module from the storyboard."
                    ),
                )
                tsx = response.tsx
                raw = {
                    "duration_in_frames": response.duration_in_frames,
                    "notes": response.notes,
                }
    duration = int(raw.get("duration_in_frames") or target_frames)
    duration = max(req.fps * 10, min(duration, req.fps * 240))

    return _cache_remotion_response(
        cache_key,
        GenerateRemotionCodeResponse(
            tsx=tsx,
            duration_in_frames=duration,
            fps=req.fps,
            width=req.width,
            height=req.height,
            notes=raw.get("notes"),
        ),
    )
