from fastapi import APIRouter, HTTPException

from src.core.llm import LLMResponseParseError, LLMUnavailableError
from .models import (
    GenerateRemotionCodeRequest,
    GenerateRemotionCodeResponse,
    GenerateStoryboardRequest,
    GenerateStoryboardResponse,
    ValidateStoryboardRequest,
    ValidateStoryboardResponse,
    RenderContractIssueModel,
    ParseSrtRequest,
    ParseSrtResponse,
)
from .storyboard_gen.builder import generate_storyboard
from .remotion_codegen.compiler import generate_remotion_code
from .project_snapshot import build_project_snapshot
from .render_contract import (
    compile_scene_timeline,
    finalize_storyboard_contract,
    validate_storyboard_contract,
)
from .srt_timeline import SrtParseError, build_srt_timeline

router = APIRouter(prefix="/planner", tags=["planner"])


@router.post("/srt/parse", response_model=ParseSrtResponse)
async def parse_srt_timeline(req: ParseSrtRequest) -> ParseSrtResponse:
    try:
        timeline = build_srt_timeline(
            req.srt,
            target_sec=req.target_sec,
            min_sec=req.min_sec,
            max_sec=req.max_sec,
        )
        return ParseSrtResponse(**timeline)
    except (SrtParseError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/validate-storyboard", response_model=ValidateStoryboardResponse)
async def validate_storyboard(req: ValidateStoryboardRequest) -> ValidateStoryboardResponse:
    try:
        storyboard = finalize_storyboard_contract(req.storyboard.model_copy(deep=True), fps=req.fps)
        issues = validate_storyboard_contract(storyboard, fps=req.fps)
        timelines = {
            scene.id: compile_scene_timeline(scene, fps=req.fps)
            for scene in storyboard.scenes
        }
        snapshot = build_project_snapshot(
            storyboard.model_dump(mode="json", by_alias=True),
            style_snapshot={
                "videoStyle": storyboard.video_style,
                "penStyle": storyboard.pen_style,
            },
            render_config={"fps": req.fps},
        )
        return ValidateStoryboardResponse(
            ok=not any(issue.severity == "error" for issue in issues),
            storyboard=storyboard,
            issues=[RenderContractIssueModel(**issue.__dict__) for issue in issues],
            timelines=timelines,
            snapshot=snapshot,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/storyboard", response_model=GenerateStoryboardResponse)
async def create_storyboard(req: GenerateStoryboardRequest) -> GenerateStoryboardResponse:
    try:
        storyboard = await generate_storyboard(req)
        return GenerateStoryboardResponse(storyboard=storyboard)
    except LLMUnavailableError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except LLMResponseParseError as e:
        raise HTTPException(status_code=502, detail=f"Storyboard model returned invalid JSON after retry: {e}") from e
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
