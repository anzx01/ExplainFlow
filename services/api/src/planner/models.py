from enum import Enum
from pydantic import BaseModel, Field

from src.explain.models import ExplainGraph


class AnimationType(str, Enum):
    WHITEBOARD_DRAW = "whiteboard_draw"       # 白板手写文字
    FORMULA_REVEAL = "formula_reveal"         # 公式逐步展示
    CONCEPT_NODE = "concept_node"             # 概念节点出现
    ARROW_CONNECT = "arrow_connect"           # 箭头连接
    HIGHLIGHT = "highlight"                   # 高亮强调
    PARTICLE_FLOW = "particle_flow"           # 粒子流动
    NETWORK_LAYER = "network_layer"           # 神经网络层
    TEXT_NARRATION = "text_narration"         # 纯文字讲解


class AnimationInstruction(BaseModel):
    type: AnimationType
    duration: float = Field(default=2.0, ge=0.5, le=10.0)
    content: str                              # 文字内容或概念标签
    latex: str | None = None
    from_node: str | None = None             # 箭头起点
    to_node: str | None = None               # 箭头终点


class Scene(BaseModel):
    id: str
    order: int
    title: str
    narration: str                            # 旁白文案（中文）
    duration_estimate: float                  # 预估时长（秒）
    animations: list[AnimationInstruction] = Field(default_factory=list)
    node_ids: list[str] = Field(default_factory=list)  # 关联的 ExplainGraph 节点


class Storyboard(BaseModel):
    topic: str
    total_duration_estimate: float
    scenes: list[Scene] = Field(default_factory=list)


class GenerateStoryboardRequest(BaseModel):
    graph: ExplainGraph
    target_duration: int = Field(default=120, ge=60, le=180)  # 秒


class GenerateStoryboardResponse(BaseModel):
    storyboard: Storyboard
