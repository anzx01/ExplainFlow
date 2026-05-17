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
    DiagramPlan,
    GenerateRemotionCodeRequest,
    GenerateRemotionCodeResponse,
    GenerateStoryboardRequest,
    Scene,
    Storyboard,
    VisualBeat,
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


def _validate_static_file_usage(code: str) -> None:
    allowed_asset = re.compile(
        r"^(?:hand-real-pen\.png|generated/[a-zA-Z0-9_-]+/[a-zA-Z0-9_.-]+\.(?:png|jpg|jpeg|webp))$"
    )
    for asset in re.findall(r"\bstaticFile\s*\(\s*['\"]([^'\"]+)['\"]\s*\)", code):
        if not allowed_asset.match(asset):
            raise ValueError(f"Generated code references disallowed static asset: {asset}")

    for arg in re.findall(r"\bstaticFile\s*\(([^)]*)\)", code):
        value = arg.strip()
        if value.startswith(("'", '"')):
            continue
        if value not in {"HAND_ASSET", "referenceImageAsset", "scene.referenceImageAsset", "reveal.asset"}:
            raise ValueError(f"Generated code uses uncontrolled staticFile() argument: {value}")


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
            "subtitles_enabled": req.subtitles_enabled,
            "background_music_url": req.background_music_url,
            "background_music_volume": round(req.background_music_volume, 3),
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


def _storyboard_has_audio_segments(storyboard: Storyboard) -> bool:
    for scene in storyboard.scenes:
        value = getattr(scene, "audioSegments", None) or getattr(scene, "audio_segments", None)
        if value:
            return True
        extra = getattr(scene, "model_extra", None)
        if isinstance(extra, dict) and (extra.get("audioSegments") or extra.get("audio_segments")):
            return True
    return False


def _validate_beat_timing_usage(code: str) -> None:
    required = ("audioSegments", "durationInFrames", "beatId")
    for token in required:
        if not re.search(rf"\b{token}\b", code):
            raise ValueError(
                "Generated Remotion code must use scene.audioSegments and beatId timing "
                "when beat-level audio is present"
            )
    if not re.search(r"<\s*Sequence\b[\s\S]{0,180}<\s*Audio\b", code) and not re.search(
        r"<\s*Audio\b[\s\S]{0,180}<\s*/\s*Sequence\s*>", code
    ):
        raise ValueError("Generated Remotion code must wrap beat audio in <Sequence> windows")


def _validate_generated_tsx_for_request(tsx: str, req: GenerateRemotionCodeRequest) -> str:
    code = _validate_generated_tsx(tsx)
    if _storyboard_has_audio_segments(req.storyboard):
        _validate_beat_timing_usage(code)
    return code


