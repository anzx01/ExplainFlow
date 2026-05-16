from enum import Enum
from pydantic import BaseModel, ConfigDict, Field

from src.explain.models import ExplainGraph


class AnimationType(str, Enum):
    # 新动画类型
    WRITE_TEXT = "write_text"             # 逐字手写文本
    WRITE_FORMULA = "write_formula"       # 公式逐步显现
    DRAW_ARROW = "draw_arrow"             # 画箭头
    DRAW_BOX = "draw_box"                 # 画矩形框
    CONCEPT_BUBBLE = "concept_bubble"     # 概念气泡
    BULLET_LIST = "bullet_list"           # 要点列表
    STEP_REVEAL = "step_reveal"           # 步骤揭示
    HIGHLIGHT_REGION = "highlight_region" # 黄色高亮区域
    # 向后兼容别名
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
    items: list[str] | None = None   # bullet_list / step_reveal 条目


class Scene(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    order: int
    title: str
    narration: str
    duration_estimate: float
    animations: list[AnimationInstruction] = Field(default_factory=list)
    node_ids: list[str] = Field(default_factory=list)
    image_description: str | None = None  # 英文，描述该场景要生成的插图内容
    image_url: str | None = None          # Seedream 生成后注入


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


class GenerateRemotionCodeResponse(BaseModel):
    tsx: str
    duration_in_frames: int
    fps: int = 30
    width: int = 1920
    height: int = 1080
    notes: str | None = None
