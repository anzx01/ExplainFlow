import asyncio
import base64
import hashlib
import io
import json
import logging
import re
import subprocess
import tempfile
import uuid
from dataclasses import dataclass, replace
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
_COOKING_CONTEXT_EN = re.compile(
    r"\b(?:cook(?:ing)?|recipe|food|dish|ingredient|dumpling|noodle|tofu|wok|skillet|"
    r"flour|dough|sauce|stir[- ]?fry|boil(?:ing)?|bake|fry|steam(?:er|ed|ing)?)\b",
    re.IGNORECASE,
)
_COOKING_CONTEXT_ZH = tuple(
    "\u996d\u83dc \u7f8e\u98df \u98df\u7269 \u83dc\u80b4 \u98df\u6750 \u83dc\u8c31 \u997a\u5b50 \u9762\u6761 \u8c46\u8150 \u9762\u7c89 \u9762\u56e2 \u7092\u9505 \u9505\u5177 \u7092\u83dc \u714e\u7092 \u716e\u6c34 \u84b8\u9505 \u70d8\u7119 \u70f9\u996a \u7096\u716e \u914d\u6599 \u9ebb\u5a46\u8c46\u8150".split()
)


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
    image_mode: str | None = None
    line_art_color_mode: str = "color"
    image_shots: list[str] | None = None
    image_style: str | None = None


def _canonical_video_style(value: str | None) -> str:
    style = str(value or "").strip().lower()
    style = VIDEO_STYLE_ALIASES.get(style, style)
    if style != ACTIVE_VIDEO_STYLE:
        return ACTIVE_VIDEO_STYLE if ACTIVE_VIDEO_STYLE in VIDEO_STYLE_PRESETS else "whiteboard"
    return style if style in VIDEO_STYLE_PRESETS else "whiteboard"


def _normalize_image_description(value: str | None) -> str:
    text = str(value or "").strip()
    replacements = [
        (r"(?:用|添加|加上|旁边|附近|并)?(?:短|小|文字)?标签(?:标出|标注|写|为|注明)?[^;；。.!]*", "留白供渲染器添加标注"),
        (r"(?:旁边|下方|上方|底部|顶部|框内|框里|短标签)写[^;；。.!]*", "留白供渲染器添加标注"),
        (r"(?:右下角|左下角|下方|上方|底部)?画短?结论框", "留白供渲染器添加结论"),
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
        "Authorization": f"Bearer {effective_ark_api_key()}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": effective_imagegen_model(),
        "prompt": prompt,
        "size": "2048x2048",
        "n": 1,
        "response_format": "url",
        "watermark": False,
    }
    resp = await client.post(
        f"{effective_imagegen_base_url()}/images/generations",
        headers=headers,
        json=payload,
        timeout=60.0,
    )
    resp.raise_for_status()
    url: str = resp.json()["data"][0]["url"]
    img_resp = await client.get(url, timeout=60.0)
    img_resp.raise_for_status()
    return img_resp.content


def _replace_workflow_values(value, replacements: dict[str, str | int]):
    if isinstance(value, dict):
        return {key: _replace_workflow_values(item, replacements) for key, item in value.items()}
    if isinstance(value, list):
        return [_replace_workflow_values(item, replacements) for item in value]
    return replacements.get(value, value) if isinstance(value, str) else value


