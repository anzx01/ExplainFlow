import re

from .validator import (
    ALLOWED_IMPORTS,
    HAND_ASSET,
    FORBIDDEN_CODE_TOKENS,
    FORBIDDEN_CODE_PATTERNS,
    _has_teaching_accent,
    _validate_stroke_following_timeline,
    _validate_glyph_outline_text,
    _validate_handwritten_whiteboard_style,
    _validate_no_paper_surface,
    _validate_static_file_usage,
    _normalize_generated_video_export,
    _strip_code_fence,
    _has_generated_video_named_export,
    _validate_beat_timing_usage,
)
from ..models import GenerateRemotionCodeRequest, Storyboard


def _storyboard_has_audio_segments(storyboard: Storyboard) -> bool:
    for scene in storyboard.scenes:
        value = getattr(scene, "audioSegments", None) or getattr(scene, "audio_segments", None)
        if value:
            return True
        extra = getattr(scene, "model_extra", None)
        if isinstance(extra, dict) and (extra.get("audioSegments") or extra.get("audio_segments")):
            return True
    return False

def _validate_generated_tsx_for_request(tsx: str, req: GenerateRemotionCodeRequest) -> str:
    code = _validate_generated_tsx(tsx)
    if _storyboard_has_audio_segments(req.storyboard):
        _validate_beat_timing_usage(code)
    return code



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


