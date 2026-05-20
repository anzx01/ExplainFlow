from pydantic import BaseModel, Field

from src.planner.models import Storyboard


class RenderQaCheck(BaseModel):
    id: str
    ok: bool
    severity: str = "info"
    message: str
    details: dict | None = None
    suggestion: str | None = None


class RenderQaResult(BaseModel):
    ok: bool
    checkedAt: str | None = None
    durationSeconds: float | None = None
    hasAudio: bool | None = None
    fileSizeBytes: int | None = None
    checks: list[RenderQaCheck] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)


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
    actualDurationSeconds: float | None = None
    qa: RenderQaResult | None = None


class RenderJobSummary(BaseModel):
    id: str
    status: str
    progress: float = 0.0
    phase: str | None = None
    topic: str | None = None
    createdAt: str | None = None
    actualDurationSeconds: float | None = None
    qa: RenderQaResult | None = None
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
