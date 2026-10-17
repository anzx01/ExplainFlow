from enum import Enum
from pydantic import BaseModel, ConfigDict, Field

from src.explain.models import ExplainGraph


class AnimationType(str, Enum):
    WRITE_TEXT = "write_text"
    WRITE_FORMULA = "write_formula"
    DRAW_ARROW = "draw_arrow"
    DRAW_BOX = "draw_box"
    CONCEPT_BUBBLE = "concept_bubble"
    BULLET_LIST = "bullet_list"
    STEP_REVEAL = "step_reveal"
    HIGHLIGHT_REGION = "highlight_region"
    WHITEBOARD_DRAW = "whiteboard_draw"
    FORMULA_REVEAL = "formula_reveal"
    CONCEPT_NODE = "concept_node"
    ARROW_CONNECT = "arrow_connect"
    HIGHLIGHT = "highlight"
    TEXT_NARRATION = "text_narration"


class AnimationInstruction(BaseModel):
    model_config = ConfigDict(extra="allow")

    type: AnimationType
    duration: float = Field(default=2.0, ge=0.5, le=15.0)
    content: str
    latex: str | None = None
    from_node: str | None = None
    to_node: str | None = None
    x: float | None = None
    y: float | None = None
    items: list[str] | None = None


class VisualBeat(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str | None = None
    draw_intent: str
    narration: str
    required_labels: list[str] = Field(default_factory=list)
    duration_estimate: float = Field(default=6.0, ge=1.0, le=30.0)


class DiagramPlan(BaseModel):
    model_config = ConfigDict(extra="allow")

    kind: str = "process"
    layout: str = ""
    required_labels: list[str] = Field(default_factory=list)


class AnnotationPlanItem(BaseModel):
    model_config = ConfigDict(extra="allow")

    type: str
    label: str
    target: str
    beat_id: str = "beat_0"
    layer: str = "renderer"


class AssetBounds(BaseModel):
    model_config = ConfigDict(extra="allow")

    x: int = Field(ge=0)
    y: int = Field(ge=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)


class SceneAssetContract(BaseModel):
    """Traceable relationship between a scene master and derived render assets."""
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    mode: str = Field(default="trace", pattern="^(trace|direct|full)$")
    master_asset: str | None = Field(default=None, alias="masterAsset")
    ink_asset: str | None = Field(default=None, alias="inkAsset")
    color_asset: str | None = Field(default=None, alias="colorAsset")
    text_asset: str | None = Field(default=None, alias="textAsset")
    width: int | None = Field(default=None, gt=0)
    height: int | None = Field(default=None, gt=0)
    source_hash: str | None = Field(default=None, alias="sourceHash")
    prompt_hash: str | None = Field(default=None, alias="promptHash")
    style_fingerprint: str | None = Field(default=None, alias="styleFingerprint")
    character_fingerprint: str | None = Field(default=None, alias="characterFingerprint")
    provider: str | None = None
    quality: str | None = None
    observed_content_bounds: AssetBounds | None = Field(default=None, alias="observedContentBounds")
    crop_confidence: float | None = Field(default=None, ge=0, le=1, alias="cropConfidence")
    layers: list[str] = Field(default_factory=lambda: ["ink", "color"])


class RenderRegion(BaseModel):
    """Integer canvas-space rectangle shared by preview and renderers."""
    model_config = ConfigDict(extra="allow")
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)


class RenderReveal(BaseModel):
    model_config = ConfigDict(extra="allow")
    start_ms: int = Field(default=0, ge=0, alias="startMs")
    duration_ms: int = Field(default=1000, gt=0, alias="durationMs")
    protected_regions: list[RenderRegion] = Field(default_factory=list, alias="protectedRegions")
    ink_weight: float = Field(default=2.0, gt=0)
    color_weight: float = Field(default=1.0, gt=0)

    model_config = ConfigDict(extra="allow", populate_by_name=True)


