import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse, Response

from src.core.llm import LLMUnavailableError, check_llm_connection
from .models import (
    BackgroundMusicLibrary,
    BulkDeleteJobsRequest,
    RenderJobPatch,
    RenderJobRequest,
    RenderJobStatus,
    RenderJobSummary,
)

router = APIRouter(prefix="/render", tags=["render"])

RENDER_SERVER = "http://localhost:3001"


@router.post("/job", response_model=RenderJobStatus)
async def create_render_job(req: RenderJobRequest) -> RenderJobStatus:
    try:
        await check_llm_connection()
        async with httpx.AsyncClient(timeout=10) as client:
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
    except httpx.ConnectError:
        raise HTTPException(
            status_code=503,
            detail="Render server not running. Start it with: bash scripts/dev-render.sh",
        )
    except LLMUnavailableError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/music", response_model=BackgroundMusicLibrary)
async def list_background_music() -> BackgroundMusicLibrary:
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{RENDER_SERVER}/music")
            resp.raise_for_status()
            return BackgroundMusicLibrary(**resp.json())
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="Render server not running")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/job/{job_id}", response_model=RenderJobStatus)
async def get_render_job(job_id: str) -> RenderJobStatus:
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{RENDER_SERVER}/job/{job_id}")
            resp.raise_for_status()
            data = resp.json()
            video_url = (
                f"/render/download/{job_id}" if data["status"] == "done" else None
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
            )
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="Render server not running")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/download/{job_id}")
async def download_video(job_id: str, request: Request):
    # Check job is done
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{RENDER_SERVER}/job/{job_id}")
            if resp.json().get("status") != "done":
                raise HTTPException(status_code=404, detail="Video not ready")
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="Render server not running")

    # Forward Range header so browser <video> can seek
    headers: dict[str, str] = {}
    if range_header := request.headers.get("range"):
        headers["Range"] = range_header

    async with httpx.AsyncClient(timeout=300) as client:
        r = await client.get(
            f"{RENDER_SERVER}/download/{job_id}",
            headers=headers,
        )

    filename = f"{job_id}.mp4"
    response_headers = {
        "Content-Type": "video/mp4",
        "Accept-Ranges": "bytes",
        "Content-Disposition": f"inline; filename={filename}",
    }
    if "content-length" in r.headers:
        response_headers["Content-Length"] = r.headers["content-length"]
    if "content-range" in r.headers:
        response_headers["Content-Range"] = r.headers["content-range"]

    return Response(
        content=r.content,
        status_code=r.status_code,
        headers=response_headers,
    )


@router.get("/jobs", response_model=list[RenderJobSummary])
async def list_render_jobs() -> list[RenderJobSummary]:
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{RENDER_SERVER}/jobs")
            resp.raise_for_status()
            return [RenderJobSummary(**j) for j in resp.json()["jobs"]]
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="Render server not running")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/job/{job_id}")
async def delete_render_job(job_id: str) -> dict:
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.delete(f"{RENDER_SERVER}/job/{job_id}")
            if resp.status_code == 404:
                raise HTTPException(status_code=404, detail="Job not found")
            resp.raise_for_status()
            return {"ok": True}
    except HTTPException:
        raise
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="Render server not running")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/jobs/delete")
async def bulk_delete_render_jobs(req: BulkDeleteJobsRequest) -> dict:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{RENDER_SERVER}/jobs/delete",
                json={"jobIds": req.job_ids},
            )
            resp.raise_for_status()
            return resp.json()
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="Render server not running")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/job/{job_id}")
async def update_render_job(job_id: str, patch: RenderJobPatch) -> dict:
    try:
        async with httpx.AsyncClient(timeout=5) as client:
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
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="Render server not running")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
