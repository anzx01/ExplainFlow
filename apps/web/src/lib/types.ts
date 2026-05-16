// ── Explain Graph ──────────────────────────────────────────────
export type NodeType = "concept" | "formula" | "example" | "conclusion" | "process";

export interface ConceptNode {
  id: string;
  label: string;
  node_type: NodeType;
  description: string;
  latex?: string | null;
  teach_order: number;
}

export interface ConceptEdge {
  source: string;
  target: string;
  relation: string;
}

export interface ExplainGraph {
  topic: string;
  summary: string;
  nodes: ConceptNode[];
  edges: ConceptEdge[];
  key_insights: string[];
}

// ── Storyboard ─────────────────────────────────────────────────
export type AnimationType =
  | "whiteboard_draw"
  | "formula_reveal"
  | "concept_node"
  | "arrow_connect"
  | "highlight"
  | "particle_flow"
  | "network_layer"
  | "text_narration";

export interface AnimationInstruction {
  type: AnimationType;
  duration: number;
  content: string;
  latex?: string | null;
  from_node?: string | null;
  to_node?: string | null;
}

export interface Scene {
  id: string;
  order: number;
  title: string;
  narration: string;
  duration_estimate: number;
  animations: AnimationInstruction[];
  node_ids: string[];
}

export interface Storyboard {
  topic: string;
  total_duration_estimate: number;
  scenes: Scene[];
}

// ── Render Jobs ─────────────────────────────────────────────────
export interface RenderJobSummary {
  id: string;
  status: "processing" | "done" | "failed";
  progress: number;
  topic: string | null;
  createdAt: string | null;
  error: string | null;
}
