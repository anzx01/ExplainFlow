import asyncio
import base64
import hashlib
import io
import logging
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

import httpx
from PIL import Image

from src.core.config import settings
from src.core.visual_prompts import BOLD_EDITORIAL_IMAGE_NEGATIVE, BOLD_EDITORIAL_IMAGE_STYLE, visual_teaching_rules_prompt
from .quality import inspect_generated_image, normalize_whiteboard_image
from .prompts import (
    ACTIVE_VIDEO_STYLE,
    BLANCHING_TERMS,
    BOILING_TERMS,
    COOKING_TERMS,
    DOUGH_TERMS,
    FINAL_TERMS,
    NEGATIVE,
    OVERVIEW_TERMS,
    PREP_TERMS,
    WRAPPER_TERMS,
    WRAPPING_TERMS,
    STIR_FRY_TERMS,
    STYLE_SUFFIX,
    VIDEO_STYLE_ALIASES,
    VIDEO_STYLE_PRESETS,
)

logger = logging.getLogger(__name__)
_LOCAL_IMAGEGEN_LOCK = asyncio.Lock()


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
    quality: str = "final"


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


def local_imagegen_status() -> dict:
    paths = {
        "runtime": Path(settings.local_imagegen_runtime),
        "model": Path(settings.local_imagegen_model),
        "vae": Path(settings.local_imagegen_vae),
        "clip_l": Path(settings.local_imagegen_clip_l),
        "t5xxl": Path(settings.local_imagegen_t5xxl),
    }
    missing = [name for name, path in paths.items() if not path.is_file()]
    comfy_configured = bool(str(settings.comfyui_workflow or '').strip())
    return {
        "provider": settings.imagegen_provider,
        "available": not missing,
        "missing": missing,
        "runtime": str(paths["runtime"]),
        "model": str(paths["model"]),
        "width": settings.local_imagegen_width,
        "height": settings.local_imagegen_height,
        "previewWidth": settings.local_imagegen_preview_width,
        "previewHeight": settings.local_imagegen_preview_height,
        "steps": settings.local_imagegen_steps,
        "backend": settings.local_imagegen_backend,
        "comfyui": {
            "baseUrl": settings.comfyui_base_url,
            "workflowConfigured": comfy_configured,
            "workflow": settings.comfyui_workflow,
        },
    }


def _local_prompt(prompt: str) -> str:
    positive = prompt.split("Negative prompt:", 1)[0].strip()
    if len(positive) > 900:
        positive = positive[:900].rsplit(" ", 1)[0]
    return f"{positive}. Clean blank margins, no text, no logo, no watermark, no artist signature."


