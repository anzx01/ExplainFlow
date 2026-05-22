import re

from src.core.text_utils import localize_chinese_terms
from src.core.golpo_styles import (
    golpo_pen_style_presets,
    golpo_video_style_aliases,
    golpo_video_style_presets,
    golpo_video_styles,
)
from src.core.visual_prompts import (
    BOLD_EDITORIAL_IMAGE_DESCRIPTION_HINT,
    visual_teaching_rules,
)
from ..models import Scene, VisualBeat, AnnotationPlanItem, DiagramPlan

# -------- Shared video/pen style tables (loaded once at import time) --------
_LEGACY_VIDEO_STYLE_PRESETS: dict = {}  # populated below
_LEGACY_VIDEO_STYLE_ALIASES: dict = {}
_LEGACY_PEN_STYLE_PRESETS: dict = {}
_LEGACY_GOLPO_CANVAS_VIDEO_STYLES: set = set()

VIDEO_STYLE_PRESETS: dict = golpo_video_style_presets()
VIDEO_STYLE_ALIASES: dict = golpo_video_style_aliases()
PEN_STYLE_PRESETS: dict = golpo_pen_style_presets()
TEACHING_RULES: dict = visual_teaching_rules()
ACTIVE_VIDEO_STYLE: str = str(TEACHING_RULES.get("active_style") or "whiteboard")
ACTIVE_PEN_STYLE: str = str(TEACHING_RULES.get("active_pen_style") or "marker")
ALLOWED_VIDEO_STYLES: set = set(VIDEO_STYLE_PRESETS) | set(VIDEO_STYLE_ALIASES)
ALLOWED_PEN_STYLES: set = set(PEN_STYLE_PRESETS)

def _localize_chinese_terms(text: str) -> str:
    """Localize Chinese terms (delegates to shared module)."""
    return localize_chinese_terms(text)

def _short_text(value: str | None, max_chars: int = 30) -> str:
    """Truncate text to max_chars, appending ellipsis if needed."""
    text = re.sub(r"\s+", " ", value or "").strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3].rstrip() + "..."

def _clean_text(value: object) -> str:
    """Clean and localize text."""
    text = "" if value is None else str(value)
    return localize_chinese_terms(re.sub(r"\s+", " ", text).strip())

