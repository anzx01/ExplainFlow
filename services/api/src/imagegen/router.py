from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .service import SceneImageRequest, generate_action_board_with_diagnostics, generate_all_scene_images_with_diagnostics, local_imagegen_status

router = APIRouter(prefix="/imagegen", tags=["imagegen"])


@router.get("", include_in_schema=False)
@router.get("/", include_in_schema=False)
async def imagegen_root() -> dict:
    return {"ok": True, "service": "imagegen", **local_imagegen_status()}


@router.get("/status")
async def imagegen_status() -> dict:
    return local_imagegen_status()


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
    quality: str = "final"
    image_mode: str | None = None


class GenerateImagesRequest(BaseModel):
    scenes: list[SceneImageItem]


class GenerateImagesResponse(BaseModel):
    images: dict[str, str | None]
    diagnostics: dict[str, dict]


class ActionBoardItem(BaseModel):
    action_id: str
    title: str = ""
    image_description: str
    quality: str = "final"


class GenerateActionBoardRequest(BaseModel):
    board_id: str
    topic: str
    actions: list[ActionBoardItem]
    columns: int = 3


class GenerateActionBoardResponse(BaseModel):
    image: str | None
    diagnostics: dict


@router.post("/scenes", response_model=GenerateImagesResponse)
async def generate_scene_images(req: GenerateImagesRequest) -> GenerateImagesResponse:
    if not req.scenes:
        raise HTTPException(status_code=400, detail="scenes list is empty")
    requests = [
        SceneImageRequest(
            scene_id=scene.scene_id,
            topic=scene.topic,
            title=scene.title,
            image_description=scene.image_description,
            board_mode=scene.board_mode,
            hand_usage=scene.hand_usage,
            video_style=scene.video_style,
            visual_style=scene.visual_style,
            pen_style=scene.pen_style,
            quality="preview" if scene.quality == "preview" else "final",
            image_mode=scene.image_mode,
        )
        for scene in req.scenes
    ]
    images, diagnostics = await generate_all_scene_images_with_diagnostics(requests)
    return GenerateImagesResponse(images=images, diagnostics=diagnostics)


@router.post("/action-board", response_model=GenerateActionBoardResponse)
async def generate_action_board(req: GenerateActionBoardRequest) -> GenerateActionBoardResponse:
    if not req.actions:
        raise HTTPException(status_code=400, detail="actions list is empty")
    if req.columns < 1 or req.columns > 6:
        raise HTTPException(status_code=400, detail="columns must be between 1 and 6")
    requests = [
        SceneImageRequest(
            scene_id=f"{req.board_id}_{action.action_id}",
            topic=req.topic,
            title=action.title or action.action_id,
            image_description=action.image_description,
            board_mode="reference",
            hand_usage="trace",
            video_style="whiteboard",
            visual_style="marketing_doodle",
            pen_style="marker",
            quality="preview" if action.quality.strip().lower() == "preview" else "final",
        )
        for action in req.actions
    ]
    image, diagnostics = await generate_action_board_with_diagnostics(
        board_id=req.board_id, topic=req.topic, actions=requests, columns=req.columns,
    )
    return GenerateActionBoardResponse(image=image, diagnostics=diagnostics)