def _comfy_workflow(prompt: str, negative: str, *, seed: int, width: int, height: int) -> dict:
    workflow_path = Path(settings.comfyui_workflow)
    if not workflow_path.is_file():
        raise RuntimeError(f"ComfyUI API workflow not found: {workflow_path}")
    try:
        template = json.loads(workflow_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Could not load ComfyUI API workflow {workflow_path}: {exc}") from exc
    if not isinstance(template, dict) or not template:
        raise RuntimeError("ComfyUI API workflow must be a non-empty object")
    # Keep the scene readable without collapsing the subject into outline-only
    # doodles. The generated image is shown as teaching artwork, so it needs
    # filled shapes, material cues, and a clear visual anchor before the
    # renderer adds handwriting.
    simplicity_prefix = (
        "finished full-color educational illustration, bold filled shapes, solid color areas, "
        "visible subject materials and simple shading, 3-5 large main objects only, clean composition, "
    )
    if settings.comfyui_lora.strip() and settings.comfyui_lora_trigger.strip():
        prompt = f"{settings.comfyui_lora_trigger}, {simplicity_prefix}{prompt}"
    else:
        prompt = f"{simplicity_prefix}{prompt}"
    workflow = _replace_workflow_values(template, {
        "__EXPLAINFLOW_PROMPT__": prompt,
        "__EXPLAINFLOW_NEGATIVE__": negative,
        "__EXPLAINFLOW_CHECKPOINT__": settings.comfyui_checkpoint,
        "__EXPLAINFLOW_LORA__": settings.comfyui_lora,
        "__EXPLAINFLOW_LORA_STRENGTH__": settings.comfyui_lora_strength,
        "__EXPLAINFLOW_SEED__": seed,
        "__EXPLAINFLOW_WIDTH__": width,
        "__EXPLAINFLOW_HEIGHT__": height,
        "__EXPLAINFLOW_STEPS__": max(1, min(50, int(settings.comfyui_steps))),
    })
    if not settings.comfyui_lora.strip():
        workflow.pop("8", None)
        for node in workflow.values():
            if not isinstance(node, dict):
                continue
            inputs = node.get("inputs")
            if not isinstance(inputs, dict):
                continue
            for key, value in list(inputs.items()):
                if value == ["8", 0]:
                    inputs[key] = ["1", 0]
                elif value == ["8", 1]:
                    inputs[key] = ["1", 1]
    return workflow


async def _call_comfyui(prompt: str, *, quality: str = "final", attempt: int = 0) -> bytes:
    preview = quality.strip().lower() == "preview"
    width = settings.local_imagegen_preview_width if preview else settings.local_imagegen_width
    height = settings.local_imagegen_preview_height if preview else settings.local_imagegen_height
    # 强化负面提示：限制复杂度，确保简洁教学风格。
    # meinaPastel 是动漫底模：复杂多对象场景会漂移成"动漫人物+奇幻构图"，
    # 必须在负面里硬性排除人物与暗背景。
    negative = (
        "text, letters, words, logo, watermark, blurry, low quality, malformed hands, duplicate objects, "
        "overly detailed, too many elements, cluttered composition, busy background, complex patterns, "
        "photorealistic details, fine textures, intricate shading, realistic rendering, "
        "outline-only drawing, thin line art, wireframe, empty white interiors, unfilled objects, icon-only symbols, "
        "anime style details, hair strands, fabric folds, glossy highlights, "
        "small objects, tiny icons, miniature details, dense infographic, "
        "more than 5 main objects, crowded scene, overlapping elements, "
        "anime, manga, 1girl, 1boy, bishoujo, anime character, human face, portrait, person, "
        "dark background, black background, night sky, galaxy, fantasy art"
    )
    timeout = max(5.0, float(settings.comfyui_timeout_s))
    client_id = f"{settings.comfyui_client_id}-{uuid.uuid4().hex}"
    async with httpx.AsyncClient(base_url=settings.comfyui_base_url.rstrip("/"), timeout=10.0) as client:
        positive, separator, generated_negative = prompt.partition("Negative prompt:")
        if separator and generated_negative.strip():
            negative = generated_negative.strip()
        response = await client.post("/prompt", json={"prompt": _comfy_workflow(positive.strip(), negative, seed=(_local_seed(prompt) + attempt * 104729) & 0x7FFFFFFF, width=width, height=height), "client_id": client_id})
        if response.is_error:
            detail = response.text.strip().replace("\n", " ")[:1200]
            raise RuntimeError(f"ComfyUI rejected the workflow ({response.status_code}): {detail}")
        prompt_id = response.json().get("prompt_id")
        if not prompt_id:
            raise RuntimeError("ComfyUI did not return prompt_id")
        deadline = asyncio.get_running_loop().time() + timeout
        while asyncio.get_running_loop().time() < deadline:
            history = await client.get(f"/history/{prompt_id}")
            if history.status_code == 200:
                item = history.json().get(prompt_id, {})
                if item.get("status", {}).get("status_str") == "error":
                    raise RuntimeError(str(item.get("status", {}).get("messages", "ComfyUI workflow failed")))
                outputs = item.get("outputs", {})
                for node in outputs.values():
                    for image in node.get("images", []):
                        params = {"filename": image["filename"], "subfolder": image.get("subfolder", ""), "type": image.get("type", "output")}
                        result = await client.get("/view", params=params)
                        result.raise_for_status()
                        return result.content
            await asyncio.sleep(0.5)
    raise RuntimeError(f"ComfyUI generation timed out after {timeout:g}s")


async def _check_comfyui_available() -> None:
    """Fail fast when the configured ComfyUI endpoint is not running."""
    base_url = settings.comfyui_base_url.rstrip("/")
    try:
        async with httpx.AsyncClient(base_url=base_url, timeout=2.0) as client:
            response = await client.get("/system_stats")
            response.raise_for_status()
    except Exception as exc:
        raise RuntimeError(
            f"ComfyUI is unreachable at {base_url}; start ComfyUI or change COMFYUI_BASE_URL ({exc})"
        ) from exc


def local_imagegen_status() -> dict:
    paths = {
        "runtime": Path(settings.local_imagegen_runtime),
        "model": Path(settings.local_imagegen_model),
        "vae": Path(settings.local_imagegen_vae),
        "clip_l": Path(settings.local_imagegen_clip_l),
        "t5xxl": Path(settings.local_imagegen_t5xxl),
    }
    provider = str(settings.imagegen_provider or "").strip().lower()
    missing = [name for name, path in paths.items() if not path.is_file()] if provider.startswith("local") else []
    comfy_workflow = Path(settings.comfyui_workflow) if str(settings.comfyui_workflow or '').strip() else None
    comfy_configured = bool(comfy_workflow and comfy_workflow.is_file())
    if provider in {"comfyui", "comfy"} and not comfy_configured:
        missing.append("comfyui_workflow")
    flux_missing = [name for name, path in paths.items() if not path.is_file()]
    if settings.local_imagegen_lora.strip() and not (Path(settings.local_imagegen_lora_dir) / settings.local_imagegen_lora).is_file():
        flux_missing.append("flux_lora")
    return {
        "provider": settings.imagegen_provider,
        "available": not missing,
        "missing": missing,
        "width": settings.local_imagegen_width,
        "height": settings.local_imagegen_height,
        "previewWidth": settings.local_imagegen_preview_width,
        "previewHeight": settings.local_imagegen_preview_height,
        "timeoutSeconds": settings.comfyui_timeout_s if provider in {"comfy", "comfyui"} else settings.local_imagegen_timeout_s,
        "maxAttempts": settings.local_imagegen_max_attempts if provider.startswith("local") else 1,
        **({
            "steps": settings.local_imagegen_steps,
            "runtime": str(paths["runtime"]),
            "model": str(paths["model"]),
            "backend": settings.local_imagegen_backend,
        } if provider.startswith("local") else {}),
        "comfyui": {
            "baseUrl": settings.comfyui_base_url,
            "workflowConfigured": comfy_configured,
            "workflow": settings.comfyui_workflow,
            "checkpoint": settings.comfyui_checkpoint,
        },
        "modes": {
            "sd15": {
                "available": comfy_configured and bool(settings.comfyui_checkpoint),
                "provider": "comfyui",
                "checkpoint": settings.comfyui_checkpoint,
                "lora": settings.comfyui_lora or None,
            },
            "flux": {
                "available": not flux_missing,
                "provider": "local",
                "missing": flux_missing,
                "model": str(paths["model"]),
                "lora": settings.local_imagegen_lora or None,
                "loraConfigured": bool(settings.local_imagegen_lora and (Path(settings.local_imagegen_lora_dir) / settings.local_imagegen_lora).is_file()),
                "steps": settings.local_imagegen_steps,
                "guidance": settings.local_imagegen_guidance,
                "width": settings.local_imagegen_flux_width,
                "height": settings.local_imagegen_flux_height,
            },
        },
    }


def _local_prompt(prompt: str) -> str:
    positive = prompt.split("Negative prompt:", 1)[0].strip()
    return f"{positive}. Clean blank margins, no text, no logo, no watermark, no artist signature."


def _flux_prompt_with_lora(prompt: str) -> str:
    if not settings.local_imagegen_lora.strip():
        return _local_prompt(prompt)
    lora_path = Path(settings.local_imagegen_lora_dir) / settings.local_imagegen_lora
    if not lora_path.is_file():
        raise RuntimeError(f"Configured Flux LoRA does not exist: {lora_path}")
    trigger = settings.local_imagegen_lora_trigger.strip()
    lora_tag = f"<lora:{lora_path.stem}:{settings.local_imagegen_lora_strength:g}>"
    return _local_prompt(f"{trigger}, {lora_tag}, {prompt}")


# 白板教学风格配方(移植自 whiteboard-video-engine 的 VisualStyle 体系,
# 字段:风格句 aesthetic / 纸面 paper / 色板 palette / 负面 avoid)。
_IMAGE_STYLES = {
    "clean-whiteboard": {
        "aesthetic": "Freshly hand-drawn whiteboard illustration using medium black round-tip marker contours, simple people and props, and only essential arrows or circles",
        "paper": "Clean matte whiteboard-white background without glare, room photography, borders, or smudged eraser bands",
        "palette": "Black marker with at most one blue and one red emphasis; most regions stay white",
        "avoid": "filled color masses, shadows, complex scenery, corporate icon libraries, dense annotations, pseudo-text",
    },
    "marker-whiteboard": {
        "aesthetic": "Confident hand-drawn marker contours with rounded starts and stops, mild pressure variation, simple blocky props, and sparse hand-drawn emphasis marks",
        "paper": "Neutral bright white board surface with no room context",
        "palette": "Charcoal black plus one vivid cyan or coral highlighter accent",
        "avoid": "tiny details, thin technical lines, airbrushed shading, stock icons, dense decoration, fake writing",
    },
    "minimal-line-explainer": {
        "aesthetic": "Minimal black-ink explainer drawing with circle-headed stick figures, dot-line faces, thin slightly wobbly contours, and flat two-dimensional geometry",
        "paper": "Plain ivory-white paper with very large negative space",
        "palette": "Pure black line on ivory paper; no gray and no colored fill",
        "avoid": "solid black silhouettes, hatching, shading, volume, thick outlines, realism, decoration",
    },
    "vivid-storybook": {
        "aesthetic": "Warm hand-drawn storybook illustration with clean dark marker outlines and vivid saturated flat color fills, cheerful educational mood",
        "paper": "Clean warm off-white drawing paper with no photographed tabletop or border",
        "palette": "Vivid brick red, bright blue, ochre, sage, and warm cream flat fills with clear separated color regions",
        "avoid": "muted pastel washes, gradients, glossy digital painting, anime polish, realistic lighting, dense scenery",
    },
}

_DEFAULT_IMAGE_STYLE = "vivid-storybook"

_SCENE_CONTRACT = (
    "Show one immediately readable story beat with ONE dominant hero subject filling at least one "
    "third of the canvas height; every other element stays clearly smaller support. Keep every object "
    "complete inside the canvas with breathing room; never crop key parts. Use two to four spatially "
    "separate clusters only when the scene contains genuinely independent objects, with clear paper "
    "gaps between clusters, and never join the whole canvas with one continuous ground line. Keep "
    "outlines distinguishable from fills so the drawing can be converted locally into line art: clean "
    "thick dark outlines, large flat color shapes, low texture, generous empty margins; no hatching, "
    "stippling, speckle noise, tiny repeated decorations, or dense small details; keep the bottom "
    "quarter of the canvas nearly empty."
)

_PRODUCTION_CONTRACT = (
    "Generate image only: no text, no letters, no single characters, no chemical element symbols, no numbers, no Greek or math symbols on any object, no pseudo-writing, captions, logo, watermark, "
    "panel border, page frame, UI, or subtitle band; avoid photorealistic texture, dense backgrounds, "
    "and tiny details; not anime, no people."
)


def _build_local_prompt(req: SceneImageRequest) -> str:
    """Build a structured local image prompt from storyboard intent.

    分段标注式结构移植自 whiteboard-video-engine 的 build_storyboard_prompt:
    description → style recipe → paper → palette → avoid → contracts。
    """
    description = _normalize_image_description(req.image_description)
    monochrome = str(req.line_art_color_mode or "color").strip().lower() == "monochrome"
    style_key = (req.image_style or _DEFAULT_IMAGE_STYLE).strip().lower()
    style = dict(_IMAGE_STYLES.get(style_key, _IMAGE_STYLES[_DEFAULT_IMAGE_STYLE]))
    if monochrome:
        style["palette"] = "Pure black line on white paper; no colored fill"
    sections = [
        description,
        f"Style recipe: {style['aesthetic']}",
        f"Paper/background: {style['paper']}",
        f"Palette and fill: {style['palette']}",
        f"Avoid: {style['avoid']}",
        f"Scene contract: {_SCENE_CONTRACT}",
        f"Production contract: {_PRODUCTION_CONTRACT}",
    ]
    return chr(10).join(section for section in sections if section)


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


def _asset_contract_metadata(req: SceneImageRequest, image_bytes: bytes, prompt: str, provider: str | None = None) -> dict:
    image = Image.open(io.BytesIO(image_bytes))
    source_hash = hashlib.sha256(image_bytes).hexdigest()
    prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    return {
        "width": int(image.width),
        "height": int(image.height),
        "sourceHash": source_hash,
        "promptHash": prompt_hash,
        "provider": provider or settings.imagegen_provider,
        "imageMode": req.image_mode or "default",
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
            local_prompt = _flux_prompt_with_lora(prompt)
            preview = quality.strip().lower() == "preview"
            width = settings.local_imagegen_flux_preview_width if preview else settings.local_imagegen_flux_width
            height = settings.local_imagegen_flux_preview_height if preview else settings.local_imagegen_flux_height
            command = [
                settings.local_imagegen_runtime,
                "--diffusion-model", settings.local_imagegen_model,
                "--vae", settings.local_imagegen_vae,
                "--clip_l", settings.local_imagegen_clip_l,
                "--t5xxl", settings.local_imagegen_t5xxl,
                "--prompt", local_prompt,
                "--seed", str((_local_seed(local_prompt) + attempt * 104729) & 0x7FFFFFFF),
                "--cfg-scale", "1.0",
                "--guidance", str(settings.local_imagegen_guidance),
                "--sampling-method", "euler",
                "--steps", str(settings.local_imagegen_steps),
                "--width", str(width),
                "--height", str(height),
                "--output", str(output),
            ]
            if settings.local_imagegen_lora.strip():
                command.extend(["--lora-model-dir", settings.local_imagegen_lora_dir])
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


def effective_imagegen_provider() -> str:
    """Runtime settings override for IMAGEGEN_PROVIDER (settings UI)."""
    from src.core import runtime_settings

    override = runtime_settings.get_override("imagegen_provider")
    if override:
        return override
    return str(settings.imagegen_provider or "").strip().lower()


def effective_ark_api_key() -> str:
    from src.core import runtime_settings

    return runtime_settings.get_override("ark_api_key") or settings.ark_api_key


def effective_imagegen_base_url() -> str:
    """Cloud image API base (Ark/Seedream compatible), runtime-overridable."""
    from src.core import runtime_settings

    return (runtime_settings.get_override("imagegen_base_url") or settings.ark_base_url).rstrip("/")


def effective_imagegen_model() -> str:
    from src.core import runtime_settings

    return runtime_settings.get_override("imagegen_model") or settings.seedream_model


def _build_prompt(req: SceneImageRequest, condensed_subject: str | None = None) -> str:
    image_mode = str(req.image_mode or "").strip().lower()
    provider_local = effective_imagegen_provider() in {"local", "local_then_ark"}
    # The local (Flux) path must take the clean short prompt regardless of
    # whether the caller sends image_mode="flux" or the render pipeline's
    # "default": the SD1.5 mega-prompt below buries the subject under
    # teaching-rule boilerplate that Flux transcribes into painted labels.
    if image_mode == "flux" or image_mode in {"", "default", "local"} and provider_local:
        return _build_local_prompt(req)
    # SD1.5's CLIP encoder only reads ~77 tokens, so the long storyboard
    # prompt gets truncated into noise. A distilled concrete subject keeps
    # the artwork on-topic; verified with direct ComfyUI tests.
    if condensed_subject:
        mode = (req.board_mode or "whiteboard").strip().lower()
        monochrome = str(req.line_art_color_mode or "color").strip().lower() == "monochrome"
        canvas_style = _canonical_video_style(req.video_style)
        if canvas_style in {"chalkboard_bw", "chalkboard_black_white", "chalkboard_color"} or mode == "chalkboard":
            style_head = "simple hand-drawn chalk doodle on dark blackboard:"
        elif monochrome:
            style_head = "simple black and gray marker doodle:"
        else:
            style_head = "simple hand-drawn teaching doodle:"
        color_tail = (
            "black marker outline only, white background"
            if monochrome else
            "black marker outline, light color fill, white background"
        )
        return (
            f"{style_head} {condensed_subject.strip().rstrip('.')}. "
            f"{color_tail}, generous margins, no text. Flat simple doodle illustration, absolutely not anime, no people"
        )
    mode = (req.board_mode or "whiteboard").strip().lower()
    monochrome = str(req.line_art_color_mode or "color").strip().lower() == "monochrome"
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
    # Keep image generation topic-agnostic. Domain-specific prompt packs (for
    # example cooking-only constraints) made generic storyboards fail before
    # the provider was called. The storyboard description is the source of
    # truth; the renderer handles drawing annotations separately.
    domain_suffix, domain_negative = "", ""
    image_description = _normalize_image_description(req.image_description)
    color_rules = ("strict monochrome black, charcoal gray and white hand-drawn marker line art, no colored accents or colored fills" if monochrome else "full-color hand-drawn teaching artwork with solid filled forms, subject-specific natural colors, visible material texture and restrained purposeful red, blue, yellow and green accents; never outline-only")
    return (
        f"{image_description}. Topic context only, do not draw as text: {req.topic}. "
        f"Scene context only, do not draw as text: {req.title}. "
        f"{domain_suffix} {suffix}. {color_rules}. Strict text-free policy: do not render any readable Chinese, English, letters, numbers, labels, captions, title, logo, watermark, UI text, or gibberish pseudo-text; leave open whitespace in the margins for renderer-added handwriting, not empty callout boxes or placeholder bubbles. "
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


def _semantic_prompt_text(value: str) -> str:
    """Normalize common Chinese storyboard terms to the English contract vocabulary.

    The image prompt may be bilingual, but semantic QA must not depend on the
    author choosing one language. Keeping this normalization in one place
    also makes future stages easier to extend than duplicating ad-hoc checks.
    """
    text = str(value or "").lower()
    aliases = {
        "\u6210\u54c1": " finished ", "\u5b8c\u6210": " finished ", "\u505a\u597d": " finished ",
        "\u88c5\u76d8": " serve ", "\u4e0a\u684c": " serve ", "\u51fa\u9505": " serve ",
        "\u9762\u7c89": " flour ", "\u548c\u9762": " mixing dough ", "\u63c9\u9762": " knead dough ",
        "\u9762\u56e2": " dough ball ", "\u6c34": " water ", "\u997a\u5b50": " dumplings ",
        "\u6d6e\u8d77": " floating ", "\u51b7\u6c34": " cold water ", "\u52fa\u5b50": " ladle ",
        "\u6f0f\u52fa": " slotted spoon ", "\u5305\u997a\u5b50": " wrapping dumpling ",
        "\u9985\u6599": " filling ", "\u9762\u76ae": " wrapper ", "\u997a\u5b50\u76ae": " wrapper ", "\u8936\u76b1": " pleats ",
        "\u64c0\u76ae": " rolling pin wrapper ", "\u5207\u5757": " cut pieces ",
        "\u716e\u6c34": " boiling water ", "\u6cb8\u6c34": " boiling water ", "\u716e\u997a\u5b50": " boil dumplings ", "\u4e0b\u9505": " boil ", "\u7092": " stir fry ",
        "\u98df\u6750": " ingredient ", "\u51c6\u5907": " prepare ", "\u5207\u83dc": " cut ",
    }
    for source, target in aliases.items():
        text = text.replace(source, target)
    return text


def _has_cooking_context(text: str) -> bool:
    return bool(_COOKING_CONTEXT_EN.search(text)) or any(term in text for term in _COOKING_CONTEXT_ZH)


def _cooking_stage(req: SceneImageRequest) -> str | None:
    """Return a deterministic semantic stage used by prompt and QA diagnostics."""
    blob = _semantic_prompt_text(f"{req.topic} {req.title} {req.image_description}")
    # Cooking constraints are domain-specific. A generic storyboard can use
    # words such as "finished" or "serve" without depicting food; do not let
    # those words activate cooking QA unless the request has clear cooking
    # context (dish, ingredients, cookware, recipe, etc.).
    if not _has_cooking_context(blob):
        return None
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
    # Image generation is topic-agnostic. Keep this shape for API diagnostics,
    # but never classify or reject a scene by a domain-specific vocabulary.
    return {"stage": None, "requiredTerms": [], "forbiddenTerms": []}
    """Legacy domain contract retained below only as unreachable documentation."""
    stage = _cooking_stage(req)
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
    prompt = _semantic_prompt_text(req.image_description)
    def positive_term(term: str) -> bool:
        for match in re.finditer(rf"\b{re.escape(term)}\b", prompt):
            prefix = prompt[max(0, match.start() - 96):match.start()]
            if re.search(r"\b(?:no|without|not)\b[^.;]*$", prefix):
                continue
            return True
        return False

    missing = [term for term in required if term not in prompt]
    return {
        "stage": stage,
        "requiredTerms": missing,
        "forbiddenTerms": [term for term in forbidden if positive_term(term)],
    }


def _heuristic_condensed_subject(req: SceneImageRequest) -> str:
    """Fallback subject extraction when the condensing LLM call is unavailable."""
    text = _normalize_image_description(req.image_description)
    text = re.sub(r"^Required scene artwork:\s*", "", text)
    # The planner writes "<style phrase>: <subject sentence>, <style details>";
    # keep the clause right after the first colon when present.
    if ":" in text[:160]:
        text = text.split(":", 1)[1]
    text = re.split(r"[.;]", text)[0] or text
    words = [w for w in re.findall(r"[A-Za-z][A-Za-z-]+", text) if w.lower() not in {
        "bold", "editorial", "hand", "drawn", "explainer", "illustration", "clean",
        "simple", "style", "whiteboard", "doodle", "marker", "thick", "imperfect",
    }]
    return " ".join(words[:28]).strip()


_CONDENSE_CACHE: dict[str, str] = {}


async def _condense_subject_for_clip(req: SceneImageRequest) -> str:
    """Distill the long storyboard artwork prompt into a concrete <=40-word
    subject line that survives SD1.5's 77-token CLIP window."""
    cache_key = hashlib.sha1(
        f"{req.topic}|{req.title}|{req.image_description}".encode("utf-8")
    ).hexdigest()
    if cache_key in _CONDENSE_CACHE:
        return _CONDENSE_CACHE[cache_key]
    fallback = _heuristic_condensed_subject(req)
    try:
        from src.core.llm import chat_json

        data = await chat_json(
            [
                {
                    "role": "system",
                    "content": (
                        "你把白板教学场景压缩成 SD1.5 文生图提示词。SD1.5 只读取约77个token,"
                        "且不擅长抽象概念。只输出 JSON:{\"subject\": \"...\"}。subject 规则:"
                        "英文;不超过40个词;只描述可见的具体对象、数量、相对位置和简单动作;"
                        "把抽象概念转成具体物件(复利→叠高的硬币堆/滚雪球,时间→时钟,利率→百分号,"
                        "频率→循环箭头);禁止出现 text/label/style/concept/process/story 这类指令或抽象词;"
                        "禁止描述文字内容;直接列出对象。"
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"主题:{req.topic}\n场景标题:{req.title}\n场景画面描述:{_normalize_image_description(req.image_description)}"
                    ),
                },
            ],
            temperature=0.2,
            max_retries=1,
        )
        subject = re.sub(r"\s+", " ", str(data.get("subject", ""))).strip().strip('"').rstrip(".").lower()
        subject = re.sub(r"\b(no|without) (text|words|letters|labels)\b.*$", "", subject).strip()
        if 3 <= len(subject.split()) <= 45:
            logger.info("[imagegen] condensed subject for %s: %s", req.scene_id, subject)
            _CONDENSE_CACHE[cache_key] = subject
            return subject
        logger.warning("[imagegen] condensed subject rejected (%d words), using heuristic", len(subject.split()))
    except Exception as exc:
        logger.warning("[imagegen] subject condensation failed, using heuristic: %s", exc)
    _CONDENSE_CACHE[cache_key] = fallback
    return fallback


def _compose_scene_panels(panels: list[bytes]) -> bytes:
    """Compose gate-passed single-subject panels into one wide scene canvas.

    每个分拍都是独立生成、独立过检的单主体图;拼成横幅后走统一的
    trace/标注/动画管线,清晰度远高于让 Flux 一张画多个主体关系。
    """
    images = [Image.open(io.BytesIO(p)).convert("RGB") for p in panels]
    gap, margin, target_h = 64, 48, 820
    scaled = []
    for img in images:
        w = max(1, round(img.width * target_h / img.height))
        scaled.append(img.resize((w, target_h), Image.Resampling.LANCZOS))
    total_w = sum(im.width for im in scaled) + gap * (len(scaled) - 1) + margin * 2
    canvas = Image.new("RGB", (total_w, target_h + margin * 2), "white")
    x = margin
    for im in scaled:
        canvas.paste(im, (x, margin))
        x += im.width + gap
    out = io.BytesIO()
    canvas.save(out, format="PNG", optimize=True)
    return out.getvalue()


async def _generate_composite_scene(req: SceneImageRequest, shots: list[str], client: httpx.AsyncClient) -> tuple[str | None, dict]:
    """Generate each single-subject shot independently, gate it, then compose."""
    attempts: list[dict] = []
    panels: list[bytes] = []
    for index, shot in enumerate(shots):
        shot_req = replace(
            req,
            scene_id=f"{req.scene_id}_shot{index + 1}",
            image_description=shot,
            image_shots=None,
        )
        b64, diag = await generate_scene_image_result(shot_req, client)
        for item in diag.get("attempts", []):
            tagged = dict(item)
            tagged["shot"] = index + 1
            attempts.append(tagged)
        if not b64:
            return None, {"ok": False, "attempts": attempts, "selectedAttempt": None,
                          "failedShot": index + 1}
        panels.append(base64.b64decode(b64))
    img_bytes = _compose_scene_panels(panels)
    quality = inspect_generated_image(img_bytes)
    quality["attempt"] = len(attempts) + 1
    quality["composed"] = len(panels)
    attempts.append(quality)
    if quality["ok"]:
        logger.info("[imagegen] %s composite of %d panels accepted", req.scene_id, len(panels))
        return base64.b64encode(img_bytes).decode(), {"ok": True, "attempts": attempts, "selectedAttempt": len(attempts)}
    logger.warning("[imagegen] %s composite rejected errors=%s", req.scene_id, quality["errors"])
    return None, {"ok": False, "attempts": attempts, "selectedAttempt": None}


async def generate_scene_image_result(req: SceneImageRequest, client: httpx.AsyncClient) -> tuple[str | None, dict]:
    shots = [s.strip() for s in (req.image_shots or []) if s and s.strip()]
    requested_mode_early = str(req.image_mode or "").strip().lower()
    if len(shots) >= 2 and requested_mode_early in {"flux", "local", "local_then_ark", "default", ""} \
            and str(settings.imagegen_provider or "").strip().lower().startswith("local"):
        return await _generate_composite_scene(req, shots, client)
    requested_mode = str(req.image_mode or "").strip().lower()
    # The render pipeline sends image_mode="default"; only flux/local bypass
    # the ComfyUI path. Everything landing on the long-prompt ComfyUI branch
    # needs the condensed subject, or SD1.5's 77-token window drops the topic.
    uses_comfyui = requested_mode not in {"flux", "local", "local_then_ark"} or (
        requested_mode in {"sd15", "sd1.5", "sd-1.5"}
    )
    condensed_subject = await _condense_subject_for_clip(req) if uses_comfyui else None
    prompt = _build_prompt(req, condensed_subject)
    semantic = _semantic_prompt_diagnostics(req)
    requested_mode = str(req.image_mode or "").strip().lower()
    if requested_mode == "flux":
        missing = local_imagegen_status()["modes"]["flux"]["missing"]
        if missing:
            return None, {
                "ok": False,
                "attempts": [{"ok": False, "errors": ["image_mode_unavailable"], "message": f"Flux mode is missing local components: {', '.join(missing)}"}],
                "selectedAttempt": None,
                "imageMode": "flux",
            }
    elif requested_mode in {"sd15", "sd1.5", "sd-1.5"}:
        modes = local_imagegen_status()["modes"]["sd15"]
        if not modes["available"]:
            return None, {
                "ok": False,
                "attempts": [{"ok": False, "errors": ["image_mode_unavailable"], "message": "SD1.5 mode requires a configured ComfyUI workflow and checkpoint"}],
                "selectedAttempt": None,
                "imageMode": "sd15",
            }
    provider = (
        "local" if requested_mode == "flux" else
        "comfyui" if requested_mode in {"sd15", "sd1.5", "sd-1.5"} else
        effective_imagegen_provider()
    )
    attempts: list[dict] = []
    max_attempts = max(1, settings.local_imagegen_max_attempts if provider.startswith("local") else 1)
    # When OCR keeps reading words in the artwork, retell the model the board
    # must stay textless — Flux tends to transcribe structural prompt terms
    # ("cause-process-result flow") into painted labels. The reworded prompt
    # also derives a fresh seed, so resubmitted jobs get genuinely new
    # candidates instead of the same deterministic rejections.
    anti_text_suffix = (
        " Absolutely no words in any language: never draw the words cause, process, result, "
        "conclusion, title, or any other label, letter, digit, number, caption, watermark, or "
        "signature — the video renderer adds all text later. Express every concept purely with "
        "icons, arrows, boxes, charts, and doodle shapes."
    )
    best_failed: tuple[int, int, bytes] | None = None  # (error_count, attempt_no, image_bytes)
    for attempt in range(max_attempts):
        try:
            prior_errors = {err for item in attempts for err in (item.get("errors") or [])}
            retry_prompt = prompt
            if "possible_readable_text_or_signature" in prior_errors:
                retry_prompt += anti_text_suffix
            if "no_clear_subject" in prior_errors:
                retry_prompt += (
                    " Redraw with ONE single dominant hero subject occupying at least one third of the "
                    "canvas height, clearly centered; remove secondary scattered objects."
                )
            if "debris_too_many" in prior_errors:
                retry_prompt += (
                    " Simplify drastically: fewer and much larger flat shapes only; remove all scattered "
                    "small elements, repeated tiny decorations, hatching, and stippling texture; keep "
                    "large empty paper areas."
                )
            if provider in {"local", "local_then_ark"}:
                img_bytes = await _call_local_flux(retry_prompt, quality=req.quality, attempt=attempt)
            elif provider in {"comfyui", "comfy"}:
                img_bytes = await _call_comfyui(retry_prompt, quality=req.quality, attempt=attempt)
            elif provider in {"ark", "seedream", "volcengine"}:
                img_bytes = await _call_seedream(retry_prompt, client)
            else:
                raise RuntimeError(f"Unsupported IMAGEGEN_PROVIDER: {settings.imagegen_provider}")
            img_bytes = normalize_whiteboard_image(img_bytes)
            # Labels belong to the renderer, not the generated illustration.
            quality = inspect_generated_image(img_bytes)
            quality["attempt"] = attempt + 1
            quality["semantic"] = semantic
            quality["sourceAsset"] = _asset_contract_metadata(req, img_bytes, prompt, provider)
            attempts.append(quality)
            if quality["ok"]:
                logger.info("[imagegen] %s provider=%s bytes=%d attempt=%d", req.scene_id, provider, len(img_bytes), attempt + 1)
                return base64.b64encode(img_bytes).decode(), {"ok": True, "attempts": attempts, "selectedAttempt": attempt + 1}
            logger.warning("[imagegen] %s rejected attempt=%d errors=%s", req.scene_id, attempt + 1, quality["errors"])
            # 优雅降级候选:全部重试都被质量门拒掉时,场景宁可带一张有瑕疵
            # 的图也不能没有中央锚点图(下游拿不到图会整场跳过插画)。
            if best_failed is None or len(quality["errors"]) < best_failed[0]:
                best_failed = (len(quality["errors"]), attempt + 1, img_bytes)
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
    if best_failed is not None:
        error_count, attempt_no, fallback_bytes = best_failed
        logger.warning(
            "[imagegen] %s all attempts rejected; degrading to least-flawed candidate (attempt=%d, %d error(s))",
            req.scene_id, attempt_no, error_count,
        )
        return base64.b64encode(fallback_bytes).decode(), {
            "ok": True,
            "attempts": attempts,
            "selectedAttempt": attempt_no,
            "bestFailedFallback": True,
        }
    return None, {"ok": False, "attempts": attempts, "selectedAttempt": None}


async def generate_scene_image(req: SceneImageRequest, client: httpx.AsyncClient) -> str | None:
    image, _ = await generate_scene_image_result(req, client)
    return image


async def generate_all_scene_images(requests: list[SceneImageRequest]) -> dict[str, str | None]:
    async with httpx.AsyncClient() as client:
        results = await asyncio.gather(*[generate_scene_image(r, client) for r in requests])
    return {req.scene_id: b64 for req, b64 in zip(requests, results)}


async def generate_all_scene_images_with_diagnostics(requests: list[SceneImageRequest]) -> tuple[dict[str, str | None], dict[str, dict]]:
    if str(settings.imagegen_provider or "").strip().lower() in {"comfy", "comfyui"}:
        await _check_comfyui_available()
    async with httpx.AsyncClient() as client:
        results = []
        total = len(requests)
        for index, request in enumerate(requests, start=1):
            started = asyncio.get_running_loop().time()
            logger.info(
                "[imagegen] scene %d/%d started: %s provider=%s quality=%s",
                index, total, request.scene_id, settings.imagegen_provider, request.quality,
            )
            result = await generate_scene_image_result(request, client)
            results.append(result)
            logger.info(
                "[imagegen] scene %d/%d finished: %s ok=%s elapsed=%.1fs",
                index, total, request.scene_id, bool(result[1].get("ok")),
                asyncio.get_running_loop().time() - started,
            )
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
        "imageMode": actions[0].image_mode or "default",
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
