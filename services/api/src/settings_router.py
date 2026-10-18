"""Settings API: runtime provider/model configuration from the web UI."""
from __future__ import annotations

import asyncio
import re
import time
from pathlib import Path

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from src.core import runtime_settings
from src.core.config import settings

router = APIRouter(tags=["settings"])


class SettingsPatch(BaseModel):
    values: dict[str, str]


def _effective_view() -> dict:
    from src.imagegen.service import effective_imagegen_provider

    overrides = runtime_settings.masked_snapshot()
    return {
        "saved": overrides,
        "effective": {
            "llm_base_url": runtime_settings.get_override("llm_base_url") or settings.openai_base_url,
            "llm_model": runtime_settings.get_override("llm_model") or settings.llm_model,
            "coder_model": runtime_settings.get_override("coder_model") or settings.coder_model,
            "imagegen_provider": effective_imagegen_provider(),
            "imagegen_base_url": runtime_settings.get_override("imagegen_base_url") or settings.ark_base_url,
            "imagegen_model": runtime_settings.get_override("imagegen_model") or settings.seedream_model,
            "cloud_text2video_base_url": runtime_settings.get_override("cloud_text2video_base_url") or "",
            "cloud_text2video_model": runtime_settings.get_override("cloud_text2video_model") or "",
            "local_text2image_available": True,
            "local_text2video_base_url": runtime_settings.get_override("local_text2video_base_url") or "",
            "local_text2video_model": runtime_settings.get_override("local_text2video_model") or "",
        },
    }


@router.get("/settings")
async def get_settings() -> dict:
    return _effective_view()


@router.put("/settings")
async def put_settings(patch: SettingsPatch) -> dict:
    try:
        runtime_settings.update_overrides(patch.values or {})
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _effective_view()


class Text2VideoTestRequest(BaseModel):
    base_url: str | None = None
    api_key: str | None = None


@router.post("/settings/test-text2video")
async def test_text2video(req: Text2VideoTestRequest) -> dict:
    """Probe a local text-to-video endpoint (OpenAI-compatible style)."""
    base = (req.base_url or runtime_settings.get_override("local_text2video_base_url") or "").strip().rstrip("/")
    if not base:
        raise HTTPException(status_code=422, detail="local_text2video_base_url is not configured")
    key = req.api_key or runtime_settings.get_override("local_text2video_api_key") or ""
    probes: list[tuple[str, int | None]] = []
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    async with httpx.AsyncClient(timeout=6.0) as client:
        for path in ("/health", "/v1/models"):
            try:
                resp = await client.get(f"{base}{path}", headers=headers)
                probes.append({"path": path, "status": resp.status_code})
            except httpx.HTTPError as exc:
                probes.append({"path": path, "error": str(exc)[:160]})
    ok = any(p.get("status") in (200, 204) for p in probes)
    return {"ok": ok, "baseUrl": base, "probes": probes}


# ---------------------------------------------------------------------------
# Local text-to-video: real OpenAI-compatible invocation path
# ---------------------------------------------------------------------------

_T2V_DIR = Path(__file__).resolve().parents[3] / "outputs" / "text2video-tests"
_T2V_TIMEOUT_S = 300.0
_POLL_INTERVAL_S = 3.0
_POLL_MAX = int(_T2V_TIMEOUT_S / _POLL_INTERVAL_S)


class Text2VideoGenerateRequest(BaseModel):
    prompt: str | None = None
    base_url: str | None = None
    model: str | None = None
    api_key: str | None = None


def _t2v_headers(api_key: str) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def _t2v_auth() -> tuple[str, str, str]:
    base = (runtime_settings.get_override("local_text2video_base_url") or "").strip().rstrip("/")
    model = (runtime_settings.get_override("local_text2video_model") or "").strip()
    key = runtime_settings.get_override("local_text2video_api_key") or ""
    return base, model, key


def _extract_video_ref(payload: dict) -> str | None:
    """Find a downloadable video URL in a common OpenAI-style response."""
    candidates = []
    if isinstance(payload.get("url"), str):
        candidates.append(payload["url"])
    if isinstance(payload.get("video_url"), str):
        candidates.append(payload["video_url"])
    for item in payload.get("data") or []:
        if isinstance(item, dict):
            for key in ("url", "video_url", "video"):
                if isinstance(item.get(key), str):
                    candidates.append(item[key])
    output = payload.get("output")
    if isinstance(output, str):
        candidates.append(output)
    elif isinstance(output, list):
        candidates.extend(x for x in output if isinstance(x, str))
    return next((c for c in candidates if c.startswith(("http://", "https://", "/"))), None)


