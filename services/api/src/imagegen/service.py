import asyncio
import base64
import logging
import re
from dataclasses import dataclass

import httpx

from src.core.config import settings
from src.core.golpo_styles import golpo_video_style_aliases, golpo_video_style_presets
from src.core.visual_prompts import BOLD_EDITORIAL_IMAGE_NEGATIVE, BOLD_EDITORIAL_IMAGE_STYLE

logger = logging.getLogger(__name__)

_STYLE_SUFFIX = (
    f"{BOLD_EDITORIAL_IMAGE_STYLE}, "
    "rich colorful educational explainer illustration, matching an engaging real teacher marker-board lecture video, "
    "one vivid central visual metaphor, object, comparison, process, or mechanism per image; never a dense infographic, "
    "place the main illustration in the middle or slightly right of center, using about 55-75 percent of the frame width, "
    "leave broad clean margins around the drawing for a hand to write callouts later, "
    "hand-drawn marker and crayon doodle style with solid readable strokes, not just thin black line art, "
    "include 3-6 meaningful illustrated parts such as people, signs, clocks, routes, scales, gears, cards, arrows, badges, containers, food, cookware, or maps when they clarify the concept, "
    "do not add a title, topic heading, scene name, readable labels, logo, watermark, paragraph text, legend box, slide frame, or poster layout inside the image, "
    "the scene title and topic are only context for the artist; never render them as words inside the image, "
    "draw the specific mechanism described with broad process arrows, state comparison groups, local zoom-in details, and concrete metaphor objects when requested, "
    "for very complex objects, show the finished colorful doodle/reference illustration cleanly and leave room around it for hand-drawn callouts added later, "
    "show the final board drawing as if it has just been sketched by a skilled visual teacher: slightly irregular marker lines, simple expressive objects, lively but readable composition, "
    "avoid generic placeholder shapes, decorative templates, glossy 3D, photorealism, monochrome-only diagrams, and dense infographic layouts"
)

_NEGATIVE = (
    "photo, realistic, poster, 3d render, painting, complex background, decorative template, "
    f"{BOLD_EDITORIAL_IMAGE_NEGATIVE}, "
    "topic heading, dense infographic, long paragraph, slide frame, card layout, legend box"
)