def _build_local_prompt(req: SceneImageRequest) -> str:
    """Build a short Flux prompt whose first tokens carry the actual action."""
    stage = _cooking_stage(req)
    stage_guidance = {
        "dough_prep": "Primary action: pour water into flour, mix it with hands or chopsticks, then knead one dough ball.",
        "wrappers": "Primary action sequence, left to right: roll one long dough rope, cut it into equal pieces with a knife, roll one piece into one round wrapper.",
        "roll_rope": "Primary action: two bare hands roll one straight long cylindrical dough rope directly on a board, palms touching the rope; no tool.",
        "cut_pieces": "Primary action: one hand holds a knife touching one straight dough rope and cuts it into equal small pieces.",
        "roll_wrapper": "Primary action: both hands hold a wooden rolling pin touching one small dough ball and flatten it into one thin round wrapper.",
        "wrapping": "Primary action: place filling on one wrapper, fold it, and pinch visible pleats.",
        "boiling": "Primary action sequence, left to right: lower crescent-shaped dumplings with folded pleated edges into clear boiling water, pour cold water into the same open pot, then scoop floating crescent dumplings with a slotted spoon.",
        "boil_drop": "Primary action: a slotted spoon lowers crescent-shaped dumplings with folded edges below the water surface in an open pot of clear boiling water.",
        "boil_add_water": "Primary action: a ladle pours cold water into the same open pot while crescent-shaped dumplings with folded edges are submerged in boiling water.",
        "boil_float_scoop": "Primary action: crescent-shaped dumplings with folded edges float on clear boiling water and a slotted spoon lifts them out.",
    }.get(stage)
    action_stages = {"roll_rope", "cut_pieces", "roll_wrapper", "boil_drop", "boil_add_water", "boil_float_scoop"}
    if stage in action_stages:
        positive_description = _normalize_image_description(req.image_description).split("; no", 1)[0].strip()
        description = f"{positive_description}. {stage_guidance}"
    elif stage_guidance:
        description = stage_guidance
    else:
        description = _normalize_image_description(req.image_description)
        if len(description) > 520:
            description = description[:520].rsplit(" ", 1)[0]
    topic_hint = _topic_visual_hint(req)
    if topic_hint:
        description = f"{topic_hint}. {description}"
    context = f"Topic subject: {req.topic}. Scene: {req.title}."
    style = "rich editorial realistic instructional hand-drawn illustration rendered as a colored whiteboard scene, 3-5 large meaningful subject-specific objects, close-up readable action view, natural subject colors, thick imperfect marker outlines, clear object relationships, generous off-white whitespace, plain unlabeled image"
    exclusions = "No captions, logos, or watermarks."
    action_exclusions = {
        "roll_rope": " No rolling pin, knife, dough ball, wrapper, bowl, or other food.",
        "cut_pieces": " No rolling pin, wrapper, filling, bowl, or other food.",
        "roll_wrapper": " No knife, filling, folded dumpling, bowl, or other food.",
        "boil_drop": " No round steamed buns, baozi, mantou, bamboo steamer, dry steam, noodles, or soup.",
        "boil_add_water": " No round steamed buns, baozi, mantou, bamboo steamer, dry steam, noodles, or soup.",
        "boil_float_scoop": " No round steamed buns, baozi, mantou, bamboo steamer, dry steam, noodles, or soup.",
    }
    exclusions += action_exclusions.get(stage, "")
    if stage in {"dough_prep", "wrappers", "roll_rope", "cut_pieces", "roll_wrapper", "wrapping", "boiling", "boil_drop", "boil_add_water", "boil_float_scoop"}:
        exclusions += " No steamer, steamed buns, baozi, mantou, noodles, soup, or plated meal."
    return f"{description} {context} {style}. Preserve the concrete topic subject and scene action; do not replace it with generic geometric icons. {exclusions}"


def _local_seed(prompt: str) -> int:
    return int.from_bytes(hashlib.sha256(prompt.encode("utf-8")).digest()[:4], "big") & 0x7FFFFFFF


def _topic_visual_hint(req: SceneImageRequest) -> str:
    """Give local image generation a concrete subject for common explainers."""
    blob = f"{req.topic} {req.title} {req.image_description}".lower()
    scene_hints = [
        (("停不下来", "滑动", "手机", "swipe", "scroll"),
         "one person holding a smartphone in close-up, thumb actively swiping a vertical short-video feed with three distinct colorful video thumbnails and a visible loop arrow; show the compulsive action clearly, with no brain, clock, or checklist"),
        (("奖励", "大脑", "回路", "dopamine", "reward", "brain"),
         "one large hand-drawn brain connected to a smartphone by a three-node reward loop, with small notification sparks and one highlighted reward pulse; show the brain and loop as the clear central subject, no sleep scene or checklist"),
        (("注意力", "碎片", "专注", "attention", "fragment"),
         "a person trying to read one open book while a smartphone with colorful short-video cards pulls the gaze in several directions, showing scattered attention and one clean focus beam splitting into fragments; show the attention conflict as the central action, no brain diagram or bed"),
        (("睡眠", "入睡", "熬夜", "sleep", "bed", "night"),
         "a tired person in bed at night holding a glowing smartphone, a bedside clock showing late night, moon and dim room objects, with the phone light interrupting sleep; show the sleep disruption clearly, no brain network or checklist"),
        (("情绪", "焦虑", "心情", "mood", "emotion", "anxious"),
         "one person surrounded by a simple sequence of changing mood faces from calm to anxious after watching a smartphone, with the phone and emotional change as the central subject; no sleep clock or checklist"),
        (("主动", "管理", "设置", "替代", "练习", "checklist", "control"),
         "a hand placing a smartphone face down beside a clear three-item habit checklist and a small timer, with a green check path showing deliberate control; make the action of managing use unmistakable, no abstract geometric icon-only diagram"),
    ]
    for terms, hint in scene_hints:
        if any(term in blob for term in terms):
            return hint
    hints = [
        (("短视频", "注意力", "奖励回路", "睡眠", "情绪", "信息茧房"),
         "a person using a smartphone with short-video cards, a simple brain reward loop, scattered attention fragments, a small sleep clock and mood symbols, shown as one connected educational scene"),
        (("打扫", "房间", "整理"),
         "a person tidying a room with large visible zones for sorting, cleaning, and putting objects away"),
        (("饺子", "dumpling", "dough"),
         "hands preparing dumplings with flour, dough, wrappers, filling, pleats, and a cooking pot"),
        (("麻婆豆腐", "豆腐", "mapo tofu"),
         "a wok of mapo tofu with white tofu cubes, red chili sauce, minced meat, green garnish, and visible steam"),
    ]
    for terms, hint in hints:
        if any(term in blob for term in terms):
            return hint
    return ""