def _ext_for(content_type: str, url: str) -> str:
    ct = (content_type or "").split(";")[0].strip().lower()
    if "webm" in ct:
        return ".webm"
    if "mp2t" in ct:
        return ".ts"
    if "mp4" in ct or "octet-stream" in ct or not ct:
        m = re.search(r"\.(mp4|webm|mov|mkv)(?:\?|$)", url or "")
        if m:
            return f".{m.group(1)}"
        return ".mp4"
    m = re.search(r"\.(mp4|webm|mov|mkv)(?:\?|$)", url or "")
    return f".{m.group(1)}" if m else ".mp4"


@router.post("/settings/generate-test-video")
async def generate_test_video(req: Text2VideoGenerateRequest) -> dict:
    """Submit one real text-to-video request to the configured local service.

    支持三种常见返回形态:直接返回视频字节、JSON 内嵌结果 URL、异步任务
    (返回 id,轮询 /v1/videos/{id} 直到 completed 再取 URL)。产物保存到
    outputs/text2video-tests 并通过 /settings/test-video/{name} 回放。
    """
    base = (req.base_url or "").strip().rstrip("/") or _t2v_auth()[0]
    model = (req.model or "").strip() or _t2v_auth()[1]
    api_key = (req.api_key or "").strip() or _t2v_auth()[2]
    prompt = (req.prompt or "").strip() or (
        "手绘白板风格动画:一列小火车从左向右行驶,蜡笔质感,简洁背景"
    )
    if not base or not model:
        raise HTTPException(status_code=422, detail="请先在设置中保存本地文生视频的服务地址和模型名")
    headers = _t2v_headers(api_key)
    started = time.time()

    async with httpx.AsyncClient(timeout=_T2V_TIMEOUT_S, follow_redirects=True) as client:
        try:
            resp = await client.post(
                f"{base}/v1/videos",
                headers=headers,
                json={"model": model, "prompt": prompt, "seconds": 5, "size": "768x432"},
            )
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=f"文生视频服务连接失败: {exc}") from exc
        if resp.status_code >= 400:
            raise HTTPException(status_code=502, detail=f"文生视频服务返回 {resp.status_code}: {resp.text[:300]}")

        content_type = resp.headers.get("content-type", "")
        if content_type.startswith(("video/", "application/octet-stream")) and resp.content:
            video_bytes, ext = resp.content, _ext_for(content_type, "")
        else:
            try:
                payload = resp.json()
            except ValueError as exc:
                raise HTTPException(status_code=502, detail=f"无法解析文生视频响应: {resp.text[:300]}") from exc
            video_url = _extract_video_ref(payload)
            task_id = payload.get("id") or payload.get("task_id")
            if not video_url and task_id:
                # 异步任务:轮询直到 completed / succeeded
                for _ in range(_POLL_MAX):
                    await asyncio.sleep(_POLL_INTERVAL_S)
                    try:
                        poll = await client.get(f"{base}/v1/videos/{task_id}", headers=headers)
                    except httpx.HTTPError as exc:
                        raise HTTPException(status_code=502, detail=f"轮询任务失败: {exc}") from exc
                    if poll.status_code >= 400:
                        raise HTTPException(status_code=502, detail=f"轮询任务返回 {poll.status_code}: {poll.text[:300]}")
                    data = poll.json()
                    status = str(data.get("status") or data.get("state") or "").lower()
                    if status in {"failed", "error", "cancelled"}:
                        raise HTTPException(status_code=502, detail=f"文生视频任务失败: {str(data)[:300]}")
                    video_url = _extract_video_ref(data)
                    if video_url:
                        break
            if not video_url:
                raise HTTPException(status_code=502, detail=f"响应中没有可下载的视频地址: {str(payload)[:300]}")
            if not video_url.startswith(("http://", "https://")):
                video_url = f"{base}{video_url}"
            dl = await client.get(video_url, headers=headers)
            if dl.status_code >= 400:
                raise HTTPException(status_code=502, detail=f"视频下载失败 {dl.status_code}")
            video_bytes, ext = dl.content, _ext_for(dl.headers.get("content-type", ""), video_url)

    if not video_bytes or len(video_bytes) < 1024:
        raise HTTPException(status_code=502, detail="文生视频服务返回了空视频")

    _T2V_DIR.mkdir(parents=True, exist_ok=True)
    name = time.strftime("t2v_%Y%m%d_%H%M%S") + ext
    (_T2V_DIR / name).write_bytes(video_bytes)
    return {
        "ok": True,
        "filename": name,
        "videoUrl": f"/settings/test-video/{name}",
        "sizeBytes": len(video_bytes),
        "elapsedSeconds": round(time.time() - started, 1),
        "baseUrl": base,
        "model": model,
    }


@router.get("/settings/test-video/{name}")
async def get_test_video(name: str) -> FileResponse:
    if not re.fullmatch(r"t2v_[\w.-]+", name):
        raise HTTPException(status_code=400, detail="invalid filename")
    path = _T2V_DIR / name
    if not path.is_file():
        raise HTTPException(status_code=404, detail="not found")
    media = "video/webm" if name.endswith(".webm") else "video/mp4"
    return FileResponse(path, media_type=media, filename=name)
