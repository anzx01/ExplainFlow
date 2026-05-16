from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .service import SceneImageRequest, generate_all_scene_images

router = APIRouter(prefix="/imagegen", tags=["imagegen"])


class SceneImageItem(BaseModel):
    scene_id: str
    topic: str
    title: str
    image_description: str


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
        )
        for s in req.scenes
    ]

    images = await generate_all_scene_images(requests)
    return GenerateImagesResponse(images=images)
