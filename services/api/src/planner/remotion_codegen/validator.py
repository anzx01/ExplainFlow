import re

from ..models import Storyboard

ALLOWED_IMPORTS = {"react", "remotion"}
HAND_ASSET = "hand-real-pen.png"

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



