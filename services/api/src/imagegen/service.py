import asyncio
import base64
import logging
import re
from dataclasses import dataclass

import httpx

from src.core.config import settings
from src.core.visual_prompts import BOLD_EDITORIAL_IMAGE_NEGATIVE, BOLD_EDITORIAL_IMAGE_STYLE, visual_teaching_rules_prompt
from .prompts import (
    ACTIVE_VIDEO_STYLE,
    BLANCHING_TERMS,
    COOKING_TERMS,
    FINAL_TERMS,
    NEGATIVE,
    OVERVIEW_TERMS,
    PREP_TERMS,
    STIR_FRY_TERMS,
    STYLE_SUFFIX,
    VIDEO_STYLE_ALIASES,
    VIDEO_STYLE_PRESETS,
)

logger = logging.getLogger(__name__)


@dataclass
class SceneImageRequest:
    scene_id: str
    topic: str
    title: str
    image_description: str
    board_mode: str = "whiteboard"
    hand_usage: str = "trace"
    video_style: str = "whiteboard"
    visual_style: str = "teacher_whiteboard"
    pen_style: str = "marker"


def _canonical_video_style(value: str | None) -> str:
    style = str(value or "").strip().lower()
    style = VIDEO_STYLE_ALIASES.get(style, style)
    if style != ACTIVE_VIDEO_STYLE:
        return ACTIVE_VIDEO_STYLE if ACTIVE_VIDEO_STYLE in VIDEO_STYLE_PRESETS else "whiteboard"
    return style if style in VIDEO_STYLE_PRESETS else "whiteboard"


def _normalize_image_description(value: str | None) -> str:
    text = str(value or "").strip()
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
    return " ".join(text.split()).strip(" .") + "."


async def _call_seedream(prompt: str, client: httpx.AsyncClient) -> bytes:
    headers = {
        "Authorization": f"Bearer {settings.ark_api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": settings.seedream_model,
        "prompt": prompt,
        "size": "2048x2048",
        "n": 1,
        "response_format": "url",
        "watermark": False,
    }
    resp = await client.post(
        f"{settings.ark_base_url}/images/generations",
        headers=headers,
        json=payload,
        timeout=60.0,
    )
    resp.raise_for_status()
    url: str = resp.json()["data"][0]["url"]
    img_resp = await client.get(url, timeout=60.0)
    img_resp.raise_for_status()
    return img_resp.content


def _build_prompt(req: SceneImageRequest) -> str:
    mode = (req.board_mode or "whiteboard").strip().lower()
    canvas_style = _canonical_video_style(req.video_style)
    style = (req.visual_style or "teacher_whiteboard").strip().lower()
    style_preset = VIDEO_STYLE_PRESETS.get(canvas_style, VIDEO_STYLE_PRESETS["whiteboard"])
    core_rules = visual_teaching_rules_prompt("imagegen")
    if canvas_style in {"chalkboard_bw", "chalkboard_black_white"}:
        suffix = style_preset["image_prompt"]
        negative = "color accents, cyan, yellow, red, green, pink, whiteboard, hand, marker, poster, dense infographic, photo, glossy 3d, colored panel, long paragraph, slide frame, card layout"
    elif canvas_style == "chalkboard_color" or mode == "chalkboard" or style == "math_chalkboard":
        suffix = VIDEO_STYLE_PRESETS["chalkboard_color"]["image_prompt"]
        negative = "whiteboard, hand, marker, poster, dense infographic, photo, glossy 3d, colored panel, long paragraph, slide frame, card layout"
    elif canvas_style == "modern_minimal" or style == "modern_minimal":
        suffix = style_preset["image_prompt"]
        negative = f"dark chalkboard, childish cartoon, thick sharpie mess, dense infographic, long text, logo, watermark, {BOLD_EDITORIAL_IMAGE_NEGATIVE}"
    elif canvas_style == "technical_blueprint" or style == "technical_reference":
        suffix = style_preset["image_prompt"]
        negative = NEGATIVE
    elif canvas_style == "editorial" or style == "editorial":
        suffix = style_preset["image_prompt"]
        negative = f"dark chalkboard, messy classroom board, childish cartoon, glossy 3d, dense poster, logo, watermark, {BOLD_EDITORIAL_IMAGE_NEGATIVE}"
    elif canvas_style == "whiteboard":
        suffix = f"{style_preset['image_prompt']}. {core_rules}"
        negative = f"dark chalkboard, corporate flat vector, dense infographic, long paragraph, slide frame, card layout, logo, watermark, monochrome-only line art, empty object, colorless food, {BOLD_EDITORIAL_IMAGE_NEGATIVE}"
    elif canvas_style == "playful" or style == "playful":
        suffix = style_preset["image_prompt"]
        negative = f"corporate flat vector, dark chalkboard, technical blueprint, stern business diagram, dense text, logo, watermark, {BOLD_EDITORIAL_IMAGE_NEGATIVE}"
    elif canvas_style == "sharpie" or style == "sharpie":
        suffix = style_preset["image_prompt"]
        negative = f"thin technical lines, pastel-only soft doodle, glossy 3d, dense poster, long text, logo, watermark, {BOLD_EDITORIAL_IMAGE_NEGATIVE}"
    elif mode == "clean_canvas" or style == "marketing_doodle":
        suffix = (
            f"{BOLD_EDITORIAL_IMAGE_STYLE}, "
            "clean canvas colorful graphic-storyboard explainer frame, rich hand-drawn finished doodle artwork, "
            "large appetizing or inspectable main subject when the topic is food, tools, products, people, or procedures, "
            "large empty margins for later marker annotations, thick friendly black ink outlines, coral pink accents and warm yellow highlight blobs, "
            "subject-specific real colors and visible material texture; for food show sauce, ingredients, steam, garnish and highlights, "
            "clear grouped visual metaphor objects with 3-6 meaningful illustrated parts, not every contour needs to be traced by hand, "
            "avoid dense poster layout and avoid all readable text inside the image"
        )
        negative = f"photo, realistic, dense infographic, long paragraph, slide frame, card layout, logo, watermark, monochrome line art only, empty object, colorless food, {BOLD_EDITORIAL_IMAGE_NEGATIVE}"
    else:
        suffix = STYLE_SUFFIX
        negative = NEGATIVE
    domain_suffix, domain_negative = _domain_prompt_constraints(req)
    image_description = _normalize_image_description(req.image_description)
    return (
        f"{image_description}. Topic context only, do not draw as text: {req.topic}. "
        f"Scene context only, do not draw as text: {req.title}. "
        f"{domain_suffix} {suffix}. Strict text-free policy: do not render any readable Chinese, English, letters, numbers, labels, captions, title, logo, watermark, UI text, or gibberish pseudo-text; leave open whitespace in the margins for renderer-added handwriting, not empty callout boxes or placeholder bubbles. "
        f"Negative prompt: {negative}, readable text, words, letters, numbers, labels, captions, title, logo, watermark, gibberish pseudo-text, empty label boxes, blank callout boxes, empty circles, unlabeled geometric shapes, placeholder bubbles, blank legend boxes, standalone annotation arrows, pointing arrows, baked callout arrows, standalone warning marks, standalone brackets, {domain_negative}"
    )


