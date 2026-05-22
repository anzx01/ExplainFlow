"""Shared visual prompt presets for storyboard planning and image generation."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def visual_teaching_rules() -> dict:
    rules_path = Path(__file__).with_name("visual_teaching_rules.json")
    return json.loads(rules_path.read_text(encoding="utf-8"))


def _rule_join(values: list[str] | tuple[str, ...]) -> str:
    return "; ".join(str(value).strip() for value in values if str(value).strip())


def visual_teaching_rules_prompt(context: str = "general") -> str:
    rules = visual_teaching_rules()
    style = rules.get("style_tokens", {})
    density = (rules.get("visual_density", {}) or {}).get(rules.get("mode_policy", {}).get("default_density", "rich"), {})
    templates = rules.get("annotation_templates", [])
    baked = rules.get("baked_image_policy", {})
    mode = rules.get("mode_policy", {})

    ui_policy = rules.get("ui_policy", {})

    lines = [
        f"Project visual teaching rules v{rules.get('version', 1)} ({rules.get('teaching_feel', 'illustrated_tutorial_handdrawn')}):",
        f"- Active style only: video_style={rules.get('active_style', 'whiteboard')}; pen_style={rules.get('active_pen_style', 'marker')}. {ui_policy.get('rule', '')}",
        f"- Default density: {mode.get('default_density', 'rich')}; {density.get('rule', '')}",
        f"- Style tokens: canvas={style.get('canvas')}; main line={style.get('main_line')}; title={style.get('title')}; risk={style.get('risk')}; safe={style.get('safe')}; emphasis={style.get('emphasis')}; relationship={style.get('relationship')}; hand={style.get('hand')}; lesson={style.get('lesson_feel')}.",
        f"- Mode split: simple trace scenes are for {_rule_join(mode.get('simple_trace', {}).get('use_for', []))}; complex direct_reference scenes are for {_rule_join(mode.get('direct_reference', {}).get('use_for', []))}.",
        f"- Mixed video rule: {mode.get('mixed_video_rule', '')}",
        "- Annotation plan required: each scene needs annotation_plan entries using at least 3 types from "
        + ", ".join(template.get("type", "") for template in templates)
        + ". Every annotation must include type, label, target, beat_id, layer='renderer'.",
        f"- Baked image policy: {baked.get('image_model_role', '')} {baked.get('prompt_rule', '')}",
        "- Forbidden baked annotations: " + _rule_join(baked.get("forbidden_baked_annotations", [])) + ".",
        "- Scene order: " + rules.get("scene_order_policy", {}).get("rule", ""),
    ]
    if context == "imagegen":
        lines.extend(
            [
                "- Imagegen must produce only clean subject artwork; no readable text, no teacher annotations, and open whitespace for renderer-added handwriting.",
                "- Allowed subject symbols: " + _rule_join(baked.get("allowed_subject_symbols", [])) + ".",
            ]
        )
    if context == "render":
        lines.extend(
            [
                "- Renderer must follow annotation_plan and bind every circle, box, arrow, bracket, tick, underline, ray, check, or crossout to a readable label or beat target.",
                "- Renderer must preserve referenceImageAsset and render it with RasterRevealImage/RasterFinalOverlay or staticFile(referenceImageAsset).",
            ]
        )
    return "\n".join(line for line in lines if line.strip())

BOLD_EDITORIAL_HANDDRAWN_STYLE_NAME = "bold_editorial_handdrawn"

BOLD_EDITORIAL_IMAGE_STYLE = (
    "bold editorial hand-drawn explainer illustration inspired by modern marker and wax-crayon storyboard slides, "
    "warm off-white whiteboard or paper surface with subtle grain, "
    "thick imperfect black marker/crayon outlines, loose sketch texture, expressive but simple people, objects, food, tools, or icons, "
    "large friendly visual anchors rather than tiny symbols, "
    "hot pink accent connectors only when they are integral process paths between subject parts; no baked callout arrows, pointing arrows, warning marks, underlines, circles, brackets, or title marks, "
    "sunny yellow paint-blob or halo highlight shapes behind the main subject, never as a full-page background, "
    "limited lively palette: black ink, warm yellow, coral pink, small grey fills, plus subject-specific semantic colors, "
    "composition has one big subject or at most three big step groups; if step connectors are needed, they connect the subject parts directly and never point at the subject as annotations, "
    "leave generous blank margins for renderer-added handwriting and later animated callouts, "
    "complex direct-reference artwork and simple hand-drawn diagrams must share the same marker/crayon line texture, palette, and whiteboard surface, "
    "reserve space for varied later annotations drawn by the renderer: short arrows, wavy underlines, brackets, edge ticks, starbursts, circles, and local zoom callouts, "
    "leave open whitespace rather than empty callout boxes, empty circles, blank speech bubbles, label plaques, or placeholder legend panels, "
    "any box, circle, bracket, arrow, badge, starburst, underline, or tick baked into the image must be part of the actual subject, never a teacher annotation placeholder, "
    "text-free artwork: do not draw titles, paragraphs, captions, labels, UI buttons, logos, watermarks, or random letters; "
    "the video renderer will add all readable text separately in a handwritten style"
)

BOLD_EDITORIAL_IMAGE_DESCRIPTION_HINT = (
    "Style preset: bold editorial hand-drawn explainer illustration, thick imperfect black crayon/marker outlines, "
    "warm off-white surface, subject-integral color accents only, sunny yellow highlight blobs behind the main subject, "
    "one large friendly subject or at most three large step groups, generous blank space, text-free artwork for later handwritten overlays."
)

BOLD_EDITORIAL_IMAGE_NEGATIVE = (
    "photorealistic, glossy 3d, stock vector template, corporate flat vector, thin technical line art only, "
    "monochrome-only diagram, dense infographic, crowded flowchart, tiny icons, tiny labels, long paragraph, "
    "AI-generated gibberish text, title text, captions, UI button, logo, watermark, full yellow background, "
    "card grid, slide deck frame, legend box, decorative border, baked callout arrows, pointing arrows, "
    "standalone warning marks, unlabeled circles, unlabeled boxes"
)

BOLD_EDITORIAL_BOARD_RULES = [
    "采用粗黑蜡笔/马克笔手绘质感：主体线条要厚、有轻微抖动，不能像细线技术图或单调简笔画。",
    "画面以一个大主体为核心，或最多三个大步骤；不要排很多小框、小图标、小锅、小字流程。",
    "使用参考图式配色：黑色主体线，主体内部可用少量题材语义色，暖黄色大色块或光晕放在主体背后；箭头、勾选、爆炸星、下划线等教学标注由渲染端后加。",
    "图像模型负责生成大手绘图形、人物、物体、食物、色块和箭头；可读文字、标题、中文标签和动态标注由渲染端手写叠加。",
    "image_description 要明确要求 text-free artwork，并预留空白给后续手写标题、callout、勾选、下划线和短箭头。",
]

BOLD_EDITORIAL_LAYOUT_RULES = [
    "一屏一个核心画面：大人物/大物体/大食物/大工具占主要视觉面积，旁边只留少量短标注。",
    "可使用暖黄色 blob/halo 放在主体背后，粉色宽箭头串起步骤，但不要做整页彩色背景或密集海报。",
    "如果有步骤流程，最多三个大节点；超过三个步骤要拆分到多个场景，用旁白承接细节。",
]
