from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .service import VOICES, synthesize

router = APIRouter(prefix="/narration", tags=["narration"])


class SynthesizeRequest(BaseModel):
    text: str
    voice: str = "xiaoxiao"


@router.post("/synthesize")
async def synthesize_endpoint(req: SynthesizeRequest) -> FileResponse:
    if req.voice not in VOICES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid voice. Choose from: {list(VOICES.keys())}",
        )
    try:
        path = await synthesize(req.text, voice_key=req.voice)
        return FileResponse(path=str(path), media_type="audio/mpeg", filename="narration.mp3")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/voices")
async def list_voices() -> dict:
    return {"voices": list(VOICES.keys())}
