"""为 Storyboard 生成标题卡片图片的辅助函数"""
import logging
from src.imagegen.service import SceneImageRequest, generate_scene_image
import httpx

logger = logging.getLogger(__name__)


async def generate_title_image(topic: str, summary: str, video_style: str = "whiteboard") -> str | None:
    """
    为视频标题卡片生成主题插图

    Args:
        topic: 视频主题
        summary: 主题摘要
        video_style: 视频风格

    Returns:
        图片 URL 或 None（生成失败时）
    """
    # 构造标题图片的描述
    image_description = (
        f"simple illustration, minimal details, 3-5 main objects only, clean composition, "
        f"bold editorial hand-drawn explainer illustration about {topic}, "
        f"one central visual metaphor or iconic representation, "
        f"thick black marker outlines, warm off-white background, "
        f"blue and yellow accent colors, generous blank margins, "
        f"text-free artwork, no titles, no labels, no readable words, no watermark"
    )

    request = SceneImageRequest(
        scene_id="title_card",
        topic=topic,
        title=f"{topic} - 标题插图",
        image_description=image_description,
        board_mode="whiteboard",
        hand_usage="direct",  # 标题图不需要手绘追踪
        video_style=video_style,
        visual_style="teacher_whiteboard",
        pen_style="marker",
        quality="final",
        image_mode=None,
    )

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            image_url = await generate_scene_image(request, client)
            if image_url:
                logger.info(f"标题图片生成成功: {topic}")
                return image_url
            else:
                logger.warning(f"标题图片生成失败: {topic}")
                return None
    except Exception as e:
        logger.error(f"标题图片生成异常: {topic}, {e}")
        return None
