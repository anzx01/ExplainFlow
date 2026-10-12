import contextlib
import os
from collections.abc import AsyncIterator

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pathlib import Path

from src.core.llm import LLMUnavailableError
from .models import (
    BackgroundMusicLibrary,
    BulkDeleteJobsRequest,
    RenderJobPatch,
    RenderJobRequest,
    RenderJobStatus,
    RenderJobSummary,
    EnginePreviewRequest,
    EnginePreviewResponse,
)
from .engine_adapter import PREVIEW_DIR, engine_status, render_engine_preview

router = APIRouter(prefix="/render", tags=["render"])

RENDER_SERVER = os.getenv("RENDER_SERVER_URL", "http://localhost:3002")


@router.get("/engine/status")
async def get_engine_status() -> dict:
    return engine_status()


@router.post("/engine/preview", response_model=EnginePreviewResponse)
async def create_engine_preview(req: EnginePreviewRequest) -> EnginePreviewResponse:
    try:
        output = await render_engine_preview(
            req.image_url,
            duration=req.duration,
            fps=req.fps,
            width=req.width,
            height=req.height,
            hand=req.hand,
            stroke_detail=req.stroke_detail,
            color_fill=req.color_fill,
            color_fill_scope=req.color_fill_scope,
        )
        return EnginePreviewResponse(
            ok=True,
            scene_id=req.scene_id,
            preview_url=f"/render/engine/preview/{output.name}",
            file_size_bytes=output.stat().st_size,
        )
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/engine/preview/{filename}")
async def get_engine_preview(filename: str) -> FileResponse:
    safe_name = Path(filename).name
    path = PREVIEW_DIR / safe_name
    if path.suffix.lower() != ".mp4" or not path.exists():
        raise HTTPException(status_code=404, detail="Preview not found")
    return FileResponse(path, media_type="video/mp4", filename=safe_name)


@contextlib.asynccontextmanager
async def _proxy(timeout: float = 5) -> AsyncIterator[httpx.AsyncClient]:
    """向渲染服务器转发请求的公共上下文管理器，统一处理连接错误。"""
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            yield client
    except httpx.ConnectError:
        raise HTTPException(
            status_code=503,
            detail="Render server not running. Start it with: bash scripts/dev-render.sh",
        )


@router.post("/job", response_model=RenderJobStatus)
async def create_render_job(req: RenderJobRequest) -> RenderJobStatus:
    try:
        async with _proxy(timeout=10) as client:
            resp = await client.post(
                f"{RENDER_SERVER}/render",
                json={
                    "storyboard": req.storyboard.model_dump(),
                    "voice": req.voice,
                    "resolution": req.resolution,
                    "subtitlesEnabled": req.subtitles_enabled,
                    "backgroundMusicEnabled": req.background_music_enabled,
                    "backgroundMusicId": req.background_music_id,
                    "backgroundMusicVolume": req.background_music_volume,
                    "forceRender": req.force_render,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return RenderJobStatus(
                job_id=data["jobId"],
                status="processing",
                phase="queued",
                createdAt=data.get("createdAt"),
            )
    except LLMUnavailableError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/music", response_model=BackgroundMusicLibrary)
async def list_background_music() -> BackgroundMusicLibrary:
    try:
        async with _proxy() as client:
            resp = await client.get(f"{RENDER_SERVER}/music")
            resp.raise_for_status()
            return BackgroundMusicLibrary(**resp.json())
    except HTTPException:
        raise
    except httpx.ConnectError as e:
        raise HTTPException(
            status_code=503,
            detail="Render server is still starting; music library is not ready",
        ) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/job/{job_id}", response_model=RenderJobStatus)
async def get_render_job(job_id: str) -> RenderJobStatus:
    try:
        async with _proxy() as client:
            resp = await client.get(f"{RENDER_SERVER}/job/{job_id}")
            resp.raise_for_status()
            data = resp.json()
            video_url = (
                f"{RENDER_SERVER}/download/{job_id}" if data["status"] == "done" else None
            )
            return RenderJobStatus(
                job_id=job_id,
                status=data["status"],
                progress=data.get("progress", 0),
                phase=data.get("phase"),
                video_url=video_url,
                error=data.get("error"),
                createdAt=data.get("createdAt"),
                actualDurationSeconds=data.get("actualDurationSeconds"),
                qa=data.get("qa"),
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/jobs", response_model=list[RenderJobSummary])
async def list_render_jobs() -> list[RenderJobSummary]:
    try:
        async with _proxy() as client:
            resp = await client.get(f"{RENDER_SERVER}/jobs")
            resp.raise_for_status()
            return [RenderJobSummary(**j) for j in resp.json()["jobs"]]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/job/{job_id}")
async def delete_render_job(job_id: str) -> dict:
    try:
        async with _proxy() as client:
            resp = await client.delete(f"{RENDER_SERVER}/job/{job_id}")
            if resp.status_code == 404:
                raise HTTPException(status_code=404, detail="Job not found")
            resp.raise_for_status()
            return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/jobs/delete")
async def bulk_delete_render_jobs(req: BulkDeleteJobsRequest) -> dict:
    try:
        async with _proxy(timeout=10) as client:
            resp = await client.post(
                f"{RENDER_SERVER}/jobs/delete",
                json={"jobIds": req.job_ids},
            )
            resp.raise_for_status()
            return resp.json()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/job/{job_id}")
async def update_render_job(job_id: str, patch: RenderJobPatch) -> dict:
    try:
        async with _proxy() as client:
            resp = await client.patch(
                f"{RENDER_SERVER}/job/{job_id}",
                json=patch.model_dump(exclude_none=True),
            )
            if resp.status_code == 404:
                raise HTTPException(status_code=404, detail="Job not found")
            resp.raise_for_status()
            return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
