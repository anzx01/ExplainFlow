from enum import Enum
from pydantic import BaseModel, ConfigDict, Field


class NodeType(str, Enum):
    CONCEPT = "concept"
    FORMULA = "formula"
    EXAMPLE = "example"
    CONCLUSION = "conclusion"
    PROCESS = "process"


class ConceptNode(BaseModel):
    id: str
    label: str
    node_type: NodeType = NodeType.CONCEPT
    description: str
    latex: str | None = None
    teach_order: int = 0


class ConceptEdge(BaseModel):
    source: str
    target: str
    relation: str


class TeachingBriefSceneOutline(BaseModel):
    model_config = ConfigDict(extra="allow")

    title: str
    learning_goal: str
    diagram_plan: str
    must_draw: list[str] = Field(default_factory=list)
    narration_focus: str | None = None


class EnhancedTeachingBrief(BaseModel):
    model_config = ConfigDict(extra="allow")

    original_prompt: str
    audience_level: str = "有高中/大学基础理科知识的初学者"
    topic_type: str = "technical_explanation"
    learning_objectives: list[str] = Field(default_factory=list)
    core_explanation_chain: list[str] = Field(default_factory=list)
    must_include_points: list[str] = Field(default_factory=list)
    visual_metaphors: list[str] = Field(default_factory=list)
    recommended_scene_outline: list[TeachingBriefSceneOutline] = Field(default_factory=list)
    common_misconceptions: list[str] = Field(default_factory=list)


class ExplainGraph(BaseModel):
    topic: str
    summary: str
    nodes: list[ConceptNode] = Field(default_factory=list)
    edges: list[ConceptEdge] = Field(default_factory=list)
    key_insights: list[str] = Field(default_factory=list)
    enhanced_brief: EnhancedTeachingBrief | None = None


class GenerateGraphRequest(BaseModel):
    prompt: str = Field(..., min_length=5, max_length=2000)
    markdown: str | None = None


class GenerateGraphResponse(BaseModel):
    graph: ExplainGraph
