from enum import Enum
from pydantic import BaseModel, Field


class NodeType(str, Enum):
    CONCEPT = "concept"       # 核心概念
    FORMULA = "formula"       # 数学公式
    EXAMPLE = "example"       # 具体示例
    CONCLUSION = "conclusion" # 结论/总结
    PROCESS = "process"       # 过程/步骤


class ConceptNode(BaseModel):
    id: str
    label: str                        # 显示名称
    node_type: NodeType = NodeType.CONCEPT
    description: str                  # 一句话说明
    latex: str | None = None          # 公式（可选）
    teach_order: int = 0              # 教学顺序


class ConceptEdge(BaseModel):
    source: str
    target: str
    relation: str                     # 关系描述，如"依赖于"、"推导出"


class ExplainGraph(BaseModel):
    topic: str
    summary: str                      # 本次讲解的一句话总结
    nodes: list[ConceptNode] = Field(default_factory=list)
    edges: list[ConceptEdge] = Field(default_factory=list)
    key_insights: list[str] = Field(default_factory=list)  # 3-5条核心洞察


class GenerateGraphRequest(BaseModel):
    prompt: str = Field(..., min_length=5, max_length=2000)
    markdown: str | None = None


class GenerateGraphResponse(BaseModel):
    graph: ExplainGraph
