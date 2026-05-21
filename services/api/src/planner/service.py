import json
import logging
import math
import re
from copy import deepcopy

from src.core.golpo_styles import (
    golpo_pen_style_presets,
    golpo_video_style_aliases,
    golpo_video_style_presets,
    golpo_video_styles,
)
from src.core.visual_prompts import BOLD_EDITORIAL_IMAGE_DESCRIPTION_HINT
from src.core.llm import chat_json, check_llm_connection
from src.core.config import settings
from src.core.text_utils import localize_chinese_terms, clean_text as utils_clean_text
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
_LEGACY_VIDEO_STYLE_PRESETS: dict[str, dict[str, str]] = {
    "auto": {
        "name": "智能推荐",
        "board_mode": "",
        "hand_usage": "",
        "visual_style": "",
        "render_strategy": "",
        "planning_rule": "Choose the best Golpo-style canvas grammar per scene from the content and complexity.",
        "image_rule": "Use the most appropriate Golpo Canvas style while keeping artwork text-free for renderer-added handwriting.",
    },
    "chalkboard_bw": {
        "name": "Chalkboard Black & White",
        "board_mode": "chalkboard",
        "hand_usage": "none",
        "visual_style": "math_chalkboard",
        "render_strategy": "trace",
        "planning_rule": (
            "Classic dark chalkboard: black background, white chalk text and diagrams, very sparse composition, "
            "one top-left handwritten title, then small icon groups appear step by step. Use for explainers, tutorials, "
            "onboarding and complex concepts that benefit from high contrast simplicity."
        ),
        "image_rule": (
            "dark black chalkboard canvas, white chalk-only hand-drawn line art, rough chalk texture, no fills, "
            "no full-color objects, sparse icon groups, large empty black space, text-free artwork except tiny unreadable chalk marks."
        ),
    },
    "chalkboard_color": {
        "name": "Chalkboard Color",
        "board_mode": "chalkboard",
        "hand_usage": "none",
        "visual_style": "math_chalkboard",
        "render_strategy": "trace",
        "planning_rule": (
            "Dark chalkboard with neon chalk accents: white/cyan line art plus yellow or teal highlights for key arrows, "
            "underlines and final results. Keep the same sparse blackboard organization as Chalkboard B/W, but use color "
            "to make important concepts pop."
        ),
        "image_rule": (
            "dark black chalkboard canvas, chalk-like white and cyan outlines, limited yellow/teal highlight strokes, "
            "glowing chalk texture, sparse hand-drawn icons, large empty black space, no poster layout."
        ),
    },
    "modern_minimal": {
        "name": "Modern Minimal",
        "board_mode": "clean_canvas",
        "hand_usage": "annotate",
        "visual_style": "modern_minimal",
        "render_strategy": "hybrid",
        "planning_rule": (
            "Modern minimal: warm light grey canvas, thin black sketch lines, lots of white space, only one cool accent color "
            "such as blue or violet. Use small grouped icons and clean alignment. Best for SaaS demos, corporate training, "
            "investor updates and polished summaries."
        ),
        "image_rule": (
            "warm light grey canvas, thin clean black hand-drawn lines, one restrained blue/violet accent, lots of white space, "
            "simple aligned icon cluster, no messy doodles, no dense labels, text-free artwork."
        ),
    },
    "technical_blueprint": {
        "name": "Technical",
        "board_mode": "reference",
        "hand_usage": "annotate",
        "visual_style": "technical_reference",
        "render_strategy": "hybrid",
        "planning_rule": (
            "Technical blueprint: deep blue engineering notebook, precise pale-blue linework, structured diagrams, UI panels, "
            "screens, wires, components and tiny measurement ticks. Use for engineering walkthroughs, architecture diagrams, "
            "developer documentation, devices and systems."
        ),
        "image_rule": (
            "deep navy blueprint canvas, precise pale blue technical line art, structured overlapping panels, subtle grid or drafting feel, "
            "small cyan/red semantic accents only, accurate parts, no playful cartoons, text-free artwork."
        ),
    },
    "editorial": {
        "name": "Editorial",
        "board_mode": "clean_canvas",
        "hand_usage": "annotate",
        "visual_style": "editorial",
        "render_strategy": "hybrid",
        "planning_rule": (
            "Editorial explainer: polished off-white canvas, bold black ink, refined accent underlines, magazine-like object collage, "
            "paper sheets, product cards, media icons and tasteful red/orange accents. Use for client/investor stories, "
            "thought leadership, product narratives and professional marketing."
        ),
        "image_rule": (
            "polished editorial hand-drawn collage on warm off-white canvas, bold clean black ink, restrained red/orange accents, "
            "stacked paper cards and media objects, clear hierarchy, premium presentation, text-free artwork."
        ),
    },
    "whiteboard": {
        "name": "Whiteboard",
        "board_mode": "clean_canvas",
        "hand_usage": "annotate",
        "visual_style": "marketing_doodle",
        "render_strategy": "hybrid",
        "planning_rule": (
            "Whiteboard explainer: light off-white board, hand-drawn black outlines, blue/green/yellow accents, visible sketch energy, "
            "diagram plus short labels, often with a real hand or marker annotations. Use for education, how-to videos, recipes, "
            "processes and any topic that needs clear friendly visuals."
        ),
        "image_rule": (
            "off-white whiteboard canvas, friendly hand-drawn black marker outlines, blue/green/yellow teaching accents, "
            "large clear illustrated objects, generous margins for marker callouts, text-free artwork."
        ),
    },
    "playful": {
        "name": "Playful",
        "board_mode": "clean_canvas",
        "hand_usage": "annotate",
        "visual_style": "playful",
        "render_strategy": "hybrid",
        "planning_rule": (
            "Playful: creamy warm background, colorful crayon-like lettering and icons, smiley marks, music notes, bouncing shapes, "
            "soft pastel palette and lighthearted composition. Use for students, social posts, community updates and approachable topics."
        ),
        "image_rule": (
            "warm cream canvas, playful crayon-like hand-drawn objects, pastel red yellow teal purple accents, expressive simple icons, "
            "rounded friendly shapes, cheerful energy, text-free artwork."
        ),
    },
    "sharpie": {
        "name": "Sharpie",
        "board_mode": "clean_canvas",
        "hand_usage": "trace",
        "visual_style": "sharpie",
        "render_strategy": "trace",
        "planning_rule": (
            "Sharpie: bright white canvas, thick black marker strokes, bold uppercase handwritten titles, raw quick-drawn feel, "
            "occasional blue/yellow/red highlighter accents and a visible hand drawing. Use for founder updates, quick explainers, "
            "behind-the-scenes and content where real and direct beats polished."
        ),
        "image_rule": (
            "bright white canvas, thick black Sharpie marker outlines, bold rough hand-drawn icons, sparse strong composition, "
            "small blue/yellow/red highlighter accents, raw human sketch feel, text-free artwork."
        ),
    },
    # Backward-compatible aliases from the first ExplainFlow style pass.
    "colorful_story": {
        "alias_for": "whiteboard",
        "name": "Whiteboard",
        "board_mode": "clean_canvas",
        "hand_usage": "annotate",
        "visual_style": "marketing_doodle",
        "render_strategy": "hybrid",
        "planning_rule": "Alias for Whiteboard.",
        "image_rule": "Alias for Whiteboard.",
    },
    "teacher_whiteboard": {
        "alias_for": "whiteboard",
        "name": "Whiteboard",
        "board_mode": "clean_canvas",
        "hand_usage": "annotate",
        "visual_style": "marketing_doodle",
        "render_strategy": "hybrid",
        "planning_rule": "Alias for Whiteboard.",
        "image_rule": "Alias for Whiteboard.",
    },
    "math_chalkboard": {
        "alias_for": "chalkboard_color",
        "name": "Chalkboard Color",
        "board_mode": "chalkboard",
        "hand_usage": "none",
        "visual_style": "math_chalkboard",
        "render_strategy": "trace",
        "planning_rule": "Alias for Chalkboard Color.",
        "image_rule": "Alias for Chalkboard Color.",
    },
    "technical_reference": {
        "alias_for": "technical_blueprint",
        "name": "Technical",
        "board_mode": "reference",
        "hand_usage": "annotate",
        "visual_style": "technical_reference",
        "render_strategy": "hybrid",
        "planning_rule": "Alias for Technical.",
        "image_rule": "Alias for Technical.",
    },
    "howto_demo": {
        "alias_for": "whiteboard",
        "name": "Whiteboard",
        "board_mode": "clean_canvas",
        "hand_usage": "annotate",
        "visual_style": "marketing_doodle",
        "render_strategy": "hybrid",
        "planning_rule": "Alias for Whiteboard.",
        "image_rule": "Alias for Whiteboard.",
    },
}
_LEGACY_VIDEO_STYLE_ALIASES: dict[str, str] = {
    "colorful_story": "whiteboard",
    "teacher_whiteboard": "whiteboard",
    "howto_demo": "whiteboard",
    "math_chalkboard": "chalkboard_color",
    "technical_reference": "technical_blueprint",
    "whiteboard_bw": "whiteboard",
    "whiteboard_color": "whiteboard",
    "sharpie_bw": "sharpie",
    "sharpie_color": "sharpie",
    "editorial_blue": "editorial",
    "editorial_paper": "editorial",
    "chalkboard_black_white": "chalkboard_bw",
    "technical": "technical_blueprint",
}
_LEGACY_GOLPO_CANVAS_VIDEO_STYLES = {
    "chalkboard_bw",
    "chalkboard_color",
    "modern_minimal",
    "technical_blueprint",
    "editorial",
    "whiteboard",
    "playful",
    "sharpie",
}
_LEGACY_PEN_STYLE_PRESETS: dict[str, dict[str, str]] = {
    "no_hand": {
        "name": "No Hand",
        "rule": "Do not show a hand. Reveal content through chalk/line drawing animation or direct staged appearances.",
    },
    "pen": {
        "name": "Pen Style",
        "rule": "Use a fine-tipped pen-in-hand feeling: precise elegant thin lines, small details and professional sketch movement.",
    },
    "fountain_pen": {
        "name": "Stylus Style",
        "rule": "Use a modern digital stylus/tablet feeling: smooth controlled strokes, tech-forward clean motion.",
    },
    "marker": {
        "name": "Marker Style",
        "rule": "Use a bold marker-in-hand feeling: thick confident strokes, whiteboard-session energy and strong callouts.",
    },
}
VIDEO_STYLE_PRESETS: dict[str, dict[str, str]] = golpo_video_style_presets()
VIDEO_STYLE_ALIASES: dict[str, str] = golpo_video_style_aliases()
GOLPO_CANVAS_VIDEO_STYLES = golpo_video_styles()
ALLOWED_VIDEO_STYLES = set(VIDEO_STYLE_PRESETS) | set(VIDEO_STYLE_ALIASES)
PEN_STYLE_PRESETS: dict[str, dict[str, str]] = golpo_pen_style_presets()
ALLOWED_PEN_STYLES = set(PEN_STYLE_PRESETS)
COOKING_TOPIC_TERMS = (
    "cook",
    "cooking",
    "recipe",
    "food",
    "dish",
    "wok",
    "skillet",
    "stir-fry",
    "stir fry",
    "sauce",
    "tofu",
    "mapo",
    "麻婆",
    "豆腐",
    "烹饪",
    "做法",
    "食材",
    "炒",
    "煸",
    "爆香",
    "锅",
    "菜",
    "勾芡",
    "出锅",
    "装盘",
)
COOKING_BLANCH_TERMS = ("blanch", "boiling water", "boil water", "parboil", "焯水", "汆", "煮水", "开水")
COOKING_PREP_TERMS = ("prep", "prepare", "ingredient", "mise en place", "食材", "准备", "切", "备料")
COOKING_FINAL_TERMS = ("finish", "serve", "plate", "plating", "finished", "出锅", "装盘", "成品")
COOKING_OVERVIEW_TERMS = ("overview", "map", "流程图", "步骤流程", "风味地图", "概览", "总览")
COOKING_DENSE_LAYOUT_TERMS = (
    "流程图",
    "步骤流程",
    "五个",
    "一排",
    "多格",
    "小框",
    "小锅",
    "tiny pots",
    "mini process",
    "process boxes",
    "five horizontal",
    "row of",
    "flowchart",
)
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


def _has_teaching_accent(code: str) -> bool:
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
    # Count path/stroke operations for diagrams - each scene needs 3-5 diagram elements
    path_ops = re.findall(r"\b['\"]?kind['\"]?\s*:\s*['\"](?:path|stroke|shape|arrow|box|circle|line)['\"]", code, flags=re.IGNORECASE)
    if len(path_ops) < 8:
        raise ValueError(
            f"drawOps must include at least 8 path/stroke operations for diagrams (found {len(path_ops)}). "
            "Each scene needs 3-5 distinct diagram elements like arrows, boxes, shapes, or connectors."
        )

    # Count text operations - each scene needs 2-4 text labels
    text_ops = re.findall(r"\b['\"]?kind['\"]?\s*:\s*['\"]text['\"]", code, flags=re.IGNORECASE)
    if len(text_ops) < 5:
        raise ValueError(
            f"drawOps must include at least 5 text operations (found {len(text_ops)}). "
            "Each scene needs title, labels, and conclusion text."
        )

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


def _validate_handwritten_whiteboard_style(code: str) -> None:
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
    if not re.search(r"\b(Diagram|Doodle|Callout|Sketch|Whiteboard)\b", code, flags=re.IGNORECASE):
        raise ValueError(
            "Generated Remotion code must include whiteboard diagram/callout helpers, "
            "not only captions or slide labels"
        )


def _validate_no_paper_surface(code: str) -> None:
    # Strictly forbidden patterns that create paper-like effects
    forbidden = {
        "washD": "paper-like wash layers are not allowed behind drawings",
        "boxShadow": "shadowed paper/card surfaces are not allowed",
        "drop-shadow": "drop-shadow effects create a paper-like backing",
        "textShadow": "text shadows create a grey backing behind handwriting",
    }
    lowered = code.lower()
    for token, reason in forbidden.items():
        if token.lower() in lowered:
            raise ValueError(
                f"Generated Remotion code contains forbidden paper-surface styling: {token} ({reason})"
            )

    # Only reject CSS property assignments that create paper/card/panel effects
    # Allow variable names, comments, and descriptive terms
    paper_surface_props = [
        r"\bpaper\s*:\s*[^;]+",
        r"\bcard\s*:\s*[^;]+",
        r"\bpanel\s*:\s*[^;]+",
        r"\bsurface\s*:\s*[^;]+",
        r"\bsheet\s*:\s*[^;]+",
        r"\bposter\s*:\s*[^;]+",
        r"\bslide\s*:\s*[^;]+",
        r"\bboardShadow\s*:\s*[^;]+",
        r"\bshadow\s*:\s*[^;]+",
        r"\bwash\s*:\s*[^;]+",
    ]
    for pattern in paper_surface_props:
        if re.search(pattern, lowered):
            raise ValueError(
                "Generated Remotion code must not define paper/card/panel/surface/shadow/wash helpers or variables"
            )

    if re.search(r"\bfilter\s*:\s*['\"][^'\"]+['\"]", code, flags=re.IGNORECASE):
        raise ValueError("Generated Remotion code must not use CSS filter effects")

    if re.search(r"\brasterReveal\s*:\s*\{|\breferenceImageAsset\s*:\s*['\"]generated/", code, flags=re.IGNORECASE):
        raise ValueError("Generated Remotion code must not bake rasterReveal/referenceImageAsset into normal generated whiteboard scenes")

    # Check for light/white background with border/shadow styling (paper-like effect)
    light_surface_pattern = (
        r"background(?:Color)?\s*:\s*['\"]"
        r"(?:#fff(?:fff)?|white|#f7f7f2|#f8f8f0|#fafafa|#f5f5f5|rgb\(\s*255\s*,\s*255\s*,\s*255\s*\))"
        r"['\"][\s\S]{0,220}\b(?:borderRadius|boxShadow|position\s*:\s*['\"]absolute['\"])"
    )
    if re.search(light_surface_pattern, code, flags=re.IGNORECASE):
        raise ValueError("Generated Remotion code must not create an inner white/light rectangle behind drawings or text")

    if re.search(r"\b(?:linear-gradient|radial-gradient)\s*\(", code, flags=re.IGNORECASE):
        raise ValueError("Generated Remotion code must not use gradient washes or panel backgrounds")


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
    _validate_handwritten_whiteboard_style(code)
    _validate_no_paper_surface(code)
    if not re.search(r"\b(KaiTi|STKaiti|Kaiti|楷体)\b", code, flags=re.IGNORECASE):
        raise ValueError("Generated Remotion code must use a Chinese handwriting-style font family such as KaiTi/STKaiti")
    if not _has_teaching_accent(code):
        raise ValueError("Generated Remotion code must include purposeful teaching accent colors, not only black and white")
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
- 必须是 text-free artwork，不要要求图像模型生成可读标题、段落、标签、按钮或水印；可读文字由渲染端叠加
- 聚焦该场景的核心视觉概念，例如：
  "a simple diagram showing a neural network with input, hidden, and output layers connected by arrows"
  "a whiteboard sketch of gradient descent showing a ball rolling down a curved loss surface"
  "an unlabeled anatomy-style diagram of a transformer attention mechanism with three clean box groups and blank callout space"

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
      "image_description": "English text-free description of the whiteboard sketch illustration for this scene",
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
2. 每个 visual_beat 都必须用 draw_intent 说明画面正在呈现什么，用 narration 说明知识本身；旁白不能先讲完、图还没画完。
3. 每个关键点按“现象 -> 原因 -> 结果 -> 类比/总结”展开，避免只写定义和 bullet list。
4. 旁白要像一个脑子很清楚、稍微有点幽默感的老师在现场讲：多用具体比喻、轻微反差和口语节奏，例如“别急着开干”“这一步像先摊开地图”“不然很容易原地忙成一团”。幽默只能帮助理解，不能变成段子、网络烂梗或抢戏。
5. 每个 scene 至少有一句把抽象关系落到生活化类比或具体动作上；每个 visual_beat 的 narration 优先 1-2 个完整短句，不写论文腔。
6. 优先用状态对比图、过程模拟图、结构图、截面图、箭头和局部放大；少用纯文字列表。
7. image_description 必须是英文，像给图像生成模型的具体画面说明：布局、主体、箭头、局部放大和留白都要写清楚，但不要让图像模型生成可读标签。
8. 用优秀老师板书的方式强调重点：关键术语下划线、圈出局部、彩色箭头、局部放大框、对比标记和结论框。
9. 使用有限教学色彩：red=current/flow, blue=voltage/control, green=channel/valid path, purple=gate/structure, yellow=emphasis underline/callout。
10. 内容 prompt 与视觉风格分离：这里规划内容和画面，不写模板库、组件库或代码。
11. 旁白禁止描述绘图动作或镜头调度：不要说“先画/再画/最后画/这里画/左边画/右边画/画出来/标出/写上/看图中/这一步”。draw_intent 可以写绘图动作，但 narration 只讲概念、因果、变化和结论。
12. 总时长是建议值；如果内容和绘图需要更久，优先保证讲画完整，不要为了卡时长裁掉 beat。
13. 每个 scene 必须给出抽象绘制策略字段 `render_strategy`、`visual_complexity`、`board_mode`、`hand_usage`、`visual_style`：
    - `trace`：结构简单、元素少、能像老师板书一样分步骤画完的图，例如流程图、状态对比图、公式推导、曲线、单个结构示意图。
    - `direct`：图像特别复杂、标签很多、细节密集、实物/参考图/成品图/三维或多层结构，直接呈现主体，再用手写箭头、圈、下划线讲重点。
    - `hybrid`：主体复杂但局部需要教学强调，先直接呈现主体，再按 visual_beats 手写局部 callout。
    - 不要按具体学科名词判断，而按“能否被观众舒服地看见手逐笔画完”判断。简单图逐笔，复杂图呈现加讲解标注。
    - `board_mode=whiteboard`：浅灰白板课堂，适合机制图、流程、结构、对比。
    - `board_mode=chalkboard`：深色黑板推导，适合数学解题、公式证明、符号推演；通常 `hand_usage=none`。
    - `board_mode=clean_canvas`：干净浅色画布，适合营销、产品、概念介绍；主体彩色 doodle 可直接出现。
    - `board_mode=reference`：复杂参考图、三维/医学/机械/电路主体；主体直接/混合呈现，手只做局部标注。
    - `hand_usage=trace` 表示手逐笔写画；`annotate` 表示主体已出现，手只标注重点；`none` 表示无手，内容按步骤显现。
    - `video_style=auto|chalkboard_bw|chalkboard_color|modern_minimal|technical_blueprint|editorial|whiteboard|playful|sharpie`，表示 Golpo Canvas 视觉风格；用户已选择风格时，每个 scene 默认继承该值。
    - `visual_style=teacher_whiteboard|marketing_doodle|math_chalkboard|technical_reference|modern_minimal|editorial|playful|sharpie`，表示渲染策略的内部视觉语法，可与 video_style 一起使用。
    - `pen_style=no_hand|pen|marker|fountain_pen`，表示独立的 Pen-in-hand 动画层；黑板场景通常为 no_hand。

通用视觉语法规则：
- 不按具体题材标签选画法，而按“这一场要讲清的关系”选 `diagram_plan.kind`。
- `overview_map`：先建立全局地图，适合一个主题下有多个对象、单元或阶段。
- `comparison`：讲前后、开关、好坏、旧新、A/B、状态变化时，用双栏或上下对比。
- `process`：讲因果链、机制、流程、变化过程时，用原因 -> 过程 -> 结果箭头。
- `structure`：讲组成、层级、部件、整体和局部时，用主体图 + 贴近标签 + 局部放大。
- `interaction`：讲两个或多个对象互相影响、协作、信息交换、反馈关系时，用角色/节点 + 双向箭头 + 共同结果。
- `tradeoff_matrix`：讲优先级、取舍、二维判断、分类象限时，用坐标/四象限或 2x2 矩阵。
- `goal_path`：讲目标、路线、倒推、成长路径、阶段推进时，用起点 -> 里程碑 -> 终点路径。
- `cycle`：讲迭代、复盘、反馈、更新、闭环时，用环形箭头和 3-5 个节点。
- `formula`：讲公式含义时，用公式 + 变量 callout + 小示意图，不只写符号。
- `reference_callout`：图很复杂或必须保真时，主体直接呈现，再用 2-4 个局部标注讲重点。
- `summary`：收束时用少量清单、闭环或框架图，不把正文段落塞到画面上。

参考白板样片的通用板书规则：
- 默认采用 bold editorial hand-drawn explainer 风格：米白纸感/白板面、粗黑蜡笔/马克笔轮廓、珊瑚粉箭头/勾选/爆炸星/下划线、暖黄色大色块或光晕、大人物/大物体/大食物做主视觉。
- 图形由文生图模型生成时，image_description 必须要求 text-free artwork：不要让图像模型生成标题、段落、中文/英文标签、按钮或水印；所有可读文字和动态标注由渲染端手写叠加。
- 图文并茂不是信息图堆字：一场只保留一个大图形或最多三个大步骤，文字只做短标题、短标签和少量结论。
- 一屏只讲一个核心想法；不要把完整报告页、海报页或密集信息图塞进一场。
- 标题使用短蓝色手写字，位于顶部左侧或顶部居中，可加一条手绘下划线。
- 主体图放在画面中部或略偏右，占画面宽度约 45%-65%；四周留出大面积空白给手和后续标注。
- 标签必须短、近、清楚：优先 1-4 个词贴近结构，不写长段落，不做大段 bullet list。
- 每个 visual_beat 只新增一个小板书动作组：一个结构块、一个箭头、一个圈选、一个结论短语或一个对比面板。
- 色彩克制且有含义：黑色主体线，蓝色标题/控制箭头，红色风险/电流/错误，绿色有效路径/正确结果，黄色只做短下划线/局部强调。
- 复杂主体不要强行拆成几百笔；直接呈现清晰主体，再用 2-4 个老师式 callout 解释。简单主体才逐笔 trace。
- 场景之间像连续板书推进：上一场讲画完整后立刻进入下一场，不留空白停顿。
- image_description 必须要求 bold editorial hand-drawn explainer illustration: thick imperfect black marker/crayon outlines, warm off-white surface, hot pink accent arrows/checks/starbursts, sunny yellow highlight blobs, one large visual anchor or at most three big step groups, generous white space, text-free artwork, no poster/card/legend/panel/background wash.