class RenderElement(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: str
    sequence: int = Field(ge=1)
    parallel_group: str | None = Field(default=None, alias="parallelGroup")
    narrative_role: str = Field(default="content", alias="narrativeRole")
    subtitle: str | None = None
    region: RenderRegion
    reveal: RenderReveal = Field(default_factory=RenderReveal)
    points: list[tuple[float, float]] = Field(default_factory=list)
    source: str = "authored"

    model_config = ConfigDict(extra="allow", populate_by_name=True)


class Scene(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    order: int
    title: str
    narration: str
    duration_estimate: float
    animations: list[AnimationInstruction] = Field(default_factory=list)
    node_ids: list[str] = Field(default_factory=list)
    image_description: str | None = None
    image_url: str | None = None
    learning_goal: str | None = None
    visual_beats: list[VisualBeat] = Field(default_factory=list)
    diagram_plan: DiagramPlan | None = None
    visual_mode: str | None = None
    teaching_density: str | None = None
    visual_anchor: str | None = None
    annotation_plan: list[AnnotationPlanItem] = Field(default_factory=list)
    render_strategy: str | None = None
    visual_complexity: str | None = None
    board_mode: str | None = None
    hand_usage: str | None = None
    video_style: str | None = None
    visual_style: str | None = None
    pen_style: str | None = None
    asset_contract: SceneAssetContract | None = Field(default=None, alias="assetContract")
    canvas_width: int = Field(default=1920, ge=1, alias="canvasWidth")
    canvas_height: int = Field(default=1080, ge=1, alias="canvasHeight")
    render_elements: list[RenderElement] = Field(default_factory=list, alias="renderElements")

    model_config = ConfigDict(extra="allow", populate_by_name=True)


class Storyboard(BaseModel):
    model_config = ConfigDict(extra="allow")

    topic: str
    total_duration_estimate: float
    scenes: list[Scene] = Field(default_factory=list)
    title_image_url: str | None = Field(default=None, alias="titleImageUrl")  # 标题卡片的主题插图
    video_style: str | None = None
    pen_style: str | None = None
    line_art_color_mode: str = Field(default="color", alias="lineArtColorMode")
    style_lock: str | None = Field(default=None, alias="styleLock")
    character_lock: str | None = Field(default=None, alias="characterLock")
    palette_id: str | None = Field(default=None, alias="paletteId")
    style_fingerprint: str | None = Field(default=None, alias="styleFingerprint")
    character_fingerprint: str | None = Field(default=None, alias="characterFingerprint")

    model_config = ConfigDict(extra="allow", populate_by_name=True)


class ValidateStoryboardRequest(BaseModel):
    storyboard: Storyboard
    fps: int = Field(default=30, ge=1, le=120)


class RenderContractIssueModel(BaseModel):
    code: str
    message: str
    severity: str
    scene_id: str | None = None
    element_id: str | None = None


class ValidateStoryboardResponse(BaseModel):
    ok: bool
    storyboard: Storyboard
    issues: list[RenderContractIssueModel]
    timelines: dict[str, list[dict]]
    snapshot: dict


class ParseSrtRequest(BaseModel):
    srt: str = Field(min_length=1)
    target_sec: float = Field(default=30.0, gt=0, le=300)
    min_sec: float = Field(default=25.0, gt=0, le=300)
    max_sec: float = Field(default=35.0, gt=0, le=300)


class ParseSrtResponse(BaseModel):
    cues: list[dict]
    scenes: list[dict]
    total_duration_ms: int = Field(alias="totalDurationMs")

    model_config = ConfigDict(populate_by_name=True)


class GenerateStoryboardRequest(BaseModel):
    graph: ExplainGraph
    target_duration: int = Field(default=120, ge=60, le=180)
    video_style: str = "whiteboard"
    pen_style: str = "marker"
    line_art_color_mode: str = Field(default="color", alias="lineArtColorMode")
    style_lock: str | None = Field(default=None, alias="styleLock")
    character_lock: str | None = Field(default=None, alias="characterLock")
    palette_id: str | None = Field(default=None, alias="paletteId")

    model_config = ConfigDict(populate_by_name=True)


class GenerateStoryboardResponse(BaseModel):
    storyboard: Storyboard


class GenerateRemotionCodeRequest(BaseModel):
    storyboard: Storyboard
    fps: int = Field(default=24, ge=24, le=60)
    width: int = Field(default=960, ge=640, le=3840)
    height: int = Field(default=540, ge=360, le=2160)
    style_prompt: str | None = None
    subtitles_enabled: bool = False
    background_music_url: str | None = None
    background_music_volume: float = Field(default=0.12, ge=0.0, le=0.5)


class GenerateRemotionCodeResponse(BaseModel):
    tsx: str
    duration_in_frames: int
    fps: int = 24
    width: int = 960
    height: int = 540
    notes: str | None = None
