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


class Storyboard(BaseModel):
    model_config = ConfigDict(extra="allow")

    topic: str
    total_duration_estimate: float
    scenes: list[Scene] = Field(default_factory=list)


class GenerateStoryboardRequest(BaseModel):
    graph: ExplainGraph
    target_duration: int = Field(default=120, ge=60, le=180)


class GenerateStoryboardResponse(BaseModel):
    storyboard: Storyboard


class GenerateRemotionCodeRequest(BaseModel):
    storyboard: Storyboard
    fps: int = Field(default=30, ge=24, le=60)
    width: int = Field(default=1920, ge=640, le=3840)
    height: int = Field(default=1080, ge=360, le=2160)
    style_prompt: str | None = None
    subtitles_enabled: bool = False
    background_music_url: str | None = None
    background_music_volume: float = Field(default=0.12, ge=0.0, le=0.5)


class GenerateRemotionCodeResponse(BaseModel):
    tsx: str
    duration_in_frames: int
    fps: int = 30
    width: int = 1920
    height: int = 1080
    notes: str | None = None
