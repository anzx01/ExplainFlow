import asyncio
import base64
import logging
from dataclasses import dataclass

import httpx

from src.core.config import settings

logger = logging.getLogger(__name__)

_STYLE_SUFFIX = (
    "classic educational whiteboard explainer frame, matching a real teacher marker-board lecture video, "
    "light grey-white empty whiteboard surface, transparent-looking background, lots of negative space, "
    "one clear object, comparison, process, or mechanism per image; never a poster or dense infographic, "
    "place the main diagram in the middle or slightly right of center, using about 45-65 percent of the frame width, "
    "leave broad clean margins around the drawing for a hand to write callouts later, "
    "clean black hand-drawn marker line art for the main drawing, slightly irregular but sharp and readable, "
    "use dark blue handwritten marker labels sparingly, only short labels close to the corresponding part, "
    "use limited teaching colors only when they carry meaning: red for current or flow, blue for voltage/control arrows, "
    "green for conductive channels or valid paths, purple for gate/structure, yellow only for a small underline or callout, "
    "follow every requested label exactly, but keep labels short and readable, "
    "do not add a title, topic heading, scene name, logo, watermark, paragraph text, legend box, slide frame, or poster layout inside the image, "
    "the scene title and topic are only context for the artist; never render them as words inside the image, "
    "draw the specific mechanism described with process arrows, state comparison panels, cross-section callouts, and local zoom-in details only when requested, "
    "for very complex objects, show the finished line diagram cleanly and leave room around it for hand-drawn callouts added later, "
    "show the final board drawing as if it has just been sketched by hand: slightly irregular marker lines, simple anatomy/device shapes, "
    "no colored paper, no yellow background, no beige paper, no pastel panels, no background washes, no tinted rectangles, "
    "avoid generic icons, placeholder shapes, decorative templates, glossy 3D, photorealism, and dense infographic layouts"
)

_NEGATIVE = (
    "photo, realistic, full-color poster, 3d render, painting, complex background, decorative template, "
    "yellow background, beige paper, colored paper, pastel panel, background wash, tinted rectangle, "
    "title text, topic heading, logo, watermark, dense infographic, long paragraph, slide frame, card layout, legend box"
)


@dataclass
class SceneImageRequest:
    scene_id: str
    topic: str
    title: str
    image_description: str
    board_mode: str = "whiteboard"
    hand_usage: str = "trace"
    visual_style: str = "teacher_whiteboard"


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
    style = (req.visual_style or "teacher_whiteboard").strip().lower()
    if mode == "chalkboard" or style == "math_chalkboard":
        suffix = (
            "black chalkboard math explainer frame, dark clean board, fluorescent chalk handwriting, "
            "step-by-step derivation layout, preserve previous lines with generous spacing, "
            "white main equations, cyan/green variables, yellow conclusions, pink key conditions, "
            "no hand, no paper texture, no poster, no decorative frame"
        )
        negative = (
            "whiteboard, hand, marker, poster, dense infographic, photo, glossy 3d, colored panel, "
            "long paragraph, slide frame, card layout"
        )
    elif mode == "clean_canvas" or style == "marketing_doodle":
        suffix = (
            "clean white canvas marketing doodle explainer frame, colorful hand-drawn finished doodle objects, "
            "large empty margins for later marker annotations, friendly sharp ink outlines, limited bright accent colors, "
            "clear grouped icons or product concept objects, not every contour needs to be traced by hand, "
            "avoid dense poster layout and avoid long paragraphs"
        )
        negative = (
            "photo, realistic, dense infographic, long paragraph, slide frame, card layout, logo, watermark, "
            "yellow background, beige paper, colored paper, background wash"
        )
    elif mode == "reference" or style == "technical_reference":
        suffix = (
            "clean technical reference doodle on a transparent-looking whiteboard surface, finished complex subject is clear first, "
            "sharp black line art with limited semantic colors, leave margins for hand-drawn callouts, "
            "labels short and close to structures, no dense legend, no poster layout, no colored background panel"
        )
        negative = _NEGATIVE
    else:
        suffix = _STYLE_SUFFIX
        negative = _NEGATIVE
    return (
        f"{req.image_description}. Topic context only, do not draw as text: {req.topic}. "
        f"Scene context only, do not draw as text: {req.title}. "
        f"{suffix}. Negative prompt: {negative}"
    )


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