烹饪/食物教程的额外规则：
- image_description 必须把食材、器具、颜色和状态写具体，不能只写 generic food / pot / ingredients。
- 炒、煸、爆香、烧煮、勾芡等中餐锅气步骤，默认画宽口黑色炒锅或平底炒锅；只有明确“焯水/煮水”时才画小锅或汤锅。
- 菜品颜色必须符合真实成品：红油/酱汁、白色豆腐块、褐色肉末、绿色葱蒜苗、蒸汽和高光都要可见；禁止无色、灰白、空锅或蓝色汤锅替代炒锅。
- 每个烹饪场景只保留 1-3 个大号短标签，标在图旁或食材附近，避免把长菜谱步骤塞进画面。
- 画面必须“一场一个大食物/锅具状态”：食材准备、炒香底料、烧豆腐、勾芡、成品各自用一个大主体讲清楚；不要把 5-6 个小锅、小框、小步骤排成密集流程图。
- 步骤概览最多 3 个大节点，并且要用大图标或大锅具状态，不用小字流程盒；真正的菜谱细节交给旁白和分场景展开。

参考营销白板/彩色 doodle 样片的通用规则：
- 不是所有图形都要由手逐笔画完；彩色成品 doodle、图标组、产品界面、复杂插图可以直接出现并保持清晰。
- 手部只负责少量老师动作：写标题、画勾选、下划线、短箭头、圈重点、指向主体。
- 用大对象组和宽松空白制造节奏，不要把一页做成密集广告海报。

参考数学黑板样片的通用规则：
- 数学推导/解题可使用 `board_mode=chalkboard`、`hand_usage=none`，不显示手。
- 黑板背景为接近黑色，公式像粉笔/荧光笔按行、按小步骤出现，保留前文上下文。
- 颜色有语义：白色主式，cyan/green 表示变量或向量，yellow 表示结论，pink/red 表示目标或关键条件。
- 每一屏只推进一个推导动作，不要一次性出现整页答案。

梯度下降专项要求（只在用户原始主题、graph.topic 或 enhanced brief 明确包含梯度下降/gradient descent 时启用；其他主题严禁引入这些内容）：
- 必须包含损失曲线、当前位置、梯度方向、负梯度更新、学习率步长、迭代收敛。

输出 JSON：
{
  "scenes": [
    {
      "id": "scene_0",
      "order": 0,
      "title": "短标题",
      "learning_goal": "这一场要让观众理解什么",
      "render_strategy": "trace|direct|hybrid",
      "visual_complexity": "simple|medium|dense|reference",
      "board_mode": "whiteboard|chalkboard|clean_canvas|reference",
      "hand_usage": "trace|annotate|none",
      "video_style": "auto|chalkboard_bw|chalkboard_color|modern_minimal|technical_blueprint|editorial|whiteboard|playful|sharpie",
      "visual_style": "teacher_whiteboard|marketing_doodle|math_chalkboard|technical_reference|modern_minimal|editorial|playful|sharpie",
      "pen_style": "no_hand|pen|marker|fountain_pen",
      "diagram_plan": {
        "kind": "overview_map|comparison|process|structure|interaction|tradeoff_matrix|goal_path|cycle|cross_section|formula|simulation|reference_callout|summary",
        "layout": "具体画面布局",
        "required_labels": ["必须写在图里的标签"]
      },
      "visual_beats": [
        {
          "id": "beat_0",
          "draw_intent": "正在画什么，包含图形、箭头、标签、变化",
          "narration": "同步讲解的知识内容，只讲概念和因果，不说正在画什么；口语、生动、可带轻微幽默或类比",
          "required_labels": ["本 beat 图上要出现的标签"],
          "duration_estimate": 6
        }
      ],
      "narration": "完整中文旁白，由 visual_beats 串起来，口语化但技术准确",
      "duration_estimate": 28,
      "node_ids": ["node_0"],
      "image_description": "English text-free image prompt with exact subject, layout, blank callout spaces, arrows, object states and process changes; no readable labels or words",
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


def _localize_chinese_terms(text: str) -> str:
    """Localize Chinese terms (delegates to shared module)."""
    return localize_chinese_terms(text)


def _clean_text(value: object) -> str:
    """Clean and localize text."""
    text = "" if value is None else str(value)
    return localize_chinese_terms(re.sub(r"\s+", " ", text).strip())


def _normalize_image_description_text(value: object) -> str:
    text = _clean_text(value)
    if not text:
        return ""
    replacements = [
        (r"\b(left|right|top|bottom|center)\s+panel\s+labeled\s+[^,.;。]+", r"\1 panel with a blank label space"),
        (r"\blabeled\s+", ""),
        (r"\blabel(?:s|ed)?\s+[^.;。]*", "blank callout spaces"),
        (r"\bwith\s+(?:exact\s+)?labels?\s+(?:for|showing|on|such as|including)\b", "with blank callout spaces for"),
        (r"\blabels?\s*[:：][^.;。]*", "blank callout spaces"),
        (r"\blabeled\b", "unlabeled"),
        (r"\bshort\s+(?:nearby\s+|handwritten\s+|blue\s+)?labels?\b", "blank nearby callout spaces"),
        (r"\breadable\s+(?:title|text|label|labels|words?)\b", "blank callout space"),
        (r"\bshort\s+(?:blue\s+)?handwritten\s+title\b", "blank title area"),
        (r"\btopic heading\b", "blank heading area"),
        (r"\bcaption(?:s)?\b", "blank callout area"),
        (r"\bformula\s+[^,.;。]+", "formula-shaped blank math area"),
        (r"\b(?:tokens?|speech marks)\s+saying\s+[^,.;。]+", "blank speech marks"),
    ]
    for pattern, replacement in replacements:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    if "text-free" not in text.lower():
        text = f"{text}. text-free artwork; no readable words, no letters, no labels, no title, no watermark"
    elif "no readable" not in text.lower():
        text = f"{text}; no readable words, letters, labels, title, or watermark"
    return re.sub(r"\s+", " ", text).strip(" .") + "."


def _style_image_rule_in_description(scene: Scene, video_style: str) -> bool:
    text = (scene.image_description or "").lower()
    if not text:
        return False
    style = _canonical_video_style(video_style)
    checks = {
        "chalkboard_bw": ["pure black chalkboard", "white chalk-only"],
        "chalkboard_color": ["black chalkboard", "cyan", "yellow"],
        "modern_minimal": ["warm light grey", "one restrained blue"],
        "technical_blueprint": ["deep navy", "pale blue"],
        "editorial": ["warm off-white", "red or orange"],
        "whiteboard": ["off-white whiteboard", "blue handwritten-style"],
        "playful": ["warm cream", "crayon"],
        "sharpie": ["bright white", "sharpie"],
    }
    return all(fragment in text for fragment in checks.get(style, []))


def _normalize_video_style(value: str | None) -> str:
    style = _clean_text(value).lower()
    style = VIDEO_STYLE_ALIASES.get(style, style)
    return style if style in VIDEO_STYLE_PRESETS else "whiteboard"


def _video_style_preset(value: str | None) -> dict[str, str]:
    preset = VIDEO_STYLE_PRESETS[_normalize_video_style(value)]
    alias = preset.get("alias_for")
    return VIDEO_STYLE_PRESETS[alias] if alias else preset


def _canonical_video_style(value: str | None) -> str:
    style = _normalize_video_style(value)
    preset = VIDEO_STYLE_PRESETS[style]
    return preset.get("alias_for") or style


def _normalize_pen_style(value: str | None) -> str:
    style = _clean_text(value).lower()
    return style if style in ALLOWED_PEN_STYLES else "marker"


def _pen_style_preset(value: str | None) -> dict[str, str]:
    return PEN_STYLE_PRESETS[_normalize_pen_style(value)]


def _clean_narration_text(value: object) -> str:
    text = _clean_text(value)
    if not text:
        return ""
    replacements = [
        (r"^\s*(?:首先|先|接着|然后|再|最后|这里|现在|我们|把|请)?\s*(?:先|再)?\s*(?:画|绘制|写|写上|标出|标注|圈出|框出|显示|展示|呈现|看|看到)\s*(?:左边|右边|上方|下方|中间|图中|画面中|这个图|这张图)?\s*(?:的|出|上)?\s*", ""),
        (r"(?:先|再|然后|接着|最后)\s*(?:画|绘制|写|写上|标出|标注|圈出|框出|显示|展示|呈现)\s*", ""),
        (r"(?:左边|右边|上方|下方|中间|旁边|图中|画面中)\s*(?:画|绘制|写|写上|标出|标注|可以看到|看到)\s*", ""),
        (r"(?:这一步|这个 beat|此时)\s*(?:同步)?\s*(?:说|讲|说明|解释)\s*", ""),
        (r"(?:我们|这里|现在)\s*(?:来|可以)?\s*(?:画|绘制|写|写上|标出|标注|看)\s*", ""),
    ]
    for pattern, replacement in replacements:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text).strip(" ：:，,。 ")
    if text and text[-1] not in "。！？.!?":
        text += "。"
    return text


def _trim_text_to_chars(text: str, max_chars: int) -> str:
    text = _clean_narration_text(text)
    if max_chars <= 0 or len(text) <= max_chars:
        return text
    sentences = [part for part in re.split(r"(?<=[。！？.!?])", text) if part.strip()]
    kept = ""
    for sentence in sentences:
        if len(kept) + len(sentence) <= max_chars:
            kept += sentence
        elif not kept and max_chars >= 28:
            candidate = sentence[:max_chars]
            pieces = re.split(r"([，,；;：:、])", candidate)
            if len(pieces) >= 3:
                candidate = "".join(pieces[:-2])
            kept = candidate.rstrip("，,；;：:、 ") + "。"
            break
        else:
            break
    if not kept:
        first_sentence = sentences[0].strip() if sentences else text
        if len(first_sentence) <= max(max_chars * 2, 96):
            kept = first_sentence
        else:
            kept = text[:max_chars].rstrip("，,；;：:、 ") + "。"
    if kept[-1] not in "。！？.!?":
        kept = kept.rstrip("，,；;：:、 ") + "。"
    return kept


def _subtitle_text(value: object) -> str | None:
    text = _clean_narration_text(value)
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


def _looks_like_mojibake(value: object) -> bool:
    text = _clean_text(value)
    if not text:
        return False
    suspicious = len(re.findall(r"[锟�\ue000-\uf8ff]", text))
    cjk = len(re.findall(r"[\u3400-\u9fff]", text))
    if suspicious >= 2:
        return True
    if "?" in text and cjk == 0 and len(text) <= 6:
        return True
    return False


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
            narration = _clean_narration_text(item.get("narration") or item.get("voiceover") or item.get("script"))
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
                    narration=_clean_narration_text(text),
                    required_labels=[],
                    duration_estimate=6.0,
                )
            )
    return beats


def _narration_from_beats(narration: str, beats: list[VisualBeat]) -> str:
    beat_text = " ".join(beat.narration for beat in beats if beat.narration).strip()
    narration = _clean_narration_text(narration)
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
        return _clean_narration_text(f"{narration} {' '.join(missing[:3])}")
    return narration


def _compress_storyboard_narration_to_target(storyboard: Storyboard, target_duration: int) -> Storyboard:
    if not storyboard.scenes:
        return storyboard
    scene_count = max(1, len(storyboard.scenes))
    target = max(45.0, float(target_duration))
    speech_budget = max(30.0, target * 0.62)
    per_scene_budget = speech_budget / scene_count
    for scene in storyboard.scenes:
        beats = scene.visual_beats or []
        beat_count = max(1, len(beats))
        per_beat_seconds = max(4.0, min(9.0, per_scene_budget / beat_count))
        max_chars = max(18, int(per_beat_seconds * 3.0))
        for beat in beats:
            beat.narration = _trim_text_to_chars(beat.narration, max_chars)
            beat.duration_estimate = round(max(4.0, min(10.0, per_beat_seconds + 1.0)), 1)
        scene.narration = _narration_from_beats(scene.narration, beats)
        scene.duration_estimate = _estimate_scene_duration(min(scene.duration_estimate, per_scene_budget + 4.0), scene.narration, beats, scene.animations)
    storyboard.total_duration_estimate = round(sum(scene.duration_estimate for scene in storyboard.scenes), 1)
    return storyboard


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


def _scene_floor_duration(scene: Scene, target_scene_seconds: float | None = None) -> float:
    beat_floor = sum(max(2.4, beat.duration_estimate * 0.75) for beat in scene.visual_beats)
    animation_floor = sum(max(1.0, animation.duration * 0.8) for animation in scene.animations)
    narration_floor = _estimate_narration_seconds(scene.narration) + 2.0
    required = max(10.0, narration_floor, beat_floor + 1.0, animation_floor + 1.0)
    cap = 32.0 if target_scene_seconds is None else max(12.0, target_scene_seconds * 1.18)
    if _is_cooking_topic_text(_scene_corpus(scene)):
        cap = min(cap, 24.0 if target_scene_seconds is None else max(14.0, target_scene_seconds * 1.05))
    return round(min(cap, required), 1)


def _fit_storyboard_to_target(storyboard: Storyboard, target_duration: int) -> Storyboard:
    """Use the UI duration as a pacing hint: stretch short lessons, never trim required content."""
    target = float(max(30, min(300, target_duration)))
    if not storyboard.scenes:
        storyboard.total_duration_estimate = target
        return storyboard

    target_scene_seconds = target / max(1, len(storyboard.scenes))
    floors = [_scene_floor_duration(scene, target_scene_seconds) for scene in storyboard.scenes]
    for scene, floor in zip(storyboard.scenes, floors):
        scene.duration_estimate = round(max(0.1, scene.duration_estimate, floor), 1)

    current = sum(max(0.1, scene.duration_estimate) for scene in storyboard.scenes)
    floor_total = sum(floors)
    if current >= target:
        if floor_total >= target:
            for scene, floor in zip(storyboard.scenes, floors):
                old_duration = max(0.1, scene.duration_estimate)
                ratio = floor / old_duration
                scene.duration_estimate = round(floor, 1)
                for beat in scene.visual_beats:
                    beat.duration_estimate = round(max(1.0, beat.duration_estimate * ratio), 1)
                for animation in scene.animations:
                    animation.duration = round(min(15.0, max(0.5, animation.duration * ratio)), 1)
            storyboard.total_duration_estimate = round(sum(scene.duration_estimate for scene in storyboard.scenes), 1)
            return storyboard
        compressible = max(0.1, current - floor_total)
        ratio = max(0.0, min(1.0, (target - floor_total) / compressible))
        for scene, floor in zip(storyboard.scenes, floors):
            old_duration = max(0.1, scene.duration_estimate)
            duration = floor + (old_duration - floor) * ratio
            beat_ratio = duration / old_duration
            scene.duration_estimate = round(duration, 1)
            for beat in scene.visual_beats:
                beat.duration_estimate = round(max(1.0, beat.duration_estimate * beat_ratio), 1)
            for animation in scene.animations:
                animation.duration = round(min(15.0, max(0.5, animation.duration * beat_ratio)), 1)
        storyboard.total_duration_estimate = round(sum(scene.duration_estimate for scene in storyboard.scenes), 1)
        return storyboard

    remaining = target - current
    weights = [max(1.0, scene.duration_estimate) for scene in storyboard.scenes]
    weight_total = sum(weights) or float(len(storyboard.scenes))

    for scene, weight in zip(storyboard.scenes, weights):
        old_duration = max(0.1, scene.duration_estimate)
        duration = old_duration + remaining * (weight / weight_total)
        ratio = duration / old_duration
        scene.duration_estimate = round(duration, 1)
        for beat in scene.visual_beats:
            beat.duration_estimate = round(max(1.0, beat.duration_estimate * ratio), 1)
        for animation in scene.animations:
            animation.duration = round(min(15.0, max(0.5, animation.duration * ratio)), 1)

    rounded_total = round(sum(scene.duration_estimate for scene in storyboard.scenes), 1)
    delta = round(target - rounded_total, 1)
    if storyboard.scenes and abs(delta) >= 0.1:
        storyboard.scenes[-1].duration_estimate = round(max(1.0, storyboard.scenes[-1].duration_estimate + delta), 1)
        old_total_without_last = sum(scene.duration_estimate for scene in storyboard.scenes[:-1])
        last = storyboard.scenes[-1]
        last.duration_estimate = round(max(_scene_floor_duration(last, target_scene_seconds), target - old_total_without_last), 1)
    storyboard.total_duration_estimate = round(sum(scene.duration_estimate for scene in storyboard.scenes), 1)
    return storyboard


def _max_scene_count_for_target(target_duration: int) -> int:
    return max(3, min(7, math.ceil(max(60, target_duration) / 22)))


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
    if _contains_semiconductor_topic(topic_blob):
        if target_duration <= 70:
            return 3
        if target_duration <= 95:
            return 4
        if target_duration <= 150:
            return 5
        return min(scene_cap, max(6, min(8, outline_count or 6)))
    if _is_cooking_topic_text(topic_blob):
        if target_duration <= 80:
            return 4
        return min(scene_cap, max(4, min(5, outline_count or 5)))
    if any(term in topic_blob for term in ["gradient", "descent", "梯度下降", "学习率", "损失"]):
        return min(scene_cap, max(4, min(6, outline_count or 4)))
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


async def generate_storyboard(req: GenerateStoryboardRequest) -> Storyboard:
    await check_llm_connection()

    graph = req.graph
    brief_data = _graph_enhanced_brief(graph)
    video_style = _canonical_video_style(req.video_style)
    video_style_preset = _video_style_preset(video_style)
    pen_style = _normalize_pen_style(req.pen_style)
    pen_style_preset = _pen_style_preset(pen_style)
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
            "selected_video_style": {
                "id": video_style,
                "name": video_style_preset["name"],
                "default_board_mode": video_style_preset["board_mode"] or None,
                "default_hand_usage": video_style_preset["hand_usage"] or None,
                "default_visual_style": video_style_preset["visual_style"] or None,
                "default_render_strategy": video_style_preset["render_strategy"] or None,
                "planning_rule": video_style_preset["planning_rule"],
                "image_rule": video_style_preset["image_rule"],
            },
            "selected_pen_style": {
                "id": pen_style,
                "name": pen_style_preset["name"],
                "animation_rule": pen_style_preset["rule"],
            },
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
                "Use natural Chinese for all scene titles, narration, diagram labels, and visual beats. When source concepts are English, transcreate them into Chinese expressions a real teacher would say; keep English only for fixed technical terms, acronyms, formulas, or search names, optionally in parentheses.",
                "Avoid dictionary-like hard translations and awkward coined shorthand. Prefer clear Chinese phrases over literal word-by-word translations; e.g. dependence/independence/interdependence can become '依赖 → 独立 → 互相依赖/成熟协作/协作共赢' depending on context, rather than a stiff literal label.",
                "Use the reference-whiteboard grammar: each scene needs one primary visual anchor, such as an object, metaphor, diagram, route, scale, funnel, matrix, clock, warning sign, tool, person/group, chart, or system stack.",
                "Every scene must specify diagram_plan.layout as a staged board composition: title/anchor first, main object or diagram second, arrows/callouts third, and one short takeaway last.",
                "Use the default visual preset for image_description: bold editorial hand-drawn explainer illustration with thick imperfect black crayon/marker outlines, warm off-white surface, coral-pink arrows/checks/starbursts/underlines, sunny yellow highlight blobs behind the main subject, one large visual anchor or at most three large step groups, generous blank space, and text-free artwork because readable text will be added by the renderer.",
                "Do not create any scene that is only a title plus bullet list, checklist, checkmarks, or text boxes. A checklist may appear only as a tiny supporting note beside a larger visual object.",
                "For abstract topics, translate the idea into a concrete visual metaphor before choosing labels: balance scale for tradeoffs, route map for goals, funnel for filtering, loop for feedback, gear/tool for mechanism, clock for timing, warning triangle for risk, clipboard for procedure, people for responsibility, chart for evidence.",
                "Each diagram_plan.required_labels list should name the short labels attached near the visual anchor, not paragraph fragments. Prefer 3-5 labels that map to visible parts of the drawing.",
                "Each scene must include learning_goal, diagram_plan, visual_beats, narration, image_description and animations.",
                "Every visual_beat must pair draw_intent with narration so voiceover follows drawing.",
                "Cover every high-priority teaching_coverage_units item from enhanced_teaching_brief in the actual scene text, labels, beats or narration. Do not merely leave it in the brief.",
                "Respect desired_scene_count. If coverage units are more numerous than scenes, group related units into one scene with multiple visual_beats instead of adding duplicate scenes.",
                "For multi-part topics, include an overview map, grouped explanation scenes, then a final visual synthesis such as a loop, roadmap, hub-and-spoke map, or evidence chart. Avoid final checklist-only scenes.",
                "Use comparison/process/structure/cross-section diagrams and arrows whenever possible.",
                "Borrow strong science-video teaching techniques: start with a hook or historical/context clue when useful, expand acronyms visually, use picture-in-picture reference diagrams, and introduce one concrete real-world analogy that maps to the mechanism.",
                "For abstract mechanisms, show the analogy and the technical diagram side by side, then transfer arrows/labels from the analogy to the device/process.",
                "Make narration lively and a little witty: every scene needs one concrete everyday metaphor, tiny reversal, or teacher-like aside that clarifies the idea. Avoid dry textbook wording and avoid internet memes.",
                "Make visuals feel active: prefer route maps, seesaws, sorting counters, warning marks, loop arrows, sticky-note-sized callouts and small teacher doodles over plain boxes and long labels.",
                "Use progressive focus: first show the whole object, then zoom/call out one region, then add colored arrows and labels only when the narration reaches them.",
                "Treat target_duration_seconds as a pacing hint, not a hard cap. Never drop required concepts or compress narration so much that drawing and voiceover become incomplete.",
                "Use red for current, blue for voltage/control signals, green for conductive channels, purple for gates/attention, and yellow underlines/callouts for key terms.",
                "Underline, circle, or box important concepts like V_G > V_th, electron channel, short-channel effect, FinFET, W_eff, learning rate, and gradient.",
                "For each scene choose board_mode, hand_usage, video_style and visual_style from the brief strategy. Use chalkboard/no hand for chalkboard styles, clean_canvas/annotate for editorial/whiteboard/playful styles, reference/annotate for technical blueprint or complex finished diagrams, and trace only when the drawing is simple enough to follow by hand.",
                "Honor selected_video_style unless it would make the explanation unclear or factually wrong. If selected_video_style.id is not auto, use its default board_mode, hand_usage, visual_style and render_strategy as the baseline for most scenes; only override individual math derivation or complex reference scenes when that clearly improves understanding.",
                "Put selected_video_style.id on each scene as video_style, unless selected_video_style.id is auto. Keep video_style as one of the eight Golpo canvas styles, not the old internal visual_style names.",
                "Reflect selected_video_style.image_rule inside each image_description. The image_description must be specific enough for an image generation model, including style, objects, colors, composition, blank margins, and text-free artwork.",
                "Honor selected_pen_style as a separate animation layer. It can combine with any visual style: pen=fine precise hand, fountain_pen=stylus/tablet feeling, marker=bold marker hand, no_hand=hide hand and use staged reveal. Put the chosen pen_style on each scene unless the scene must hide the hand.",
                "For cooking or food how-to topics, make image_description concrete and appetizing: name the cookware, ingredients, sauce color, steam, garnish, and finished state. For Chinese stir-fry/simmer steps prefer a wide black wok or skillet; use a blue soup pot only for explicit blanching or boiling-water scenes. Map colors to real food, e.g. red chili oil/sauce, white tofu cubes, brown minced meat, green garlic sprouts or scallions.",
                "For cooking or food how-to scenes, use one large food/cookware state per scene. Avoid dense step-flow diagrams with many tiny pots, boxes, or captions. If an overview is needed, use at most three large illustrated nodes; leave recipe details to narration and later scenes.",
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
                    duration=min(15.0, max(0.5, float(a.get("duration", 2.0)))),
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
                image_description=_normalize_image_description_text(s.get("image_description")) or None,
                learning_goal=s.get("learning_goal") or None,
                visual_beats=visual_beats,
                diagram_plan=diagram_plan,
                render_strategy=_clean_text(s.get("render_strategy") or s.get("raster_strategy") or ""),
                visual_complexity=_clean_text(s.get("visual_complexity") or ""),
                board_mode=_clean_text(s.get("board_mode") or ""),
                hand_usage=_clean_text(s.get("hand_usage") or ""),
                video_style=_clean_text(s.get("video_style") or s.get("videoStyle") or ""),
                visual_style=_clean_text(s.get("visual_style") or ""),
                pen_style=_clean_text(s.get("pen_style") or s.get("penStyle") or ""),
            )
        )

    storyboard = Storyboard(
        topic=graph.topic,
        total_duration_estimate=total_duration,
        scenes=scenes,
        video_style=video_style,
        pen_style=pen_style,
    )
    storyboard = _trim_storyboard_scene_count(storyboard, req.target_duration, graph)
    storyboard = _ensure_storyboard_quality(storyboard, graph, req.target_duration)
    storyboard = _trim_storyboard_scene_count(storyboard, req.target_duration, graph)
    storyboard = _compress_storyboard_narration_to_target(storyboard, req.target_duration)
    storyboard = _fit_storyboard_to_target(storyboard, req.target_duration)
    storyboard = _sanitize_storyboard_narration(storyboard)

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


