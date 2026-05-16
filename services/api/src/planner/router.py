from fastapi import APIRouter, HTTPException

from .models import GenerateStoryboardRequest, GenerateStoryboardResponse
from .service import generate_storyboard

router = APIRouter(prefix="/planner", tags=["planner"])


@router.post("/storyboard", response_model=GenerateStoryboardResponse)
async def create_storyboard(req: GenerateStoryboardRequest) -> GenerateStoryboardResponse:
    try:
        storyboard = await generate_storyboard(req)
        return GenerateStoryboardResponse(storyboard=storyboard)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