def _normalize_image_description_text(value: object) -> str:
    text = _clean_text(value)
    if not text:
        return ""
    replacements = [
        (r"\b(?:top|bottom|upper|lower|left|right|center)(?:[-\s]+(?:left|right|center))?\s+(?:blue|red|green|yellow|pink|coral[-\s]?pink)?\s*(?:hand[-\s]?drawn\s+)?(?:scene\s+)?title\s+['\"][^.;]*['\"]?[^.;]*", "open top margin for renderer-added title"),
        (r"\b(?:top|bottom|upper|lower|left|right|center)(?:[-\s]+(?:left|right|center))?\s+(?:blue|red|green|yellow|pink|coral[-\s]?pink)?\s*(?:hand[-\s]?drawn\s+)?(?:scene\s+)?title[^.;]*", "open top margin for renderer-added title"),
        (r"\blater additions?\s*[:：-]?\s*[^.;]*(?:arrow|circle|callout|highlight|label|title|star|warning|underline|tick)[^.;]*", "open whitespace for renderer-drawn annotations"),
        (r"\b(?:thick|large|bold|curved|straight|wavy|short|long)\s+(?:red|blue|green|yellow|pink|coral[-\s]?pink)?\s*(?:hand[-\s]?drawn\s+)?arrows?\s+(?:from|to|pointing|points|highlight|callout|toward|towards)[^.;]*", "open whitespace for renderer-drawn arrows"),
        (r"\b(?:red|blue|green|yellow|pink|coral[-\s]?pink)\s+(?:hand[-\s]?drawn\s+)?arrows?\s+(?:from|to|pointing|points|highlight|callout|toward|towards)[^.;]*", "open whitespace for renderer-drawn arrows"),
        (r"\b(?:red|blue|green|yellow|pink|coral[-\s]?pink)\s+(?:hand[-\s]?drawn\s+)?(?:arrow|arrows|underline|underlines|tick|ticks|starburst|starbursts|star|stars|warning mark|warning marks)[^.;]*", "open whitespace for renderer-drawn annotations"),
        (r"\b(left|right|top|bottom|center)\s+panel\s+labeled\s+[^,.;。]+", r"\1 panel with open whitespace nearby"),
        (r"\b(?:\w+\s+)?(?:red|blue|green|yellow|pink)\s+(?:hand[-\s]?drawn\s+)?circles?\s+and\s+arrows?\s+highlight[^.;。]*", "open whitespace for renderer-drawn risk callouts"),
        (r"\b(?:red|blue|green|yellow|pink)\s+(?:hand[-\s]?drawn\s+)?circles?\s+(?:circle|around|near|highlight|mark)[^.;。]*", "open whitespace for renderer-drawn circle callouts"),
        (r"\b(?:draw|show|add)\s+(?:a\s+)?(?:red|blue|green|yellow|pink)\s+(?:lightning bolt|exclamation mark|warning icon|walkie-talkie icon|train icon|broken line|cross mark)[^.;。]*", "leave that risk marker for the renderer to draw later"),
        (r"\blabeled\s+", ""),
        (r"\blabel(?:s|ed)?\s+[^.;。]*", "open whitespace for later callouts"),
        (r"\bwith\s+(?:exact\s+)?labels?\s+(?:for|showing|on|such as|including)\b", "with open whitespace for"),
        (r"\blabels?\s*[:：][^.;。]*", "open whitespace for later callouts"),
        (r"\blabeled\b", "unlabeled"),
        (r"\bshort\s+(?:nearby\s+|handwritten\s+|blue\s+)?labels?\b", "open nearby whitespace"),
        (r"(?<!no )\breadable\s+(?:title|text|label|labels|words?)\b", "open whitespace"),
        (r"\bshort\s+(?:blue\s+)?handwritten\s+title\b", "open top margin"),
        (r"\btopic heading\b", "open top margin"),
        (r"\bcaption(?:s)?\b", "open margin area"),
        (r"\bformula\s+[^,.;。]+", "formula-shaped blank math area"),
        (r"\b(?:tokens?|speech marks)\s+saying\s+[^,.;。]+", "blank speech marks"),
    ]
    for pattern, replacement in replacements:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    if "text-free" not in text.lower():
        text = f"{text}. text-free artwork; no readable words, no letters, no labels, no title, no watermark"
    elif "no readable" not in text.lower():
        text = f"{text}; no readable words, letters, labels, title, or watermark"
    text = re.sub(r"\bno open whitespace\b", "no readable words", text, flags=re.IGNORECASE)
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
    if style != ACTIVE_VIDEO_STYLE:
        return ACTIVE_VIDEO_STYLE if ACTIVE_VIDEO_STYLE in VIDEO_STYLE_PRESETS else "whiteboard"
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
    if style != ACTIVE_PEN_STYLE:
        return ACTIVE_PEN_STYLE if ACTIVE_PEN_STYLE in ALLOWED_PEN_STYLES else "marker"
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

def _annotation_template_types() -> list[str]:
    templates = TEACHING_RULES.get("annotation_templates", [])
    types = [_clean_text(item.get("type")) for item in templates if isinstance(item, dict)]
    return [item for item in types if item]

def _parse_annotation_plan(value: object) -> list[AnnotationPlanItem]:
    if not isinstance(value, list):
        return []
    allowed = set(_annotation_template_types())
    items: list[AnnotationPlanItem] = []
    for raw in value:
        if not isinstance(raw, dict):
            continue
        annotation_type = _clean_text(raw.get("type"))
        label = _clean_text(raw.get("label"))
        target = _clean_text(raw.get("target"))
        beat_id = _clean_text(raw.get("beat_id") or raw.get("beatId")) or "beat_0"
        layer = _clean_text(raw.get("layer")) or "renderer"
        if not annotation_type or (allowed and annotation_type not in allowed):
            continue
        if not label or not target:
            continue
        items.append(
            AnnotationPlanItem(
                type=annotation_type,
                label=label[:24],
                target=target[:36],
                beat_id=beat_id,
                layer=layer if layer in {"renderer", "image"} else "renderer",
            )
        )
    return items[:8]

