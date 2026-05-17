from fastapi import APIRouter, HTTPException

from src.core.llm import LLMUnavailableError
from .models import (
    GenerateRemotionCodeRequest,
    GenerateRemotionCodeResponse,
    GenerateStoryboardRequest,
    GenerateStoryboardResponse,
)
from .service import generate_remotion_code, generate_storyboard

router = APIRouter(prefix="/planner", tags=["planner"])


@router.post("/storyboard", response_model=GenerateStoryboardResponse)
async def create_storyboard(req: GenerateStoryboardRequest) -> GenerateStoryboardResponse:
    try:
        storyboard = await generate_storyboard(req)
        return GenerateStoryboardResponse(storyboard=storyboard)
    except LLMUnavailableError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/remotion-code", response_model=GenerateRemotionCodeResponse)
async def create_remotion_code(
    req: GenerateRemotionCodeRequest,
) -> GenerateRemotionCodeResponse:
    try:
        return await generate_remotion_code(req)
    except LLMUnavailableError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
