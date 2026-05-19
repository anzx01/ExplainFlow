from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .service import SceneImageRequest, generate_all_scene_images

router = APIRouter(prefix="/imagegen", tags=["imagegen"])


class SceneImageItem(BaseModel):
    scene_id: str
    topic: str
    title: str
    image_description: str
    board_mode: str = "whiteboard"
    hand_usage: str = "trace"
    video_style: str = "whiteboard"
    visual_style: str = "teacher_whiteboard"
    pen_style: str = "marker"


class GenerateImagesRequest(BaseModel):
    scenes: list[SceneImageItem]


class GenerateImagesResponse(BaseModel):
    images: dict[str, str | None]   # scene_id → url (None 表示生成失败)


@router.post("/scenes", response_model=GenerateImagesResponse)
async def generate_scene_images(req: GenerateImagesRequest) -> GenerateImagesResponse:
    if not req.scenes:
        raise HTTPException(status_code=400, detail="scenes list is empty")

    requests = [
        SceneImageRequest(
            scene_id=s.scene_id,
            topic=s.topic,
            title=s.title,
            image_description=s.image_description,
            board_mode=s.board_mode,
            hand_usage=s.hand_usage,
            video_style=s.video_style,
            visual_style=s.visual_style,
            pen_style=s.pen_style,
        )
        for s in req.scenes
    ]

    images = await generate_all_scene_images(requests)
    return GenerateImagesResponse(images=images)
