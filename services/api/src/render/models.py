from pydantic import BaseModel

from src.planner.models import Storyboard


class RenderJobRequest(BaseModel):
    storyboard: Storyboard
    voice: str = "xiaoxiao"
    resolution: str = "1080p"


class RenderJobStatus(BaseModel):
    job_id: str
    status: str  # pending | processing | done | failed
    progress: float = 0.0
    video_url: str | None = None
    error: str | None = None


class RenderJobSummary(BaseModel):
    id: str
    status: str
    progress: float = 0.0
    topic: str | None = None
    createdAt: str | None = None
    error: str | None = None


class RenderJobPatch(BaseModel):
    topic: str | None = None