_COOKING_TERMS = (
    "cook",
    "cooking",
    "recipe",
    "food",
    "dish",
    "wok",
    "skillet",
    "stir-fry",
    "simmer",
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

_BLANCHING_TERMS = (
    "blanch",
    "boiling water",
    "boil water",
    "parboil",
    "焯水",
    "汆",
    "煮水",
    "开水",
)

_STIR_FRY_TERMS = (
    "wok",
    "skillet",
    "stir-fry",
    "stir fry",
    "simmer",
    "thicken",
    "sauce",
    "炒",
    "煸",
    "爆香",
    "烧",
    "勾芡",
    "收汁",
    "底料",
)

_PREP_TERMS = ("prep", "prepare", "ingredient", "mise en place", "食材", "准备", "切", "备料")
_FINAL_TERMS = ("finish", "serve", "plate", "plating", "finished", "出锅", "装盘", "成品")
_OVERVIEW_TERMS = ("overview", "map", "流程图", "步骤流程", "风味地图", "概览", "总览")

_VIDEO_STYLE_ALIASES = golpo_video_style_aliases()
_VIDEO_STYLE_PRESETS = golpo_video_style_presets(include_aliases=False)


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
    style = _VIDEO_STYLE_ALIASES.get(style, style)
    return style if style in _VIDEO_STYLE_PRESETS else "whiteboard"


def _normalize_image_description(value: str | None) -> str:
    text = str(value or "").strip()
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
    return " ".join(text.split()).strip(" .") + "."


async def _call_seedream(prompt: str, client: httpx.AsyncClient) -> bytes:
    """调用 Seedream 5.0 生成图片，返回图片原始字节（Python 侧下载，避免 Node.js 访问外网超时）。"""
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

    # 在 Python 侧下载图片，避免 Node.js 跨网络访问 TOS 超时
    img_resp = await client.get(url, timeout=60.0)
    img_resp.raise_for_status()
    return img_resp.content


def _build_prompt(req: SceneImageRequest) -> str:
    mode = (req.board_mode or "whiteboard").strip().lower()
    canvas_style = _canonical_video_style(req.video_style)
    style = (req.visual_style or "teacher_whiteboard").strip().lower()
    style_preset = _VIDEO_STYLE_PRESETS.get(canvas_style, _VIDEO_STYLE_PRESETS["whiteboard"])
    if canvas_style in {"chalkboard_bw", "chalkboard_black_white"}:
        suffix = style_preset["image_prompt"]
        negative = (
            "color accents, cyan, yellow, red, green, pink, whiteboard, hand, marker, poster, dense infographic, photo, glossy 3d, "
            "colored panel, long paragraph, slide frame, card layout"
        )
    elif canvas_style == "chalkboard_color" or mode == "chalkboard" or style == "math_chalkboard":
        suffix = _VIDEO_STYLE_PRESETS["chalkboard_color"]["image_prompt"]
        negative = (
            "whiteboard, hand, marker, poster, dense infographic, photo, glossy 3d, colored panel, "
            "long paragraph, slide frame, card layout"
        )
    elif canvas_style == "modern_minimal" or style == "modern_minimal":
        suffix = style_preset["image_prompt"]
        negative = f"dark chalkboard, childish cartoon, thick sharpie mess, dense infographic, long text, logo, watermark, {BOLD_EDITORIAL_IMAGE_NEGATIVE}"
    elif canvas_style == "technical_blueprint" or style == "technical_reference":
        suffix = style_preset["image_prompt"]
        negative = _NEGATIVE
    elif canvas_style == "editorial" or style == "editorial":
        suffix = style_preset["image_prompt"]
        negative = f"dark chalkboard, messy classroom board, childish cartoon, glossy 3d, dense poster, logo, watermark, {BOLD_EDITORIAL_IMAGE_NEGATIVE}"
    elif canvas_style == "whiteboard":
        suffix = style_preset["image_prompt"]
        negative = (
            f"dark chalkboard, corporate flat vector, dense infographic, long paragraph, slide frame, card layout, logo, watermark, "
            f"monochrome-only line art, empty object, colorless food, {BOLD_EDITORIAL_IMAGE_NEGATIVE}"
        )
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
        negative = (
            f"photo, realistic, dense infographic, long paragraph, slide frame, card layout, logo, watermark, monochrome line art only, empty object, colorless food, {BOLD_EDITORIAL_IMAGE_NEGATIVE}"
        )
    else:
        suffix = _STYLE_SUFFIX
        negative = _NEGATIVE
    domain_suffix, domain_negative = _domain_prompt_constraints(req)
    image_description = _normalize_image_description(req.image_description)
    return (
        f"{image_description}. Topic context only, do not draw as text: {req.topic}. "
        f"Scene context only, do not draw as text: {req.title}. "
        f"{domain_suffix} {suffix}. Strict text-free policy: do not render any readable Chinese, English, letters, numbers, labels, captions, title, logo, watermark, UI text, or gibberish pseudo-text; leave clean blank callout spaces for renderer-added handwriting. "
        f"Negative prompt: {negative}, readable text, words, letters, numbers, labels, captions, title, logo, watermark, gibberish pseudo-text, {domain_negative}"
    )


def _domain_prompt_constraints(req: SceneImageRequest) -> tuple[str, str]:
    blob = f"{req.topic} {req.title} {req.image_description}".lower()
    if not any(term in blob for term in _COOKING_TERMS):
        return "", ""

    constraints = [
        "Food and cooking accuracy requirements: make the dish look appetizing and semantically correct, not a generic diagram.",
        "Use real food colors and visible texture: glossy red/orange sauce or chili oil where appropriate, white tofu cubes, brown minced meat, green scallions or garlic sprouts, steam, highlights, and small oil droplets.",
        "Keep it in the bold editorial hand-drawn explainer style: thick black crayon/marker outlines, coral pink arrows or emphasis marks, warm yellow highlight blobs, generous blank margins, no readable text in the image.",
        "The cookware, ingredients, and finished food must be immediately recognizable.",
        "Use one large food or cookware state as the primary visual anchor; avoid dense rows of tiny pots, mini process boxes, and small unreadable recipe captions.",
    ]
    negative = [
        "empty cookware",
        "grey or colorless food",
        "plain black-and-white food",
        "generic ingredients with no dish",
        "wrong cookware",
        "tiny unreadable food",
        "readable text inside the artwork",
        "gibberish labels",
    ]

    is_mapo = "mapo" in blob or "麻婆" in blob or "doubanjiang" in blob or "豆瓣" in blob
    if is_mapo:
        constraints.append(
            "For mapo tofu specifically: show Sichuan mapo tofu with white tofu cubes in a glossy red chili-bean sauce, brown minced meat, green garlic sprouts or scallions, red chili oil, Sichuan pepper speckles, and rising steam."
        )
        negative.extend(["white plain tofu only", "tomato soup", "western stew", "salad-like tofu"])

    is_prep = any(term in blob for term in _PREP_TERMS)
    is_final = any(term in blob for term in _FINAL_TERMS)
    is_blanch = any(term in blob for term in _BLANCHING_TERMS)
    is_stir_fry = any(term in blob for term in _STIR_FRY_TERMS)
    is_overview = any(term in blob for term in _OVERVIEW_TERMS)

    if is_final:
        constraints.append(
            "For the finished serving scene, show a shallow white bowl or plate filled with red mapo tofu, tofu cubes clearly visible, garnish on top, and sauce color rich and warm."
        )
    elif is_prep:
        constraints.append(
            "For ingredient preparation, show a cutting board and small bowls with tofu cubes, minced meat, doubanjiang chili bean paste, Sichuan pepper, garlic or garlic sprouts, starch slurry, and scallions; no empty pot as the main subject."
        )
    elif is_overview:
        constraints.append(
            "For an overview scene, show at most three large illustrated cooking states, or one finished dish with 3-5 big flavor callouts; do not create a five-step row of small pots or tiny text boxes."
        )
    elif is_blanch and not is_stir_fry:
        constraints.append(
            "For blanching only, a simple pot of boiling water is acceptable, with white tofu cubes gently moving in clear water and steam; do not make this look like the final sauce step."
        )
    else:
        constraints.append(
            "For stir-fry, sauce simmering, or thickening steps, use a wide black Chinese wok or skillet on a burner, not a blue soup pot; show red chili oil sauce around tofu cubes and minced meat."
        )
        negative.extend(["blue soup pot", "stockpot as the main pan", "sauce cooked in a blue pot"])

    return " ".join(constraints), ", ".join(negative)


async def generate_scene_image(req: SceneImageRequest, client: httpx.AsyncClient) -> str | None:
    """生成单个场景插图，返回 base64 编码的图片数据（失败返回 None）。"""
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
    """并行生成所有场景图片，返回 {scene_id: base64_data} 字典。"""
    async with httpx.AsyncClient() as client:
        results = await asyncio.gather(*[generate_scene_image(r, client) for r in requests])
    return {req.scene_id: b64 for req, b64 in zip(requests, results)}