def _graph_source_corpus(graph: ExplainGraph) -> str:
    brief = _graph_enhanced_brief(graph) or {}
    parts = [graph.topic, graph.summary, " ".join(graph.key_insights)]
    if isinstance(brief, dict):
        parts.extend(
            [
                _clean_text(brief.get("original_prompt")),
                _clean_text(brief.get("topic_type")),
                json.dumps(brief.get("must_include_points") or [], ensure_ascii=False),
                json.dumps(brief.get("learning_objectives") or [], ensure_ascii=False),
            ]
        )
    return " ".join(part for part in parts if part).lower()


def _storyboard_scene_corpus(storyboard: Storyboard) -> str:
    parts: list[str] = []
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


def _apply_video_style_to_scene(scene: Scene, video_style: str) -> None:
    style = _canonical_video_style(video_style)
    if style == "auto":
        return
    preset = _video_style_preset(style)
    scene.video_style = style
    scene_corpus = _scene_corpus(scene)
    is_math_scene = _contains_terms(
        scene_corpus,
        [
            "数学",
            "解题",
            "证明",
            "公式推导",
            "derivation",
            "proof",
            "equation",
            "formula",
            "plane normal",
            "perpendicular",
            "parametric",
            "iit",
            "gradient descent",
            "梯度下降",
            "loss function",
            "损失函数",
            "learning rate",
            "学习率",
        ],
    )
    is_reference_scene = _contains_terms(
        scene_corpus,
        [
            "reference",
            "cross-section",
            "cross section",
            "3d",
            "三维",
            "截面",
            "剖面",
            "电路",
            "医学",
            "机械",
            "多层",
            "interface",
            "ui",
        ],
    )

    if style in {"chalkboard_bw", "chalkboard_color"}:
        scene.board_mode = "chalkboard"
        scene.hand_usage = "none"
        scene.visual_style = "math_chalkboard"
        scene.render_strategy = "trace"
    elif style == "technical_blueprint":
        scene.board_mode = "reference"
        scene.hand_usage = "annotate"
        scene.visual_style = "technical_reference"
        scene.render_strategy = "hybrid"
    elif style == "whiteboard":
        if is_math_scene:
            scene.board_mode = "whiteboard"
            scene.hand_usage = "trace"
            scene.visual_style = "teacher_whiteboard"
            scene.render_strategy = scene.render_strategy or "trace"
        elif is_reference_scene and (scene.visual_complexity or "").lower() in {"dense", "reference"}:
            scene.board_mode = "reference"
            scene.hand_usage = "annotate"
            scene.visual_style = "technical_reference"
            scene.render_strategy = "hybrid"
        else:
            scene.board_mode = "clean_canvas"
            scene.hand_usage = "annotate"
            scene.visual_style = "marketing_doodle"
            scene.render_strategy = "hybrid" if scene.render_strategy == "trace" else scene.render_strategy or "hybrid"
    elif style in {"modern_minimal", "editorial", "playful", "sharpie"}:
        scene.board_mode = "clean_canvas"
        scene.hand_usage = "annotate" if style != "sharpie" else "trace"
        scene.visual_style = style
        scene.render_strategy = "hybrid" if style != "sharpie" else "hybrid"

    image_rule = preset["image_rule"]
    if scene.image_description and not _style_image_rule_in_description(scene, style):
        scene.image_description = f"{scene.image_description}. {image_rule}".strip(". ")
    scene.image_description = _normalize_image_description_text(scene.image_description)


def _apply_pen_style_to_scene(scene: Scene, pen_style: str) -> None:
    style = _normalize_pen_style(pen_style)
    scene.pen_style = style
    if style == "no_hand" or scene.board_mode == "chalkboard" or scene.visual_style == "math_chalkboard":
        scene.hand_usage = "none"
        scene.pen_style = "no_hand"
        return
    if not scene.hand_usage or scene.hand_usage == "none":
        scene.hand_usage = "annotate"
    if style == "marker" and scene.hand_usage == "trace" and scene.video_style not in {"sharpie"}:
        scene.hand_usage = "annotate"


def _contains_semiconductor_topic(corpus: str) -> bool:
    lowered = corpus.lower()
    if any(
        re.search(pattern, lowered)
        for pattern in [
            r"(?<![a-z0-9_])mos(?![a-z0-9_])",
            r"(?<![a-z0-9_])mosfet(?![a-z0-9_])",
            r"(?<![a-z0-9_])finfet(?![a-z0-9_])",
        ]
    ):
        return True
    return _contains_terms(corpus, ["晶体管", "场效应管", "栅极", "源极", "漏极", "沟道"])


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


def _coverage_scene_spec(unit: dict, index: int, topic: str) -> dict:
    label = _coverage_unit_label(unit) or f"关键单元 {index + 1}"
    kind = _diagram_kind_for_coverage_unit(unit)
    must_show = _planner_str_list(unit.get("must_show") or unit.get("required_labels") or unit.get("must_draw"), limit=5)
    if not must_show:
        must_show = [label]
    teaching_goal = _clean_text(unit.get("teaching_goal")) or f"讲清楚 {label} 的含义、原因和结果。"
    narration_focus = _clean_text(unit.get("narration_focus")) or teaching_goal
    short_label = _short_text(label, 22)

    if kind == "comparison":
        diagram_kind = "comparison"
        layout = "two whiteboard panels contrasting the state before and after the key change"
        beat_one_draw = f"用双栏对比呈现 {short_label} 的前后状态，并放上最短标签。"
        beat_two_draw = f"在两栏之间补箭头、差异圈选和结论下划线，让变化原因可见。"
        beat_one_narration = f"{short_label} 不能单独拎着看，不然就像只看菜单不看菜，味道全靠猜。"
        beat_two_narration = _clean_narration_text(narration_focus)
    elif kind == "tradeoff_matrix":
        diagram_kind = "tradeoff_matrix"
        layout = "2x2 whiteboard matrix showing two decision axes, four zones, and the preferred zone underlined"
        beat_one_draw = f"把 {short_label} 放进二维判断矩阵，横轴和纵轴各表达一个关键标准。"
        beat_two_draw = "圈出最值得关注的区域，并用箭头说明取舍方向。"
        beat_one_narration = f"{short_label} 需要两个维度来降噪，不然所有方案都在喊“选我”，会议很快变成菜市场。"
        beat_two_narration = _clean_narration_text(narration_focus)
    elif kind == "interaction":
        diagram_kind = "interaction"
        layout = "two or three actors/nodes with bidirectional arrows, exchanged signals, and a shared outcome callout"
        beat_one_draw = f"把 {short_label} 拆成参与对象和它们之间的相互影响。"
        beat_two_draw = "补双向箭头、信息交换标签和共同结果，让关系不是孤立节点。"
        beat_one_narration = f"{short_label} 的重点不在单个角色，而在它们怎么互相递球；球传歪了，结果也会跟着跑偏。"
        beat_two_narration = _clean_narration_text(narration_focus)
    elif kind == "goal_path":
        diagram_kind = "goal_path"
        layout = "start point, milestones, target point, and a backcasting arrow on a sparse whiteboard"
        beat_one_draw = f"把 {short_label} 画成从当前位置到目标的路径。"
        beat_two_draw = "加入里程碑和倒推箭头，说明每一步为什么服务于终点。"
        beat_one_narration = f"{short_label} 要先把终点钉住，否则行动会很勤奋，但方向可能像没开导航的出租车。"
        beat_two_narration = _clean_narration_text(narration_focus)
    elif kind == "cycle":
        diagram_kind = "cycle"
        layout = "3 to 5 node circular loop with arrows and one highlighted improvement point"
        beat_one_draw = f"把 {short_label} 做成一个闭环，而不是一次性动作。"
        beat_two_draw = "用环形箭头连接各节点，并强调下一轮会带来什么改进。"
        beat_one_narration = f"{short_label} 不是交卷就散场，而是看一眼结果，再把下一轮动作调准一点。"
        beat_two_narration = _clean_narration_text(narration_focus)
    elif kind == "formula":
        diagram_kind = "formula"
        layout = "one formula line with variable callouts and a small meaning diagram"
        beat_one_draw = f"写出 {short_label} 的核心表达，并把变量拆成短标签。"
        beat_two_draw = "用箭头把公式中的变量连接到旁边的小示意图。"
        beat_one_narration = f"{short_label} 的关键不只是记住符号，而是知道每个量对应现实中的哪一部分。"
        beat_two_narration = _clean_narration_text(narration_focus)
    elif kind == "process":
        diagram_kind = "process"
        layout = "left-to-right cause-process-result flow with arrows and a small conclusion underline"
        beat_one_draw = f"把 {short_label} 拆成原因、过程、结果三个节点。"
        beat_two_draw = "用箭头表示变化方向，并圈出最关键的转折点。"
        beat_one_narration = f"理解 {short_label} 要抓住因果链，别只盯着结论；那就像只看终点照片，不知道车是怎么开到那里的。"
        beat_two_narration = _clean_narration_text(narration_focus)
    elif kind == "summary":
        diagram_kind = "summary"
        layout = "teacher checklist or loop map summarizing the key units"
        beat_one_draw = f"把 {short_label} 做成一张总结清单或闭环图。"
        beat_two_draw = "给核心结论加下划线，并把它连回主题。"
        beat_one_narration = f"{short_label} 是收口动作，把刚才散落的零件装回工具箱，下次要用时才找得到。"
        beat_two_narration = _clean_narration_text(narration_focus)
    elif kind == "overview_map":
        diagram_kind = "overview_map"
        layout = "central topic with 3 to 5 surrounding units, arrows showing the lesson route, and one highlighted current unit"
        beat_one_draw = f"先把 {short_label} 放在中心，并展开本主题的几个核心单元。"
        beat_two_draw = "用路线箭头串起这些单元，让观众知道后面会怎样推进。"
        beat_one_narration = f"{short_label} 要先有全局地图，不然观众会像进了陌生商场，走得很努力但不知道电梯在哪。"
        beat_two_narration = _clean_narration_text(narration_focus)
    else:
        diagram_kind = "structure"
        layout = "central concept sketch with nearby short labels, arrows and a concrete example"
        beat_one_draw = f"在白板中央呈现 {short_label} 的核心对象，并贴近写短标签。"
        beat_two_draw = "补一个具体例子或局部放大，再用下划线强调结论。"
        beat_one_narration = f"{short_label} 要先放回整体里看，否则它就像桌上的一颗螺丝，重要但不知道拧在哪。"
        beat_two_narration = _clean_narration_text(narration_focus)

    return {
        "title": short_label,
        "learning_goal": teaching_goal,
        "render_strategy": "trace",
        "visual_complexity": "medium",
        "board_mode": "whiteboard",
        "hand_usage": "trace",
        "visual_style": "teacher_whiteboard",
        "diagram_plan": {
            "kind": diagram_kind,
            "layout": layout,
            "required_labels": must_show[:6],
        },
        "visual_beats": [
            {
                "draw_intent": beat_one_draw,
                "narration": beat_one_narration,
                "required_labels": must_show[:3],
                "duration_estimate": 8,
            },
            {
                "draw_intent": beat_two_draw,
                "narration": beat_two_narration,
                "required_labels": must_show[:5],
                "duration_estimate": 9,
            },
        ],
        "image_description": (
            "clean light grey-white whiteboard, rich colorful educational doodle illustration, strong readable marker outlines, short blue handwritten title, "
            f"{layout}, topic {topic}, labels {', '.join(must_show[:6])}, yellow underline for the key term, "
            "3-6 meaningful visual parts, purposeful semantic color accents, generous white space, no poster, no card, no legend box, no colored background"
        ),
        "duration_estimate": 30,
    }


def _generic_relation_story_specs(graph: ExplainGraph, target_duration: int) -> list[dict]:
    topic = _short_text(graph.topic or "主题", 20)
    desired = _max_scene_count_for_target(target_duration)
    source_corpus = _graph_source_corpus(graph)
    framework_terms = [
        "通用问题解决框架",
        "问题解决框架",
        "全局地图",
        "取舍矩阵",
        "目标路径",
        "反馈闭环",
        "閫氱敤闂瑙ｅ喅妗嗘灦",
        "闂瑙ｅ喅妗嗘灦",
        "鍏ㄥ眬鍦板浘",
        "鍙栬垗鐭╅樀",
        "鐩爣璺緞",
        "鍙嶉闂幆",
    ]
    is_problem_framework = _contains_terms(source_corpus, framework_terms)
    if _contains_terms(source_corpus, ["通用问题解决框架", "问题解决框架", "取舍矩阵", "目标路径", "反馈闭环"]):
        desired = min(5, desired)
    if is_problem_framework:
        desired = min(5, desired)
    base_specs = [
        {
            "title": "全局地图",
            "learning_goal": f"先建立 {topic} 的整体认知，知道接下来会讲哪些部分。",
            "render_strategy": "trace",
            "visual_complexity": "medium",
            "board_mode": "whiteboard",
            "hand_usage": "trace",
            "visual_style": "teacher_whiteboard",
            "diagram_plan": {"kind": "overview_map", "layout": "central topic with surrounding units and route arrows", "required_labels": ["主题", "现象", "结构", "过程", "结果"]},
            "visual_beats": [
                {
                    "draw_intent": "在中心写主题，周围展开几个核心单元。",
                    "narration": f"解决问题先别急着撸袖子，得先摊开一张全局地图；不然很可能跑得满头汗，却在错误楼层找门牌。",
                    "required_labels": ["主题", "全局地图"],
                    "duration_estimate": 7,
                },
                {
                    "draw_intent": "用箭头串起后续讲解路线。",
                    "narration": "地图上至少要有目标、约束、关键对象和顺序，后面的每一步才知道自己是在给谁打工。",
                    "required_labels": ["对象", "边界", "顺序"],
                    "duration_estimate": 8,
                },
            ],
            "image_description": f"clean light grey-white whiteboard, rich colorful playful hand-drawn map for {topic}: central messy knot labeled 问题, compass icon, 4 route signs for 全局/结构/取舍/目标, red warning mark, green route arrow, blue route lines, yellow emphasis marks, generous white space, no poster no card no paper panel",
            "duration_estimate": 24,
        },
        {
            "title": "结构拆解",
            "learning_goal": "把复杂对象拆成组成部分，说明整体和局部如何连接。",
            "render_strategy": "trace",
            "visual_complexity": "medium",
            "board_mode": "whiteboard",
            "hand_usage": "trace",
            "visual_style": "teacher_whiteboard",
            "diagram_plan": {"kind": "structure", "layout": "main object broken into parts with nearby labels and a zoom callout", "required_labels": ["整体", "局部", "关键部分"]},
            "visual_beats": [
                {
                    "draw_intent": "画一个主体框架，并拆出 3 个局部。",
                    "narration": "结构拆解像把一台卡住的机器拆开看，别对着整机许愿，先找到哪个齿轮真在咬住结果。",
                    "required_labels": ["整体", "局部"],
                    "duration_estimate": 7,
                },
                {
                    "draw_intent": "圈出关键局部，并补一个放大框。",
                    "narration": "真正要紧的不是零件数量，而是谁连着谁、谁一动会带着一串人跟着动。",
                    "required_labels": ["关键部分", "连接"],
                    "duration_estimate": 8,
                },
            ],
            "image_description": "clean teacher whiteboard colorful playful structure diagram, big tangled ball split into 3 gears/blocks, magnifying glass callout, tiny question mark marks, blue/red/green arrows and nearby short labels, generous white space, no poster layout no paper panel",
            "duration_estimate": 24,
        },
        {
            "title": "状态对比",
            "learning_goal": "用对比让观众看见变化前后或方案 A/B 的差异。",
            "render_strategy": "trace",
            "visual_complexity": "medium",
            "board_mode": "whiteboard",
            "hand_usage": "trace",
            "visual_style": "teacher_whiteboard",
            "diagram_plan": {"kind": "comparison", "layout": "two-panel comparison with difference circles and an arrow between panels", "required_labels": ["A", "B", "差异", "结果"]},
            "visual_beats": [
                {
                    "draw_intent": "画左右两个面板，分别标出 A 和 B。",
                    "narration": "方案一多，大家都会举手说自己很香。对比图先把它们放到同一张桌上，别让嗓门替代判断。",
                    "required_labels": ["A", "B"],
                    "duration_estimate": 7,
                },
                {
                    "draw_intent": "圈出差异，并用箭头指向结果。",
                    "narration": "差异必须连到结果，才知道这是关键区别，还是包装纸上印得比较热闹。",
                    "required_labels": ["差异", "结果"],
                    "duration_estimate": 8,
                },
            ],
            "image_description": "two-panel whiteboard comparison with lively voting marks, option A and B as simple objects on a scale, circled differences, arrow to outcome, sparse handwritten labels, no poster no card",
            "duration_estimate": 24,
        },
        {
            "title": "优先取舍",
            "learning_goal": "用二维矩阵说明优先级和取舍规则。",
            "render_strategy": "trace",
            "visual_complexity": "medium",
            "board_mode": "whiteboard",
            "hand_usage": "trace",
            "visual_style": "teacher_whiteboard",
            "diagram_plan": {"kind": "tradeoff_matrix", "layout": "2x2 matrix with two axes and a highlighted preferred quadrant", "required_labels": ["重要", "紧急", "优先", "取舍"]},
            "visual_beats": [
                {
                    "draw_intent": "画 2x2 矩阵和两个判断轴。",
                    "narration": "取舍矩阵像给方案排队验票：一个维度看收益，一个维度看代价，谁插队一眼就露馅。",
                    "required_labels": ["重要", "紧急"],
                    "duration_estimate": 7,
                },
                {
                    "draw_intent": "圈出优先象限，并用箭头说明移动方向。",
                    "narration": "优先级不是把清单全吃完，而是先夹那块最能顶饱的菜；资源有限，就别假装自己有八只手。",
                    "required_labels": ["优先", "取舍"],
                    "duration_estimate": 8,
                },
            ],
            "image_description": "2x2 whiteboard priority matrix with four funny方案 tokens, one green winner badge, one red avoid zone, tiny crowd speech marks saying 选我, yellow underline on priority, large negative space no panel",
            "duration_estimate": 24,
        },
        {
            "title": "目标路径",
            "learning_goal": "把目标和行动路线连起来，避免只停留在愿望。",
            "render_strategy": "trace",
            "visual_complexity": "medium",
            "board_mode": "whiteboard",
            "hand_usage": "trace",
            "visual_style": "teacher_whiteboard",
            "diagram_plan": {"kind": "goal_path", "layout": "start point, milestones, target point, and a backcasting arrow", "required_labels": ["现在", "里程碑", "目标", "倒推"]},
            "visual_beats": [
                {
                    "draw_intent": "画从现在到目标的路径，并加入里程碑。",
                    "narration": "目标路径把愿望变成路线图。只喊我要到终点，听起来很燃，但出租车司机会问：到底往哪拐？",
                    "required_labels": ["现在", "目标"],
                    "duration_estimate": 7,
                },
                {
                    "draw_intent": "从目标反向画倒推箭头，标出下一步。",
                    "narration": "从终点倒推，会逼我们把里程碑说清楚；下一步不再是玄学，而是导航上的第一段路。",
                    "required_labels": ["倒推", "下一步"],
                    "duration_estimate": 8,
                },
            ],
            "image_description": "clean whiteboard colorful goal path as a winding road, current point as small confused dot, milestones as colored flags, target as star, backcasting arrow, tiny taxi/navigation icon, short nearby labels, generous white space, no card",
            "duration_estimate": 24,
        },
        {
            "title": "反馈闭环",
            "learning_goal": "说明结果会回到下一轮行动中，形成持续改进。",
            "render_strategy": "trace",
            "visual_complexity": "medium",
            "board_mode": "whiteboard",
            "hand_usage": "trace",
            "visual_style": "teacher_whiteboard",
            "diagram_plan": {"kind": "cycle", "layout": "circular feedback loop with plan, act, check, adjust nodes", "required_labels": ["计划", "执行", "检查", "调整"]},
            "visual_beats": [
                {
                    "draw_intent": "画一个四节点闭环。",
                    "narration": "反馈闭环的意思是，做完别马上散会。结果像小票，别揉了扔，它能告诉你下一轮哪里该调。",
                    "required_labels": ["计划", "执行", "检查", "调整"],
                    "duration_estimate": 8,
                },
                {
                    "draw_intent": "给闭环加循环箭头和改进下划线。",
                    "narration": "厉害的框架不靠一次神操作，而是每轮都校准一点点；像调收音机，噪声少一点，信号就清楚一点。",
                    "required_labels": ["反馈", "改进"],
                    "duration_estimate": 7,
                },
            ],
            "image_description": "whiteboard circular feedback loop with receipt/check ticket metaphor, plan act check adjust nodes, loop arrows, small tuning dial icon, yellow underline on improvement, no paper panel",
            "duration_estimate": 24,
        },
        {
            "title": "总结框架",
            "learning_goal": "把全片内容收束成可复述的框架。",
            "render_strategy": "trace",
            "visual_complexity": "simple",
            "board_mode": "whiteboard",
            "hand_usage": "trace",
            "visual_style": "teacher_whiteboard",
            "diagram_plan": {"kind": "summary", "layout": "short teacher checklist connected back to the overview map", "required_labels": ["看全局", "拆结构", "做对比", "定优先", "走闭环"]},
            "visual_beats": [
                {
                    "draw_intent": "写一列短清单，并用勾选符号逐项出现。",
                    "narration": "最后把工具装回工具箱：看全局，拆结构和过程，做取舍，按目标倒推，再用反馈修正。下次遇到乱麻，就不用徒手薅了。",
                    "required_labels": ["看全局", "拆结构", "做对比", "定优先", "走闭环"],
                    "duration_estimate": 9,
                }
            ],
            "image_description": "clean teacher whiteboard colorful summary map with green ticks, a small loop arrow, 3-5 tiny visual anchors, yellow emphasis underline, short labels only, no long paragraphs",
            "duration_estimate": 20,
        },
    ]
    if _contains_terms(source_corpus, ["通用问题解决框架", "问题解决框架", "取舍矩阵", "目标路径", "反馈闭环"]):
        priority_titles = {"全局地图", "结构拆解", "优先取舍", "目标路径", "反馈闭环"}
        selected = [spec for spec in base_specs if spec["title"] in priority_titles][:desired]
        if is_problem_framework and len(selected) < desired:
            return [base_specs[index] for index in [0, 1, 3, 4, 5]][:desired]
        return selected
    return base_specs[:desired]


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
            duration=min(15.0, max(4.0, float(beat.duration_estimate))),
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
        image_description=_normalize_image_description_text(spec["image_description"]),
        render_strategy=spec.get("render_strategy", ""),
        visual_complexity=spec.get("visual_complexity", ""),
        board_mode=spec.get("board_mode", ""),
        hand_usage=spec.get("hand_usage", ""),
        video_style=spec.get("video_style"),
        visual_style=spec.get("visual_style", ""),
        pen_style=spec.get("pen_style"),
    )


