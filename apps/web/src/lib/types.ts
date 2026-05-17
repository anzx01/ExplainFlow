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
  | "write_title"
  | "write_text"
  | "write_formula"
  | "draw_arrow"
  | "draw_box"
  | "concept_bubble"
  | "bullet_list"
  | "step_reveal"
  | "highlight_region"
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
  x?: number | null;
  y?: number | null;
  items?: string[] | null;
}

export interface Scene {
  id: string;
  order: number;
  title: string;
  narration: string;
  duration_estimate: number;
  animations: AnimationInstruction[];
  node_ids: string[];
  image_description?: string | null;
  image_url?: string | null;
  imageUrl?: string | null;
  audioUrl?: string | null;
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
  phase?: "queued" | "tts" | "imagegen" | "codegen" | "bundling" | "rendering" | "done" | null;
  topic: string | null;
  createdAt: string | null;
  error: string | null;
}

export interface RenderJobStatus {
  job_id: string;
  status: "processing" | "done" | "failed";
  progress: number;
  phase?: "queued" | "tts" | "imagegen" | "codegen" | "bundling" | "rendering" | "done" | null;
  video_url?: string | null;
  error?: string | null;
  createdAt?: string | null;
}
