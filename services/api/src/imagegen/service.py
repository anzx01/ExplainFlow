import asyncio
import base64
import logging
from dataclasses import dataclass

import httpx

from src.core.config import settings

logger = logging.getLogger(__name__)

_STYLE_SUFFIX = (
    "whiteboard sketch illustration style, black outline drawing on a plain white or transparent-looking background, "
    "simple line art, minimal clean style, educational diagram, "
    "use limited teaching colors: red for current or flow, blue for voltage/control arrows, "
    "green for conductive channels or valid paths, purple for gate/structure, yellow for key underlines and callouts, "
    "hand-drawn marker look, bold black lines, clear labels, "
    "follow every requested label exactly, draw the specific mechanism described, "
    "include process arrows, state comparison panels, cross-section callouts, and local zoom-in details when requested, "
    "when helpful include a small picture-in-picture reference sketch or real-world analogy diagram that maps to the technical mechanism, "
    "show progressive focus with large readable labels, arrows added only to the relevant region, and acronym expansion when the concept has an acronym, "
    "underline or circle important terms like an excellent teacher's board notes, "
    "do not use colored paper, yellow background, pastel panels, background washes, frames, or tinted rectangles, "
    "avoid generic icons or placeholder shapes"
)

_NEGATIVE = "photo, realistic, full-color poster, 3d render, painting, complex background, decorative template, yellow background, beige paper, colored paper, pastel panel, background wash, tinted rectangle"


@dataclass
class SceneImageRequest:
    scene_id: str
    topic: str
    title: str
    image_description: str


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
    return (
        f"{req.image_description}, topic: {req.topic}, "
        f"scene: {req.title}, "
        f"{_STYLE_SUFFIX}"
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
