from pydantic import AliasChoices, BaseModel, Field

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
    resolution: str = "720p"
    subtitles_enabled: bool = True
    background_music_enabled: bool = False
    background_music_id: str | None = None
    background_music_volume: float = Field(default=0.12, ge=0.0, le=0.5)
    force_render: bool = Field(default=False, validation_alias=AliasChoices("force_render", "forceRender"))


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


class EnginePreviewRequest(BaseModel):
    scene_id: str
    image_url: str
    duration: float = Field(default=6.0, ge=1.0, le=60.0)
    fps: int = Field(default=24, ge=12, le=60)
    width: int = Field(default=1280, ge=320, le=3840)
    height: int = Field(default=720, ge=240, le=2160)
    hand: str = "asian"
    stroke_detail: str = "rich"
    color_fill: str = "contour-wipe"
    color_fill_scope: str = "block"


class EnginePreviewResponse(BaseModel):
    ok: bool
    scene_id: str
    preview_url: str
    file_size_bytes: int
    renderer: str = "whiteboard-video-engine"