def _semiconductor_story_specs() -> list[dict]:
    return [
        {
            "title": "MOS 基本结构",
            "learning_goal": "让观众理解源极、漏极、栅极、氧化层、衬底和沟道区域的位置关系。",
            "render_strategy": "trace",
            "visual_complexity": "simple",
            "board_mode": "whiteboard",
            "hand_usage": "trace",
            "visual_style": "teacher_whiteboard",
            "diagram_plan": {
                "kind": "structure",
                "layout": "planar MOS cross-section with labels from left to right",
                "required_labels": ["Source", "Drain", "Gate", "Oxide", "Substrate", "Channel"],
            },
            "visual_beats": [
                {
                    "draw_intent": "画一条衬底横截面，在左右分别画 Source 和 Drain，中间留出 channel region。",
                    "narration": "平面 MOS 的剖面里，左右是源极和漏极，中间的衬底表面就是未来可能形成沟道的位置。",
                    "required_labels": ["Source", "Drain", "Channel region"],
                    "duration_estimate": 7,
                },
                {
                    "draw_intent": "在沟道上方画薄氧化层和 Gate，并用蓝色电场箭头指向衬底表面。",
                    "narration": "栅极并不直接接触沟道，它隔着很薄的氧化层，用电场影响衬底表面的电荷。",
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
            "render_strategy": "trace",
            "visual_complexity": "simple",
            "board_mode": "whiteboard",
            "hand_usage": "trace",
            "visual_style": "teacher_whiteboard",
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
            "render_strategy": "trace",
            "visual_complexity": "medium",
            "board_mode": "whiteboard",
            "hand_usage": "trace",
            "visual_style": "teacher_whiteboard",
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
                    "draw_intent": "沿沟道画多根红色电流箭头 I_D，并在旁边画一个被栅压控制的开关图标。",
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
            "render_strategy": "trace",
            "visual_complexity": "medium",
            "board_mode": "whiteboard",
            "hand_usage": "trace",
            "visual_style": "teacher_whiteboard",
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
            "render_strategy": "hybrid",
            "visual_complexity": "dense",
            "board_mode": "reference",
            "hand_usage": "annotate",
            "visual_style": "technical_reference",
            "diagram_plan": {
                "kind": "structure",
                "layout": "simple 3D fin channel with gate wrapping top and two sidewalls",
                "required_labels": ["Fin channel", "Gate wraps 3 sides", "Source", "Drain"],
            },
            "visual_beats": [
                {
                    "draw_intent": "画一个竖起的 fin/channel，两端分别连接 Source 和 Drain。",
                    "narration": "FinFET 把原来趴在平面上的沟道竖起来，变成一条鳍片状的三维通道。",
                    "required_labels": ["Fin channel", "Source", "Drain"],
                    "duration_estimate": 8,
                },
                {
                    "draw_intent": "画 U 形 Gate 从顶部和两侧包住 fin，并从三面画控制箭头。",
                    "narration": "栅极不再只从上方控制，而是像夹子一样包住顶部和两个侧壁，三面同时施加电场，栅控能力就明显增强。",
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
            "render_strategy": "hybrid",
            "visual_complexity": "dense",
            "board_mode": "reference",
            "hand_usage": "annotate",
            "visual_style": "technical_reference",
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
            "render_strategy": "trace",
            "visual_complexity": "simple",
            "board_mode": "whiteboard",
            "hand_usage": "trace",
            "visual_style": "teacher_whiteboard",
            "diagram_plan": {"kind": "simulation", "layout": "loss curve with axes", "required_labels": ["Loss", "theta"]},
            "visual_beats": [
                {
                    "draw_intent": "画 theta 横轴和 Loss 纵轴，再画一条下降的曲线。",
                    "narration": "损失函数可以理解成一条地形曲线，越高代表模型错得越多，越低代表参数更合适。",
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
            "render_strategy": "trace",
            "visual_complexity": "simple",
            "board_mode": "whiteboard",
            "hand_usage": "trace",
            "visual_style": "teacher_whiteboard",
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
            "render_strategy": "trace",
            "visual_complexity": "medium",
            "board_mode": "whiteboard",
            "hand_usage": "trace",
            "visual_style": "teacher_whiteboard",
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
    for scene in scenes:
        if scene.image_description:
            scene.image_description = _normalize_image_description_text(scene.image_description)
    return Storyboard(
        topic=storyboard.topic,
        total_duration_estimate=round(sum(scene.duration_estimate for scene in scenes), 1),
        scenes=scenes,
        video_style=storyboard.video_style,
        pen_style=storyboard.pen_style,
    )


def _append_missing_coverage_scenes(storyboard: Storyboard, graph: ExplainGraph, target_duration: int, limit: int | None = None) -> Storyboard:
    missing = _missing_coverage_units(storyboard, graph)
    if not missing:
        return storyboard
    effective_limit = limit if limit is not None else _max_scene_count_for_target(target_duration)
    room = max(0, effective_limit - len(storyboard.scenes))
    protected_ids = {id(scene) for scene in _protected_coverage_scenes(storyboard, graph, max(1, len(storyboard.scenes)))}
    for unit in missing:
        scene = _scene_from_spec(
            len(storyboard.scenes),
            _coverage_scene_spec(unit, len(storyboard.scenes), graph.topic),
        )
        if room > 0:
            storyboard.scenes.append(scene)
            protected_ids.add(id(scene))
            room -= 1
            continue
        replace_at = _replaceable_scene_index(storyboard.scenes, protected_ids)
        if replace_at is None:
            continue
        storyboard.scenes[replace_at] = scene
        protected_ids.add(id(scene))
    for index, scene in enumerate(storyboard.scenes):
        scene.order = index
        scene.id = f"scene_{index}"
    storyboard.total_duration_estimate = round(sum(scene.duration_estimate for scene in storyboard.scenes), 1)
    return storyboard


def _sanitize_storyboard_narration(storyboard: Storyboard) -> Storyboard:
    for scene in storyboard.scenes:
        for beat in scene.visual_beats:
            beat.narration = _clean_narration_text(beat.narration)
        scene.narration = _narration_from_beats(scene.narration, scene.visual_beats)
    return storyboard


def _ensure_storyboard_quality(storyboard: Storyboard, graph: ExplainGraph, target_duration: int) -> Storyboard:
    corpus = _storyboard_corpus(storyboard, graph)
    source_corpus = _graph_source_corpus(graph)
    video_style = _canonical_video_style(storyboard.video_style)
    storyboard.video_style = video_style
    pen_style = _normalize_pen_style(storyboard.pen_style)
    storyboard.pen_style = pen_style
    is_cooking_topic = _is_cooking_topic_text(f"{corpus} {source_corpus}")
    gradient = _contains_terms(source_corpus, ["gradient", "descent", "梯度下降", "学习率", "损失"])
    brief = _graph_enhanced_brief(graph) or {}
    default_board_mode = _clean_text(brief.get("recommended_board_mode") if isinstance(brief, dict) else "") or "whiteboard"
    default_hand_usage = _clean_text(brief.get("recommended_hand_usage") if isinstance(brief, dict) else "") or "trace"
    default_visual_style = _clean_text(brief.get("recommended_visual_style") if isinstance(brief, dict) else "") or "teacher_whiteboard"
    framework_terms = ["通用问题解决框架", "问题解决框架", "全局地图", "取舍矩阵", "目标路径", "反馈闭环"]
    framework_terms.extend(["通用问题解决框架", "问题解决框架", "全局地图", "取舍矩阵", "目标路径", "反馈闭环"])
    is_problem_framework = _contains_terms(source_corpus, framework_terms)
    if is_problem_framework:
        storyboard = _replace_with_specs(storyboard, _generic_relation_story_specs(graph, target_duration))
        corpus = _storyboard_corpus(storyboard, graph)

    if gradient:
        coverage_groups = [
            ["loss", "损失"],
            ["gradient", "梯度"],
            ["learning rate", "学习率"],
            ["iteration", "迭代", "converge", "收敛"],
        ]
        coverage = sum(1 for group in coverage_groups if _contains_terms(corpus, group))
        if len(storyboard.scenes) < 3 or coverage < 4:
            storyboard = _replace_with_specs(storyboard, _gradient_story_specs())
            corpus = _storyboard_corpus(storyboard, graph)

    if _contains_semiconductor_topic(corpus):
        storyboard = _replace_with_specs(storyboard, _generic_relation_story_specs(graph, target_duration))
        corpus = _storyboard_corpus(storyboard, graph)

    if not is_problem_framework:
        storyboard = _append_missing_coverage_scenes(storyboard, graph, target_duration)
        corpus = _storyboard_corpus(storyboard, graph)
    if is_cooking_topic:
        storyboard = _apply_mapo_cooking_defaults(storyboard, target_duration)
        corpus = _storyboard_corpus(storyboard, graph)

    for scene in storyboard.scenes:
        if not scene.visual_beats:
            labels = []
            if scene.diagram_plan:
                labels = scene.diagram_plan.required_labels
            scene.visual_beats = [
                VisualBeat(
                    id="beat_0",
                    draw_intent=scene.image_description or scene.title,
                    narration=_clean_narration_text(scene.narration or scene.title),
                    required_labels=labels,
                    duration_estimate=max(5.0, min(10.0, scene.duration_estimate * 0.35)),
                )
            ]
        for beat in scene.visual_beats:
            beat.narration = _clean_narration_text(beat.narration)
        scene.narration = _narration_from_beats(scene.narration, scene.visual_beats)
        if not scene.board_mode:
            scene.board_mode = default_board_mode
        if not scene.hand_usage:
            scene.hand_usage = default_hand_usage
        if not scene.video_style and video_style != "auto":
            scene.video_style = video_style
        if not scene.visual_style:
            scene.visual_style = default_visual_style
        scene.title = _clean_text(scene.title)
        scene.learning_goal = _clean_text(scene.learning_goal)
        scene.image_description = _normalize_image_description_text(scene.image_description)
        if scene.diagram_plan:
            scene.diagram_plan.kind = _clean_text(scene.diagram_plan.kind)
            scene.diagram_plan.layout = _clean_text(scene.diagram_plan.layout)
            scene.diagram_plan.required_labels = [_clean_text(label) for label in scene.diagram_plan.required_labels if _clean_text(label)]
        for beat in scene.visual_beats:
            beat.draw_intent = _clean_text(beat.draw_intent)
            beat.required_labels = [_clean_text(label) for label in beat.required_labels if _clean_text(label)]
        for animation in scene.animations:
            animation.content = _clean_text(animation.content)
            if animation.items:
                animation.items = [_clean_text(item) for item in animation.items if _clean_text(item)]
        scene_corpus = _scene_corpus(scene)
        cooking_suffix = _cooking_prompt_suffix(scene_corpus)
        if cooking_suffix and cooking_suffix not in (scene.image_description or ""):
            scene.image_description = f"{scene.image_description}. {cooking_suffix}".strip(". ")
            scene.image_description = _normalize_image_description_text(scene.image_description)
        is_math_board = (
            video_style in {"auto", "chalkboard_bw", "chalkboard_color"}
            and default_visual_style == "math_chalkboard"
        ) or _contains_terms(
            scene_corpus,
            ["数学解题", "数学证明", "公式推导", "plane normal", "perpendicular", "parametric", "iit"],
        )
        if is_math_board:
            scene.board_mode = "chalkboard"
            scene.hand_usage = "none"
            scene.visual_style = "math_chalkboard"
        _apply_video_style_to_scene(scene, video_style)
        if scene.board_mode == "chalkboard" or scene.visual_style == "math_chalkboard":
            scene.hand_usage = "none"
            scene.render_strategy = scene.render_strategy or "trace"
            scene.visual_complexity = scene.visual_complexity or "medium"
        if scene.hand_usage == "annotate" and not scene.render_strategy:
            scene.render_strategy = "hybrid"
        _apply_pen_style_to_scene(scene, pen_style)
        if scene.board_mode == "chalkboard" or scene.visual_style == "math_chalkboard":
            scene.hand_usage = "none"
            scene.pen_style = "no_hand"
            scene.render_strategy = scene.render_strategy or "trace"
        scene.duration_estimate = _estimate_scene_duration(
            scene.duration_estimate,
            scene.narration,
            scene.visual_beats,
            scene.animations,
        )
        if is_cooking_topic:
            scene.duration_estimate = min(scene.duration_estimate, 24.0 if len(storyboard.scenes) >= 5 else 28.0)
            for beat in scene.visual_beats:
                beat.duration_estimate = min(beat.duration_estimate, 6.0)
            for animation in scene.animations:
                animation.duration = min(animation.duration, 6.0)
    storyboard.total_duration_estimate = round(sum(scene.duration_estimate for scene in storyboard.scenes), 1)
    return _sanitize_storyboard_narration(storyboard)


def _short_text(value: str | None, max_chars: int = 30) -> str:
    text = re.sub(r"\s+", " ", value or "").strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3].rstrip() + "..."


def _text_visual_width(value: str, font_size: float) -> float:
    width = 0.0
    for char in value:
        width += font_size * (1.0 if re.match(r"[\u3400-\u9fff]", char) else 0.55)
    return width


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
    _retime_draw_ops_in_window(draw_ops, 0.0, max(1.0, duration - 4.0))


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
    buckets: list[list[dict]] = [[] for _ in segments]
    segment_index_by_id = {
        str(segment.get("id") or f"beat_{index}"): index
        for index, segment in enumerate(segments)
    }
    unassigned: list[dict] = []
    for op in ordered:
        existing_beat_id = str(op.get("beatId") or "")
        segment_index = segment_index_by_id.get(existing_beat_id)
        if segment_index is None:
            unassigned.append(op)
        else:
            buckets[segment_index].append(op)

    weights = [max(1.0, float(segment.get("drawBudgetFrames") or segment.get("duration") or 1)) for segment in segments]
    total_weight = sum(weights) or float(len(segments))
    cursor = 0
    for index in range(len(segments)):
        remaining_ops = len(unassigned) - cursor
        remaining_segments = len(segments) - index
        if remaining_ops <= 0:
            break
        if index == len(segments) - 1:
            take = remaining_ops
        else:
            target = round(len(unassigned) * (weights[index] / total_weight))
            take = max(1, min(remaining_ops - (remaining_segments - 1), target))
        group = unassigned[cursor : cursor + take]
        cursor += take
        buckets[index].extend(group)

    if cursor < len(unassigned):
        buckets[-1].extend(unassigned[cursor:])

    for index, segment in enumerate(segments):
        group = sorted(
            buckets[index],
            key=lambda op: (float(op.get("startFrame", 0)), str(op.get("id", ""))),
        )
        if not group:
            continue
        start = float(segment.get("startFrame", 0) or 0)
        end = float(segment.get("endFrame", duration) or duration)
        audio_start = float(segment.get("audioStartFrame", start) or start)
        audio_end = float(segment.get("audioEndFrame", end) or end)
        # Keep each drawing group inside its own beat. A large pre-audio lead makes the
        # hand appear to explain the next idea before the narration reaches it.
        lead_frames = 4.0 if index == 0 else 2.0
        window_start = max(0.0, start, audio_start - lead_frames)
        window_end = min(max(audio_end + 8.0, end - 2.0), max(1.0, duration - 1.0))
        window_end = max(window_start + 1.0, window_end)
        _retime_draw_ops_in_window(group, window_start, window_end, str(segment.get("id") or f"beat_{index}"))


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


def _is_cooking_topic_text(corpus: str) -> bool:
    return _contains_any(corpus, list(COOKING_TOPIC_TERMS))


def _cooking_prompt_suffix(corpus: str) -> str:
    if not _is_cooking_topic_text(corpus):
        return ""
    parts = [
        BOLD_EDITORIAL_IMAGE_DESCRIPTION_HINT,
        "Food/cooking accuracy: make the visual concrete and appetizing, not generic. Show correct cookware, ingredients, sauce color, steam, garnish, and real cooking state.",
        "Use real food colors: red/orange chili oil or sauce, white tofu cubes, brown minced meat, green scallions or garlic sprouts, warm highlights.",
        "Use one large food or cookware state as the primary visual anchor; avoid dense rows of many tiny pots, mini process boxes, or small unreadable recipe captions.",
        "Text policy: keep generated artwork text-free; the video renderer will add Chinese title, labels, ticks, underlines, and callouts.",
    ]
    if "mapo" in corpus or "麻婆" in corpus or "豆瓣" in corpus:
        parts.append(
            "For mapo tofu, always show recognizable Sichuan mapo tofu: white tofu cubes in glossy red chili-bean sauce, brown minced meat, green garlic sprouts/scallions, Sichuan pepper speckles, and red oil."
        )
    is_prep = _contains_any(corpus, list(COOKING_PREP_TERMS))
    is_final = _contains_any(corpus, list(COOKING_FINAL_TERMS))
    is_blanch = _contains_any(corpus, list(COOKING_BLANCH_TERMS))
    if is_final:
        parts.append("Finished scene: show a shallow white plate or bowl filled with the colorful finished dish.")
    elif is_prep:
        parts.append("Preparation scene: show cutting board and small ingredient bowls; do not use an empty pot as the main object.")
    elif _contains_any(corpus, list(COOKING_OVERVIEW_TERMS)):
        parts.append("Overview scene: show at most three large illustrated cooking states, or one finished dish with 3-5 flavor callouts; do not use a five-step row of tiny pots.")
    elif is_blanch:
        parts.append("Blanching scene: a pot of boiling clear water is acceptable only here, with tofu cubes and steam.")
    else:
        parts.append("Stir-fry/simmer/thickening scene: use a wide black Chinese wok or skillet on a burner, not a blue soup pot or empty stockpot.")
    return " ".join(parts)


def _is_dense_cooking_scene(scene: Scene) -> bool:
    corpus = _scene_corpus(scene)
    if not _is_cooking_topic_text(corpus):
        return False
    label_count = len(scene.diagram_plan.required_labels) if scene.diagram_plan else 0
    beat_count = len(scene.visual_beats or [])
    animation_item_count = sum(len(animation.items or []) for animation in scene.animations)
    dense_terms = _contains_any(corpus, list(COOKING_DENSE_LAYOUT_TERMS))
    too_many_labels = label_count >= 7 or animation_item_count >= 8
    too_many_beats = beat_count >= 5
    return dense_terms or too_many_labels or too_many_beats


def _mapo_cooking_story_specs(target_duration: int) -> list[dict]:
    duration = 18 if target_duration <= 95 else 20
    return [
        {
            "title": "风味先看懂",
            "learning_goal": "让观众先建立麻婆豆腐的好吃标准：红油亮、豆腐嫩、麻辣香。",
            "render_strategy": "hybrid",
            "visual_complexity": "medium",
            "board_mode": "clean_canvas",
            "hand_usage": "annotate",
            "visual_style": "marketing_doodle",
            "diagram_plan": {
                "kind": "overview_map",
                "layout": "一盘大号麻婆豆腐作为主视觉，周围只加 3 个大号侧边短标注和粉色强调箭头。",
                "required_labels": ["红油亮", "豆腐嫩", "麻辣香"],
            },
            "visual_beats": [
                {
                    "draw_intent": "直接呈现一盘大号麻婆豆腐，红油、白豆腐、肉末、葱绿和蒸汽都清楚。",
                    "narration": "好吃的麻婆豆腐，第一眼就该有红油的亮、豆腐的嫩，还有花椒和豆瓣酱顶上来的香。",
                    "required_labels": ["红油亮"],
                    "duration_estimate": 6,
                },
                {
                    "draw_intent": "在盘子边缘加粉色箭头和大字标注豆腐嫩、麻辣香。",
                    "narration": "这道菜不是把豆腐煮红就结束，关键是让豆腐完整吸味，汤汁还能稳稳挂住。",
                    "required_labels": ["豆腐嫩", "麻辣香"],
                    "duration_estimate": 6,
                },
            ],
            "image_description": (
                "large appetizing Sichuan mapo tofu in a shallow white bowl as the main subject, glossy red chili oil sauce, "
                "clear white tofu cubes, brown minced meat, green garlic sprouts or scallions, Sichuan pepper speckles, rising steam, "
                "bold editorial hand-drawn explainer style, thick imperfect black crayon marker outlines, warm off-white surface, "
                "sunny yellow halo behind the bowl, coral pink accent arrows around it, generous blank margins, text-free artwork"
            ),
            "duration_estimate": duration,
        },
        {
            "title": "备料要分工",
            "learning_goal": "让观众知道关键食材各自负责什么，不把食材画成泛泛一堆。",
            "render_strategy": "hybrid",
            "visual_complexity": "medium",
            "board_mode": "clean_canvas",
            "hand_usage": "annotate",
            "visual_style": "marketing_doodle",
            "diagram_plan": {
                "kind": "structure",
                "layout": "大切板和几个大碗占主体，豆腐、肉末、豆瓣酱、花椒、蒜苗、水淀粉清楚分组。",
                "required_labels": ["豆腐", "豆瓣酱", "水淀粉"],
            },
            "visual_beats": [
                {
                    "draw_intent": "呈现大切板、豆腐块和几只大食材碗，颜色和形状要容易认出。",
                    "narration": "备料像给乐队分声部：豆腐负责口感，肉末和豆瓣酱负责底味，花椒和蒜苗负责最后的香气。",
                    "required_labels": ["豆腐", "豆瓣酱"],
                    "duration_estimate": 6,
                },
                {
                    "draw_intent": "用粉色勾选和短箭头强调水淀粉这一小碗。",
                    "narration": "水淀粉看着不起眼，但后面能不能挂汁、能不能亮起来，很大程度就靠它收尾。",
                    "required_labels": ["水淀粉"],
                    "duration_estimate": 6,
                },
            ],
            "image_description": (
                "large kitchen prep scene with cutting board and big ingredient bowls: neat white tofu cubes, minced meat, red doubanjiang chili bean paste, "
                "Sichuan pepper, chopped garlic sprouts or scallions, small bowl of starch slurry, bold editorial hand-drawn explainer style, "
                "thick black crayon outlines, warm off-white surface, coral pink check marks and arrows, sunny yellow highlight blob, text-free artwork, no tiny labels"
            ),
            "duration_estimate": duration,
        },
        {
            "title": "红油先炒香",
            "learning_goal": "让观众理解炒肉末和豆瓣酱出红油，是颜色和底香的来源。",
            "render_strategy": "hybrid",
            "visual_complexity": "medium",
            "board_mode": "clean_canvas",
            "hand_usage": "annotate",
            "visual_style": "marketing_doodle",
            "diagram_plan": {
                "kind": "process",
                "layout": "一个大号黑色炒锅占主体，锅里肉末、豆瓣酱和红油正在被小火炒香。",
                "required_labels": ["小火", "炒出红油", "底香"],
            },
            "visual_beats": [
                {
                    "draw_intent": "呈现一个大号黑色炒锅，锅里有红豆瓣酱、肉末和红油，不用小锅流程图。",
                    "narration": "先小火把肉末和豆瓣酱炒香，红油出来以后，这道菜的颜色和底香才真正站住。",
                    "required_labels": ["小火", "炒出红油"],
                    "duration_estimate": 7,
                },
                {
                    "draw_intent": "在锅边加粉色短箭头和黄色下划线，强调底香。",
                    "narration": "这一步急不得，火太猛容易糊，火太轻又出不来香味，像把音量拧到刚刚好。",
                    "required_labels": ["底香"],
                    "duration_estimate": 6,
                },
            ],
            "image_description": (
                "one large wide black Chinese wok on a burner, minced meat and red doubanjiang frying in glossy red chili oil, steam and aroma lines, "
                "bold editorial hand-drawn explainer style, thick imperfect black marker outlines, coral pink motion arrows, sunny yellow highlight behind the wok, "
                "warm off-white surface, text-free artwork, no blue soup pot, no tiny process boxes"
            ),
            "duration_estimate": duration,
        },
        {
            "title": "豆腐烧入味",
            "learning_goal": "让观众掌握豆腐下锅后的状态：轻推、慢烧、让汤汁进入豆腐。",
            "render_strategy": "hybrid",
            "visual_complexity": "medium",
            "board_mode": "clean_canvas",
            "hand_usage": "annotate",
            "visual_style": "marketing_doodle",
            "diagram_plan": {
                "kind": "process",
                "layout": "一个大号炒锅里豆腐块在红色汤汁中慢烧，旁边只写轻推和烧透两个短标签。",
                "required_labels": ["轻推", "烧透", "吸味"],
            },
            "visual_beats": [
                {
                    "draw_intent": "呈现大炒锅里的白豆腐块、红汤汁、肉末和蒸汽，豆腐块要完整。",
                    "narration": "豆腐下锅以后别粗暴翻炒，轻轻推着走，让它在红汤里慢慢吸味。",
                    "required_labels": ["轻推", "吸味"],
                    "duration_estimate": 7,
                },
                {
                    "draw_intent": "用粉色弧形箭头表现轻推，用黄色短线强调烧透。",
                    "narration": "烧透不是把豆腐煮散，而是让每一块外面有汁、里面也有味。",
                    "required_labels": ["烧透"],
                    "duration_estimate": 6,
                },
            ],
            "image_description": (
                "large wide black wok with white tofu cubes simmering in red chili-bean sauce, brown minced meat, steam, gentle curved stirring motion, "
                "bold editorial hand-drawn explainer style, thick black crayon outlines, coral pink curved arrows, sunny yellow glow, warm off-white surface, "
                "text-free artwork, no stockpot, no empty cookware"
            ),
            "duration_estimate": duration,
        },
        {
            "title": "勾芡才挂汁",
            "learning_goal": "让观众理解水淀粉让汤汁包住豆腐，形成亮、浓、挂汁的口感。",
            "render_strategy": "hybrid",
            "visual_complexity": "medium",
            "board_mode": "clean_canvas",
            "hand_usage": "annotate",
            "visual_style": "marketing_doodle",
            "diagram_plan": {
                "kind": "comparison",
                "layout": "一个大号近景：红亮汤汁包住豆腐块，旁边用粉色勾和短箭头强调挂汁。",
                "required_labels": ["两次勾芡", "挂汁", "亮起来"],
            },
            "visual_beats": [
                {
                    "draw_intent": "呈现近景豆腐块被红亮酱汁包住，水淀粉从小碗倒入锅中。",
                    "narration": "勾芡像给豆腐披一层薄薄的外衣，让汤汁不再各走各的，而是贴住豆腐。",
                    "required_labels": ["挂汁"],
                    "duration_estimate": 7,
                },
                {
                    "draw_intent": "补粉色勾选和黄色下划线，强调两次勾芡和亮起来。",
                    "narration": "分两次加水淀粉更稳，第一次让汤变稠，第二次让芡汁更均匀、更亮。",
                    "required_labels": ["两次勾芡", "亮起来"],
                    "duration_estimate": 7,
                },
            ],
            "image_description": (
                "close-up of mapo tofu in a wide wok, glossy red sauce coating white tofu cubes, small bowl pouring starch slurry, sauce looks shiny and thick, "
                "brown minced meat and green scallions, bold editorial hand-drawn explainer style, thick black marker outlines, coral pink check marks, sunny yellow highlight, "
                "warm off-white surface, text-free artwork, no dense diagram"
            ),
            "duration_estimate": duration,
        },
    ]


def _apply_mapo_cooking_defaults(storyboard: Storyboard, target_duration: int) -> Storyboard:
    corpus = _storyboard_scene_corpus(storyboard)
    if not _is_cooking_topic_text(corpus) or not _contains_any(corpus, ["麻婆", "mapo", "豆瓣", "豆腐"]):
        return storyboard
    # Mapo tofu is our regression case for rich food how-to videos. Use the
    # curated large-subject storyboard by default so the image model creates
    # appetizing artwork, while readable Chinese text remains renderer-controlled.
    return _replace_with_specs(storyboard, _mapo_cooking_story_specs(target_duration))


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
    if _contains_semiconductor_topic(corpus) or _contains_any(
        corpus,
        ["v_g", "v_ds", "w_eff", "阈值", "短沟道"],
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


def _scene_extra(scene: Scene, name: str, default: object = None) -> object:
    aliases = [name]
    if "_" in name:
        parts = name.split("_")
        aliases.append(parts[0] + "".join(part.capitalize() for part in parts[1:]))
    else:
        aliases.append(re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower())
    aliases = list(dict.fromkeys(alias for alias in aliases if alias))

    for alias in aliases:
        value = getattr(scene, alias, default)
        if value is not default and value is not None:
            return value

    extra = getattr(scene, "model_extra", None)
    if isinstance(extra, dict):
        for alias in aliases:
            if alias in extra:
                return extra[alias]
    return default


def _audio_segments_for_scene(scene: Scene, fps: int) -> tuple[list[dict], int, int]:
    raw_segments = (
        _scene_extra(scene, "audioSegments")
        or _scene_extra(scene, "audio_segments")
        or _scene_extra(scene, "audio_segments_json")
        or []
    )
    raw_timing = _scene_extra(scene, "timingPlan") or _scene_extra(scene, "timing_plan") or {}
    transition_frames = 0
    if isinstance(raw_timing, dict):
        transition_frames = max(0, min(18, int(raw_timing.get("transitionFrames") or raw_timing.get("transition_frames") or 0)))
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
            audio_start = int(round(float(raw.get("audioStartFrame") or raw.get("audio_start_frame") or start)))
            audio_start = max(start, min(end - 1, audio_start))
            audio_end = int(round(float(raw.get("audioEndFrame") or raw.get("audio_end_frame") or (audio_start + audio_duration))))
            audio_end = max(audio_start + 1, min(end, audio_end))
            segments.append(
                {
                    "id": _clean_text(raw.get("id")) or f"beat_{index}",
                    "index": index,
                    "startFrame": start,
                    "endFrame": end,
                    "duration": end - start,
                    "audioStartFrame": audio_start,
                    "audioEndFrame": audio_end,
                    "audioSequenceDuration": max(1, end - audio_start),
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
    board_mode = (_clean_text(_scene_extra(scene, "board_mode") or _scene_extra(scene, "boardMode")) or "whiteboard").lower()
    hand_usage = (_clean_text(_scene_extra(scene, "hand_usage") or _scene_extra(scene, "handUsage")) or "trace").lower()
    video_style = _canonical_video_style(
        _scene_extra(scene, "video_style") or _scene_extra(scene, "videoStyle") or _scene_extra(scene, "visual_style")
    )
    visual_style = (_clean_text(_scene_extra(scene, "visual_style") or _scene_extra(scene, "visualStyle")) or "teacher_whiteboard").lower()
    allowed_visual_styles = {
        "teacher_whiteboard",
        "marketing_doodle",
        "math_chalkboard",
        "technical_reference",
        "modern_minimal",
        "editorial",
        "playful",
        "sharpie",
    }
    if board_mode not in {"whiteboard", "chalkboard", "clean_canvas", "reference"}:
        board_mode = "whiteboard"
    if hand_usage not in {"trace", "annotate", "none"}:
        hand_usage = "trace"
    if visual_style not in allowed_visual_styles:
        visual_style = "teacher_whiteboard"
    if board_mode == "chalkboard" or visual_style == "math_chalkboard":
        board_mode = "chalkboard"
        hand_usage = "none"
        visual_style = "math_chalkboard"
    if video_style in {"chalkboard_bw", "chalkboard_color"}:
        board_mode = "chalkboard"
        hand_usage = "none"
        visual_style = "math_chalkboard"
    left = width * 0.065
    top = height * 0.055
    diagram_left = width * 0.18
    diagram_top = height * 0.19
    board_center_x = width * 0.50
    board_draw_w = width * 0.64
    board_draw_h = height * 0.56
    accent_palette_by_style = {
        "chalkboard_bw": ["#F4F2E8"],
        "chalkboard_color": ["#5DE6FF", "#F2E85C", "#A8F06A"],
        "modern_minimal": ["#5D6FE8", "#8790A0"],
        "technical_blueprint": ["#7CC7E8", "#D66767", "#A5D6E8"],
        "editorial": ["#D85C4A", "#D9A514", "#111318"],
        "whiteboard": ["#2F6FB2", "#3F8F68", "#F3BE22", "#D85C4A"],
        "playful": ["#F06E6E", "#F1C84B", "#42B8A7", "#7A65B8"],
        "sharpie": ["#111318", "#2F6FB2", "#F3BE22", "#D85C4A"],
    }
    accent_colors = accent_palette_by_style.get(video_style, ["#FFD65A", "#FF4F7B", "#A8D8F0", "#BFE3C0", "#D7C5F7"])
    accent = accent_colors[scene_index % len(accent_colors)]
    is_chalkboard = board_mode == "chalkboard"
    ink = "#F4F2E8" if is_chalkboard else "#1D1D1F"
    blue = "#5DE6FF" if is_chalkboard else "#2F6FB2"
    red = "#FF6FAE" if is_chalkboard else "#FF4F7B"
    green = "#A8F06A" if is_chalkboard else "#3F8F68"
    violet = "#C6A7FF" if is_chalkboard else "#6E58B5"
    yellow = "#F2E85C" if is_chalkboard else "#F3BE22"
    if video_style == "technical_blueprint":
        ink, blue, red, green, violet, yellow = "#B8D7E8", "#7CC7E8", "#D66767", "#8AC7B4", "#9FB7D8", "#D7B85A"
    elif video_style == "modern_minimal":
        ink, blue, red, green, violet, yellow = "#22242A", "#5D6FE8", "#C85C5C", "#5E8E77", "#6A5ACD", "#D9B84C"
    elif video_style == "editorial":
        ink, blue, red, green, violet, yellow = "#121212", "#2F5E8E", "#D85C4A", "#4F8068", "#6E58B5", "#D9A514"
    elif video_style == "playful":
        ink, blue, red, green, violet, yellow = "#34302B", "#42B8D0", "#F06E6E", "#60B56A", "#7A65B8", "#F1C84B"
    elif video_style == "sharpie":
        ink, blue, red, green, violet, yellow = "#111111", "#2F6FB2", "#D85C4A", "#3F8F68", "#6E58B5", "#F3BE22"
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
        beat_id: str | None = None,
    ) -> None:
        op_id = f"s{scene_index}_text_{len(texts)}"
        safe_text = _short_text(text, max_chars)
        text_max_width = max_width if max_width is not None else width - x - 70
        safe_start, end = fit_timing(start, frames)
        draw_op = {
            "id": op_id,
            "kind": "text",
            "startFrame": safe_start,
            "endFrame": end,
            "points": _text_stroke_points(safe_text, x, y, font_size, text_max_width),
        }
        if beat_id:
            draw_op["beatId"] = beat_id
        draw_ops.append(draw_op)
        has_cjk = bool(re.search(r"[\u3400-\u9fff]", safe_text))
        has_many_latin = len(re.findall(r"[A-Za-z0-9]", safe_text)) >= 3
        marker_width = max(
            2.2,
            min(5.2, font_size * (0.052 if font_size >= 54 else 0.066)),
        )
        if has_many_latin and not has_cjk:
            marker_width = max(2.0, min(4.2, font_size * 0.044))
        elif has_many_latin:
            marker_width = max(2.4, marker_width * 0.78)
        texts.append(
            {
                "opId": op_id,
                "text": safe_text,
                "x": round(x, 1),
                "y": round(y, 1),
                "fontSize": font_size,
                "color": color,
                "maxWidth": round(text_max_width, 1),
                "markerStrokeWidth": round(marker_width, 1),
                "markerFillOpacity": (0.48 if has_many_latin else 0.74) if font_size >= 54 else (0.56 if has_many_latin else 0.86),
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
            add_stroke(
                "emphasis_underline",
                underline_points,
                yellow,
                max(3, round(font_size * 0.075)),
                end + 1,
                8,
                beat_id=beat_id,
            )

    def add_stroke(
        role: str,
        points: list[dict[str, float]],
        color: str,
        stroke_width: int,
        start: int,
        frames: int,
        close: bool = False,
        beat_id: str | None = None,
    ) -> None:
        op_id = f"s{scene_index}_stroke_{len(strokes)}"
        safe_start, end = fit_timing(start, frames)
        draw_op = {
            "id": op_id,
            "kind": "path",
            "startFrame": safe_start,
            "endFrame": end,
            "points": points,
        }
        if beat_id:
            draw_op["beatId"] = beat_id
        draw_ops.append(draw_op)
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
        beat_id: str | None = None,
    ) -> None:
        add_stroke(role, points, color, stroke_width, start, frames, beat_id=beat_id)
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
            add_stroke("arrowhead", [side, _point(end["x"], end["y"])], color, stroke_width, head_start, 7, beat_id=beat_id)

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
        beat_id: str | None = None,
    ) -> int:
        add_stroke(role, _rect_points(x, y, w, h), color, 4, start, 18, close=True, beat_id=beat_id)
        add_text(label, x + w * 0.14, y + h * 0.25, font_size or body_size, color, start + 12, 22, w * 0.78, beat_id=beat_id)
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
        beat_id: str | None = None,
    ) -> int:
        add_stroke(role, _circle_points(cx, cy, rx, ry, count=24), color, 4, start, 18, beat_id=beat_id)
        add_text(label, cx - rx * 0.55, cy - ry * 0.28, font_size or body_size, color, start + 12, 22, rx * 1.1, beat_id=beat_id)
        return start + 36

    def beat_id_for(index: int) -> str | None:
        if 0 <= index < len(audio_segments):
            raw_id = audio_segments[index].get("id")
            return str(raw_id) if raw_id else f"beat_{index}"
        return f"beat_{index}" if audio_segments else None

    def draw_star(cx: float, cy: float, radius: float, color: str, start: int, frames: int, beat_id: str | None = None) -> int:
        points: list[dict[str, float]] = []
        for index in range(11):
            angle = -math.pi / 2 + index * math.pi / 5
            local_radius = radius if index % 2 == 0 else radius * 0.42
            points.append(_point(cx + math.cos(angle) * local_radius, cy + math.sin(angle) * local_radius))
        add_stroke("star", points, color, 4, start, frames, close=True, beat_id=beat_id)
        return start + frames + 3

    def draw_person_icon(cx: float, cy: float, color: str, start: int, scale: float = 1.0, beat_id: str | None = None) -> int:
        local = start
        add_stroke("person", _circle_points(cx, cy, width * 0.018 * scale, height * 0.028 * scale, count=14), color, 3, local, 7, beat_id=beat_id)
        local += 8
        add_stroke("person", _line_points(cx, cy + height * 0.030 * scale, cx, cy + height * 0.095 * scale, count=4), color, 3, local, 6, beat_id=beat_id)
        add_stroke("person", _line_points(cx - width * 0.030 * scale, cy + height * 0.055 * scale, cx + width * 0.030 * scale, cy + height * 0.055 * scale, count=4), color, 3, local + 4, 6, beat_id=beat_id)
        add_stroke("person", _line_points(cx, cy + height * 0.095 * scale, cx - width * 0.026 * scale, cy + height * 0.145 * scale, count=4), color, 3, local + 8, 6, beat_id=beat_id)
        add_stroke("person", _line_points(cx, cy + height * 0.095 * scale, cx + width * 0.026 * scale, cy + height * 0.145 * scale, count=4), color, 3, local + 12, 6, beat_id=beat_id)
        return local + 20

    def build_seven_habits_overview(start: int) -> int:
        cursor = start
        b0 = beat_id_for(0)
        b1 = beat_id_for(1)
        x = board_center_x - width * 0.25
        y = diagram_top + height * 0.31
        step_w = width * 0.19
        step_h = height * 0.095
        step_points = [
            _point(x, y + step_h * 2),
            _point(x + step_w, y + step_h * 2),
            _point(x + step_w, y + step_h),
            _point(x + step_w * 2, y + step_h),
            _point(x + step_w * 2, y),
            _point(x + step_w * 3, y),
            _point(x + step_w * 3, y + step_h * 3),
            _point(x, y + step_h * 3),
            _point(x, y + step_h * 2),
        ]
        add_stroke("staircase", step_points, ink, 5, cursor, 34, beat_id=b0)
        cursor += 38
        step_labels = [
            ("\u4f9d\u8d56", x + step_w * 0.25, y + step_h * 2.18, red),
            ("\u72ec\u7acb", x + step_w * 1.22, y + step_h * 1.18, blue),
            ("\u4e92\u76f8\u4f9d\u8d56", x + step_w * 2.06, y + step_h * 0.18, green),
        ]
        for label, tx, ty, color in step_labels:
            add_text(label, tx, ty, body_size, color, cursor, 18, step_w * 0.80, emphasis=True, max_chars=4, beat_id=b0)
            cursor += 14
        add_arrow(_curve_points(x - width * 0.03, y + step_h * 2.80, x + step_w * 3.04, y - height * 0.02, count=20, wave=-height * 0.035), blue, 5, cursor, 26, role="growth_arrow", beat_id=b0)
        cursor += 30
        groups = [
            ("\u4e60\u60ef1-3", "\u4e3b\u52a8  \u7ec8\u5c40  \u8981\u4e8b", x - width * 0.16, y + step_h * 1.05, blue),
            ("\u4e60\u60ef4-6", "\u53cc\u8d62  \u503e\u542c  \u7edf\u5408", x + step_w * 2.25, y + step_h * 1.28, green),
        ]
        for title, detail, gx, gy, color in groups:
            cursor = add_node_box(title, gx, gy, width * 0.14, height * 0.070, cursor, color, role="habit_group", font_size=max(18, body_size - 8), beat_id=b1)
            add_text(detail, gx - width * 0.015, gy + height * 0.086, max(17, body_size - 11), color, cursor, 22, width * 0.20, max_chars=12, beat_id=b1)
            cursor += 24
        cx = x + step_w * 1.55
        cy = y - height * 0.080
        add_stroke("renew_badge", _circle_points(cx, cy, width * 0.050, height * 0.055, count=20), violet, 4, cursor, 12, beat_id=b1)
        add_text("\u4e60\u60ef7", cx - width * 0.030, cy - height * 0.018, max(18, body_size - 9), violet, cursor + 9, 16, width * 0.08, max_chars=4, beat_id=b1)
        add_arrow(_arc_points(cx, cy + height * 0.10, width * 0.34, height * 0.27, -math.pi * 0.80, math.pi * 0.10, count=24), violet, 4, cursor + 22, 26, role="renew_orbit", beat_id=b1)
        cursor += 55
        for index, (mx, my, color) in enumerate([(x - 32, y + step_h * 2.85, red), (x + step_w * 1.48, y + step_h * 1.06, yellow), (x + step_w * 3.10, y - 8, green)]):
            add_stroke("spark", _line_points(mx, my, mx + 18, my - 20, count=3), color, 3, cursor + index * 5, 5, beat_id=b1)
        return cursor + 24

    def build_proactive_circles(start: int) -> int:
        cursor = start
        b0 = beat_id_for(0)
        b1 = beat_id_for(1)
        cx = board_center_x + width * 0.12
        cy = diagram_top + height * 0.25
        add_stroke("concern_circle", _circle_points(cx, cy, width * 0.19, height * 0.22, count=34), ink, 4, cursor, 22, beat_id=b0)
        cursor += 24
        add_stroke("influence_circle", _circle_points(cx, cy, width * 0.105, height * 0.125, count=28), green, 5, cursor, 18, beat_id=b0)
        cursor += 22
        add_text("\u5f71\u54cd\u5708", cx - width * 0.052, cy - height * 0.030, body_size, green, cursor, 20, width * 0.14, emphasis=True, max_chars=4, beat_id=b0)
        add_text("\u5173\u6ce8\u5708", cx - width * 0.045, cy - height * 0.205, body_size, ink, cursor + 10, 20, width * 0.13, max_chars=4, beat_id=b0)
        cursor += 30
        add_text("\u6211\u80fd\u63a7\u5236", cx - width * 0.070, cy + height * 0.055, max(18, body_size - 8), green, cursor, 18, width * 0.14, max_chars=6, beat_id=b0)
        add_text("\u5173\u5fc3\u4f46\u63a7\u5236\u4e0d\u4e86", cx - width * 0.160, cy + height * 0.175, max(17, body_size - 10), red, cursor + 8, 20, width * 0.32, max_chars=10, beat_id=b0)
        cursor += 28
        y = cy + height * 0.33
        x0 = board_center_x - width * 0.31
        x1 = board_center_x + width * 0.31
        add_node_box("\u523a\u6fc0", x0, y, width * 0.105, height * 0.065, cursor, red, role="stimulus", font_size=max(18, body_size - 8), beat_id=b1)
        add_node_box("\u53cd\u5e94", x1 - width * 0.105, y, width * 0.105, height * 0.065, cursor + 8, green, role="response", font_size=max(18, body_size - 8), beat_id=b1)
        cursor += 24
        add_arrow(_line_points(x0 + width * 0.120, y + height * 0.033, x1 - width * 0.135, y + height * 0.033, count=12), ink, 4, cursor, 16, role="choice_line", beat_id=b1)
        cursor += 20
        choice_cx = board_center_x
        choice_cy = y + height * 0.033
        add_stroke("choice_space", _circle_points(choice_cx, choice_cy, width * 0.055, height * 0.052, count=20), blue, 4, cursor, 12, beat_id=b1)
        add_text("\u9009\u62e9", choice_cx - width * 0.030, choice_cy - height * 0.020, max(18, body_size - 8), blue, cursor + 8, 16, width * 0.08, emphasis=True, max_chars=4, beat_id=b1)
        cursor += 28
        draw_star(cx + width * 0.145, cy - height * 0.165, width * 0.023, yellow, cursor, 8, beat_id=b1)
        return cursor + 18

    def build_begin_with_end(start: int) -> int:
        cursor = start
        b0 = beat_id_for(0)
        b1 = beat_id_for(1)
        x0 = board_center_x - width * 0.30
        y0 = diagram_top + height * 0.39
        x1 = board_center_x + width * 0.31
        y1 = diagram_top + height * 0.17
        cursor = add_node_circle("\u73b0\u5728", x0, y0, width * 0.055, height * 0.050, cursor, blue, font_size=max(18, body_size - 7), beat_id=b0)
        path = _curve_points(x0 + width * 0.060, y0 - height * 0.010, x1 - width * 0.080, y1 + height * 0.050, count=24, wave=height * 0.09)
        add_arrow(path, green, 5, cursor, 28, role="vision_path", beat_id=b0)
        cursor += 32
        for index, point in enumerate([path[6], path[12], path[18]]):
            add_stroke("principle_milestone", _circle_points(point["x"], point["y"], width * 0.020, height * 0.028, count=14), violet if index % 2 else blue, 4, cursor, 8, beat_id=b0)
            add_text("\u539f\u5219", point["x"] - width * 0.027, point["y"] + height * 0.034, max(16, body_size - 11), violet, cursor + 5, 12, width * 0.07, max_chars=4, beat_id=b0)
            cursor += 15
        cursor = add_node_circle("\u613f\u666f/\u4f7f\u547d", x1, y1, width * 0.075, height * 0.060, cursor, red, font_size=max(18, body_size - 8), beat_id=b0)
        compass_cx = x1 - width * 0.02
        compass_cy = y1 - height * 0.18
        add_stroke("compass", _circle_points(compass_cx, compass_cy, width * 0.055, height * 0.060, count=24), ink, 4, cursor, 16, beat_id=b1)
        cursor += 18
        add_stroke("compass_needle", [_point(compass_cx, compass_cy - height * 0.045), _point(compass_cx + width * 0.022, compass_cy + height * 0.008), _point(compass_cx, compass_cy + height * 0.045), _point(compass_cx - width * 0.014, compass_cy - height * 0.006), _point(compass_cx, compass_cy - height * 0.045)], red, 4, cursor, 16, close=True, beat_id=b1)
        cursor += 18
        add_text("\u6307\u5357\u9488", compass_cx - width * 0.050, compass_cy - height * 0.115, max(18, body_size - 8), ink, cursor, 16, width * 0.12, max_chars=4, beat_id=b1)
        add_arrow(_curve_points(compass_cx - width * 0.060, compass_cy + height * 0.045, path[12]["x"], path[12]["y"], count=12, wave=-height * 0.025), violet, 4, cursor + 10, 16, role="principle_pointer", beat_id=b1)
        cursor += 34
        add_text("\u5148\u5b9a\u65b9\u5411", board_center_x - width * 0.070, diagram_top + height * 0.53, body_size, yellow, cursor, 20, width * 0.17, emphasis=True, max_chars=6, beat_id=b1)
        return cursor + 26

    def build_time_matrix_rich(start: int) -> int:
        cursor = start
        b0 = beat_id_for(0)
        b1 = beat_id_for(1)
        x = board_center_x - width * 0.27
        y = diagram_top + height * 0.06
        w = width * 0.54
        h = height * 0.46
        mid_x = x + w * 0.5
        mid_y = y + h * 0.5
        add_stroke("matrix_frame", _rect_points(x, y, w, h), ink, 5, cursor, 20, close=True, beat_id=b0)
        cursor += 22
        add_stroke("matrix_axis", _line_points(mid_x, y, mid_x, y + h, count=7), ink, 4, cursor, 12, beat_id=b0)
        add_stroke("matrix_axis", _line_points(x, mid_y, x + w, mid_y, count=7), ink, 4, cursor + 7, 12, beat_id=b0)
        cursor += 24
        add_text("\u91cd\u8981", x - width * 0.065, y + h * 0.14, body_size, blue, cursor, 16, width * 0.08, max_chars=4, beat_id=b0)
        add_text("\u4e0d\u91cd\u8981", x - width * 0.080, y + h * 0.68, max(18, body_size - 7), ink, cursor + 6, 16, width * 0.10, max_chars=4, beat_id=b0)
        add_text("\u7d27\u6025", x + w * 0.18, y + h + height * 0.030, body_size, red, cursor + 12, 16, width * 0.08, max_chars=4, beat_id=b0)
        add_text("\u4e0d\u7d27\u6025", x + w * 0.68, y + h + height * 0.030, max(18, body_size - 7), green, cursor + 18, 16, width * 0.10, max_chars=4, beat_id=b0)
        cursor += 38
        quadrants = [
            ("\u5371\u673a", x + w * 0.14, y + h * 0.18, red, "alarm"),
            ("\u9884\u9632/\u89c4\u5212", x + w * 0.60, y + h * 0.18, green, "star"),
            ("\u5e72\u6270", x + w * 0.16, y + h * 0.66, yellow, "noise"),
            ("\u6d6a\u8d39", x + w * 0.66, y + h * 0.66, violet, "waste"),
        ]
        for index, (label, tx, ty, color, role_name) in enumerate(quadrants):
            add_text(label, tx, ty, max(21, body_size - 4), color, cursor, 20, w * 0.28, emphasis=index == 1, max_chars=8, beat_id=b1)
            if role_name == "star":
                draw_star(tx + w * 0.18, ty + height * 0.020, width * 0.028, yellow, cursor + 16, 10, beat_id=b1)
                add_stroke("focus_circle", _circle_points(tx + w * 0.10, ty + height * 0.030, w * 0.18, h * 0.16, count=22), green, 4, cursor + 26, 12, beat_id=b1)
            elif role_name == "alarm":
                add_stroke("alarm", _line_points(tx + w * 0.11, ty - height * 0.035, tx + w * 0.11, ty - height * 0.070, count=3), red, 4, cursor + 15, 6, beat_id=b1)
                add_stroke("alarm", _line_points(tx + w * 0.09, ty - height * 0.057, tx + w * 0.13, ty - height * 0.057, count=3), red, 4, cursor + 19, 6, beat_id=b1)
            cursor += 24
        add_arrow(_curve_points(x + w * 0.22, y + h * 0.78, x + w * 0.70, y + h * 0.30, count=15, wave=-height * 0.025), blue, 4, cursor, 18, role="priority_shift", beat_id=b1)
        cursor += 24
        add_text("\u8981\u4e8b\u7b2c\u4e00", x + w * 0.58, y + h * 0.49, body_size, violet, cursor, 22, width * 0.18, emphasis=True, max_chars=6, beat_id=b1)
        return cursor + 30

    def build_interdependence_rich(start: int) -> int:
        cursor = start
        b0 = beat_id_for(0)
        b1 = beat_id_for(1)
        b2 = beat_id_for(2)
        sx = board_center_x - width * 0.31
        sy = diagram_top + height * 0.15
        add_stroke("scale_base", _line_points(sx, sy + height * 0.145, sx + width * 0.18, sy + height * 0.145, count=5), ink, 4, cursor, 8, beat_id=b0)
        add_stroke("scale_stem", _line_points(sx + width * 0.09, sy + height * 0.145, sx + width * 0.09, sy + height * 0.015, count=5), ink, 4, cursor + 6, 8, beat_id=b0)
        add_stroke("scale_bar", _line_points(sx + width * 0.015, sy + height * 0.035, sx + width * 0.165, sy + height * 0.035, count=5), ink, 4, cursor + 12, 8, beat_id=b0)
        add_stroke("scale_pan", _arc_points(sx + width * 0.025, sy + height * 0.055, width * 0.045, height * 0.035, 0.05, math.pi - 0.05, count=10), blue, 4, cursor + 19, 9, beat_id=b0)
        add_stroke("scale_pan", _arc_points(sx + width * 0.155, sy + height * 0.055, width * 0.045, height * 0.035, 0.05, math.pi - 0.05, count=10), green, 4, cursor + 25, 9, beat_id=b0)
        cursor += 40
        add_text("\u6211", sx + width * 0.004, sy + height * 0.084, max(18, body_size - 8), blue, cursor, 10, width * 0.05, max_chars=2, beat_id=b0)
        add_text("\u4f60", sx + width * 0.137, sy + height * 0.084, max(18, body_size - 8), green, cursor + 4, 10, width * 0.05, max_chars=2, beat_id=b0)
        add_text("\u53cc\u8d62", sx + width * 0.060, sy - height * 0.035, body_size, green, cursor + 8, 18, width * 0.10, emphasis=True, max_chars=4, beat_id=b0)
        cursor += 28
        seesaw_x = sx + width * 0.22
        add_stroke("seesaw", _line_points(seesaw_x, sy + height * 0.12, seesaw_x + width * 0.18, sy + height * 0.045, count=6), red, 4, cursor, 10, beat_id=b0)
        add_stroke("seesaw_base", [_point(seesaw_x + width * 0.09, sy + height * 0.085), _point(seesaw_x + width * 0.07, sy + height * 0.14), _point(seesaw_x + width * 0.11, sy + height * 0.14), _point(seesaw_x + width * 0.09, sy + height * 0.085)], ink, 3, cursor + 8, 8, close=True, beat_id=b0)
        add_text("\u8f93\u8d62", seesaw_x + width * 0.055, sy + height * 0.150, max(18, body_size - 8), red, cursor + 15, 14, width * 0.08, max_chars=4, beat_id=b0)
        cursor += 32
        px = board_center_x + width * 0.10
        py = diagram_top + height * 0.09
        draw_person_icon(px, py + height * 0.06, blue, cursor, 1.1, b1)
        draw_person_icon(px + width * 0.22, py + height * 0.06, green, cursor + 8, 1.1, b1)
        add_stroke("big_ear", _arc_points(px + width * 0.042, py + height * 0.045, width * 0.025, height * 0.040, -math.pi * 0.55, math.pi * 0.65, count=12), blue, 5, cursor + 28, 10, beat_id=b1)
        add_stroke("mouth", _arc_points(px + width * 0.205, py + height * 0.055, width * 0.025, height * 0.018, 0, math.pi, count=8), green, 4, cursor + 36, 8, beat_id=b1)
        add_text("\u503e\u542c", px - width * 0.020, py + height * 0.225, max(18, body_size - 8), blue, cursor + 42, 14, width * 0.08, max_chars=4, beat_id=b1)
        add_text("\u8868\u8fbe", px + width * 0.185, py + height * 0.225, max(18, body_size - 8), green, cursor + 48, 14, width * 0.08, max_chars=4, beat_id=b1)
        add_arrow(_curve_points(px + width * 0.070, py + height * 0.08, px + width * 0.180, py + height * 0.08, count=10, wave=-height * 0.015), violet, 4, cursor + 54, 12, role="understand_arrow", beat_id=b1)
        add_text("\u7406\u89e3", px + width * 0.096, py + height * 0.025, max(18, body_size - 8), violet, cursor + 62, 14, width * 0.08, max_chars=4, beat_id=b1)
        cursor += 86
        bx = board_center_x - width * 0.21
        by = diagram_top + height * 0.45
        add_stroke("puzzle_circle", _circle_points(bx, by, width * 0.045, height * 0.050, count=18), blue, 4, cursor, 12, beat_id=b2)
        add_stroke("puzzle_square", _rect_points(bx + width * 0.055, by - height * 0.045, width * 0.090, height * 0.090), green, 4, cursor + 8, 12, close=True, beat_id=b2)
        draw_star(bx + width * 0.205, by, width * 0.046, yellow, cursor + 18, 12, beat_id=b2)
        add_arrow(_line_points(bx + width * 0.145, by, bx + width * 0.160, by, count=3), ink, 3, cursor + 22, 8, beat_id=b2)
        add_text("1+1>2", bx + width * 0.160, by + height * 0.070, body_size, green, cursor + 32, 18, width * 0.12, emphasis=True, max_chars=5, beat_id=b2)
        add_node_box("\u59a5\u534f", bx + width * 0.36, by - height * 0.046, width * 0.11, height * 0.080, cursor + 12, violet, role="compromise", font_size=max(18, body_size - 8), beat_id=b2)
        cursor += 64
        return cursor

    def build_renewal_summary_rich(start: int) -> int:
        cursor = start
        b0 = beat_id_for(0)
        b1 = beat_id_for(1)
        cx = board_center_x
        cy = diagram_top + height * 0.22
        rx = width * 0.19
        ry = height * 0.18
        labels = [
            ("\u8eab\u4f53", cx, cy - ry, blue, "run"),
            ("\u5fc3\u667a", cx + rx, cy, green, "book"),
            ("\u7cbe\u795e", cx, cy + ry, violet, "med"),
            ("\u793e\u4f1a\u60c5\u611f", cx - rx, cy, red, "hand"),
        ]
        for index, (label, nx, ny, color, icon) in enumerate(labels):
            cursor = add_node_circle(label, nx, ny, width * 0.066, height * 0.055, cursor, color, font_size=max(17, body_size - 8), beat_id=b0)
            if icon == "run":
                add_arrow(_line_points(nx - 22, ny + height * 0.060, nx + 24, ny + height * 0.045, count=4), color, 3, cursor, 6, role="mini_icon", beat_id=b0)
            elif icon == "book":
                add_stroke("book_icon", _rect_points(nx - 24, ny + height * 0.055, 48, 34), color, 3, cursor, 6, close=True, beat_id=b0)
            elif icon == "med":
                add_stroke("med_icon", _arc_points(nx, ny + height * 0.070, 40, 22, 0, math.pi, count=9), color, 3, cursor, 6, beat_id=b0)
            else:
                add_stroke("handshake", _line_points(nx - 36, ny + height * 0.070, nx + 36, ny + height * 0.070, count=5), color, 3, cursor, 6, beat_id=b0)
            cursor += 8
        for start_angle, end_angle in [(-math.pi * 0.46, math.pi * 0.05), (math.pi * 0.05, math.pi * 0.55), (math.pi * 0.55, math.pi * 1.05), (math.pi * 1.05, math.pi * 1.55)]:
            add_arrow(_arc_points(cx, cy, rx * 0.96, ry * 0.95, start_angle, end_angle, count=13), ink, 4, cursor, 12, role="renew_loop", beat_id=b0)
            cursor += 14
        add_text("\u66f4\u65b0", cx - width * 0.038, cy - height * 0.026, body_size, violet, cursor, 18, width * 0.09, emphasis=True, max_chars=4, beat_id=b0)
        cursor += 24
        sx = board_center_x - width * 0.20
        sy = diagram_top + height * 0.51
        mini_w = width * 0.13
        mini_h = height * 0.050
        mini = [
            ("\u4f9d\u8d56", sx, sy + mini_h * 1.8, red),
            ("\u72ec\u7acb", sx + mini_w, sy + mini_h * 0.9, blue),
            ("\u4e92\u76f8\u4f9d\u8d56", sx + mini_w * 2, sy, green),
        ]
        prev = None
        for label, tx, ty, color in mini:
            cursor = add_node_box(label, tx, ty, mini_w * 0.92, mini_h * 1.05, cursor, color, role="mini_step", font_size=max(16, body_size - 12), beat_id=b1)
            if prev:
                add_arrow(_line_points(prev[0] + mini_w * 0.82, prev[1] + mini_h * 0.50, tx - 10, ty + mini_h * 0.50, count=5), ink, 3, cursor, 8, beat_id=b1)
                cursor += 8
            prev = (tx, ty)
        add_text("\u4ece\u88ab\u52a8\u5230\u5171\u8d62", sx + mini_w * 0.55, sy + mini_h * 2.95, body_size, yellow, cursor, 22, width * 0.24, emphasis=True, max_chars=8, beat_id=b1)
        return cursor + 28

    def fallback_label(index: int, value: str) -> str:
        pool = steps or core_lines
        return _short_text(pool[index], 16) if index < len(pool) else value

    def direct_callout_labels() -> list[str]:
        labels: list[str] = []
        for beat in getattr(scene, "visual_beats", []) or []:
            for label in beat.required_labels or []:
                short = _short_text(label, 14)
                if short and short not in labels:
                    labels.append(short)
            if len(labels) >= 4:
                break
        for step in steps:
            short = _short_text(step, 14)
            if short and short not in labels:
                labels.append(short)
            if len(labels) >= 4:
                break
        defaults = ["关键结构", "控制关系", "变化路径", "重点结论"]
        for default in defaults:
            if len(labels) >= 4:
                break
            labels.append(default)
        return labels[:4]

    def title_x_for_text(text: str, font_size: int, max_chars: int = 24) -> float:
        safe_text = _short_text(text, max_chars)
        estimated = min(width * 0.78, max(font_size * 2.4, _text_visual_width(safe_text, font_size) * 0.84))
        return max(width * 0.06, (width - estimated) * 0.5)

    def add_process_doodles(start: int, x: float, y: float) -> int:
        cursor = start
        route = _curve_points(x, y + 20, x + 118, y - 18, count=14, wave=height * 0.030)
        add_arrow(route, blue, 3, cursor, 16, role="route_doodle")
        cursor += 18
        marker_specs = [
            (route[0], green, "\u8d77\u70b9"),
            (route[len(route) // 2], violet, "\u8c03\u6574"),
            (route[-1], red, "\u7ed3\u8bba"),
        ]
        for point, color, label in marker_specs:
            add_stroke("route_marker", _circle_points(point["x"], point["y"], width * 0.010, height * 0.016, count=10), color, 3, cursor, 6)
            cursor += 7
            add_text(label, point["x"] - width * 0.018, point["y"] + height * 0.022, max(15, body_size - 12), color, cursor, 10, width * 0.08, emphasis=False, max_chars=4)
            cursor += 11
        for index in range(3):
            ray_x = x + 132 + index * 16
            add_stroke("spark", _line_points(ray_x, y - 38, ray_x + 8, y - 54 - index * 2, count=3), yellow, 3, cursor, 5)
            cursor += 6
        return cursor

    def build_raster_reveal(start: int) -> int:
        nonlocal raster_reveal_spec
        if not reference_image_asset or not raster_reveal:
            return builders.get(diagram_kind, build_process_flow)(start)

        image_w = float(raster_reveal.get("imageWidth") or raster_reveal.get("image_width") or 1)
        image_h = float(raster_reveal.get("imageHeight") or raster_reveal.get("image_height") or 1)
        image_aspect = max(0.1, image_w / max(1.0, image_h))
        render_mode = _clean_text(raster_reveal.get("renderMode") or raster_reveal.get("render_mode")).lower()
        if render_mode == "direct":
            region_x = width * 0.245
            region_y = height * 0.18
            region_w = width * 0.56
            region_h = height * 0.58
        else:
            region_x = width * 0.20
            region_y = diagram_top - height * 0.01
            region_w = width * 0.60
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

        if render_mode == "direct":
            raster_reveal_spec = {
                "asset": str(reference_image_asset),
                "x": round(draw_x, 1),
                "y": round(draw_y, 1),
                "width": round(draw_w, 1),
                "height": round(draw_h, 1),
                "renderMode": "direct",
                "directAppearFrame": 0,
                "strokes": [],
            }
            labels = direct_callout_labels()[:3]
            segment_windows: list[tuple[str | None, int, int]] = []
            if audio_segments:
                for segment in audio_segments:
                    segment_windows.append(
                        (
                            str(segment.get("id") or f"beat_{len(segment_windows)}"),
                            max(0, int(segment.get("startFrame") or 0)),
                            max(1, int(segment.get("endFrame") or duration)),
                        )
                    )
            else:
                usable_start = max(start + 18, int(duration * 0.22))
                usable_end = max(usable_start + 1, duration - 14)
                span = max(36, (usable_end - usable_start) // 3)
                for index in range(3):
                    segment_start = usable_start + index * span
                    segment_windows.append((None, segment_start, min(usable_end, segment_start + span)))

            note_size = max(50, int(body_size * 1.62))
            note_width = width * 0.22
            left_note_x = max(width * 0.055, draw_x - note_width - width * 0.055)
            right_note_x = min(width - note_width - width * 0.055, draw_x + draw_w + width * 0.055)
            label_specs = [
                {
                    "label": labels[0],
                    "side": "left",
                    "text_x": left_note_x,
                    "text_y": draw_y + draw_h * 0.17,
                    "color": blue,
                },
                {
                    "label": labels[1],
                    "side": "right",
                    "text_x": right_note_x,
                    "text_y": draw_y + draw_h * 0.40,
                    "color": violet,
                },
                {
                    "label": labels[2],
                    "side": "left",
                    "text_x": left_note_x,
                    "text_y": draw_y + draw_h * 0.66,
                    "color": red,
                },
            ]
            cursor = max(start + 8, int(duration * 0.16))
            for index, spec in enumerate(label_specs):
                beat_id, segment_start, segment_end = segment_windows[min(index, len(segment_windows) - 1)]
                segment_span = max(36, segment_end - segment_start)
                local_cursor = max(cursor, segment_start + min(12, max(0, segment_span // 8)))
                label_y = spec["text_y"]
                label_x = spec["text_x"]
                color = spec["color"]
                side = spec["side"]
                note_text_width = min(note_width * 0.82, _text_visual_width(spec["label"], note_size) * 0.88 + width * 0.018)
                link_start_x = label_x + note_text_width if side == "left" else label_x - width * 0.012
                edge_x = draw_x - width * 0.014 if side == "left" else draw_x + draw_w + width * 0.014
                edge_y = min(draw_y + draw_h * 0.86, max(draw_y + draw_h * 0.14, label_y + note_size * 0.58))
                note_frames = min(34, max(18, segment_span // 5))
                add_text(
                    spec["label"],
                    label_x,
                    label_y,
                    note_size,
                    color,
                    local_cursor,
                    note_frames,
                    note_width,
                    emphasis=True,
                    max_chars=9,
                    beat_id=beat_id,
                )
                underline_w = min(note_width * 0.86, max(width * 0.070, _text_visual_width(spec["label"], note_size) * 0.82))
                add_stroke(
                    "bold_callout_underline",
                    _curve_points(
                        label_x,
                        label_y + note_size * 1.08,
                        label_x + underline_w,
                        label_y + note_size * 1.08,
                        count=9,
                        wave=height * 0.006,
                    ),
                    red,
                    7,
                    local_cursor + note_frames + 1,
                    min(12, max(7, segment_span // 10)),
                    beat_id=beat_id,
                )
                # Direct reference images are not semantically segmented, so keep marks near the image edge.
                # This avoids fake precision where a generated arrow points to the wrong ingredient/part.
                add_stroke(
                    "callout_link",
                    _curve_points(
                        link_start_x,
                        label_y + note_size * 0.56,
                        edge_x,
                        edge_y,
                        count=8,
                        wave=height * 0.006,
                    ),
                    red,
                    5,
                    local_cursor + note_frames + 6,
                    min(16, max(8, segment_span // 8)),
                    beat_id=beat_id,
                )
                tick_dir = 1 if side == "left" else -1
                add_stroke(
                    "callout_tick",
                    _line_points(edge_x, edge_y, edge_x + tick_dir * width * 0.030, edge_y, count=4),
                    red,
                    7,
                    local_cursor + note_frames + min(18, max(8, segment_span // 8)),
                    min(10, max(6, segment_span // 12)),
                    beat_id=beat_id,
                )
                cursor = max(local_cursor + note_frames + 32, segment_end - 4)
            return min(duration - 8, cursor)

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
        trace_x = width * 0.22
        trace_y = diagram_top + height * 0.045
        trace_w = width * 0.56
        trace_h = height * 0.48
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
            _curve_points(trace_x - width * 0.06, trace_y + trace_h * 0.44, trace_x + trace_w * 0.34, trace_y + trace_h * 0.46, count=16, wave=height * 0.025),
            blue,
            4,
            arrow_start,
            18,
        )
        add_text(label, trace_x - width * 0.145, trace_y + trace_h * 0.36, body_size, blue, arrow_start + 12, 28, width * 0.16, max_chars=14)
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
        y = diagram_top + height * 0.17
        box_w = width * 0.15
        box_h = height * 0.13
        gap = width * 0.055
        total_w = box_w * 3 + gap * 2
        x1 = board_center_x - total_w * 0.5
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
        return add_process_doodles(cursor, x3 + box_w * 0.30, y + box_h + height * 0.08)

    def build_comparison_transform(start: int) -> int:
        y = diagram_top + height * 0.16
        w = width * 0.19
        h = height * 0.18
        gap = width * 0.12
        left_x = board_center_x - (w * 2 + gap) * 0.5
        right_x = left_x + w + gap
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

        x = board_center_x - width * 0.22
        y = diagram_top + height * 0.08
        w = width * 0.44
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
        axis_x = board_center_x - width * 0.23
        axis_y = diagram_top + height * 0.44
        axis_w = width * 0.46
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
        x0 = board_center_x - width * 0.29
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
        x = board_center_x - width * 0.29
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

    def build_priority_matrix(start: int) -> int:
        cursor = start
        x = board_center_x - width * 0.25
        y = diagram_top + height * 0.08
        w = width * 0.50
        h = height * 0.42
        mid_x = x + w * 0.5
        mid_y = y + h * 0.5
        add_stroke("matrix_frame", _rect_points(x, y, w, h), ink, 4, cursor, 18, close=True)
        cursor += 20
        add_stroke("matrix_axis", _line_points(mid_x, y, mid_x, y + h, count=6), ink, 3, cursor, 10)
        add_stroke("matrix_axis", _line_points(x, mid_y, x + w, mid_y, count=6), ink, 3, cursor + 6, 10)
        cursor += 20
        add_text("重要", x - width * 0.065, y + h * 0.18, body_size, blue, cursor, 16, width * 0.08)
        add_text("紧急", x + w * 0.72, y + h + height * 0.035, body_size, red, cursor + 8, 16, width * 0.10)
        cursor += 24
        quadrant_labels = [
            (fallback_label(0, "计划"), x + w * 0.10, y + h * 0.16, blue),
            (fallback_label(1, "危机"), x + w * 0.62, y + h * 0.16, red),
            (fallback_label(2, "授权"), x + w * 0.62, y + h * 0.62, violet),
            (fallback_label(3, "减少"), x + w * 0.10, y + h * 0.62, green),
        ]
        for index, (label, tx, ty, color) in enumerate(quadrant_labels):
            add_text(label, tx, ty, max(20, body_size - 2), color, cursor, 20, w * 0.30, emphasis=index == 0, max_chars=10)
            if index == 0:
                add_stroke("focus_circle", _circle_points(tx + w * 0.11, ty + body_size * 0.45, w * 0.15, h * 0.16, count=22), yellow, 4, cursor + 18, 12)
            cursor += 25
        add_arrow(_curve_points(x + w * 0.25, y + h * 0.77, x + w * 0.25, y + h * 0.32, count=12, wave=height * 0.018), blue, 4, cursor, 14, role="priority_arrow")
        add_arrow(_curve_points(x + w * 0.77, y + h * 0.28, x + w * 0.36, y + h * 0.28, count=12, wave=height * 0.016), green, 4, cursor + 12, 14, role="priority_arrow")
        cursor += 34
        add_text(fallback_label(4, "把时间留给真正重要的事"), x + w * 0.10, y + h + height * 0.085, body_size, violet, cursor, 28, w * 0.70, emphasis=True, max_chars=18)
        return cursor + 38

    def build_feedback_loop(start: int) -> int:
        cursor = start
        cx = board_center_x
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

    def build_goal_path(start: int) -> int:
        cursor = start
        x0 = board_center_x - width * 0.30
        y0 = diagram_top + height * 0.37
        x1 = board_center_x + width * 0.30
        y1 = diagram_top + height * 0.18
        path_points = _curve_points(x0, y0, x1, y1, count=18, wave=height * 0.08)
        cursor = add_node_circle(fallback_label(0, "现在"), x0, y0, width * 0.055, height * 0.050, cursor, blue, font_size=max(18, body_size - 7))
        add_arrow(path_points, green, 5, cursor, 24, role="goal_path")
        cursor += 30
        milestones = [path_points[5], path_points[10], path_points[14]]
        for index, point in enumerate(milestones):
            add_stroke("milestone", _circle_points(point["x"], point["y"], width * 0.020, height * 0.028, count=14), violet if index % 2 else blue, 4, cursor, 8)
            add_text(fallback_label(index + 2, f"阶段{index + 1}"), point["x"] - width * 0.045, point["y"] + height * 0.035, max(17, body_size - 9), ink, cursor + 6, 14, width * 0.12, max_chars=8)
            cursor += 18
        cursor = add_node_circle(fallback_label(1, "目标"), x1, y1, width * 0.065, height * 0.060, cursor, red, font_size=max(19, body_size - 6))
        add_arrow(_curve_points(x1 - width * 0.03, y1 + height * 0.08, x0 + width * 0.08, y0 - height * 0.06, count=16, wave=-height * 0.055), violet, 4, cursor, 18, role="backcast")
        cursor += 24
        add_text(fallback_label(5, "从终点倒推"), board_center_x - width * 0.11, diagram_top + height * 0.48, body_size, violet, cursor, 26, width * 0.28, emphasis=True, max_chars=12)
        return cursor + 34

    def build_overview_map(start: int) -> int:
        cursor = start
        labels = steps or core_lines or [_short_text(scene.title, 18), "现象", "机制", "结果", "总结"]
        labels = labels[:5]
        cx = board_center_x
        cy = diagram_top + height * 0.24
        cursor = add_node_circle(labels[0], cx, cy, width * 0.090, height * 0.065, cursor, blue, role="overview_center", font_size=max(18, body_size - 5))
        positions = [
            (cx - width * 0.24, cy - height * 0.14, red),
            (cx + width * 0.24, cy - height * 0.13, green),
            (cx + width * 0.22, cy + height * 0.15, violet),
            (cx - width * 0.22, cy + height * 0.16, yellow),
        ]
        for index, label in enumerate(labels[1:5]):
            px, py, color = positions[index]
            add_arrow(_curve_points(cx + (width * 0.085 if px > cx else -width * 0.085), cy, px + (width * 0.065 if px < cx else -width * 0.065), py, count=12, wave=height * 0.020), ink, 3, cursor, 12, role="overview_link")
            cursor += 14
            cursor = add_node_box(label, px - width * 0.065, py - height * 0.034, width * 0.13, height * 0.068, cursor, color if color != yellow else ink, role="overview_unit", font_size=max(17, body_size - 8))
        add_stroke("route", _arc_points(cx, cy, width * 0.30, height * 0.23, -math.pi * 0.82, math.pi * 0.12, count=18), green, 4, cursor, 18)
        cursor += 22
        add_text(fallback_label(5, "学习路线"), cx - width * 0.07, cy + height * 0.25, body_size, violet, cursor, 22, width * 0.20, emphasis=True, max_chars=10)
        return cursor + 30

    def build_interaction_scenario(start: int) -> int:
        cursor = start
        corpus_local = _scene_corpus(scene)
        relation_kind = _visual_relation_kind_for_scene(scene)
        x = board_center_x - width * 0.30
        y = diagram_top + height * 0.12
        panel_w = width * 0.22
        panel_h = height * 0.25

        def draw_person(cx: float, cy: float, color: str, label: str, start_frame: int) -> int:
            local = start_frame
            add_stroke("person", _circle_points(cx, cy, width * 0.028, height * 0.045, count=18), color, 4, local, 10)
            local += 11
            add_stroke("person", _line_points(cx, cy + height * 0.045, cx, cy + height * 0.14, count=5), color, 4, local, 8)
            add_stroke("person", _line_points(cx - width * 0.045, cy + height * 0.085, cx + width * 0.045, cy + height * 0.085, count=5), color, 4, local + 5, 8)
            add_stroke("person", _line_points(cx, cy + height * 0.14, cx - width * 0.040, cy + height * 0.20, count=4), color, 4, local + 10, 8)
            add_stroke("person", _line_points(cx, cy + height * 0.14, cx + width * 0.040, cy + height * 0.20, count=4), color, 4, local + 15, 8)
            add_text(label, cx - width * 0.060, cy + height * 0.225, max(18, body_size - 6), color, local + 18, 18, width * 0.14, max_chars=8)
            return local + 42

        relation_mode = relation_kind == "interaction_scenario" or _contains_any(
            corpus_local,
            [
                "collabor",
                "communication",
                "team",
                "沟通",
                "合作",
                "协作",
                "交流",
                "互相",
                "互动",
                "关系",
                "交换",
                "共同",
                "双方",
            ],
        )
        renewal_mode = relation_kind == "feedback_loop" or _contains_any(corpus_local, ["renew", "growth", "sharpen", "improve", "更新", "成长", "复盘", "精进", "循环", "闭环", "迭代"])
        goal_mode = relation_kind == "goal_path" or _contains_any(corpus_local, ["goal", "end", "target", "vision", "目标", "愿景", "路径", "路线", "里程碑", "倒推"])

        if relation_mode:
            left_end = draw_person(x + panel_w * 0.40, y + panel_h * 0.26, blue, fallback_label(0, "A"), cursor)
            right_end = draw_person(x + panel_w * 1.75, y + panel_h * 0.26, green, fallback_label(1, "B"), cursor + 10)
            cursor = max(left_end, right_end)
            bubble_y = y + panel_h * 0.06
            add_stroke("speech", _circle_points(x + panel_w * 0.63, bubble_y, width * 0.070, height * 0.052, count=20), blue, 3, cursor, 12)
            add_text(fallback_label(2, "输入"), x + panel_w * 0.55, bubble_y - height * 0.020, max(18, body_size - 7), blue, cursor + 8, 16, width * 0.14, max_chars=8)
            add_stroke("speech", _circle_points(x + panel_w * 1.47, bubble_y, width * 0.070, height * 0.052, count=20), green, 3, cursor + 14, 12)
            add_text(fallback_label(3, "反馈"), x + panel_w * 1.39, bubble_y - height * 0.020, max(18, body_size - 7), green, cursor + 22, 16, width * 0.14, max_chars=8)
            cursor += 42
            add_arrow(_curve_points(x + panel_w * 0.70, y + panel_h * 0.50, x + panel_w * 1.48, y + panel_h * 0.50, count=14, wave=height * 0.030), red, 4, cursor, 16, role="mutual_path")
            add_arrow(_curve_points(x + panel_w * 1.42, y + panel_h * 0.59, x + panel_w * 0.76, y + panel_h * 0.59, count=14, wave=-height * 0.022), violet, 4, cursor + 12, 16, role="mutual_path")
            cursor += 34
            add_text(fallback_label(4, "共同结果"), x + panel_w * 0.83, y + panel_h * 0.78, body_size, violet, cursor, 24, width * 0.22, emphasis=True, max_chars=12)
            add_stroke("emphasis", _curve_points(x + panel_w * 0.83, y + panel_h * 0.92, x + panel_w * 1.25, y + panel_h * 0.92, count=10, wave=height * 0.005), yellow, 4, cursor + 20, 8)
            return cursor + 40

        if renewal_mode:
            cx = board_center_x
            cy = y + panel_h * 0.36
            nodes = [
                (fallback_label(0, "身体"), cx, cy - height * 0.15, blue),
                (fallback_label(1, "智力"), cx + width * 0.18, cy, green),
                (fallback_label(2, "情感"), cx, cy + height * 0.15, violet),
                (fallback_label(3, "精神"), cx - width * 0.18, cy, red),
            ]
            for label, nx, ny, color in nodes:
                cursor = add_node_circle(label, nx, ny, width * 0.055, height * 0.048, cursor, color, font_size=max(18, body_size - 7))
            for start_angle, end_angle in [(-math.pi * 0.45, math.pi * 0.05), (math.pi * 0.05, math.pi * 0.55), (math.pi * 0.55, math.pi * 1.05), (math.pi * 1.05, math.pi * 1.55)]:
                add_arrow(_arc_points(cx, cy, width * 0.22, height * 0.19, start_angle, end_angle, count=12), ink, 4, cursor, 12, role="renew_loop")
                cursor += 15
            add_text(fallback_label(4, "持续更新"), cx - width * 0.075, cy - height * 0.020, body_size, violet, cursor, 24, width * 0.18, emphasis=True, max_chars=10)
            return cursor + 34

        if goal_mode:
            person_end = draw_person(x + panel_w * 0.28, y + panel_h * 0.34, blue, fallback_label(0, "现在"), cursor)
            cursor = max(cursor + 36, person_end)
            target_x = x + panel_w * 1.55
            target_y = y + panel_h * 0.32
            add_stroke("target", _circle_points(target_x, target_y, width * 0.085, height * 0.085, count=24), red, 4, cursor, 12)
            add_stroke("target", _circle_points(target_x, target_y, width * 0.050, height * 0.050, count=18), red, 3, cursor + 10, 10)
            add_stroke("target", _circle_points(target_x, target_y, width * 0.018, height * 0.018, count=12), red, 3, cursor + 18, 8)
            add_text(fallback_label(1, "目标"), target_x - width * 0.050, target_y + height * 0.105, body_size, red, cursor + 20, 18, width * 0.12, max_chars=8)
            cursor += 40
            add_arrow(_curve_points(x + panel_w * 0.44, y + panel_h * 0.48, target_x - width * 0.095, target_y, count=14, wave=height * 0.040), green, 4, cursor, 18, role="path")
            add_text(fallback_label(2, "倒推行动"), x + panel_w * 0.80, y + panel_h * 0.12, body_size, violet, cursor + 12, 24, width * 0.20, emphasis=True, max_chars=10)
            return cursor + 44

        left_x = x
        mid_x = x + panel_w * 0.98
        right_x = x + panel_w * 1.96
        cursor = add_node_box(fallback_label(0, "输入"), left_x, y + panel_h * 0.20, panel_w * 0.62, panel_h * 0.28, cursor, red, font_size=max(18, body_size - 6))
        add_arrow(_line_points(left_x + panel_w * 0.66, y + panel_h * 0.34, mid_x - 16, y + panel_h * 0.34, count=6), ink, 4, cursor, 12)
        cursor += 18
        cursor = add_node_circle(fallback_label(1, "转换"), mid_x + panel_w * 0.15, y + panel_h * 0.34, width * 0.065, height * 0.060, cursor, blue, font_size=max(18, body_size - 6))
        add_arrow(_line_points(mid_x + panel_w * 0.30, y + panel_h * 0.34, right_x - 16, y + panel_h * 0.34, count=6), green, 4, cursor, 12)
        cursor += 18
        cursor = add_node_box(fallback_label(2, "输出"), right_x, y + panel_h * 0.20, panel_w * 0.62, panel_h * 0.28, cursor, green, font_size=max(18, body_size - 6))
        add_text(fallback_label(3, "关键关系"), mid_x + panel_w * 0.02, y + panel_h * 0.60, body_size, violet, cursor, 24, width * 0.20, emphasis=True, max_chars=10)
        return cursor + 40

    def build_teaching_board(start: int) -> int:
        cursor = start
        labels = core_lines[:]
        if scene.diagram_plan and scene.diagram_plan.required_labels:
            labels = [_short_text(label, 18) for label in scene.diagram_plan.required_labels if _short_text(label, 18)]
        for beat in getattr(scene, "visual_beats", []) or []:
            for label in beat.required_labels or []:
                short = _short_text(label, 18)
                if short and short not in labels:
                    labels.append(short)
            if len(labels) >= 6:
                break
        if not labels:
            labels = [_short_text(scene.title, 18), "原因", "过程", "结果"]
        labels = labels[:6]
        corpus = _scene_corpus(scene)

        def build_visual_synthesis(start_frame: int) -> int:
            local_labels = [label for label in labels if label and not _looks_like_mojibake(label)]
            synthesis_defaults = ["\u5168\u5c40", "\u7ed3\u6784", "\u53d6\u820d", "\u884c\u52a8", "\u53cd\u9988"]
            for default in synthesis_defaults:
                if len(local_labels) >= 5:
                    break
                if default not in local_labels:
                    local_labels.append(default)
            local_labels = local_labels[:5]
            cursor_local = start_frame
            cx = board_center_x
            cy = diagram_top + height * 0.25
            hub_rx = width * 0.080
            hub_ry = height * 0.062
            cursor_local = add_node_circle(local_labels[0], cx, cy, hub_rx, hub_ry, cursor_local, blue, role="synthesis_hub", font_size=max(18, body_size - 5))
            positions = [
                (cx - width * 0.24, cy - height * 0.12, red, "warning_icon"),
                (cx + width * 0.24, cy - height * 0.12, violet, "gear_icon"),
                (cx + width * 0.23, cy + height * 0.15, green, "route_icon"),
                (cx - width * 0.23, cy + height * 0.15, yellow, "loop_icon"),
            ]
            for index, (px, py, color, role_name) in enumerate(positions):
                label = local_labels[index + 1] if index + 1 < len(local_labels) else synthesis_defaults[index + 1]
                add_arrow(
                    _curve_points(cx + (hub_rx if px > cx else -hub_rx), cy, px + (width * 0.054 if px < cx else -width * 0.054), py, count=13, wave=height * 0.018 * (1 if index % 2 == 0 else -1)),
                    ink,
                    3,
                    cursor_local,
                    12,
                    role="synthesis_link",
                )
                cursor_local += 14
                cursor_local = add_node_box(label, px - width * 0.060, py - height * 0.036, width * 0.12, height * 0.072, cursor_local, color if color != yellow else ink, role=role_name, font_size=max(17, body_size - 8))
                if index == 0:
                    tri = [_point(px, py - height * 0.075), _point(px + width * 0.038, py - height * 0.010), _point(px - width * 0.038, py - height * 0.010), _point(px, py - height * 0.075)]
                    add_stroke("warning_triangle", tri, red, 3, cursor_local, 9, close=True)
                    cursor_local += 10
                elif index == 1:
                    add_stroke("gear_ring", _circle_points(px, py - height * 0.070, width * 0.028, height * 0.032, count=18), violet, 3, cursor_local, 9)
                    for spoke in range(4):
                        angle = spoke * math.pi / 2
                        add_stroke("gear_tooth", _line_points(px + math.cos(angle) * width * 0.032, py - height * 0.070 + math.sin(angle) * height * 0.036, px + math.cos(angle) * width * 0.047, py - height * 0.070 + math.sin(angle) * height * 0.050, count=3), violet, 3, cursor_local + 4, 5)
                    cursor_local += 12
                elif index == 2:
                    mini_path = _curve_points(px - width * 0.046, py + height * 0.066, px + width * 0.052, py + height * 0.044, count=9, wave=height * 0.020)
                    add_arrow(mini_path, green, 3, cursor_local, 10, role="mini_route")
                    cursor_local += 12
                else:
                    add_arrow(_arc_points(px, py + height * 0.058, width * 0.044, height * 0.034, -math.pi * 0.2, math.pi * 1.25, count=12), blue, 3, cursor_local, 11, role="mini_loop")
                    cursor_local += 13
            add_stroke("synthesis_orbit", _arc_points(cx, cy, width * 0.315, height * 0.235, -math.pi * 0.83, math.pi * 0.22, count=22), green, 4, cursor_local, 18)
            cursor_local += 22
            add_text(local_labels[-1], cx - width * 0.070, cy + height * 0.250, body_size, violet, cursor_local, 24, width * 0.20, emphasis=True, max_chars=10)
            cursor_local += 28
            add_stroke("synthesis_underline", _curve_points(cx - width * 0.08, cy + height * 0.325, cx + width * 0.09, cy + height * 0.318, count=10, wave=height * 0.005), yellow, 4, cursor_local, 9)
            return cursor_local + 10

        if _contains_any(corpus, ["summary", "checklist", "recap", "conclusion", "\u603b\u7ed3", "\u6e05\u5355", "\u590d\u76d8"]):
            return build_visual_synthesis(start)

        if _contains_any(corpus, ["summary", "checklist", "总结", "清单", "复盘"]):
            summary_defaults = ["看全局", "拆结构", "做取舍", "走目标", "跑反馈"]
            labels = [label for label in labels if label and not _looks_like_mojibake(label)]
            for default in summary_defaults:
                if len(labels) >= 5:
                    break
                if default not in labels:
                    labels.append(default)
            labels = labels[:5]
            x = board_center_x - width * 0.25
            y = diagram_top + height * 0.07
            row_gap = height * 0.078
            add_stroke("summary_frame", _rect_points(x - width * 0.025, y - height * 0.025, width * 0.50, row_gap * (len(labels) + 0.8)), ink, 4, cursor, 18, close=True)
            cursor += 20
            for index, label in enumerate(labels):
                row_y = y + index * row_gap
                check = [
                    _point(x, row_y + body_size * 0.45),
                    _point(x + width * 0.012, row_y + body_size * 0.72),
                    _point(x + width * 0.038, row_y + body_size * 0.10),
                ]
                add_stroke("check", check, green, 4, cursor, 8)
                add_text(label, x + width * 0.055, row_y, body_size, ink if index % 2 else blue, cursor + 6, 24, width * 0.38, emphasis=index == len(labels) - 1, max_chars=18)
                cursor += 32
            add_stroke("summary_underline", _curve_points(x + width * 0.05, y + row_gap * len(labels) + 8, x + width * 0.40, y + row_gap * len(labels) + 4, count=12, wave=height * 0.006), yellow, 4, cursor, 10)
            return cursor + 14

        if _contains_any(corpus, ["comparison", "compare", "versus", " vs ", "before", "after", "对比", "状态"]):
            return build_comparison_transform(start)

        if _contains_any(corpus, ["process", "flow", "mechanism", "过程", "流程", "步骤", "变化", "机制"]):
            return build_process_flow(start)

        center_label = labels[0]
        cx = board_center_x
        cy = diagram_top + height * 0.24
        center_rx = width * 0.105
        center_ry = height * 0.070
        cursor = add_node_circle(center_label, cx, cy, center_rx, center_ry, cursor, blue, role="center", font_size=max(20, body_size - 2))
        branch_labels = labels[1:] if len(labels) > 1 else ["现象", "原因", "结果", "例子"]
        positions = [
            (cx - width * 0.24, cy - height * 0.13, red),
            (cx + width * 0.24, cy - height * 0.12, green),
            (cx - width * 0.22, cy + height * 0.16, violet),
            (cx + width * 0.22, cy + height * 0.16, yellow),
            (cx, cy + height * 0.24, blue),
        ]
        for index, label in enumerate(branch_labels[:5]):
            bx, by, color = positions[index]
            add_arrow(_curve_points(cx + (center_rx if bx > cx else -center_rx), cy, bx + (width * 0.055 if bx < cx else -width * 0.055), by, count=12, wave=height * 0.018 * (1 if index % 2 == 0 else -1)), ink, 3, cursor, 12, role="relation")
            cursor += 14
            cursor = add_node_box(label, bx - width * 0.055, by - height * 0.035, width * 0.11, height * 0.07, cursor, color if color != yellow else ink, role="branch", font_size=max(18, body_size - 7))
            if index in {0, len(branch_labels[:5]) - 1}:
                add_stroke("emphasis", _curve_points(bx - width * 0.045, by + height * 0.052, bx + width * 0.045, by + height * 0.052, count=8, wave=height * 0.004), yellow, 4, cursor, 8)
                cursor += 9
        add_stroke("teacher_mark", _circle_points(cx + center_rx * 0.06, cy, center_rx * 1.14, center_ry * 1.22, count=28), yellow, 4, cursor, 14)
        cursor += 16
        add_process_doodles(cursor, cx + width * 0.31, cy + height * 0.14)
        return min(duration - 8, cursor + 40)

    def build_chalkboard_derivation(start: int) -> int:
        cursor = start
        x = width * 0.12
        y = height * 0.18
        line_gap = height * 0.087
        chalk_size = max(30, int(body_size * 1.05))
        lines: list[str] = []
        if scene.diagram_plan and scene.diagram_plan.required_labels:
            lines.extend(scene.diagram_plan.required_labels[:5])
        for animation in scene.animations:
            raw_type = getattr(animation.type, "value", str(animation.type))
            if raw_type in {"write_formula", "formula_reveal"} and (animation.latex or animation.content):
                lines.append(animation.latex or animation.content)
            elif animation.items:
                lines.extend(animation.items[:4])
            elif animation.content:
                lines.append(animation.content)
        for beat in getattr(scene, "visual_beats", []) or []:
            if beat.required_labels:
                lines.extend(beat.required_labels[:3])
            elif beat.draw_intent:
                pieces = re.split(r"[。；;,.，、]", beat.draw_intent)
                lines.extend(piece for piece in pieces[:2] if piece.strip())
        if not lines:
            lines = re.split(r"[。；;]", scene.narration)[:6]
        lines = [_short_text(line, 34) for line in lines if _short_text(line, 34)]
        if not lines:
            lines = [_short_text(scene.title, 24), "Known", "Derive", "Conclusion"]
        color_cycle = [ink, blue, green, yellow, red]
        cursor = max(cursor, 12)
        for index, line in enumerate(lines[:7]):
            line_y = y + index * line_gap
            color = color_cycle[index % len(color_cycle)]
            frames = max(24, min(54, int(len(line) * 2.2)))
            add_text(line, x + (width * 0.035 if index % 2 else 0), line_y, chalk_size, color, cursor, frames, width * 0.78, emphasis=index in {0, len(lines[:7]) - 1}, max_chars=34)
            cursor += frames + 10
            if index in {0, 2, 4} and cursor + 10 < duration - 10:
                underline_y = line_y + chalk_size * 1.05
                add_stroke(
                    "chalk_underline",
                    _line_points(x, underline_y, min(width * 0.86, x + _text_visual_width(line, chalk_size) * 0.62), underline_y, count=8),
                    yellow if index == 0 else green,
                    3,
                    cursor,
                    8,
                )
                cursor += 10
        return cursor

    def build_semiconductor_device(start: int) -> int:
        cursor = start
        corpus = _scene_corpus(scene)
        x = board_center_x - width * 0.30
        y = diagram_top + height * 0.12
        panel_w = width * 0.22
        panel_h = height * 0.30

        def draw_planar_mos(px: float, py: float, label: str, on_state: bool, start_frame: int) -> int:
            local = start_frame
            add_text(label, px, py - height * 0.065, max(22, body_size - 4), green if on_state else red, local, 18, panel_w, max_chars=18)
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

    def select_seven_habits_builder():
        corpus_local = _scene_corpus(scene)
        title_local = _clean_text(scene.title).lower()
        habit_markers = [
            "七个习惯",
            "习惯1",
            "习惯2",
            "习惯3",
            "习惯4",
            "习惯5",
            "习惯6",
            "习惯7",
            "主动积极",
            "以终为始",
            "要事第一",
            "双赢",
            "知彼解己",
            "统合综效",
            "不断更新",
        ]
        if not any(marker in corpus_local for marker in habit_markers):
            return None
        if "不断更新" in title_local or "习惯7" in title_local:
            return build_renewal_summary_rich
        if "总览" in title_local or ("七个习惯" in corpus_local and "依赖" in corpus_local and ("互相依赖" in corpus_local or "互赖" in corpus_local)):
            return build_seven_habits_overview
        if "主动积极" in corpus_local or "影响圈" in corpus_local or "关注圈" in corpus_local:
            return build_proactive_circles
        if "以终为始" in corpus_local or "愿景" in corpus_local or "使命" in corpus_local:
            return build_begin_with_end
        if "要事第一" in corpus_local or "时间管理" in corpus_local or "四象限" in corpus_local:
            return build_time_matrix_rich
        if "双赢" in corpus_local or "知彼解己" in corpus_local or "统合综效" in corpus_local:
            return build_interdependence_rich
        if "不断更新" in corpus_local or "习惯7" in title_local or "总结" in corpus_local:
            return build_renewal_summary_rich
        return None

    cursor = 0
    title_size = 58 if width >= 1600 else 44
    body_size = 32 if width >= 1600 else 26
    title_text = scene.title or f"Scene {scene_index + 1}"
    add_text(title_text, title_x_for_text(title_text, title_size), top, title_size, blue, cursor, 44, emphasis=True, max_width=width * 0.78, max_chars=24)
    cursor += 54

    builders = {
        "process_flow": build_process_flow,
        "comparison_transform": build_comparison_transform,
        "formula_derivation": build_formula_derivation,
        "chalkboard_derivation": build_chalkboard_derivation,
        "optimization_curve": build_optimization_curve,
        "attention_network": build_attention_network,
        "matrix_transform": build_matrix_transform,
        "priority_matrix": build_priority_matrix,
        "feedback_loop": build_feedback_loop,
        "interaction_scenario": build_interaction_scenario,
        "goal_path": build_goal_path,
        "overview_map": build_overview_map,
        "teaching_board": build_teaching_board,
        "semiconductor_device": build_semiconductor_device,
    }
    if raster_reveal and reference_image_asset:
        cursor = build_raster_reveal(cursor)
    elif trace_strokes:
        cursor = build_reference_trace(cursor)
    elif is_chalkboard:
        cursor = build_chalkboard_derivation(cursor)
    else:
        seven_habits_builder = select_seven_habits_builder()
        cursor = (seven_habits_builder or builders.get(diagram_kind, build_process_flow))(cursor)

    _retime_draw_ops_to_audio_segments(draw_ops, audio_segments, duration)
    return {
        "title": scene.title,
        "diagramKind": diagram_kind,
        "boardMode": board_mode,
        "handUsage": hand_usage,
        "videoStyle": video_style,
        "visualStyle": visual_style,
        "duration": duration,
        "audioUrl": _scene_extra(scene, "audioUrl") or _scene_extra(scene, "audio_url"),
        "audioSegments": audio_segments,
        "transitionFrames": transition_frames,
        "accent": accent,
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
        for index, scene in enumerate(storyboard.scenes)
    ]
    for scene_spec, scene in zip(scene_specs, storyboard.scenes):
        scene_spec["subtitleText"] = _subtitle_text(scene.narration) if subtitles_enabled else None
        if not subtitles_enabled:
            for segment in scene_spec.get("audioSegments") or []:
                segment["subtitleText"] = None
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
const BOARD_BACKGROUND = "#F7F7F2";
const BACKGROUND_MUSIC_URL: string | null = __BACKGROUND_MUSIC_URL__;
const BACKGROUND_MUSIC_VOLUME = __BACKGROUND_MUSIC_VOLUME__;
const FONT_FAMILY = "'STXingkai', '华文行楷', KaiTi, STKaiti, 'Kaiti SC', cursive";

type Point = { x: number; y: number };
type DrawOp = { id: string; kind: "text" | "path"; startFrame: number; endFrame: number; points: Point[]; pace?: "glyph" | "ease"; beatId?: string };
type TextSpec = { opId: string; text: string; x: number; y: number; fontSize: number; color: string; maxWidth: number; markerStrokeWidth?: number; markerFillOpacity?: number };
type GlyphPathSpec = { opId: string; sourceOpId: string; d: string; color: string; strokeWidth: number; dashLength: number; fontOutline: boolean; markerFillOpacity?: number };
type StrokeSpec = { opId: string; role: string; d: string; color: string; strokeWidth: number; dashLength: number };
type RasterStrokeSpec = { opId: string; d: string; revealWidth: number; dashLength: number };
type RasterRevealSpec = { asset: string; x: number; y: number; width: number; height: number; strokes: RasterStrokeSpec[]; renderMode?: "trace" | "direct"; directAppearFrame?: number };
type AudioSegmentSpec = { id: string; index?: number; startFrame: number; endFrame: number; duration: number; audioStartFrame?: number; audioEndFrame?: number; audioSequenceDuration?: number; audioUrl?: string | null; audioDurationFrames: number; drawBudgetFrames: number; subtitleText?: string | null; drawIntent?: string | null };
type SceneSpec = {
  title: string;
  diagramKind?: string;
  boardMode?: "whiteboard" | "chalkboard" | "clean_canvas" | "reference";
  handUsage?: "trace" | "annotate" | "none";
  videoStyle?: "auto" | "chalkboard_bw" | "chalkboard_color" | "modern_minimal" | "technical_blueprint" | "editorial" | "whiteboard" | "playful" | "sharpie";
  visualStyle?: "teacher_whiteboard" | "marketing_doodle" | "math_chalkboard" | "technical_reference" | "modern_minimal" | "editorial" | "playful" | "sharpie";
  duration: number;
  audioUrl?: string | null;
  audioSegments?: AudioSegmentSpec[];
  transitionFrames?: number;
  accent: string;
  drawOps: DrawOp[];
  texts: TextSpec[];
  glyphPaths?: GlyphPathSpec[];
  strokes: StrokeSpec[];
  referenceImageAsset?: string | null;
  rasterReveal?: RasterRevealSpec | null;
  subtitleText?: string | null;
};

const scenes = __SCENES_JSON__ as SceneSpec[];
const SUBTITLES_ENABLED = __SUBTITLES_ENABLED__;

const clamp01 = (value: number) => Math.max(0, Math.min(1, value));
const MIN_START_PROGRESS = 0.018;
const sceneBackground = (scene: SceneSpec) => {
  if (scene.boardMode === "chalkboard" || scene.visualStyle === "math_chalkboard") return "#050806";
  if (scene.videoStyle === "technical_blueprint") return "#18364A";
  if (scene.videoStyle === "modern_minimal") return "#F1F3F0";
  if (scene.videoStyle === "editorial") return "#FAF4EA";
  if (scene.videoStyle === "whiteboard") return "#FBFCF8";
  if (scene.videoStyle === "playful") return "#FBF7D8";
  if (scene.videoStyle === "sharpie") return "#FFFDF7";
  if (scene.boardMode === "clean_canvas") return "#F7F7F2";
  return BOARD_BACKGROUND;
};
const sceneCaptionColor = (scene: SceneSpec) =>
  scene.boardMode === "chalkboard" || scene.visualStyle === "math_chalkboard" ? "#F6F2E9" : "#111318";

const progressForOp = (frame: number, op: DrawOp) => {
  const baseConfig = {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  } as const;
  if (frame < op.startFrame) return 0;
  if (op.pace === "glyph") {
    return Math.max(MIN_START_PROGRESS, interpolate(frame, [op.startFrame, op.endFrame], [0, 1], baseConfig));
  }
  return Math.max(MIN_START_PROGRESS, interpolate(frame, [op.startFrame, op.endFrame], [0, 1], {
    ...baseConfig,
    easing: Easing.bezier(0.2, 0.8, 0.2, 1),
  }));
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
  const sentences = source.match(/[^。！？.!?；;]+[。！？.!?；;]?/g) ?? [source];
  const chunks: string[] = [];
  for (const sentence of sentences) {
    const clean = sentence.trim();
    if (!clean) continue;
    const prev = chunks[chunks.length - 1];
    if (prev && captionWeight(prev + clean) <= 64) {
      chunks[chunks.length - 1] = prev + clean;
    } else {
      chunks.push(clean);
    }
  }
  return chunks.filter(Boolean);
};

const SubtitleOverlay = ({ scene }: { scene: SceneSpec }) => {
  if (!SUBTITLES_ENABLED) return null;
  const frame = useCurrentFrame();
  const segments = scene.audioSegments ?? [];
  const activeSegment = segments.find((segment) => {
    const audioStart = segment.audioStartFrame ?? segment.startFrame;
    const audioEnd = segment.audioEndFrame ?? segment.endFrame;
    return frame >= audioStart && frame < audioEnd;
  });
  if (segments.length > 0 && !activeSegment) return null;
  const text = (activeSegment ? activeSegment.subtitleText : scene.subtitleText)?.trim();
  if (!text) return null;
  const chunks = splitSubtitleText(text);
  if (chunks.length === 0) return null;
  const audioStart = activeSegment ? activeSegment.audioStartFrame ?? activeSegment.startFrame : 0;
  const audioEnd = activeSegment ? activeSegment.audioEndFrame ?? activeSegment.endFrame : scene.duration;
  const localFrame = activeSegment ? frame - audioStart : frame;
  const localDuration = activeSegment ? Math.max(1, audioEnd - audioStart) : scene.duration;
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
          color: sceneCaptionColor(scene),
          fontFamily: "'Noto Sans SC', 'Microsoft YaHei', sans-serif",
          fontSize: 34,
          fontWeight: 500,
          lineHeight: 1.42,
          letterSpacing: 0,
          textAlign: "center",
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
  const fillOpacity = spec.fontOutline
    ? interpolate(progress, [0.68, 0.92], [0, spec.markerFillOpacity ?? 0.96], {
        extrapolateLeft: "clamp",
        extrapolateRight: "clamp",
      })
    : 0;
  return (
    <g>
      {fillOpacity > 0 ? <path d={spec.d} fill={spec.color} opacity={fillOpacity} stroke="none" /> : null}
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
    </g>
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
  if (reveal.renderMode === "direct") return null;
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
  if (reveal.renderMode === "direct") {
    const appearFrame = reveal.directAppearFrame ?? 0;
    const opacity = interpolate(frame, [appearFrame, appearFrame + 10], [0, 1], {
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
          zIndex: 4,
        }}
      />
    );
  }
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
        zIndex: 12,
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
            <Sequence key={segment.id} from={segment.audioStartFrame ?? segment.startFrame} durationInFrames={segment.audioSequenceDuration ?? Math.max(1, segment.endFrame - (segment.audioStartFrame ?? segment.startFrame))} layout="none">
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
  if (scene.boardMode === "whiteboard" && scene.visualStyle === "teacher_whiteboard") return null;
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
        backgroundColor: sceneBackground(scene),
        pointerEvents: "none",
        zIndex: 40,
      }}
    />
  );
};

const WhiteboardScene = ({ scene, sceneIndex }: { scene: SceneSpec; sceneIndex: number }) => {
  const frame = useCurrentFrame();
  const drawOps = scene.drawOps;
  const orderedDrawOps = [...drawOps].sort((a, b) => a.startFrame - b.startFrame);
  const backgroundColor = sceneBackground(scene);
  const showHand = scene.handUsage !== "none" && scene.boardMode !== "chalkboard" && scene.visualStyle !== "math_chalkboard";
  const getActiveDrawOp = (frame: number) =>
    orderedDrawOps.find((op) => frame >= op.startFrame && frame <= op.endFrame);
  const getPenPosition = (frame: number) => {
    const active = getActiveDrawOp(frame);
    if (active) {
      const progress = progressForOp(frame, active);
      const point = pointOnPolyline(active.points, progress);
      return { x: point.x, y: point.y, visible: true };
    }
    const previous = [...orderedDrawOps].reverse().find((op) => op.endFrame < frame);
    const next = orderedDrawOps.find((op) => op.startFrame > frame);
    if (previous && next) {
      const gap = next.startFrame - previous.endFrame;
      if (gap > 0 && gap <= 26 && frame >= previous.endFrame && frame <= next.startFrame) {
        const from = pointOnPolyline(previous.points, 1);
        const to = pointOnPolyline(next.points, 0);
        const t = interpolate(frame, [previous.endFrame, next.startFrame], [0, 1], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
          easing: Easing.bezier(0.2, 0.8, 0.2, 1),
        });
        return {
          x: interpolate(t, [0, 1], [from.x, to.x]),
          y: interpolate(t, [0, 1], [from.y, to.y]),
          visible: true,
        };
      }
    }
    return { x: -400, y: -400, visible: false };
  };
  const pen = getPenPosition(frame);

  return (
    <AbsoluteFill style={{ backgroundColor, overflow: "hidden" }}>
      <SceneAudio scene={scene} />
      {scene.boardMode === "chalkboard" || scene.visualStyle === "math_chalkboard" ? (
        <div
          style={{
            position: "absolute",
            inset: 0,
            backgroundColor: backgroundColor,
            pointerEvents: "none",
            zIndex: 1,
          }}
        />
      ) : null}
      <svg style={{ position: "absolute", inset: 0, width: "100%", height: "100%", zIndex: 10 }} viewBox={`0 0 ${VIDEO_WIDTH} ${VIDEO_HEIGHT}`}>
        <RasterRevealImage scene={scene} sceneIndex={sceneIndex} />
        <AnimeDoodle scene={scene} />
        <CartoonDiagram scene={scene} />
        <GlyphText scene={scene} />
      </svg>
      <RasterFinalOverlay scene={scene} />
      <SubtitleOverlay scene={scene} />
      <HandPen tipX={pen.x} tipY={pen.y} visible={showHand && pen.visible} />
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
        .replace("__SUBTITLES_ENABLED__", "true" if subtitles_enabled else "false")
        .strip(),
        duration,
    )


REMOTION_CODE_SYSTEM_PROMPT = """You are an expert Remotion engineer and motion designer.

Generate ONE self-contained TSX module for a complete educational whiteboard video.

Target visual reference:
- A clean light grey-white whiteboard canvas with rich colorful educational doodle/reference visuals where a real visible hand holds a marker and writes/draws concise board annotations live.
- Default generated reference art should match a bold editorial hand-drawn explainer: thick imperfect black crayon/marker outlines, warm off-white surface, coral-pink arrows/checks/starbursts/underlines, sunny yellow highlight blobs, one large subject or at most three large step groups, and generous blank space.
- Treat generated reference images as text-free artwork. Add all readable Chinese titles, labels, ticks, underlines and callouts in TSX with large handwritten glyph text, not as text baked into the image.
- Also support explicit scene-level modes from the storyboard:
  - `board_mode="whiteboard"` with `hand_usage="trace"`: teacher whiteboard with meaningful colorful marker visuals; the hand writes/draws the active strokes when the subject is simple enough.
  - `board_mode="reference"` or `hand_usage="annotate"`: present the complex/finished subject clearly, then use the hand only for short callouts, circles, arrows and underlines.
  - `board_mode="clean_canvas"` with `visual_style="marketing_doodle"`: colorful finished doodle groups may appear directly; the hand writes titles, ticks, arrows and emphasis marks.
  - `board_mode="chalkboard"` or `visual_style="math_chalkboard"`: use a dark chalkboard background, no visible hand, and reveal equations/steps line by line with chalk-like colors.
- Respect scene.videoStyle as the Golpo Canvas style layer:
  - `chalkboard_bw`: black canvas, white chalk only, sparse rough chalk line art, no hand.
  - `chalkboard_color`: black canvas, white/cyan chalk with limited yellow/teal emphasis, no hand.
  - `modern_minimal`: warm light grey canvas, thin lines, one cool accent, large whitespace.
  - `technical_blueprint`: deep navy canvas, pale-blue precise technical lines, subtle grid/drafting feel.
  - `editorial`: warm off-white canvas, bold black ink, restrained red/orange accents, collage-like object group.
  - `whiteboard`: off-white board, black marker outlines, blue labels, small colored fills, clear tutorial layout.
  - `playful`: warm cream canvas, crayon-like multicolor accents, rounded friendly objects.
  - `sharpie`: bright white canvas, thick black marker, bold rough icons, small highlighter accents, visible hand unless hand_usage is none.
- The hand must be on screen during drawing, with the pen tip touching the active text stroke, line, arrow, box, equation, or diagram.
- Use black marker outlines plus purposeful teaching colors: coral pink for arrows/checks/starbursts/active emphasis, red for current/flow/risk, blue for control arrows, green for valid paths/results, purple for relationships/systems, and yellow underlines/callouts/highlight blobs for key ideas. Keep the canvas clean and warm off-white; do not add dense colored panels behind diagrams.
- Text should feel handwritten: irregular but readable, large, dark/blue marker strokes, revealed character-by-character or word-by-word while the hand follows the reveal.
- Text must look like solid marker handwriting after it is written, not hollow font outlines.
- For Chinese text, fontFamily must start with a handwriting-style Chinese font stack like "KaiTi, STKaiti, Kaiti SC, cursive". Do not rely on default bold sans-serif Chinese.
- Graphics should feel like a teacher's hand-sketched board work: arrows, boxes, curves, charts, objects, callouts, underlines, and concept diagrams are revealed by strokes being drawn.
- Layout should match a real sparse whiteboard lesson: short blue handwritten title near the top-left or top-center, one central diagram occupying about 45-65% of the canvas width, large empty margins, and short labels placed near the parts they describe.
- Do not use a fixed left text column. Avoid explanatory paragraphs on the board; use only short labels, one-line conclusions, arrows, circles, brackets, and underlines.
- Every scene MUST have at least 5-8 distinct visual elements drawn, including:
  * The scene title as a short blue handwritten header
  * 1-3 large central diagram/icon/object illustrations (like a funnel, scale, gear, person, chart, map, matrix, cross-section, etc.)
  * 2-4 labeled arrows connecting elements or pointing to key parts
  * 1-2 colored callout boxes or circles highlighting important points
  * 1-2 underlines or brackets for emphasis
  * Short conclusion text or key takeaway label
- A scene that only has title text + bullet list or checkmarks is NOT acceptable. The diagram must be the hero of each scene.
- For topics like "how to improve English listening/reading", draw concrete visual metaphors:
  * For listening: headphones, waveform, ear, speech bubble, TV/screen, book, clock/timer, path/road
  * For reading: book, magnifying glass, eye, pen/highlighter, page with lines, comprehension ladder, brain with connections
  * Use person icons, action arrows, and process diagrams to make abstract skills tangible
- Never make a scene that is only a heading plus checklist, bullets, checkmarks, or generic text boxes. Checklist/checkmark marks may only be tiny supporting annotations beside a larger visual anchor.
- Use staged reveal like the reference videos: title or anchor first, main line-art object second, labels/arrows/callouts third, and one short conclusion last.
- Preserve lots of empty white space. Never create an inner paper, card, panel, slide, sheet, poster, white rectangle, or separate board surface; the full canvas background is the only whiteboard.
- Do not use washD, boxShadow, textShadow, drop-shadow, CSS filter, gradients, or any shadow/backing behind drawings or board text.
- Make the drawings feel lively and lightly humorous with small teacher-board metaphors, such as wrong-floor signs, tug-of-war choices, taxi route arrows, receipt/check tickets, tuning knobs, alarm marks, and playful marker annotations drawn directly on the board.
- Avoid slide-deck cards, polished UI panels, gradients, stock images, and decorative template layouts.
- Prefer one meaningful illustrated explanation per scene over dense bullet lists.
- Make the timeline feel continuous: do not leave long static holds between scenes, and stretch drawing operations so the hand keeps writing/drawing until shortly before the next scene starts.
- New scenes should begin writing immediately or within the first few frames; avoid one-second blank boards after a cut.
- Emphasize key concepts like a strong teacher's board work: underline terms, circle important regions, draw colored callout boxes, and use red/blue/green arrows to distinguish current, voltage, and channel formation.
- If subtitles_enabled is true, render scene.narration as readable bottom subtitles. Subtitles are a caption overlay, not board handwriting, so the hand should not write them and they should not consume drawOps time. If subtitles_enabled is false, omit subtitle overlays entirely.
- When scenes include audioSegments, use beat-level timing. DrawOps use startFrame/endFrame, but Audio and subtitles must start at audioStartFrame when provided, so the board can write a title or base outline before narration begins. Never play a whole-scene narration over unrelated drawing when beat audio is available.
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
- If subtitles_enabled is false, ignore scene.subtitleText and audioSegments[].subtitleText completely; do not render any caption overlay.
- The central animation model must be a `drawOps` array. Each op must have `kind`, `startFrame`, `endFrame`, and a `points: {x:number; y:number}[]` polyline that represents the actual stroke path the marker tip follows.
- The drawOps timeline should fill each scene with drawing work and avoid dead air. The final drawOp of a scene should end near the scene duration, leaving only a short natural beat before the next Sequence.
- If a drawOp belongs to a beat, set beatId and keep its startFrame/endFrame inside that beat's audioSegment. A scene may exceed the requested target duration if real TTS and drawing need it.
- Preserve beatId on teacher callouts and emphasis strokes so each beat visually points to the same concept that its narration explains.
- Define `pointOnPolyline(points, progress)`, `getActiveDrawOp(frame)`, and `getPenPosition(frame)`. The rendered `<HandPen>` must use `const pen = getPenPosition(frame)` and pass `tipX={pen.x}` and `tipY={pen.y}`. Hand visibility must come from whether an active draw op exists.
- During short gaps between neighboring drawOps, keep the hand visible and move it from the previous stroke endpoint to the next stroke start without drawing; this should feel like a teacher lifting and repositioning the marker, not a cursor teleport.
- The pen must move up, down, left, and right inside words and drawings. Do not make the hand travel along a single straight baseline for text. Text ops must include zig-zag or stroke-like points for each word/phrase so the marker visibly writes within glyph shapes.
- Never define `const tipX = interpolate(frame, [...])` or `const tipY = interpolate(frame, [...])` at scene level. Pen coordinates must be sampled from active `drawOps.points`.
- Every animated SVG path/arrow/box/diagram stroke must have a matching drawOp with similar points. The hand tip should be near the visible end of the stroke as strokeDashoffset reveals it.
- Handwritten text must use a real Chinese handwriting stack like `"STXingkai, 华文行楷, KaiTi, STKaiti, Kaiti SC, cursive"`. Do not use bold sans-serif text.
- The visual language must be classic teacher whiteboard: add small hand-drawn emphasis marks only when useful, such as ticks, brackets, circles, arrows, local zoom boxes, or callout rays. Use playful teaching metaphors when they clarify the idea; do not force mascots or decorative cartoon characters.
- Import Img and staticFile from "remotion" and render the visible hand using <Img src={staticFile("hand-real-pen.png")} />.
- Define a HandPen component in the same TSX module. It must receive `tipX`, `tipY` coordinates and position the hand image so the actual marker tip follows the currently drawn element.
- In explicit chalkboard/no-hand scenes, keep the HandPen component defined for other scenes but hide it for that scene; do not force a decorative hand onto math derivations.
- Use these exact hand alignment constants in TSX: `const HAND_WIDTH = 260; const HAND_HEIGHT = 289; const PEN_TIP_X = 15; const PEN_TIP_Y = 78;`. Render the hand with width HAND_WIDTH and height HAND_HEIGHT, and position it with `left: tipX - PEN_TIP_X`, `top: tipY - PEN_TIP_Y`.
- HandPen must return an absolutely positioned HTML `<div>` wrapping `<Img>`. Never render `<HandPen>` inside `<svg>`; render it as a sibling overlay after the SVG so Remotion's Img stays in HTML, not SVG namespace.
- The hand cannot be decorative. It must move across the canvas during every draw/write operation and be hidden only during pauses or completed static holds.
- Create a deterministic drawing timeline array or helper function that maps frame ranges to pen tip coordinates. Use interpolate() to move the hand between points; never jump instantly.
- The hand should be large enough to resemble the reference video, roughly 240-300 px wide on a 1920x1080 canvas, not a tiny cursor.
- SVG line drawings must use strokeDasharray and strokeDashoffset driven by useCurrentFrame()/interpolate().
- If a scene includes rasterReveal and referenceImageAsset, use rasterReveal.renderMode. For renderMode "trace", reveal the original line-art image through an SVG mask whose white paths use strokeDasharray/strokeDashoffset; drive HandPen from the same raster drawOps centerline points. For renderMode "direct", directly present the complex reference image with a short frame-driven opacity reveal, centered with generous empty space, then use HandPen only for large readable side callouts, short underlines, and small edge ticks near the image. Do not pretend to know exact internal object locations unless the storyboard provides explicit anchors; avoid long sweeping arrows and large circles covering the diagram. After trace raster drawOps finish, crossfade the masked SVG image out while adding a short final HTML <Img> overlay of the same transparent image outside the SVG, so the last frame fully matches the reference asset without turning transparent pixels black or double-darkening strokes.
- Animated dashed paths must have `fill="none"`. Do not use background washes or colored panels; use color only on teaching strokes, arrows, underlines, callouts, and small emphasis marks.
- Text must be progressively revealed with slice(), substring(), or a frame-driven clipPath. Do not show full paragraphs instantly.
- For Chinese text, define a `glyphPaths` array and render it with inline `GlyphText` / `DrawGlyphPath` helpers using SVG `<path>` plus strokeDasharray/strokeDashoffset. The render server will preprocess these glyph paths from a local Chinese font with opentype.js, so include text specs and matching text drawOps instead of static SVG `<text>`.
- For large handwritten glyph paths, after the stroke finishes, a light fill using the same marker color is allowed so the writing does not look hollow.
- Do not use an HTML `HandText` slice-only renderer as the final text drawing path. The pen must follow glyph outline/path points that can be replaced by the renderer.
- Opacity fade may be used only as a secondary polish, never as the main animation for text or diagrams.
- Do not use SVG SMIL tags such as <animate>. Even SVG details must be driven by Remotion frame values.
- Include multiple limited instructional colors in non-raster scenes, such as red current arrows, blue voltage/control arrows, green channel paths, purple gate/structure strokes, and yellow key underlines/callouts. Do not add color washes or colored panels behind any diagram; keep image assets transparent over the whiteboard canvas.
- Do not use transition, animation, @keyframes, Tailwind animate-* class names, setTimeout, setInterval, requestAnimationFrame, Date.now(), or Math.random().
- Do not use fetch, eval, Function, require, filesystem APIs, browser globals, or dangerouslySetInnerHTML.
- Hardcode the provided storyboard content and audio URLs into the TSX.
- Use <Audio src="..."> from remotion for scene voiceover when audioUrl exists.
- Prefer beat-level audio: for each scene.audioSegments item with audioUrl, render <Audio> inside a <Sequence from={segment.audioStartFrame ?? segment.startFrame} durationInFrames={segment.audioSequenceDuration ?? segment.duration}>.
- Use one additional global <Audio src={background_music_url} volume={background_music_volume} loop /> only when background_music_url is not null.
- Build visuals directly in TSX using HTML/CSS/SVG: hand-drawn lines, equations, arrows, curves, labels, diagrams, highlights.
- Avoid generic slide decks. Each scene must contain a meaningful visual explanation, not just bullets.
- If the storyboard asks for a summary, render it as a visual synthesis: loop, roadmap, hub-and-spoke map, evidence chart, or metaphor object. Do not render it as a plain checklist.
- Use the canvas background and palette implied by scene.videoStyle. Only fall back to the clean Chinese whiteboard teaching style when videoStyle is missing or `whiteboard`.
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
        "never creating inner paper/card/panel/sheet surfaces, shadows, washes, gradients, or backings behind drawings, "
        "making generic-topic visuals lively with small humorous teacher-board metaphors, "
        "using staticFile('hand-real-pen.png'), <Img>, and getPenPosition(frame) coordinates. "
        "When scene.audioSegments exist, synchronize Audio, subtitles, and drawOps to those beat windows. "
        "If subtitles_enabled is true, show scene.narration as bottom subtitles; if false, do not show captions. "
        "If background_music_url is provided, add it as one low-volume looping background Audio track behind narration. "
        "Respect scene board_mode/hand_usage/visual_style: hide the hand for chalkboard or hand_usage=none scenes, use direct/hybrid presentation for reference or annotate scenes, and use colorful finished doodles plus hand annotations for marketing_doodle scenes. "
        "Respect scene.video_style as the Golpo Canvas layer: black/white chalkboard stays white-only, color chalkboard uses limited cyan/yellow accents, modern_minimal stays sparse, technical_blueprint stays navy/pale-blue, editorial stays bold off-white/red-orange, whiteboard stays marker-board, playful stays crayon-pastel, and sharpie stays thick black marker. "
        "Use Chinese handwritten fonts and teacher-style whiteboard callouts. "
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
                    "include limited teaching accent colors and teacher-style whiteboard callouts, with a clean whiteboard background, "
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
