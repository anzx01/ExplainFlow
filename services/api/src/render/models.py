from pydantic import BaseModel, Field

from src.planner.models import Storyboard


class RenderJobRequest(BaseModel):
    storyboard: Storyboard
    voice: str = "xiaoxiao"
    resolution: str = "1080p"
    subtitles_enabled: bool = False
    background_music_enabled: bool = False
    background_music_id: str | None = None
    background_music_volume: float = Field(default=0.12, ge=0.0, le=0.5)


class RenderJobStatus(BaseModel):
    job_id: str
    status: str  # pending | processing | done | failed
    progress: float = 0.0
    phase: str | None = None
    video_url: str | None = None
    error: str | None = None
    createdAt: str | None = None


class RenderJobSummary(BaseModel):
    id: str
    status: str
    progress: float = 0.0
    phase: str | None = None
    topic: str | None = None
    createdAt: str | None = None
    error: str | None = None


class RenderJobPatch(BaseModel):
    topic: str | None = None


class BulkDeleteJobsRequest(BaseModel):
    job_ids: list[str]


class BackgroundMusicTrack(BaseModel):
    id: str
    name: str
    url: str
    size: int


class BackgroundMusicLibrary(BaseModel):
    tracks: list[BackgroundMusicTrack]