def _compile_fast_remotion_response(
    req: GenerateRemotionCodeRequest,
    note: str,
) -> GenerateRemotionCodeResponse:
    fallback_tsx, fallback_duration = _build_fallback_remotion_tsx(
        req.storyboard,
        req.fps,
        req.width,
        req.height,
        req.subtitles_enabled,
        req.background_music_url,
        req.background_music_volume,
    )
    return GenerateRemotionCodeResponse(
        tsx=_validate_generated_tsx(fallback_tsx),
        duration_in_frames=fallback_duration,
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
    _validate_static_file_usage(code)
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


STORYBOARD_SYSTEM_PROMPT = """你是一个教学视频 production storyboard 规划师，负责把 Explain Graph 和 EnhancedTeachingBrief 变成可绘制、可配音、可同步的中文白板视频分镜。

核心目标：
1. 解说必须跟随绘图过程。每个 scene 都要有 learning_goal、diagram_plan、visual_beats。
2. 每个 visual_beat 都必须说明“正在画什么”和“此时说什么”，旁白不能先讲完、图还没画完。
3. 每个关键点按“现象 -> 原因 -> 结果 -> 类比/总结”展开，避免只写定义和 bullet list。
4. 优先用状态对比图、过程模拟图、结构图、截面图、箭头和局部放大；少用纯文字列表。
5. image_description 必须是英文，像给图像生成模型的具体白板线稿说明：布局、标签、箭头、局部放大都要写清楚。
6. 用优秀老师板书的方式强调重点：关键术语下划线、圈出局部、彩色箭头、局部放大框、对比标记和结论框。
7. 使用有限教学色彩：red=current/flow, blue=voltage/control, green=channel/valid path, purple=gate/structure, yellow=emphasis underline/callout。
8. 内容 prompt 与视觉风格分离：这里规划内容和画面，不写模板库、组件库或代码。
9. 总时长必须服从 target_duration_seconds；如果画面复杂，要提高绘图密度或拆分 beat，不要超过目标时长。

MOS/FinFET 专项要求：
- 必须包含 MOS Off/On 对比：未加栅压无沟道无电流；V_G > V_th 后形成反型电子通道。
- 必须画出 V_DS 驱动源漏电流，把 MOS 总结为电压控制开关。
- 必须解释短沟道效应为什么随着尺寸缩小出现。
- 必须画出 FinFET 的三维 fin 和 gate 三面包住沟道。
- 必须画出 FinFET 截面，标注 W_eff = 2H_fin + W_fin，并显示三面感应电荷。

梯度下降专项要求：
- 必须包含损失曲线、当前位置、梯度方向、负梯度更新、学习率步长、迭代收敛。

输出 JSON：
{
  "scenes": [
    {
      "id": "scene_0",
      "order": 0,
      "title": "短标题",
      "learning_goal": "这一场要让观众理解什么",
      "diagram_plan": {
        "kind": "comparison|process|structure|cross_section|formula|simulation",
        "layout": "具体画面布局",
        "required_labels": ["必须写在图里的标签"]
      },
      "visual_beats": [
        {
          "id": "beat_0",
          "draw_intent": "正在画什么，包含图形、箭头、标签、变化",
          "narration": "这一步同步说什么，必须解释因果",
          "required_labels": ["本 beat 图上要出现的标签"],
          "duration_estimate": 6
        }
      ],
      "narration": "完整中文旁白，由 visual_beats 串起来，口语化但技术准确",
      "duration_estimate": 28,
      "node_ids": ["node_0"],
      "image_description": "English whiteboard line-art diagram prompt with exact labels, layout, arrows and process changes",
      "animations": [
        {
          "type": "whiteboard_draw",
          "duration": 8.0,
          "content": "与 visual beat 对应的绘图动作",
          "latex": null,
          "items": ["可选：步骤标签或图中标签"]
        }
      ]
    }
  ]
}"""


def _clean_text(value: object) -> str:
    text = "" if value is None else str(value)
    return re.sub(r"\s+", " ", text).strip()


def _subtitle_text(value: object) -> str | None:
    text = _clean_text(value)
    return text or None


def _planner_str_list(value: object, limit: int | None = None) -> list[str]:
    if isinstance(value, list):
        items = [_clean_text(item) for item in value]
    elif isinstance(value, str):
        items = [_clean_text(part) for part in re.split(r"[\n；;]+", value)]
    else:
        items = []
    items = [item for item in items if item]
    return items[:limit] if limit else items


def _parse_diagram_plan(value: object) -> DiagramPlan | None:
    if isinstance(value, DiagramPlan):
        return value
    if isinstance(value, dict):
        return DiagramPlan(
            kind=_clean_text(value.get("kind")) or "process",
            layout=_clean_text(value.get("layout")) or _clean_text(value.get("description")),
            required_labels=_planner_str_list(value.get("required_labels") or value.get("labels"), limit=12),
        )
    if isinstance(value, str) and value.strip():
        return DiagramPlan(kind="process", layout=_clean_text(value), required_labels=[])
    return None


def _parse_visual_beats(value: object) -> list[VisualBeat]:
    if not isinstance(value, list):
        return []
    beats: list[VisualBeat] = []
    for index, item in enumerate(value):
        if isinstance(item, dict):
            draw_intent = _clean_text(item.get("draw_intent") or item.get("draw") or item.get("visual"))
            narration = _clean_text(item.get("narration") or item.get("voiceover") or item.get("script"))
            if not draw_intent and not narration:
                continue
            beats.append(
                VisualBeat(
                    id=_clean_text(item.get("id")) or f"beat_{index}",
                    draw_intent=draw_intent or narration,
                    narration=narration or draw_intent,
                    required_labels=_planner_str_list(
                        item.get("required_labels") or item.get("labels") or item.get("must_draw"),
                        limit=12,
                    ),
                    duration_estimate=float(item.get("duration_estimate") or item.get("duration") or 6.0),
                )
            )
        elif isinstance(item, str) and item.strip():
            text = _clean_text(item)
            beats.append(
                VisualBeat(
                    id=f"beat_{index}",
                    draw_intent=text,
                    narration=text,
                    required_labels=[],
                    duration_estimate=6.0,
                )
            )
    return beats


def _narration_from_beats(narration: str, beats: list[VisualBeat]) -> str:
    beat_text = " ".join(beat.narration for beat in beats if beat.narration).strip()
    narration = _clean_text(narration)
    if not beat_text:
        return narration
    if len(narration) < max(80, len(beat_text) * 0.45):
        return beat_text
    missing = [
        beat.narration
        for beat in beats
        if beat.narration and beat.narration[:18] not in narration
    ]
    if missing and len(narration) < 180:
        return _clean_text(f"{narration} {' '.join(missing[:3])}")
    return narration


def _estimate_narration_seconds(narration: str) -> float:
    cjk_chars = len(re.findall(r"[\u3400-\u9fff]", narration))
    total_chars = len(narration)
    # Edge TTS pauses on Chinese punctuation; this slower estimate prevents scene audio being clipped.
    return max(8.0, cjk_chars / 3.35 + max(0, total_chars - cjk_chars) / 7.2)


def _estimate_scene_duration(raw_duration: float, narration: str, beats: list[VisualBeat], animations: list[AnimationInstruction]) -> float:
    narration_seconds = _estimate_narration_seconds(narration)
    beat_seconds = sum(max(3.0, beat.duration_estimate) for beat in beats) + (4.0 if beats else 0.0)
    animation_seconds = sum(animation.duration for animation in animations) + (4.0 if animations else 0.0)
    minimum = 22.0 if beats else 16.0
    duration = max(float(raw_duration or 0), narration_seconds + 3.0, beat_seconds, animation_seconds, minimum)
    return round(min(duration, 55.0), 1)


def _scene_floor_duration(scene: Scene) -> float:
    beat_floor = sum(max(2.4, beat.duration_estimate * 0.75) for beat in scene.visual_beats)
    animation_floor = sum(max(1.0, animation.duration * 0.8) for animation in scene.animations)
    narration_floor = _estimate_narration_seconds(scene.narration) + 2.0
    required = max(12.0, narration_floor, beat_floor + 2.0, animation_floor + 2.0)
    return round(min(36.0, required), 1)


def _fit_storyboard_to_target(storyboard: Storyboard, target_duration: int) -> Storyboard:
    """Treat the UI duration as the final contract without starving narration-heavy scenes."""
    target = float(max(60, min(180, target_duration)))
    if not storyboard.scenes:
        storyboard.total_duration_estimate = target
        return storyboard

    current = sum(max(0.1, scene.duration_estimate) for scene in storyboard.scenes)
    if current <= 0:
        per_scene = target / len(storyboard.scenes)
        for scene in storyboard.scenes:
            scene.duration_estimate = round(per_scene, 1)
        storyboard.total_duration_estimate = target
        return storyboard

    floors = [_scene_floor_duration(scene) for scene in storyboard.scenes]
    floor_total = sum(floors)
    if floor_total <= target:
        weights = [max(0.1, scene.duration_estimate - floor) for scene, floor in zip(storyboard.scenes, floors)]
        weight_total = sum(weights) or float(len(storyboard.scenes))
        remaining = target - floor_total
        running = 0.0
        for index, (scene, floor, weight) in enumerate(zip(storyboard.scenes, floors, weights)):
            if index == len(storyboard.scenes) - 1:
                duration = max(1.0, target - running)
            else:
                duration = floor + remaining * (weight / weight_total)
                running += duration
            ratio = duration / max(0.1, scene.duration_estimate)
            scene.duration_estimate = round(duration, 1)
            for beat in scene.visual_beats:
                beat.duration_estimate = round(max(1.0, beat.duration_estimate * ratio), 1)
            for animation in scene.animations:
                animation.duration = round(max(0.5, min(15.0, animation.duration * ratio)), 1)
        rounded_total = round(sum(scene.duration_estimate for scene in storyboard.scenes), 1)
        delta = round(target - rounded_total, 1)
        if storyboard.scenes and abs(delta) >= 0.1:
            storyboard.scenes[-1].duration_estimate = round(max(1.0, storyboard.scenes[-1].duration_estimate + delta), 1)
        storyboard.total_duration_estimate = round(sum(scene.duration_estimate for scene in storyboard.scenes), 1)
        return storyboard

    scale = target / floor_total
    running = 0.0
    for index, scene in enumerate(storyboard.scenes):
        if index == len(storyboard.scenes) - 1:
            duration = max(1.0, target - running)
        else:
            duration = max(8.0, _scene_floor_duration(scene) * scale)
            running += duration
        ratio = duration / max(0.1, scene.duration_estimate)
        scene.duration_estimate = round(duration, 1)
        for beat in scene.visual_beats:
            beat.duration_estimate = round(max(1.0, beat.duration_estimate * ratio), 1)
        for animation in scene.animations:
            animation.duration = round(max(0.5, min(15.0, animation.duration * ratio)), 1)

    rounded_total = round(sum(scene.duration_estimate for scene in storyboard.scenes), 1)
    delta = round(target - rounded_total, 1)
    if storyboard.scenes and abs(delta) >= 0.1:
        storyboard.scenes[-1].duration_estimate = round(max(1.0, storyboard.scenes[-1].duration_estimate + delta), 1)
    storyboard.total_duration_estimate = round(sum(scene.duration_estimate for scene in storyboard.scenes), 1)
    return storyboard


def _graph_enhanced_brief(graph: ExplainGraph) -> dict | None:
    brief = getattr(graph, "enhanced_brief", None)
    if not brief:
        return None
    if hasattr(brief, "model_dump"):
        return brief.model_dump(mode="json")
    if isinstance(brief, dict):
        return brief
    return None


def _desired_scene_count(graph: ExplainGraph, target_duration: int) -> int:
    brief = _graph_enhanced_brief(graph) or {}
    outline = brief.get("recommended_scene_outline") if isinstance(brief, dict) else None
    outline_count = len(outline) if isinstance(outline, list) else 0
    topic_blob = " ".join(
        [
            graph.topic,
            graph.summary,
            " ".join(graph.key_insights),
            json.dumps(brief, ensure_ascii=False) if brief else "",
        ]
    ).lower()
    if any(term in topic_blob for term in ["mos", "mosfet", "finfet", "晶体管", "栅极", "沟道"]):
        if target_duration <= 70:
            return 3
        if target_duration <= 95:
            return 4
        if target_duration <= 150:
            return 5
        return max(6, min(8, outline_count or 6))
    if any(term in topic_blob for term in ["gradient", "descent", "梯度下降", "学习率", "损失"]):
        return max(4, min(6, outline_count or 4))
    if outline_count:
        return max(3, min(8, outline_count))
    return max(3, min(6, len(graph.nodes), max(3, target_duration // 24)))


async def generate_storyboard(req: GenerateStoryboardRequest) -> Storyboard:
    await check_llm_connection()

    graph = req.graph
    brief_data = _graph_enhanced_brief(graph)
    desired_scene_count = _desired_scene_count(graph, req.target_duration)
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

    user_content = json.dumps(
        {
            "topic": graph.topic,
            "summary": graph.summary,
            "target_duration_seconds": req.target_duration,
            "desired_scene_count": desired_scene_count,
            "enhanced_teaching_brief": brief_data,
            "concept_nodes": [
                {
                    "id": node.id,
                    "label": node.label,
                    "node_type": node.node_type.value,
                    "description": node.description,
                    "latex": node.latex,
                    "teach_order": node.teach_order,
                }
                for node in sorted(graph.nodes, key=lambda item: item.teach_order)
            ],
            "edges": [edge.model_dump(mode="json") for edge in graph.edges],
            "key_insights": graph.key_insights,
            "requirements": [
                "Generate concrete scenes, not generic slide bullets.",
                "Each scene must include learning_goal, diagram_plan, visual_beats, narration, image_description and animations.",
                "Every visual_beat must pair draw_intent with narration so voiceover follows drawing.",
                "Use comparison/process/structure/cross-section diagrams and arrows whenever possible.",
                "Borrow strong science-video teaching techniques: start with a hook or historical/context clue when useful, expand acronyms visually, use picture-in-picture reference diagrams, and introduce one concrete real-world analogy that maps to the mechanism.",
                "For abstract mechanisms, show the analogy and the technical diagram side by side, then transfer arrows/labels from the analogy to the device/process.",
                "Use progressive focus: first show the whole object, then zoom/call out one region, then add colored arrows and labels only when the narration reaches them.",
                "The total duration must match target_duration_seconds. If content is complex, split the drawing more efficiently instead of exceeding the target.",
                "Use red for current, blue for voltage/control signals, green for conductive channels, purple for gates/attention, and yellow underlines/callouts for key terms.",
                "Underline, circle, or box important concepts like V_G > V_th, electron channel, short-channel effect, FinFET, W_eff, learning rate, and gradient.",
            ],
        },
        ensure_ascii=False,
    )

    logger.info("Generating storyboard for: %s, target=%ds", graph.topic, req.target_duration)

    raw = await chat_json(
        messages=[
            {"role": "system", "content": STORYBOARD_SYSTEM_PROMPT},
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
        visual_beats = _parse_visual_beats(s.get("visual_beats"))
        diagram_plan = _parse_diagram_plan(s.get("diagram_plan"))
        narration = _narration_from_beats(s.get("narration") or "", visual_beats)
        dur = _estimate_scene_duration(float(s.get("duration_estimate", 20)), narration, visual_beats, animations)
        total_duration += dur
        scenes.append(
            Scene(
                id=s.get("id") or f"scene_{len(scenes)}",
                order=s.get("order", len(scenes)),
                title=s.get("title") or f"场景 {len(scenes) + 1}",
                narration=narration,
                duration_estimate=dur,
                animations=animations,
                node_ids=s.get("node_ids") or [],
                image_description=s.get("image_description") or None,
                learning_goal=s.get("learning_goal") or None,
                visual_beats=visual_beats,
                diagram_plan=diagram_plan,
            )
        )

    storyboard = Storyboard(
        topic=graph.topic,
        total_duration_estimate=total_duration,
        scenes=scenes,
    )
    storyboard = _ensure_storyboard_quality(storyboard, graph, req.target_duration)
    storyboard = _fit_storyboard_to_target(storyboard, req.target_duration)

    logger.info("Storyboard generated: %d scenes, %.1fs total", len(storyboard.scenes), storyboard.total_duration_estimate)
    return storyboard


def _storyboard_corpus(storyboard: Storyboard, graph: ExplainGraph) -> str:
    brief = _graph_enhanced_brief(graph) or {}
    parts = [graph.topic, graph.summary, " ".join(graph.key_insights), json.dumps(brief, ensure_ascii=False)]
    for scene in storyboard.scenes:
        parts.extend([scene.title, scene.narration, scene.learning_goal or "", scene.image_description or ""])
        if scene.diagram_plan:
            parts.append(scene.diagram_plan.kind)
            parts.append(scene.diagram_plan.layout)
            parts.extend(scene.diagram_plan.required_labels)
        for beat in scene.visual_beats:
            parts.extend([beat.draw_intent, beat.narration, *beat.required_labels])
        for animation in scene.animations:
            parts.append(animation.content)
            parts.append(animation.latex or "")
            if animation.items:
                parts.extend(animation.items)
    return " ".join(part for part in parts if part).lower()


def _contains_terms(corpus: str, terms: list[str]) -> bool:
    return any(term.lower() in corpus for term in terms)


def _scene_from_spec(index: int, spec: dict) -> Scene:
    beats = [
        VisualBeat(
            id=f"beat_{beat_index}",
            draw_intent=beat["draw_intent"],
            narration=beat["narration"],
            required_labels=beat.get("required_labels", []),
            duration_estimate=beat.get("duration_estimate", 6.0),
        )
        for beat_index, beat in enumerate(spec["visual_beats"])
    ]
    animations = [
        AnimationInstruction(
            type=AnimationType.WHITEBOARD_DRAW,
            duration=min(15.0, max(4.0, beat.duration_estimate)),
            content=beat.draw_intent,
            items=beat.required_labels or None,
        )
        for beat in beats
    ]
    if spec.get("formula"):
        animations.append(
            AnimationInstruction(
                type=AnimationType.WRITE_FORMULA,
                duration=5.0,
                content=spec["formula"],
                latex=spec["formula"],
            )
        )
    narration = _narration_from_beats(spec.get("narration", ""), beats)
    duration = _estimate_scene_duration(float(spec.get("duration_estimate", 28)), narration, beats, animations)
    diagram = spec.get("diagram_plan") or {}
    return Scene(
        id=f"scene_{index}",
        order=index,
        title=spec["title"],
        learning_goal=spec["learning_goal"],
        diagram_plan=DiagramPlan(
            kind=diagram.get("kind", "process"),
            layout=diagram.get("layout", ""),
            required_labels=diagram.get("required_labels", []),
        ),
        visual_beats=beats,
        narration=narration,
        duration_estimate=duration,
        animations=animations,
        node_ids=spec.get("node_ids", []),
        image_description=spec["image_description"],
    )


def _semiconductor_story_specs() -> list[dict]:
    return [
        {
            "title": "MOS 结构先搭起来",
            "learning_goal": "先让观众知道源极、漏极、栅极、氧化层、衬底和沟道区域的位置关系。",
            "diagram_plan": {
                "kind": "structure",
                "layout": "planar MOS cross-section with labels from left to right",
                "required_labels": ["Source", "Drain", "Gate", "Oxide", "Substrate", "Channel"],
            },
            "visual_beats": [
                {
                    "draw_intent": "画一条衬底横截面，在左右分别画 Source 和 Drain，中间留出 channel region。",
                    "narration": "先把平面 MOS 的剖面搭起来：左右是源极和漏极，中间的衬底表面就是未来可能形成沟道的位置。",
                    "required_labels": ["Source", "Drain", "Channel region"],
                    "duration_estimate": 7,
                },
                {
                    "draw_intent": "在沟道上方画薄氧化层和 Gate，并用虚线电场箭头指向衬底表面。",
                    "narration": "栅极并不直接接触沟道，它隔着很薄的氧化层，用电场去影响衬底表面的电荷。",
                    "required_labels": ["Gate", "Oxide", "electric field"],
                    "duration_estimate": 8,
                },
            ],
            "image_description": "whiteboard line drawing of a planar MOS transistor cross-section, source and drain blocks on a substrate, a thin oxide layer and a gate over the channel region, labels Source, Drain, Gate, Oxide, Substrate, Channel region, simple electric field arrows",
            "duration_estimate": 26,
        },
        {
            "title": "Off/On 两种状态",
            "learning_goal": "用双图对比解释阈值电压如何决定有没有连续电子沟道。",
            "diagram_plan": {
                "kind": "comparison",
                "layout": "two panels: OFF on the left, ON on the right",
                "required_labels": ["OFF: V_G < V_th", "ON: V_G > V_th", "no channel", "electron channel"],
            },
            "visual_beats": [
                {
                    "draw_intent": "左侧画 OFF 状态，源漏之间断开，用叉号标出 no channel / no current。",
                    "narration": "在 Off 状态，栅压还没有超过阈值，衬底表面没有形成连续电子通道，源极和漏极就像被断开的两端。",
                    "required_labels": ["OFF", "V_G < V_th", "no channel"],
                    "duration_estimate": 8,
                },
                {
                    "draw_intent": "右侧画 ON 状态，从栅极向下画电场箭头，再画一条连续 electron channel。",
                    "narration": "当 V_G 大于 V_th，栅极电场会在衬底表面感应出足够电子，最后连成一条反型沟道。",
                    "required_labels": ["ON", "V_G > V_th", "electron channel"],
                    "duration_estimate": 9,
                },
            ],
            "image_description": "two-panel whiteboard comparison of a MOS transistor OFF and ON state, left panel labeled OFF V_G < V_th with no channel and crossed current arrow, right panel labeled ON V_G > V_th with a dark electron channel between source and drain and downward gate electric field arrows",
            "duration_estimate": 30,
        },
        {
            "title": "电流被电压打开",
            "learning_goal": "说明 V_DS 只有在沟道形成后才能推动源漏电流，MOS 因此像电压控制开关。",
            "diagram_plan": {
                "kind": "process",
                "layout": "ON MOS diagram with channel, source-drain battery, current arrows and switch analogy",
                "required_labels": ["V_DS", "I_D", "Voltage-controlled switch"],
            },
            "visual_beats": [
                {
                    "draw_intent": "在已经形成的沟道两端画 V_DS 电源符号。",
                    "narration": "有了沟道还不等于自动有电流，源漏之间还需要一个 V_DS 来提供推动载流子的电势差。",
                    "required_labels": ["V_DS"],
                    "duration_estimate": 7,
                },
                {
                    "draw_intent": "沿沟道画多根电流箭头 I_D，并在旁边画一个被栅压控制的开关图标。",
                    "narration": "于是电子沿沟道移动，形成漏电流 I_D。直观地说，栅极电压负责开门，源漏电压负责把电流推过去。",
                    "required_labels": ["I_D", "switch"],
                    "duration_estimate": 9,
                },
            ],
            "image_description": "whiteboard MOS ON diagram with electron channel between source and drain, a V_DS battery connected across source and drain, arrows labeled I_D flowing through the channel, small voltage-controlled switch analogy icon",
            "duration_estimate": 29,
        },
        {
            "title": "短沟道效应",
            "learning_goal": "解释为什么尺寸缩小时平面 MOS 的栅极控制会变弱。",
            "diagram_plan": {
                "kind": "comparison",
                "layout": "long-channel MOS versus short-channel MOS with source/drain fields intruding",
                "required_labels": ["long channel", "short channel", "short-channel effect"],
            },
            "visual_beats": [
                {
                    "draw_intent": "画长沟道和平面栅极，标出栅极主要控制中间沟道。",
                    "narration": "在长沟道器件里，沟道足够长，栅极像一个比较强的总闸门，能主导中间区域的电荷。",
                    "required_labels": ["long channel", "gate control"],
                    "duration_estimate": 7,
                },
                {
                    "draw_intent": "把沟道画短，源漏电场箭头挤进沟道区域，并画失控提示。",
                    "narration": "尺寸继续缩小时，源极和漏极离得太近，它们的电场会伸进沟道，抢走一部分控制权，这就是短沟道效应的直观来源。",
                    "required_labels": ["short channel", "field intrusion"],
                    "duration_estimate": 9,
                },
            ],
            "image_description": "whiteboard comparison of long-channel and short-channel planar MOS devices, long channel controlled by gate, short channel with source and drain electric field arrows intruding into the channel, warning label short-channel effect",
            "duration_estimate": 29,
        },
        {
            "title": "FinFET 三面包住沟道",
            "learning_goal": "看懂 FinFET 为什么把沟道做成竖起的 fin，并让栅极从三面包住它。",
            "diagram_plan": {
                "kind": "structure",
                "layout": "simple 3D fin channel with gate wrapping top and two sidewalls",
                "required_labels": ["Fin channel", "Gate wraps 3 sides", "Source", "Drain"],
            },
            "visual_beats": [
                {
                    "draw_intent": "画一个竖起的 fin/channel，两端分别连接 Source 和 Drain。",
                    "narration": "FinFET 的第一步，是把原来趴在平面上的沟道竖起来，变成一条鳍片状的三维通道。",
                    "required_labels": ["Fin channel", "Source", "Drain"],
                    "duration_estimate": 8,
                },
                {
                    "draw_intent": "画 U 形 Gate 从顶部和两侧包住 fin，并从三面画控制箭头。",
                    "narration": "然后栅极不再只从上方控制，而是像夹子一样包住顶部和两个侧壁，三面同时施加电场，栅控能力就明显增强。",
                    "required_labels": ["Gate wraps 3 sides", "three-side control"],
                    "duration_estimate": 10,
                },
            ],
            "image_description": "simple 3D whiteboard sketch of a FinFET: vertical fin channel standing between source and drain, a U-shaped gate wrapping over the top and both sidewalls of the fin, three control arrows, labels Fin channel, Source, Drain, Gate wraps 3 sides",
            "duration_estimate": 32,
        },
        {
            "title": "截面里的有效宽度",
            "learning_goal": "用 FinFET 截面解释 W_eff = 2H_fin + W_fin 和三面感应电荷。",
            "diagram_plan": {
                "kind": "cross_section",
                "layout": "FinFET cross-section with U-shaped gate, top width and two sidewall heights",
                "required_labels": ["H_fin", "W_fin", "W_eff = 2H_fin + W_fin", "induced electrons"],
            },
            "visual_beats": [
                {
                    "draw_intent": "画 fin 的截面和 U 形栅极，分别标出顶部 W_fin 和两侧 H_fin。",
                    "narration": "从截面看，FinFET 的沟道不是只有顶部一条线，两侧壁也被栅极包住，所以都能参与导通。",
                    "required_labels": ["W_fin", "H_fin"],
                    "duration_estimate": 8,
                },
                {
                    "draw_intent": "在三面画出 induced electrons，再写公式 W_eff = 2H_fin + W_fin。",
                    "narration": "当栅极加电后，顶部和两侧都能感应出电荷，有效沟道宽度就来自两侧高度加上顶部宽度，也就是 W_eff 等于 2H_fin 加 W_fin。",
                    "required_labels": ["induced electrons", "W_eff = 2H_fin + W_fin"],
                    "duration_estimate": 10,
                },
            ],
            "formula": "W_{eff}=2H_{fin}+W_{fin}",
            "image_description": "FinFET cross-section whiteboard diagram with a U-shaped gate around a rectangular fin, labels H_fin on both sidewalls, W_fin on the top, small induced electron dots on the three gated surfaces, formula W_eff = 2H_fin + W_fin",
            "duration_estimate": 33,
        },
    ]


def _semiconductor_story_specs_for_target(target_duration: int) -> list[dict]:
    specs = _semiconductor_story_specs()
    if target_duration <= 70:
        return [specs[1], specs[4], specs[5]]
    if target_duration <= 95:
        return [specs[1], specs[3], specs[4], specs[5]]
    if target_duration <= 150:
        return [specs[1], specs[2], specs[3], specs[4], specs[5]]
    return specs


def _gradient_story_specs() -> list[dict]:
    return [
        {
            "title": "把损失画成地形",
            "learning_goal": "让观众知道 loss 曲线的高度代表错误大小。",
            "diagram_plan": {"kind": "simulation", "layout": "loss curve with axes", "required_labels": ["Loss", "theta"]},
            "visual_beats": [
                {
                    "draw_intent": "画 theta 横轴和 Loss 纵轴，再画一条下降的曲线。",
                    "narration": "先把损失函数画成一条地形曲线，越高代表模型错得越多，越低代表参数更合适。",
                    "required_labels": ["Loss", "theta"],
                    "duration_estimate": 7,
                }
            ],
            "image_description": "whiteboard loss curve with theta axis and Loss axis, a current parameter dot on the curve",
            "duration_estimate": 23,
        },
        {
            "title": "沿负梯度走一步",
            "learning_goal": "解释梯度方向、负梯度方向和学习率步长。",
            "diagram_plan": {"kind": "process", "layout": "gradient and negative gradient arrows", "required_labels": ["gradient", "-gradient", "learning rate"]},
            "visual_beats": [
                {
                    "draw_intent": "标出当前位置，画梯度箭头和反方向更新箭头。",
                    "narration": "梯度指向损失上升最快的方向，所以要往相反方向走。学习率决定这一步到底迈多远。",
                    "required_labels": ["gradient", "-gradient", "learning rate"],
                    "duration_estimate": 9,
                }
            ],
            "image_description": "whiteboard diagram of a point on a loss curve with gradient arrow, negative gradient update arrow, learning-rate step length label",
            "duration_estimate": 25,
        },
        {
            "title": "重复迭代直到收敛",
            "learning_goal": "展示多次更新如何接近低损失区域。",
            "diagram_plan": {"kind": "process", "layout": "multiple update dots toward minimum", "required_labels": ["iteration", "minimum", "converge"]},
            "visual_beats": [
                {
                    "draw_intent": "沿曲线画多个迭代点和逐步变短的箭头，最后靠近最低点。",
                    "narration": "把这一步重复很多次，参数点就会沿着曲线逐渐靠近低损失区域；步长太大可能来回震荡，太小则走得很慢。",
                    "required_labels": ["iteration", "converge", "minimum"],
                    "duration_estimate": 10,
                }
            ],
            "image_description": "whiteboard loss curve with several iteration dots moving toward a minimum, arrows shrinking near convergence, labels iteration, converge, minimum",
            "duration_estimate": 27,
        },
    ]


def _replace_with_specs(storyboard: Storyboard, specs: list[dict]) -> Storyboard:
    scenes = [_scene_from_spec(index, spec) for index, spec in enumerate(specs)]
    return Storyboard(
        topic=storyboard.topic,
        total_duration_estimate=round(sum(scene.duration_estimate for scene in scenes), 1),
        scenes=scenes,
    )


def _ensure_storyboard_quality(storyboard: Storyboard, graph: ExplainGraph, target_duration: int) -> Storyboard:
    corpus = _storyboard_corpus(storyboard, graph)
    semiconductor = _contains_terms(corpus, ["mos", "mosfet", "finfet", "晶体管", "栅极", "沟道"])
    gradient = _contains_terms(corpus, ["gradient", "descent", "梯度下降", "学习率", "损失"])

    if semiconductor:
        target_specs = _semiconductor_story_specs_for_target(target_duration)
        if len(storyboard.scenes) > len(target_specs):
            return _replace_with_specs(storyboard, target_specs)
        coverage_groups = [
            ["off", "on", "v_g", "vth", "v_th", "阈值"],
            ["v_ds", "i_d", "源漏", "电流"],
            ["短沟道", "short-channel"],
            ["finfet", "fin", "三面", "包住"],
            ["w_eff", "2h_fin", "截面", "有效宽度"],
        ]
        coverage = sum(1 for group in coverage_groups if _contains_terms(corpus, group))
        if len(storyboard.scenes) < min(5, len(target_specs)) or coverage < 4:
            return _replace_with_specs(storyboard, target_specs)

    if gradient:
        coverage_groups = [
            ["loss", "损失"],
            ["gradient", "梯度"],
            ["learning rate", "学习率"],
            ["iteration", "迭代", "converge", "收敛"],
        ]
        coverage = sum(1 for group in coverage_groups if _contains_terms(corpus, group))
        if len(storyboard.scenes) < 3 or coverage < 4:
            return _replace_with_specs(storyboard, _gradient_story_specs())

    for scene in storyboard.scenes:
        if not scene.visual_beats:
            labels = []
            if scene.diagram_plan:
                labels = scene.diagram_plan.required_labels
            scene.visual_beats = [
                VisualBeat(
                    id="beat_0",
                    draw_intent=scene.image_description or scene.title,
                    narration=scene.narration or scene.title,
                    required_labels=labels,
                    duration_estimate=max(5.0, min(10.0, scene.duration_estimate * 0.35)),
                )
            ]
        scene.narration = _narration_from_beats(scene.narration, scene.visual_beats)
        scene.duration_estimate = _estimate_scene_duration(
            scene.duration_estimate,
            scene.narration,
            scene.visual_beats,
            scene.animations,
        )
    storyboard.total_duration_estimate = round(sum(scene.duration_estimate for scene in storyboard.scenes), 1)
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


def _retime_draw_ops_in_window(
    draw_ops: list[dict],
    start_frame: float,
    end_frame: float,
    beat_id: str | None = None,
) -> None:
    if not draw_ops:
        return
    ordered = sorted(
        enumerate(draw_ops),
        key=lambda item: (float(item[1].get("startFrame", 0)), item[0]),
    )
    spans = [
        max(0.5, float(op.get("endFrame", 0)) - float(op.get("startFrame", 0)))
        for _, op in ordered
    ]
    target_end = max(start_frame + 1.0, end_frame)
    target_span = max(1.0, target_end - start_frame)
    default_gap = 0.35 if len(ordered) > 80 else 0.65
    gap = min(default_gap, target_span * 0.18 / max(1, len(ordered) - 1))
    available = max(1.0, target_span - gap * max(0, len(ordered) - 1))
    min_span = min(0.5, max(0.08, available / max(1, len(ordered)) * 0.8))
    scale = available / max(1.0, sum(spans))
    cursor = start_frame
    for index, ((_, op), span) in enumerate(zip(ordered, spans)):
        safe_start = min(cursor, max(start_frame, target_end - min_span))
        next_end = target_end if index == len(ordered) - 1 else min(target_end, safe_start + max(min_span, span * scale))
        op["startFrame"] = round(safe_start, 2)
        op["endFrame"] = round(max(safe_start + min_span, next_end), 2)
        if beat_id:
            op["beatId"] = beat_id
        cursor = op["endFrame"] + gap


def _retime_draw_ops_to_fill_scene(draw_ops: list[dict], duration: int) -> None:
    _retime_draw_ops_in_window(draw_ops, 0.0, max(1.0, duration - 10.0))


def _retime_draw_ops_to_audio_segments(draw_ops: list[dict], audio_segments: list[dict], duration: int) -> None:
    if not draw_ops:
        return
    segments = [
        segment
        for segment in audio_segments
        if isinstance(segment, dict)
        and float(segment.get("endFrame", 0) or 0) > float(segment.get("startFrame", 0) or 0)
    ]
    if not segments:
        _retime_draw_ops_to_fill_scene(draw_ops, duration)
        return
    ordered = sorted(
        draw_ops,
        key=lambda op: (float(op.get("startFrame", 0)), str(op.get("id", ""))),
    )
    weights = [max(1.0, float(segment.get("drawBudgetFrames") or segment.get("duration") or 1)) for segment in segments]
    total_weight = sum(weights) or float(len(segments))
    cursor = 0
    for index, segment in enumerate(segments):
        remaining_ops = len(ordered) - cursor
        remaining_segments = len(segments) - index
        if remaining_ops <= 0:
            break
        if index == len(segments) - 1:
            take = remaining_ops
        else:
            target = round(len(ordered) * (weights[index] / total_weight))
            take = max(1, min(remaining_ops - (remaining_segments - 1), target))
        group = ordered[cursor : cursor + take]
        cursor += take
        start = float(segment.get("startFrame", 0) or 0)
        end = float(segment.get("endFrame", duration) or duration)
        window_end = min(max(start + 1.0, end - 4.0), max(1.0, duration - 2.0))
        _retime_draw_ops_in_window(group, start, window_end, str(segment.get("id") or f"beat_{index}"))
    if cursor < len(ordered):
        _retime_draw_ops_in_window(ordered[cursor:], 0.0, max(1.0, duration - 10.0))


def _animation_lines(scene: Scene) -> list[str]:
    lines: list[str] = []
    seen: set[str] = set()

    def add_line(value: str | None, max_chars: int = 22) -> None:
        text = _short_text(value, max_chars)
        if not text or text in seen:
            return
        seen.add(text)
        lines.append(text)

    if scene.diagram_plan:
        for label in scene.diagram_plan.required_labels[:4]:
            add_line(label, 22)

    for beat in getattr(scene, "visual_beats", []) or []:
        if beat.required_labels:
            for label in beat.required_labels[:3]:
                add_line(label, 22)
        elif beat.narration and len(lines) < 2:
            add_line(beat.narration, 18)
        if len(lines) >= 5:
            break
    for animation in scene.animations:
        raw_type = getattr(animation.type, "value", str(animation.type))
        if raw_type in {"write_formula", "formula_reveal"}:
            value = animation.latex or animation.content
            if value:
                add_line(value, 28)
        elif animation.items:
            if animation.content:
                add_line(animation.content, 20)
            for item in animation.items[:3]:
                add_line(item, 20)
        elif animation.content:
            add_line(animation.content, 20)
    if not lines:
        return []
    return lines[:4]


def _scene_corpus(scene: Scene) -> str:
    parts: list[str] = [scene.title, scene.narration, scene.learning_goal or "", scene.image_description or ""]
    if scene.diagram_plan:
        parts.extend([scene.diagram_plan.kind, scene.diagram_plan.layout])
        parts.extend(scene.diagram_plan.required_labels)
    for beat in getattr(scene, "visual_beats", []) or []:
        parts.extend([beat.draw_intent, beat.narration])
        parts.extend(beat.required_labels)
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
    for beat in getattr(scene, "visual_beats", []) or []:
        if beat.draw_intent:
            steps.append(beat.draw_intent)
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
    if scene.diagram_plan and scene.diagram_plan.kind in {"semiconductor_device", "mos_device", "finfet_device"}:
        return "semiconductor_device"
    if _contains_any(
        corpus,
        [
            "mos",
            "mosfet",
            "finfet",
            "source",
            "drain",
            "gate",
            "oxide",
            "substrate",
            "channel",
            "v_g",
            "v_ds",
            "w_eff",
            "晶体管",
            "栅极",
            "源极",
            "漏极",
            "沟道",
            "阈值",
            "短沟道",
        ],
    ):
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


def _scene_extra(scene: Scene, name: str, default: object = None) -> object:
    value = getattr(scene, name, None)
    if value is not None:
        return value
    extra = getattr(scene, "model_extra", None)
    if isinstance(extra, dict):
        return extra.get(name, default)
    return default


def _audio_segments_for_scene(scene: Scene, fps: int) -> tuple[list[dict], int, int]:
    raw_segments = (
        _scene_extra(scene, "audioSegments")
        or _scene_extra(scene, "audio_segments")
        or _scene_extra(scene, "audio_segments_json")
        or []
    )
    raw_timing = _scene_extra(scene, "timingPlan") or _scene_extra(scene, "timing_plan") or {}
    transition_frames = 10
    if isinstance(raw_timing, dict):
        transition_frames = max(0, min(18, int(raw_timing.get("transitionFrames") or raw_timing.get("transition_frames") or 10)))
    segments: list[dict] = []
    if isinstance(raw_segments, list):
        for index, raw in enumerate(raw_segments):
            if not isinstance(raw, dict):
                continue
            start = max(0, int(round(float(raw.get("startFrame") or raw.get("start_frame") or 0))))
            duration = int(round(float(raw.get("duration") or 0)))
            end = int(round(float(raw.get("endFrame") or raw.get("end_frame") or 0)))
            if duration <= 0 and end > start:
                duration = end - start
            if duration <= 0:
                duration = max(fps * 3, int(round(float(raw.get("audioDurationFrames") or fps * 3))) + 12)
            end = max(start + 1, start + duration)
            audio_duration = max(1, int(round(float(raw.get("audioDurationFrames") or raw.get("audio_duration_frames") or duration))))
            segments.append(
                {
                    "id": _clean_text(raw.get("id")) or f"beat_{index}",
                    "index": index,
                    "startFrame": start,
                    "endFrame": end,
                    "duration": end - start,
                    "audioUrl": raw.get("audioUrl") or raw.get("audio_url"),
                    "audioDurationFrames": audio_duration,
                    "drawBudgetFrames": max(1, int(round(float(raw.get("drawBudgetFrames") or raw.get("draw_budget_frames") or (end - start - 8))))),
                    "subtitleText": _subtitle_text(raw.get("subtitleText") or raw.get("subtitle_text") or raw.get("narration")),
                    "drawIntent": _clean_text(raw.get("drawIntent") or raw.get("draw_intent")),
                }
            )
    duration_frames = 0
    if isinstance(raw_timing, dict):
        duration_frames = int(round(float(raw_timing.get("durationFrames") or raw_timing.get("duration_frames") or 0)))
    if segments:
        duration_frames = max(duration_frames, max(segment["endFrame"] for segment in segments) + transition_frames)
    return segments, duration_frames, transition_frames


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
    audio_segments, timing_duration, transition_frames = _audio_segments_for_scene(scene, fps)
    duration = max(fps * 8, round(scene.duration_estimate * fps), timing_duration)
    left = width * 0.07
    top = height * 0.08
    diagram_left = width * 0.405
    diagram_top = height * 0.22
    accent_colors = ["#F7D77E", "#A8D8F0", "#F4A7A1", "#BFE3C0", "#D7C5F7"]
    accent = accent_colors[scene_index % len(accent_colors)]
    ink = "#1D1D1F"
    blue = "#2F6FB2"
    red = "#D85C4A"
    green = "#3F8F68"
    violet = "#6E58B5"
    yellow = "#D9A514"
    draw_ops: list[dict] = []
    texts: list[dict] = []
    strokes: list[dict] = []
    raster_reveal_spec: dict | None = None
    diagram_kind = _diagram_kind_for_scene(scene, scene_index)
    core_lines = _animation_lines(scene)
    steps = _scene_steps(scene)
    raw_trace_strokes = _scene_extra(scene, "trace_strokes") or _scene_extra(scene, "traceStrokes") or []
    trace_strokes = raw_trace_strokes if isinstance(raw_trace_strokes, list) else []
    raw_raster_reveal = _scene_extra(scene, "rasterReveal") or _scene_extra(scene, "raster_reveal") or {}
    raster_reveal = raw_raster_reveal if isinstance(raw_raster_reveal, dict) else {}
    raster_strokes = raster_reveal.get("strokes") if isinstance(raster_reveal.get("strokes"), list) else []
    reference_image_asset = (
        _scene_extra(scene, "referenceImageAsset")
        or _scene_extra(scene, "reference_image_asset")
        or raster_reveal.get("asset")
    )

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
        emphasis: bool | None = None,
        max_chars: int = 38,
    ) -> None:
        op_id = f"s{scene_index}_text_{len(texts)}"
        safe_text = _short_text(text, max_chars)
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
        emphasis_terms = [
            "V_G",
            "V_th",
            "V_DS",
            "I_D",
            "W_eff",
            "MOS",
            "FinFET",
            "Gate",
            "Source",
            "Drain",
            "Channel",
            "Loss",
            "gradient",
            "learning rate",
            "阈值",
            "沟道",
            "短沟道",
            "电流",
            "栅极",
            "学习率",
            "梯度",
            "损失",
        ]
        should_emphasize = (
            emphasis
            if emphasis is not None
            else len(safe_text) <= 28 and _contains_any(safe_text.lower(), [term.lower() for term in emphasis_terms])
        )
        if should_emphasize:
            estimated_width = min(
                text_max_width,
                max(font_size * 1.6, len(safe_text) * font_size * (0.72 if re.search(r"[\u3400-\u9fff]", safe_text) else 0.48)),
            )
            underline_y = y + font_size * 1.05
            underline_points = _curve_points(
                x,
                underline_y,
                x + estimated_width,
                underline_y,
                count=10,
                wave=max(2.0, font_size * 0.035),
            )
            add_stroke("emphasis_underline", underline_points, yellow, max(4, round(font_size * 0.10)), end + 1, 8)

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

    def build_raster_reveal(start: int) -> int:
        nonlocal raster_reveal_spec
        if not reference_image_asset or not raster_strokes:
            return builders.get(diagram_kind, build_process_flow)(start)

        image_w = float(raster_reveal.get("imageWidth") or raster_reveal.get("image_width") or 1)
        image_h = float(raster_reveal.get("imageHeight") or raster_reveal.get("image_height") or 1)
        image_aspect = max(0.1, image_w / max(1.0, image_h))
        region_x = diagram_left + width * 0.005
        region_y = diagram_top - height * 0.015
        region_w = width * 0.52
        region_h = height * 0.60
        region_aspect = region_w / max(1.0, region_h)
        if image_aspect >= region_aspect:
            draw_w = region_w
            draw_h = region_w / image_aspect
        else:
            draw_h = region_h
            draw_w = region_h * image_aspect
        draw_x = region_x + (region_w - draw_w) * 0.5
        draw_y = region_y + (region_h - draw_h) * 0.5

        prepared: list[dict] = []
        for raw_path in raster_strokes:
            if not isinstance(raw_path, dict):
                continue
            raw_points = raw_path.get("points")
            if not isinstance(raw_points, list) or len(raw_points) < 2:
                continue
            points: list[dict[str, float]] = []
            for raw_point in raw_points:
                if not isinstance(raw_point, dict):
                    continue
                px = raw_point.get("x")
                py = raw_point.get("y")
                if not isinstance(px, (int, float)) or not isinstance(py, (int, float)):
                    continue
                points.append(
                    _point(
                        draw_x + max(0.0, min(1.0, float(px))) * draw_w,
                        draw_y + max(0.0, min(1.0, float(py))) * draw_h,
                    )
                )
            if len(points) < 2:
                continue
            normalized_width = raw_path.get("revealWidth") or raw_path.get("reveal_width") or 0.018
            reveal_width = max(36.0, min(128.0, float(normalized_width) * max(draw_w, draw_h)))
            prepared.append(
                {
                    "points": points,
                    "revealWidth": round(reveal_width, 1),
                    "dashLength": round(_polyline_length(points), 1),
                    "weight": math.sqrt(max(1.0, _polyline_length(points))),
                }
            )

        if not prepared:
            return builders.get(diagram_kind, build_process_flow)(start)

        window_start = min(max(0, start), max(0, duration - 32))
        window_end = max(window_start + 12.0, duration - 24.0)
        total_weight = sum(item["weight"] for item in prepared) or float(len(prepared))
        cursor_float = float(window_start)
        raster_paths: list[dict] = []
        for index, item in enumerate(prepared):
            op_id = f"s{scene_index}_raster_{index}"
            span = max(0.45, (window_end - window_start) * item["weight"] / total_weight)
            end_float = window_end if index == len(prepared) - 1 else min(window_end, cursor_float + span)
            draw_ops.append(
                {
                    "id": op_id,
                    "kind": "path",
                    "startFrame": round(cursor_float, 2),
                    "endFrame": round(max(cursor_float + 0.35, end_float), 2),
                    "points": item["points"],
                }
            )
            raster_paths.append(
                {
                    "opId": op_id,
                    "d": _path_from_points(item["points"]),
                    "revealWidth": item["revealWidth"],
                    "dashLength": item["dashLength"],
                }
            )
            cursor_float = end_float

        raster_reveal_spec = {
            "asset": str(reference_image_asset),
            "x": round(draw_x, 1),
            "y": round(draw_y, 1),
            "width": round(draw_w, 1),
            "height": round(draw_h, 1),
            "strokes": raster_paths,
        }
        return min(duration - 8, int(math.ceil(window_end + 6)))

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

    def build_semiconductor_device(start: int) -> int:
        cursor = start
        corpus = _scene_corpus(scene)
        x = diagram_left + width * 0.015
        y = diagram_top + height * 0.12
        panel_w = width * 0.22
        panel_h = height * 0.30

        def draw_planar_mos(px: float, py: float, label: str, on_state: bool, start_frame: int) -> int:
            local = start_frame
            add_text(label, px, py - height * 0.065, body_size, green if on_state else red, local, 18, panel_w)
            local += 20
            substrate_y = py + panel_h * 0.58
            add_stroke("substrate", _rect_points(px, substrate_y, panel_w, panel_h * 0.18), ink, 4, local, 14, close=True)
            local += 16
            source_x = px + panel_w * 0.08
            drain_x = px + panel_w * 0.68
            add_stroke("terminal", _rect_points(source_x, py + panel_h * 0.35, panel_w * 0.20, panel_h * 0.21), blue, 4, local, 12, close=True)
            add_stroke("terminal", _rect_points(drain_x, py + panel_h * 0.35, panel_w * 0.20, panel_h * 0.21), blue, 4, local + 8, 12, close=True)
            local += 22
            oxide_y = py + panel_h * 0.28
            add_stroke("oxide", _line_points(px + panel_w * 0.32, oxide_y, px + panel_w * 0.68, oxide_y, count=8), violet, 4, local, 10)
            add_stroke("gate", _rect_points(px + panel_w * 0.38, py + panel_h * 0.12, panel_w * 0.24, panel_h * 0.12), ink, 4, local + 8, 12, close=True)
            local += 22
            add_text("S", source_x + panel_w * 0.06, py + panel_h * 0.39, max(18, body_size - 6), blue, local, 10, panel_w * 0.10)
            add_text("D", drain_x + panel_w * 0.06, py + panel_h * 0.39, max(18, body_size - 6), blue, local + 4, 10, panel_w * 0.10)
            add_text("G", px + panel_w * 0.45, py + panel_h * 0.13, max(18, body_size - 6), ink, local + 8, 10, panel_w * 0.10)
            local += 18
            channel_y = py + panel_h * 0.51
            if on_state:
                add_stroke("channel", _line_points(px + panel_w * 0.29, channel_y, px + panel_w * 0.73, channel_y, count=12), green, 7, local, 16)
                add_arrow(_line_points(px + panel_w * 0.30, channel_y + 24, px + panel_w * 0.72, channel_y + 24, count=8), red, 4, local + 15, 16, role="current")
                add_text("I_D", px + panel_w * 0.47, channel_y + 38, max(16, body_size - 10), red, local + 28, 12, panel_w * 0.20)
                local += 44
            else:
                add_stroke("no_channel", _line_points(px + panel_w * 0.34, channel_y, px + panel_w * 0.65, channel_y, count=5), red, 3, local, 8)
                add_stroke("no_channel", _line_points(px + panel_w * 0.48, channel_y - 18, px + panel_w * 0.55, channel_y + 18, count=4), red, 4, local + 8, 8)
                add_stroke("no_channel", _line_points(px + panel_w * 0.55, channel_y - 18, px + panel_w * 0.48, channel_y + 18, count=4), red, 4, local + 15, 8)
                local += 28
            return local

        if _contains_any(corpus, ["w_eff", "2h_fin", "cross-section", "cross section", "截面", "有效宽度"]):
            fin_x = x + panel_w * 0.86
            fin_y = y + panel_h * 0.18
            fin_w = width * 0.10
            fin_h = height * 0.34
            add_stroke("fin", _rect_points(fin_x, fin_y, fin_w, fin_h), green, 5, cursor, 18, close=True)
            cursor += 20
            gate_points = [
                _point(fin_x - width * 0.045, fin_y - height * 0.025),
                _point(fin_x - width * 0.045, fin_y + fin_h + height * 0.025),
                _point(fin_x + fin_w + width * 0.045, fin_y + fin_h + height * 0.025),
                _point(fin_x + fin_w + width * 0.045, fin_y - height * 0.025),
            ]
            add_stroke("gate_wrap", gate_points, violet, 6, cursor, 22)
            cursor += 26
            add_arrow(_line_points(fin_x - width * 0.10, fin_y + fin_h * 0.48, fin_x - 8, fin_y + fin_h * 0.48, count=7), blue, 3, cursor, 12)
            add_arrow(_line_points(fin_x + fin_w + width * 0.10, fin_y + fin_h * 0.52, fin_x + fin_w + 8, fin_y + fin_h * 0.52, count=7), blue, 3, cursor + 8, 12)
            add_arrow(_line_points(fin_x + fin_w * 0.5, fin_y - height * 0.10, fin_x + fin_w * 0.5, fin_y - 6, count=7), blue, 3, cursor + 16, 12)
            cursor += 34
            add_text("H_fin", fin_x - width * 0.105, fin_y + fin_h * 0.42, body_size, blue, cursor, 20, width * 0.12)
            add_text("W_fin", fin_x + fin_w * 0.10, fin_y - height * 0.085, body_size, blue, cursor + 8, 20, width * 0.13)
            add_text("W_eff = 2H_fin + W_fin", x, y + panel_h + height * 0.10, body_size, violet, cursor + 18, 36, width * 0.42)
            cursor += 60
            for offset in [0.18, 0.5, 0.82]:
                add_stroke("charge", _circle_points(fin_x + fin_w * offset, fin_y + fin_h * 0.10, 8, 8, count=10), red, 3, cursor, 6)
                cursor += 7
            return cursor

        if _contains_any(corpus, ["finfet", "fin channel", "wrap", "三面", "包住", "鳍"]):
            base_y = y + panel_h * 0.64
            fin_x = x + panel_w * 0.55
            fin_y = y + panel_h * 0.18
            add_stroke("source", _rect_points(x + panel_w * 0.05, base_y - 40, panel_w * 0.30, 80), blue, 4, cursor, 16, close=True)
            add_stroke("drain", _rect_points(x + panel_w * 1.15, base_y - 40, panel_w * 0.30, 80), blue, 4, cursor + 10, 16, close=True)
            cursor += 28
            add_stroke("fin", _rect_points(fin_x, fin_y, panel_w * 0.45, panel_h * 0.55), green, 5, cursor, 18, close=True)
            cursor += 22
            add_stroke("gate_wrap", _rect_points(fin_x - 28, fin_y + 20, panel_w * 0.56, panel_h * 0.34), violet, 6, cursor, 20, close=True)
            cursor += 26
            add_text("Source", x + panel_w * 0.06, base_y + 54, body_size, blue, cursor, 18, width * 0.12)
            add_text("Drain", x + panel_w * 1.17, base_y + 54, body_size, blue, cursor + 7, 18, width * 0.12)
            add_text("Gate wraps 3 sides", fin_x - width * 0.04, fin_y - height * 0.08, body_size, violet, cursor + 16, 28, width * 0.28)
            cursor += 50
            for side_x in [fin_x - 48, fin_x + panel_w * 0.22, fin_x + panel_w * 0.50]:
                add_arrow(_line_points(side_x, fin_y - height * 0.06, fin_x + panel_w * 0.22, fin_y + panel_h * 0.20, count=7), red, 3, cursor, 12)
                cursor += 13
            return cursor

        if _contains_any(corpus, ["short-channel", "short channel", "短沟道"]):
            left_end = draw_planar_mos(x, y, "Long channel", False, cursor)
            right_x = x + panel_w * 1.25
            cursor = max(left_end, cursor + 70)
            add_arrow(_curve_points(x + panel_w + 8, y + panel_h * 0.40, right_x - 24, y + panel_h * 0.40, count=12, wave=height * 0.03), ink, 4, cursor, 18)
            cursor += 24
            right_end = draw_planar_mos(right_x, y, "Short channel", False, cursor)
            cursor = max(cursor, right_end)
            add_arrow(_line_points(right_x + panel_w * 0.12, y + panel_h * 0.50, right_x + panel_w * 0.45, y + panel_h * 0.50, count=7), red, 4, cursor, 12)
            add_arrow(_line_points(right_x + panel_w * 0.88, y + panel_h * 0.50, right_x + panel_w * 0.55, y + panel_h * 0.50, count=7), red, 4, cursor + 8, 12)
            add_text("field intrusion", right_x + panel_w * 0.22, y + panel_h * 0.74, body_size, red, cursor + 18, 24, panel_w * 0.70)
            return cursor + 50

        if _contains_any(corpus, ["off", "on", "v_g", "vth", "v_th", "阈值"]):
            left_end = draw_planar_mos(x, y, "OFF: V_G < V_th", False, cursor)
            right_x = x + panel_w * 1.30
            cursor = max(left_end, cursor + 70)
            add_arrow(_curve_points(x + panel_w + 6, y + panel_h * 0.40, right_x - 22, y + panel_h * 0.40, count=16, wave=height * 0.035), ink, 4, cursor, 18)
            cursor += 24
            right_end = draw_planar_mos(right_x, y, "ON: V_G > V_th", True, cursor)
            return max(cursor, right_end)

        cursor = draw_planar_mos(x + panel_w * 0.35, y, fallback_label(0, "MOS structure"), True, cursor)
        add_text(fallback_label(1, "Gate controls channel"), x, y + panel_h + height * 0.09, body_size, violet, cursor, 30, width * 0.42)
        return cursor + 36

    cursor = 8
    title_size = 54 if width >= 1600 else 42
    body_size = 34 if width >= 1600 else 27
    add_text(scene.title or f"Scene {scene_index + 1}", left, top, title_size, blue, cursor, 48, emphasis=True, max_chars=24)
    cursor += 60

    builders = {
        "process_flow": build_process_flow,
        "comparison_transform": build_comparison_transform,
        "formula_derivation": build_formula_derivation,
        "optimization_curve": build_optimization_curve,
        "attention_network": build_attention_network,
        "matrix_transform": build_matrix_transform,
        "feedback_loop": build_feedback_loop,
        "semiconductor_device": build_semiconductor_device,
    }
    if raster_strokes and reference_image_asset:
        cursor = build_raster_reveal(cursor)
    elif trace_strokes:
        cursor = build_reference_trace(cursor)
    else:
        cursor = builders.get(diagram_kind, build_process_flow)(cursor)

    note_y = top + height * 0.30
    note_lines = [] if diagram_kind == "semiconductor_device" or raster_reveal_spec else core_lines[:2]
    for note_index, line in enumerate(note_lines):
        if cursor + 42 > duration - 8:
            break
        add_text(line, left + 34, note_y + note_index * (body_size + 28), body_size, ink, cursor, 30, width * 0.30, max_chars=18)
        cursor += 43

    if len(texts) < 2 and cursor + 42 <= duration - 8:
        add_text(_short_text(scene.narration, 24), left + 34, top + height * 0.38, body_size, ink, cursor, 36, width * 0.30, max_chars=18)

    _retime_draw_ops_to_audio_segments(draw_ops, audio_segments, duration)
    wash_points = _rect_points(diagram_left - 28, diagram_top + height * 0.02, width * 0.48, height * 0.48)
    return {
        "title": scene.title,
        "diagramKind": diagram_kind,
        "duration": duration,
        "audioUrl": _scene_extra(scene, "audioUrl") or _scene_extra(scene, "audio_url"),
        "audioSegments": audio_segments,
        "transitionFrames": transition_frames,
        "accent": accent,
        "washD": _path_from_points(wash_points, close=True),
        "drawOps": draw_ops,
        "texts": texts,
        "glyphPaths": [],
        "strokes": strokes,
        "referenceImageAsset": str(reference_image_asset) if reference_image_asset else None,
        "rasterReveal": raster_reveal_spec,
    }


def _build_fallback_remotion_tsx(
    storyboard: Storyboard,
    fps: int,
    width: int,
    height: int,
    subtitles_enabled: bool = False,
    background_music_url: str | None = None,
    background_music_volume: float = 0.12,
) -> tuple[str, int]:
    scene_specs = [
        _build_fallback_scene_spec(scene, index, fps, width, height)
        for index, scene in enumerate(storyboard.scenes[:6])
    ]
    for scene_spec, scene in zip(scene_specs, storyboard.scenes[:6]):
        scene_spec["subtitleText"] = _subtitle_text(scene.narration) if subtitles_enabled else None
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
const BACKGROUND_MUSIC_URL: string | null = __BACKGROUND_MUSIC_URL__;
const BACKGROUND_MUSIC_VOLUME = __BACKGROUND_MUSIC_VOLUME__;
const FONT_FAMILY = "'STXingkai', '华文行楷', KaiTi, STKaiti, 'Kaiti SC', cursive";

type Point = { x: number; y: number };
type DrawOp = { id: string; kind: "text" | "path"; startFrame: number; endFrame: number; points: Point[]; pace?: "glyph" | "ease"; beatId?: string };
type TextSpec = { opId: string; text: string; x: number; y: number; fontSize: number; color: string; maxWidth: number };
type GlyphPathSpec = { opId: string; sourceOpId: string; d: string; color: string; strokeWidth: number; dashLength: number; fontOutline: boolean };
type StrokeSpec = { opId: string; role: string; d: string; color: string; strokeWidth: number; dashLength: number };
type RasterStrokeSpec = { opId: string; d: string; revealWidth: number; dashLength: number };
type RasterRevealSpec = { asset: string; x: number; y: number; width: number; height: number; strokes: RasterStrokeSpec[] };
type AudioSegmentSpec = { id: string; startFrame: number; endFrame: number; duration: number; audioUrl?: string | null; audioDurationFrames: number; drawBudgetFrames: number; subtitleText?: string | null; drawIntent?: string | null };
type SceneSpec = {
  title: string;
  diagramKind?: string;
  duration: number;
  audioUrl?: string | null;
  audioSegments?: AudioSegmentSpec[];
  transitionFrames?: number;
  accent: string;
  washD: string;
  drawOps: DrawOp[];
  texts: TextSpec[];
  glyphPaths?: GlyphPathSpec[];
  strokes: StrokeSpec[];
  referenceImageAsset?: string | null;
  rasterReveal?: RasterRevealSpec | null;
  subtitleText?: string | null;
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

const captionWeight = (value: string) =>
  Array.from(value).reduce((sum, char) => sum + (char.charCodeAt(0) > 255 ? 2 : 1), 0);

const splitSubtitleText = (value: string): string[] => {
  const source = value.replace(/\s+/g, " ").trim();
  if (!source) return [];
  const chunks: string[] = [];
  let current = "";
  for (const char of Array.from(source)) {
    const candidate = current + char;
    const shouldBreak = current && captionWeight(candidate) > 54;
    if (shouldBreak) {
      chunks.push(current.trim());
      current = char.trimStart();
    } else {
      current = candidate;
    }
    if (/[。！？；.!?;]/.test(char) && captionWeight(current) >= 28) {
      chunks.push(current.trim());
      current = "";
    }
  }
  if (current.trim()) chunks.push(current.trim());
  return chunks.filter(Boolean);
};

const SubtitleOverlay = ({ scene }: { scene: SceneSpec }) => {
  const frame = useCurrentFrame();
  const segments = scene.audioSegments ?? [];
  const activeSegment = segments.find((segment) => frame >= segment.startFrame && frame < segment.endFrame);
  const text = (activeSegment?.subtitleText || scene.subtitleText)?.trim();
  if (!text) return null;
  const chunks = splitSubtitleText(text);
  if (chunks.length === 0) return null;
  const localFrame = activeSegment ? frame - activeSegment.startFrame : frame;
  const localDuration = activeSegment ? activeSegment.duration : scene.duration;
  const progress = clamp01(localFrame / Math.max(1, localDuration - 1));
  const index = Math.min(chunks.length - 1, Math.floor(progress * chunks.length));
  const opacity = interpolate(localFrame, [0, 8, Math.max(9, localDuration - 10), Math.max(10, localDuration - 2)], [0, 1, 1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  return (
    <div
      style={{
        position: "absolute",
        left: 0,
        right: 0,
        bottom: 42,
        display: "flex",
        justifyContent: "center",
        pointerEvents: "none",
        zIndex: 30,
        opacity,
      }}
    >
      <div
        style={{
          maxWidth: VIDEO_WIDTH * 0.78,
          padding: "0 24px",
          color: "#111318",
          fontFamily: "'Noto Sans SC', 'Microsoft YaHei', sans-serif",
          fontSize: 34,
          fontWeight: 500,
          lineHeight: 1.42,
          letterSpacing: 0,
          textAlign: "center",
          textShadow: "0 1px 0 #fff, 0 0 8px #fff, 0 0 16px #fff",
          whiteSpace: "pre-wrap",
        }}
      >
        {chunks[index]}
      </div>
    </div>
  );
};

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

const RasterMaskStroke = ({ spec, op }: { spec: RasterStrokeSpec; op: DrawOp }) => {
  const frame = useCurrentFrame();
  const progress = progressForOp(frame, op);
  const length = spec.dashLength;
  return (
    <path
      d={spec.d}
      fill="none"
      stroke="white"
      strokeWidth={spec.revealWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeDasharray={length}
      strokeDashoffset={length * (1 - progress)}
    />
  );
};

const RasterRevealImage = ({ scene, sceneIndex }: { scene: SceneSpec; sceneIndex: number }) => {
  const frame = useCurrentFrame();
  const reveal = scene.rasterReveal;
  if (!reveal || !scene.referenceImageAsset) return null;
  const maskId = `raster-reveal-mask-${sceneIndex}`;
  const referenceImageAsset = scene.referenceImageAsset;
  const coverageStart = reveal.strokes.reduce((latest, stroke) => {
    const op = scene.drawOps.find((drawOp) => drawOp.id === stroke.opId);
    return op ? Math.max(latest, op.endFrame) : latest;
  }, 0);
  const finalCoverageOpacity = interpolate(frame, [coverageStart, coverageStart + 8], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  return (
    <g>
      <defs>
        <mask id={maskId} maskUnits="userSpaceOnUse">
          <rect x="0" y="0" width={VIDEO_WIDTH} height={VIDEO_HEIGHT} fill="black" />
          {reveal.strokes.map((stroke) => {
            const op = scene.drawOps.find((drawOp) => drawOp.id === stroke.opId);
            return op ? <RasterMaskStroke key={stroke.opId} spec={stroke} op={op} /> : null;
          })}
        </mask>
      </defs>
      <image
        href={staticFile(referenceImageAsset)}
        x={reveal.x}
        y={reveal.y}
        width={reveal.width}
        height={reveal.height}
        preserveAspectRatio="none"
        mask={`url(#${maskId})`}
        opacity={1 - finalCoverageOpacity}
      />
    </g>
  );
};

const RasterFinalOverlay = ({ scene }: { scene: SceneSpec }) => {
  const frame = useCurrentFrame();
  const reveal = scene.rasterReveal;
  if (!reveal || !scene.referenceImageAsset) return null;
  const referenceImageAsset = scene.referenceImageAsset;
  const coverageStart = reveal.strokes.reduce((latest, stroke) => {
    const op = scene.drawOps.find((drawOp) => drawOp.id === stroke.opId);
    return op ? Math.max(latest, op.endFrame) : latest;
  }, 0);
  const opacity = interpolate(frame, [coverageStart, coverageStart + 8], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  return (
    <Img
      src={staticFile(referenceImageAsset)}
      style={{
        position: "absolute",
        left: reveal.x,
        top: reveal.y,
        width: reveal.width,
        height: reveal.height,
        opacity,
        pointerEvents: "none",
      }}
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

const SceneAudio = ({ scene }: { scene: SceneSpec }) => {
  const segments = scene.audioSegments ?? [];
  if (segments.length > 0) {
    return (
      <>
        {segments.map((segment) =>
          segment.audioUrl ? (
            <Sequence key={segment.id} from={segment.startFrame} durationInFrames={segment.duration} layout="none">
              <Audio src={segment.audioUrl} />
            </Sequence>
          ) : null,
        )}
      </>
    );
  }
  return scene.audioUrl ? <Audio src={scene.audioUrl} /> : null;
};

const SceneTransitionWipe = ({ scene }: { scene: SceneSpec }) => {
  const frame = useCurrentFrame();
  const transition = Math.max(0, scene.transitionFrames ?? 10);
  if (transition <= 0) return null;
  const start = Math.max(0, scene.duration - transition);
  const progress = interpolate(frame, [start, Math.max(start + 1, scene.duration - 1)], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  return (
    <div
      style={{
        position: "absolute",
        top: 0,
        bottom: 0,
        left: 0,
        width: `${progress * 100}%`,
        backgroundColor: "#FFFFFF",
        pointerEvents: "none",
        zIndex: 40,
      }}
    />
  );
};

const WhiteboardScene = ({ scene, sceneIndex }: { scene: SceneSpec; sceneIndex: number }) => {
  const frame = useCurrentFrame();
  const drawOps = scene.drawOps;
  const backgroundColor = "#FFFFFF";
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
    <AbsoluteFill style={{ backgroundColor, overflow: "hidden" }}>
      <SceneAudio scene={scene} />
      <svg style={{ position: "absolute", inset: 0, width: "100%", height: "100%" }} viewBox={`0 0 ${VIDEO_WIDTH} ${VIDEO_HEIGHT}`}>
        <RasterRevealImage scene={scene} sceneIndex={sceneIndex} />
        <AnimeDoodle scene={scene} />
        <CartoonDiagram scene={scene} />
        <GlyphText scene={scene} />
      </svg>
      <RasterFinalOverlay scene={scene} />
      <SubtitleOverlay scene={scene} />
      <HandPen tipX={pen.x} tipY={pen.y} visible={pen.visible} />
      <SceneTransitionWipe scene={scene} />
    </AbsoluteFill>
  );
};

export function GeneratedVideo() {
  let from = 0;
  return (
    <>
      {BACKGROUND_MUSIC_URL ? <Audio src={BACKGROUND_MUSIC_URL} volume={BACKGROUND_MUSIC_VOLUME} loop /> : null}
      {scenes.map((scene, index) => {
        const start = from;
        from += scene.duration;
        return (
          <Sequence key={`${scene.title}-${index}`} from={start} durationInFrames={scene.duration}>
            <WhiteboardScene scene={scene} sceneIndex={index} />
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
        .replace("__BACKGROUND_MUSIC_URL__", json.dumps(background_music_url))
        .replace("__BACKGROUND_MUSIC_VOLUME__", str(max(0.0, min(0.5, background_music_volume))))
        .strip(),
        duration,
    )


REMOTION_CODE_SYSTEM_PROMPT = """You are an expert Remotion engineer and motion designer.

Generate ONE self-contained TSX module for a complete educational whiteboard video.

Target visual reference:
- A sparse white canvas where a real visible hand holds a marker and writes/draws every visible element live.
- The hand must be on screen during drawing, with the pen tip touching the active text stroke, line, arrow, box, equation, or diagram.
- Use black marker outlines plus purposeful teaching colors: red for current/flow, blue for voltage/control arrows, green for channels/valid paths, purple for gate/structure, and yellow underlines/callouts for key ideas. Keep the canvas plain white; do not add colored background washes, paper tints, or colored panels behind diagrams.
- Text should feel handwritten: irregular but readable, large, dark/blue marker strokes, revealed character-by-character or word-by-word while the hand follows the reveal.
- For Chinese text, fontFamily must start with a handwriting-style Chinese font stack like "KaiTi, STKaiti, Kaiti SC, cursive". Do not rely on default bold sans-serif Chinese.
- Graphics should feel hand-sketched: speech bubbles, arrows, boxes, curves, icons, charts, characters, objects, and concept diagrams are revealed by strokes being drawn.
- Preserve lots of empty white space. Avoid slide-deck cards, polished UI panels, gradients, stock images, and decorative template layouts.
- Prefer one meaningful illustrated explanation per scene over dense bullet lists.
- Make the timeline feel continuous: do not leave long static holds between scenes, and stretch drawing operations so the hand keeps writing/drawing until shortly before the next scene starts.
- Emphasize key concepts like a strong teacher's board work: underline terms, circle important regions, draw colored callout boxes, and use red/blue/green arrows to distinguish current, voltage, and channel formation.
- If subtitles_enabled is true, render scene.narration as readable bottom subtitles. Subtitles are a caption overlay, not board handwriting, so the hand should not write them and they should not consume drawOps time. If subtitles_enabled is false, omit subtitle overlays entirely.
- When scenes include audioSegments, use those beat-level startFrame/endFrame windows for Audio, subtitles, and drawOps. Never play a whole-scene narration over unrelated drawing when beat audio is available.
- If background_music_url is provided, add one global low-volume looping <Audio> track using that exact URL and background_music_volume. It should sit behind all scene narration and never replace scene voiceover audio.

Hard requirements:
- Export exactly one named component, either `export const GeneratedVideo = ...` or `export function GeneratedVideo() ...`.
- Do not use default exports.
- Use only imports from "react" and "remotion".
- Do not import local files, component libraries, templates, CSS, npm packages, images, fonts, or helper modules. The asset exceptions are `staticFile("hand-real-pen.png")` for the hand and controlled job-local `staticFile(scene.referenceImageAsset)` when a storyboard scene includes rasterReveal/referenceImageAsset.
- Do not use CSS animations/transitions. All motion must use Remotion frame APIs: useCurrentFrame(), interpolate(), Easing, spring(), Sequence, AbsoluteFill.
- The TSX must explicitly use useCurrentFrame(), Sequence, and at least one of interpolate() or spring().
- Every scene must draw text and shapes over time. Define inline helper components such as HandText, DrawPath, SketchBubble, SketchArrow, or DiagramStroke inside the same TSX module.
- Board text must use glyphPaths; optional subtitles may use normal HTML text as a separate overlay because they are captions rather than handwritten board content.
- The central animation model must be a `drawOps` array. Each op must have `kind`, `startFrame`, `endFrame`, and a `points: {x:number; y:number}[]` polyline that represents the actual stroke path the marker tip follows.
- The drawOps timeline should fill each scene with drawing work and avoid dead air. The final drawOp of a scene should end near the scene duration, leaving only a short natural beat before the next Sequence.
- If a drawOp belongs to a beat, set beatId and keep its startFrame/endFrame inside that beat's audioSegment. A scene may exceed the requested target duration if real TTS and drawing need it.
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
- If a scene includes rasterReveal and referenceImageAsset, reveal the original line-art image through an SVG mask whose white paths use strokeDasharray/strokeDashoffset; drive HandPen from the same raster drawOps centerline points. Do not fade in or directly display the full reference image as the main animation. After all raster drawOps finish, crossfade the masked SVG image out while adding a short final HTML <Img> overlay of the same transparent image outside the SVG, so the last frame fully matches the reference asset without turning transparent pixels black or double-darkening strokes.
- Animated dashed paths must have `fill="none"`. Do not use background washes or colored panels; use color only on teaching strokes, arrows, underlines, callouts, and small emphasis marks.
- Text must be progressively revealed with slice(), substring(), or a frame-driven clipPath. Do not show full paragraphs instantly.
- For Chinese text, define a `glyphPaths` array and render it with inline `GlyphText` / `DrawGlyphPath` helpers using SVG `<path>` plus strokeDasharray/strokeDashoffset. The render server will preprocess these glyph paths from a local Chinese font with opentype.js, so include text specs and matching text drawOps instead of static SVG `<text>`.
- Do not use an HTML `HandText` slice-only renderer as the final text drawing path. The pen must follow glyph outline/path points that can be replaced by the renderer.
- Opacity fade may be used only as a secondary polish, never as the main animation for text or diagrams.
- Do not use SVG SMIL tags such as <animate>. Even SVG details must be driven by Remotion frame values.
- Include multiple limited instructional colors in non-raster scenes, such as red current arrows, blue voltage/control arrows, green channel paths, purple gate/structure strokes, and yellow key underlines/callouts. Do not add color washes or colored panels behind any diagram; keep image assets transparent over a plain white canvas.
- Do not use transition, animation, @keyframes, Tailwind animate-* class names, setTimeout, setInterval, requestAnimationFrame, Date.now(), or Math.random().
- Do not use fetch, eval, Function, require, filesystem APIs, browser globals, or dangerouslySetInnerHTML.
- Hardcode the provided storyboard content and audio URLs into the TSX.
- Use <Audio src="..."> from remotion for scene voiceover when audioUrl exists.
- Prefer beat-level audio: for each scene.audioSegments item with audioUrl, render <Audio> inside a <Sequence from={segment.startFrame} durationInFrames={segment.duration}>.
- Use one additional global <Audio src={background_music_url} volume={background_music_volume} loop /> only when background_music_url is not null.
- Build visuals directly in TSX using HTML/CSS/SVG: hand-drawn lines, equations, arrows, curves, labels, diagrams, highlights.
- Avoid generic slide decks. Each scene must contain a meaningful visual explanation, not just bullets.
- Use a clean Chinese whiteboard teaching style: plain white background for every scene, black ink outlines, purposeful colored teaching strokes, spacious layout, progressive reveal.
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
        "using rasterReveal/referenceImageAsset masks when the storyboard provides an original reference image to reveal, "
        "using staticFile('hand-real-pen.png'), <Img>, and getPenPosition(frame) coordinates. "
        "When scene.audioSegments exist, synchronize Audio, subtitles, and drawOps to those beat windows. "
        "If subtitles_enabled is true, show scene.narration as bottom subtitles; if false, do not show captions. "
        "If background_music_url is provided, add it as one low-volume looping background Audio track behind narration. "
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
            "subtitles_enabled": req.subtitles_enabled,
            "background_music_url": req.background_music_url,
            "background_music_volume": req.background_music_volume,
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
        tsx = _validate_generated_tsx_for_request(raw.get("tsx") or raw.get("code") or "", req)
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
                    "render scene.narration as bottom HTML subtitles only when subtitles_enabled is true, "
                    "synchronize beat-level Audio, subtitles, and drawOps to scene.audioSegments when present, "
                    "add one global low-volume looping background Audio track only when background_music_url is provided, "
                    "use STXingkai/华文行楷/KaiTi/STKaiti for Chinese handwriting, never bold sans-serif, "
                    "include limited teaching accent colors and anime/cartoon whiteboard doodles, with a plain white background, "
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
                tsx = _validate_generated_tsx_for_request(candidate_tsx, req)
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
    try:
        raw_duration_frames = int(raw.get("duration_in_frames") or 0)
    except (TypeError, ValueError):
        raw_duration_frames = 0
    duration = max(req.fps * 10, target_frames, raw_duration_frames)

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