def _asset_contract_metadata(req: SceneImageRequest, image_bytes: bytes, prompt: str) -> dict:
    image = Image.open(io.BytesIO(image_bytes))
    source_hash = hashlib.sha256(image_bytes).hexdigest()
    prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    return {
        "width": int(image.width),
        "height": int(image.height),
        "sourceHash": source_hash,
        "promptHash": prompt_hash,
        "provider": settings.imagegen_provider,
        "quality": req.quality,
        "stage": "generated",
    }


async def _call_local_flux(prompt: str, *, quality: str = "final", attempt: int = 0) -> bytes:
    status = local_imagegen_status()
    if not status["available"]:
        raise RuntimeError(f"Local image generator is incomplete; missing: {', '.join(status['missing'])}")
    async with _LOCAL_IMAGEGEN_LOCK:
        with tempfile.TemporaryDirectory(prefix="explainflow-flux-") as tmp:
            output = Path(tmp) / "output.png"
            local_prompt = _local_prompt(prompt)
            preview = quality.strip().lower() == "preview"
            width = settings.local_imagegen_preview_width if preview else settings.local_imagegen_width
            height = settings.local_imagegen_preview_height if preview else settings.local_imagegen_height
            command = [
                settings.local_imagegen_runtime,
                "--diffusion-model", settings.local_imagegen_model,
                "--vae", settings.local_imagegen_vae,
                "--clip_l", settings.local_imagegen_clip_l,
                "--t5xxl", settings.local_imagegen_t5xxl,
                "--prompt", local_prompt,
                "--seed", str((_local_seed(local_prompt) + attempt * 104729) & 0x7FFFFFFF),
                "--cfg-scale", "1.0",
                "--sampling-method", "euler",
                "--steps", str(settings.local_imagegen_steps),
                "--width", str(width),
                "--height", str(height),
                "--output", str(output),
            ]
            if settings.local_imagegen_backend.strip():
                command.extend(["--backend", settings.local_imagegen_backend.strip()])
            if settings.local_imagegen_offload_to_cpu:
                command.append("--offload-to-cpu")
            if settings.local_imagegen_diffusion_flash_attention:
                command.append("--diffusion-fa")
            if settings.local_imagegen_vae_tiling:
                command.extend(["--vae-tiling", "--vae-tile-size", settings.local_imagegen_vae_tile_size])
            try:
                completed = await asyncio.to_thread(
                    subprocess.run,
                    command,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    timeout=settings.local_imagegen_timeout_s,
                    check=False,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
            except subprocess.TimeoutExpired:
                raise RuntimeError(f"Local Flux generation timed out after {settings.local_imagegen_timeout_s:g}s")
            log = completed.stdout.decode(errors="replace")
            if completed.returncode != 0 or not output.is_file():
                raise RuntimeError(f"Local Flux failed with exit code {completed.returncode}: {' '.join(log.splitlines()[-20:])}")
            image = output.read_bytes()
            if len(image) < 10_000:
                raise RuntimeError(f"Local Flux returned an undersized image ({len(image)} bytes)")
            return image


def _build_prompt(req: SceneImageRequest) -> str:
    if str(settings.imagegen_provider or "").strip().lower() == "local":
        return _build_local_prompt(req)
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
    is_dough = any(term in blob for term in DOUGH_TERMS)
    is_wrapper = any(term in blob for term in WRAPPER_TERMS)
    is_wrapping = any(term in blob for term in WRAPPING_TERMS)
    is_boiling_dumpling = any(term in blob for term in BOILING_TERMS)
    is_overview = any(term in blob for term in OVERVIEW_TERMS)
    is_blanch = any(term in blob for term in BLANCHING_TERMS)
    is_stir_fry = any(term in blob for term in STIR_FRY_TERMS)

    if is_boiling_dumpling:
        constraints.append("For boiling Chinese dumplings, show an open wide cooking pot or saucepan filled with visible clear water, never a steamer: first dumplings are actively dropped below the water surface, then a ladle pours a visible stream of cold water into the same boiling pot to settle the boil, and finally several dumplings visibly float and swell while a slotted spoon lifts them out. The water surface, submerged dumplings, bubbles, and slotted spoon must be unmistakable; this is boiling in water, not steaming.")
        negative.extend(["noodles", "ramen", "spaghetti", "soup bowl", "eating noodles", "finished plate as the main subject", "bamboo steamer", "steamer basket", "steamed buns", "baozi", "mantou", "dry steam", "lidded steamer"])
    elif is_wrapping:
        constraints.append("For wrapping dumplings, show one round wrapper held in a hand, a spoon placing visible filling in the center, the wrapper folded into a half moon, and fingers pinching a row of pleats; this must read as an active wrapping action, not a plated dumpling.")
        negative.extend(["noodles", "rolling pin", "boiling pot", "finished dish only", "empty round plate"])
    elif is_wrapper:
        constraints.append("For making wrappers, use a clear left-to-right three-stage action strip with no overhead still-life composition: stage one shows both hands rolling a long dough rope on a board, stage two shows a knife actively cutting the rope into equal dough pieces, stage three shows a wooden rolling pin touching and flattening one dough piece into a round wrapper. Each stage must show tool-to-dough contact and visible action; the three stages must be large and readable, with no duplicated finished meal.")
        negative.extend(["noodles", "chopsticks", "soup", "boiling pot", "finished dumpling dish", "static ingredient flat lay", "overhead still life", "decorative platter"])
    elif is_prep or is_dough:
        constraints.append("For preparing dough, show a bag or bowl of flour, water being poured into flour, chopsticks or hands mixing shaggy dough, and one dough ball being kneaded or resting; the main subject must be flour-to-dough preparation, never noodles or a finished meal.")
        negative.extend(["noodles", "ramen", "spaghetti", "eating noodles", "finished dumplings", "soup", "chopsticks lifting noodles"])
    elif is_final:
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


def _cooking_stage(req: SceneImageRequest) -> str | None:
    """Return a deterministic semantic stage used by prompt and QA diagnostics."""
    blob = f"{req.topic} {req.title} {req.image_description}".lower()
    action_scene = req.scene_id.strip().lower()
    for action in ("roll_rope", "cut_pieces", "roll_wrapper", "boil_drop", "boil_add_water", "boil_float_scoop"):
        if action_scene == action or action_scene.endswith(f"_{action}"):
            return action
    if any(term in blob for term in BOILING_TERMS) or ("boiling water" in blob and "dumpling" in blob):
        return "boiling"
    if any(term in blob for term in WRAPPING_TERMS):
        return "wrapping"
    if any(term in blob for term in WRAPPER_TERMS):
        return "wrappers"
    if any(term in blob for term in PREP_TERMS + DOUGH_TERMS):
        return "dough_prep"
    if any(term in blob for term in FINAL_TERMS):
        return "finished_dish"
    return None


def _semantic_prompt_diagnostics(req: SceneImageRequest) -> dict:
    stage = _cooking_stage(req)
    if not stage:
        return {"stage": None, "requiredTerms": [], "forbiddenTerms": []}
    required = {
        "dough_prep": ["flour", "water", "dough", "mix"],
        "wrappers": ["dough", "rolling pin", "wrapper", "hands", "knife", "cut", "rolling"],
        "roll_rope": ["hands", "rolling", "dough rope"],
        "cut_pieces": ["hand", "knife", "cut", "dough rope"],
        "roll_wrapper": ["hands", "rolling pin", "touching", "dough", "wrapper"],
        "boil_drop": ["boiling water", "dumplings", "submerged", "slotted spoon"],
        "boil_add_water": ["boiling water", "dumplings", "cold water", "ladle"],
        "boil_float_scoop": ["boiling water", "dumplings", "floating", "slotted spoon"],
        "wrapping": ["wrapper", "filling", "pleats"],
        "boiling": ["boiling water", "dumplings", "floating", "slotted spoon", "cold water", "submerged"],
        "finished_dish": ["finished", "serve"],
    }[stage]
    forbidden = {
        "dough_prep": ["noodles", "ramen", "soup", "finished dumplings"],
        "wrappers": ["noodles", "boiling pot", "finished meal"],
        "roll_rope": ["noodles", "knife", "finished dumpling"],
        "cut_pieces": ["noodles", "rolling pin", "finished dumpling"],
        "roll_wrapper": ["noodles", "knife", "filling", "finished dumpling"],
        "boil_drop": ["steamer", "steamed buns", "baozi", "bamboo steamer", "dry steam"],
        "boil_add_water": ["steamer", "steamed buns", "baozi", "bamboo steamer", "dry steam"],
        "boil_float_scoop": ["steamer", "steamed buns", "baozi", "bamboo steamer", "dry steam"],
        "wrapping": ["noodles", "rolling pin", "boiling pot"],
        "boiling": ["noodles", "ramen", "eating noodles", "steamer", "steamed buns", "baozi", "bamboo steamer"],
        "finished_dish": ["raw flour", "empty pot"],
    }[stage]
    prompt = req.image_description.lower()
    def positive_term(term: str) -> bool:
        for match in re.finditer(rf"\b{re.escape(term)}\b", prompt):
            prefix = prompt[max(0, match.start() - 96):match.start()]
            if re.search(r"\b(?:no|without|not)\b[^.;]*$", prefix):
                continue
            return True
        return False

    return {
        "stage": stage,
        "requiredTerms": [term for term in required if term not in prompt],
        "forbiddenTerms": [term for term in forbidden if positive_term(term)],
    }


async def generate_scene_image_result(req: SceneImageRequest, client: httpx.AsyncClient) -> tuple[str | None, dict]:
    prompt = _build_prompt(req)
    semantic = _semantic_prompt_diagnostics(req)
    if semantic["requiredTerms"] or semantic["forbiddenTerms"]:
        return None, {
            "ok": False,
            "attempts": [{"ok": False, "errors": ["semantic_prompt_incomplete"], "semantic": semantic}],
            "selectedAttempt": None,
            "semantic": semantic,
        }
    provider = settings.imagegen_provider.strip().lower()
    attempts: list[dict] = []
    max_attempts = max(1, settings.local_imagegen_max_attempts if provider.startswith("local") else 1)
    for attempt in range(max_attempts):
        try:
            if provider in {"local", "local_then_ark"}:
                img_bytes = await _call_local_flux(prompt, quality=req.quality, attempt=attempt)
            elif provider in {"ark", "seedream", "volcengine"}:
                img_bytes = await _call_seedream(prompt, client)
            else:
                raise RuntimeError(f"Unsupported IMAGEGEN_PROVIDER: {settings.imagegen_provider}")
            img_bytes = normalize_whiteboard_image(img_bytes)
            quality = inspect_generated_image(img_bytes)
            quality["attempt"] = attempt + 1
            quality["semantic"] = semantic
            quality["sourceAsset"] = _asset_contract_metadata(req, img_bytes, prompt)
            attempts.append(quality)
            if quality["ok"]:
                logger.info("[imagegen] %s provider=%s bytes=%d attempt=%d", req.scene_id, provider, len(img_bytes), attempt + 1)
                return base64.b64encode(img_bytes).decode(), {"ok": True, "attempts": attempts, "selectedAttempt": attempt + 1}
            logger.warning("[imagegen] %s rejected attempt=%d errors=%s", req.scene_id, attempt + 1, quality["errors"])
        except Exception as exc:
            attempts.append({"ok": False, "attempt": attempt + 1, "errors": ["generation_failed"], "message": str(exc)})
            logger.warning("[imagegen] %s attempt=%d failed: %s", req.scene_id, attempt + 1, exc)
    if provider == "local_then_ark":
        try:
            img_bytes = await _call_seedream(prompt, client)
            img_bytes = normalize_whiteboard_image(img_bytes)
            quality = inspect_generated_image(img_bytes)
            attempts.append({**quality, "attempt": len(attempts) + 1, "provider": "ark"})
            if quality["ok"]:
                return base64.b64encode(img_bytes).decode(), {"ok": True, "attempts": attempts, "selectedAttempt": len(attempts)}
        except Exception as exc:
            attempts.append({"ok": False, "errors": ["ark_fallback_failed"], "message": str(exc)})
    return None, {"ok": False, "attempts": attempts, "selectedAttempt": None}


async def generate_scene_image(req: SceneImageRequest, client: httpx.AsyncClient) -> str | None:
    image, _ = await generate_scene_image_result(req, client)
    return image


async def generate_all_scene_images(requests: list[SceneImageRequest]) -> dict[str, str | None]:
    async with httpx.AsyncClient() as client:
        results = await asyncio.gather(*[generate_scene_image(r, client) for r in requests])
    return {req.scene_id: b64 for req, b64 in zip(requests, results)}


async def generate_all_scene_images_with_diagnostics(requests: list[SceneImageRequest]) -> tuple[dict[str, str | None], dict[str, dict]]:
    async with httpx.AsyncClient() as client:
        results = await asyncio.gather(*[generate_scene_image_result(r, client) for r in requests])
    return (
        {req.scene_id: result[0] for req, result in zip(requests, results)},
        {req.scene_id: result[1] for req, result in zip(requests, results)},
    )


def compose_action_board(images: list[bytes], *, columns: int = 3, panel_size: tuple[int, int] = (480, 480), gap: int = 24) -> bytes:
    """Compose ordered single-action references on a clean board without baked labels."""
    if not images:
        raise ValueError("action board requires at least one image")
    columns = max(1, min(columns, len(images)))
    panel_width, panel_height = panel_size
    rows = (len(images) + columns - 1) // columns
    board = Image.new("RGB", (columns * panel_width + (columns - 1) * gap, rows * panel_height + (rows - 1) * gap), "white")
    for index, raw in enumerate(images):
        image = Image.open(io.BytesIO(raw)).convert("RGB")
        image.thumbnail((panel_width - 24, panel_height - 24), Image.Resampling.LANCZOS)
        panel = Image.new("RGB", panel_size, "white")
        panel.paste(image, ((panel_width - image.width) // 2, (panel_height - image.height) // 2))
        x = (index % columns) * (panel_width + gap)
        y = (index // columns) * (panel_height + gap)
        board.paste(panel, (x, y))
    output = io.BytesIO()
    board.save(output, format="PNG", optimize=True)
    return output.getvalue()


async def generate_action_board_with_diagnostics(
    *,
    board_id: str,
    topic: str,
    actions: list[SceneImageRequest],
    columns: int = 3,
) -> tuple[str | None, dict]:
    """Generate each atomic action independently, then compose the accepted images."""
    if not actions:
        return None, {"ok": False, "errors": ["action_board_empty"], "panels": []}
    images, panel_diagnostics = await generate_all_scene_images_with_diagnostics(actions)
    ordered_images: list[bytes] = []
    panel_results: list[dict] = []
    for action in actions:
        encoded = images.get(action.scene_id)
        diagnostic = panel_diagnostics.get(action.scene_id, {})
        panel_results.append({"actionId": action.scene_id, "diagnostics": diagnostic})
        if not encoded or not diagnostic.get("ok"):
            return None, {
                "ok": False,
                "errors": ["action_panel_rejected"],
                "boardId": board_id,
                "topic": topic,
                "panels": panel_results,
            }
        ordered_images.append(base64.b64decode(encoded))
    final_board = all(action.quality.strip().lower() != "preview" for action in actions)
    panel_size = (1024, 1024) if final_board else (480, 480)
    try:
        board = compose_action_board(ordered_images, columns=columns, panel_size=panel_size, gap=32 if final_board else 24)
    except Exception as exc:
        return None, {"ok": False, "errors": ["action_board_compose_failed"], "message": str(exc), "panels": panel_results}
    quality = inspect_generated_image(board)
    if not quality["ok"]:
        return None, {"ok": False, "errors": ["action_board_quality_failed"], "quality": quality, "panels": panel_results}
    board_width, board_height = Image.open(io.BytesIO(board)).size
    board_source = {
        "width": board_width,
        "height": board_height,
        "sourceHash": hashlib.sha256(board).hexdigest(),
        "promptHash": hashlib.sha256("\n".join((action.image_description for action in actions)).encode("utf-8")).hexdigest(),
        "provider": settings.imagegen_provider,
        "quality": "final" if final_board else "preview",
        "stage": "composed",
    }
    return base64.b64encode(board).decode(), {
        "ok": True,
        "boardId": board_id,
        "topic": topic,
        "panelCount": len(actions),
        "qualityMode": "final" if final_board else "preview",
        "panelSize": {"width": panel_size[0], "height": panel_size[1]},
        "sourceAsset": board_source,
        "panels": panel_results,
        "quality": quality,
    }