def _domain_prompt_constraints(req: SceneImageRequest) -> tuple[str, str]:
    blob = f"{req.topic} {req.title} {req.image_description}".lower()
    if not any(term in blob for term in COOKING_TERMS):
        return "", ""

    constraints = [
        "Food and cooking accuracy requirements: make the dish look appetizing and semantically correct, not a generic diagram.",
        "Use real food colors and visible texture: glossy red/orange sauce or chili oil where appropriate, white tofu cubes, brown minced meat, green scallions or garlic sprouts, steam, highlights, and small oil droplets.",
        "Keep it in the bold editorial hand-drawn explainer style: thick black crayon/marker outlines, subject-integral color accents only, warm yellow highlight blobs behind the food, generous blank margins, no readable text or teacher annotation marks in the image.",
        "The cookware, ingredients, and finished food must be immediately recognizable.",
        "Use one large food or cookware state as the primary visual anchor; avoid dense rows of tiny pots, mini process boxes, and small unreadable recipe captions.",
    ]
    negative = [
        "empty cookware", "grey or colorless food", "plain black-and-white food",
        "generic ingredients with no dish", "wrong cookware", "tiny unreadable food",
        "readable text inside the artwork", "gibberish labels",
    ]

    is_mapo = "mapo" in blob or "麻婆" in blob or "doubanjiang" in blob or "豆瓣" in blob
    if is_mapo:
        constraints.append("For mapo tofu specifically: show Sichuan mapo tofu with white tofu cubes in a glossy red chili-bean sauce, brown minced meat, green garlic sprouts or scallions, red chili oil, Sichuan pepper speckles, and rising steam.")
        negative.extend(["white plain tofu only", "tomato soup", "western stew", "salad-like tofu"])

    is_final = any(term in blob for term in FINAL_TERMS)
    is_prep = any(term in blob for term in PREP_TERMS)
    is_overview = any(term in blob for term in OVERVIEW_TERMS)
    is_blanch = any(term in blob for term in BLANCHING_TERMS)
    is_stir_fry = any(term in blob for term in STIR_FRY_TERMS)

    if is_final:
        constraints.append("For the finished serving scene, show a shallow white bowl or plate filled with red mapo tofu, tofu cubes clearly visible, garnish on top, and sauce color rich and warm.")
    elif is_prep:
        constraints.append("For ingredient preparation, show a cutting board and small bowls with tofu cubes, minced meat, doubanjiang chili bean paste, Sichuan pepper, garlic or garlic sprouts, starch slurry, and scallions; no empty pot as the main subject.")
    elif is_overview:
        constraints.append("For an overview scene, show at most three large illustrated cooking states, or one finished dish with 3-5 big flavor callouts; do not create a five-step row of small pots or tiny text boxes.")
    elif is_blanch and not is_stir_fry:
        constraints.append("For blanching only, a simple pot of boiling water is acceptable, with white tofu cubes gently moving in clear water and steam; do not make this look like the final sauce step.")
    else:
        constraints.append("For stir-fry, sauce simmering, or thickening steps, use a wide black Chinese wok or skillet on a burner, not a blue soup pot; show red chili oil sauce around tofu cubes and minced meat.")
        negative.extend(["blue soup pot", "stockpot as the main pan", "sauce cooked in a blue pot"])

    return " ".join(constraints), ", ".join(negative)


async def generate_scene_image(req: SceneImageRequest, client: httpx.AsyncClient) -> str | None:
    prompt = _build_prompt(req)
    try:
        img_bytes = await _call_seedream(prompt, client)
        b64 = base64.b64encode(img_bytes).decode()
        logger.info("[imagegen] %s → %d bytes", req.scene_id, len(img_bytes))
        return b64
    except Exception as e:
        logger.warning("[imagegen] %s failed: %s", req.scene_id, e)
        return None


async def generate_all_scene_images(requests: list[SceneImageRequest]) -> dict[str, str | None]:
    async with httpx.AsyncClient() as client:
        results = await asyncio.gather(*[generate_scene_image(r, client) for r in requests])
    return {req.scene_id: b64 for req, b64 in zip(requests, results)}
