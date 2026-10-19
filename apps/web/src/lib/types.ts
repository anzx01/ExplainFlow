export type VideoStyleId =
  | "auto"
  | "chalkboard_bw"
  | "chalkboard_color"
  | "modern_minimal"
  | "technical_blueprint"
  | "editorial"
  | "whiteboard"
  | "playful"
  | "sharpie"
  | "colorful_story"
  | "teacher_whiteboard"
  | "math_chalkboard"
  | "technical_reference"
  | "howto_demo";

export type PenStyleId = "no_hand" | "pen" | "marker" | "fountain_pen";
export type ImageGenerationMode = "sd15" | "flux";
export type LineArtColorMode = "color" | "monochrome";

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
  enhanced_brief?: EnhancedTeachingBrief | null;
}

export interface TeachingBriefSceneOutline {
  title: string;
  learning_goal: string;
  diagram_plan: string;
  must_draw: string[];
  narration_focus?: string | null;
}

export interface EnhancedTeachingBrief {
  original_prompt: string;
  audience_level: string;
  topic_type: string;
  learning_objectives: string[];
  core_explanation_chain: string[];
  must_include_points: string[];
  visual_metaphors: string[];
  recommended_scene_outline: TeachingBriefSceneOutline[];
  common_misconceptions: string[];
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

export interface VisualBeat {
  id?: string | null;
  draw_intent: string;
  narration: string;
  required_labels: string[];
  duration_estimate: number;
}

export interface DiagramPlan {
  kind: string;
  layout: string;
  required_labels: string[];
}

export type VisualMode = "trace" | "direct_reference" | "hybrid";

export type AnnotationPlanType =
  | "side_label"
  | "short_arrow"
  | "wavy_underline"
  | "edge_tick"
  | "risk_ray"
  | "checkmark"
  | "crossout"
  | "route_trace"
  | "labeled_zoom";

export interface AnnotationPlanItem {
  type: AnnotationPlanType | string;
  label: string;
  target: string;
  beat_id: string;
  layer: "renderer" | string;
}

export interface RenderRegion {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface RenderReveal {
  startMs: number;
  durationMs: number;
  protectedRegions: RenderRegion[];
  ink_weight?: number;
  color_weight?: number;
}

export interface RenderElement {
  id: string;
  sequence: number;
  parallelGroup?: string | null;
  narrativeRole?: string;
  subtitle?: string | null;
  region: RenderRegion;
  reveal: RenderReveal;
  points?: Array<[number, number]>;
  source?: "generated" | "authored" | string;
}

export interface AssetBounds {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface SceneAssetContract {
  mode: "trace" | "direct" | "full" | string;
  masterAsset?: string | null;
  inkAsset?: string | null;
  colorAsset?: string | null;
  textAsset?: string | null;
  width?: number | null;
  height?: number | null;
  sourceHash?: string | null;
  promptHash?: string | null;
  styleFingerprint?: string | null;
  characterFingerprint?: string | null;
  provider?: string | null;
  quality?: string | null;
  observedContentBounds?: AssetBounds | null;
  cropConfidence?: number | null;
  layers?: string[];
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
  reference_image_base64?: string | null;
  audioUrl?: string | null;
  learning_goal?: string | null;
  visual_beats?: VisualBeat[];
  diagram_plan?: DiagramPlan | null;
  visual_mode?: VisualMode | string | null;
  teaching_density?: "rich" | string | null;
  visual_anchor?: string | null;
  annotation_plan?: AnnotationPlanItem[];
  render_strategy?: string | null;
  visual_complexity?: string | null;
  board_mode?: string | null;
  hand_usage?: string | null;
  video_style?: VideoStyleId | string | null;
  visual_style?: string | null;
  pen_style?: PenStyleId | string | null;
  qa_fix_hint?: string | null;
  canvasWidth?: number;
  canvasHeight?: number;
  renderElements?: RenderElement[];
  assetContract?: SceneAssetContract | null;
}

export interface Storyboard {
  image_generation_mode?: ImageGenerationMode;
  line_art_color_mode?: LineArtColorMode;
  topic: string;
  total_duration_estimate: number;
  scenes: Scene[];
  video_style?: VideoStyleId | string | null;
  pen_style?: PenStyleId | string | null;
  style_lock?: string | null;
  character_lock?: string | null;
  palette_id?: string | null;
  style_fingerprint?: string | null;
  character_fingerprint?: string | null;
  titleImageUrl?: string | null;  // 标题卡片的主题插图
}

// ── Render Jobs ─────────────────────────────────────────────────
export interface RenderQaCheck {
  id: string;
  ok: boolean;
  severity: "info" | "warning" | "error" | string;
  message: string;
  details?: Record<string, unknown> | null;
  suggestion?: string | null;
}

export interface RenderQaResult {
  ok: boolean;
  checkedAt?: string | null;
  durationSeconds?: number | null;
  hasAudio?: boolean | null;
  fileSizeBytes?: number | null;
  checks: RenderQaCheck[];
  suggestions?: string[];
}

export interface RenderJobSummary {
  id: string;
  status: "processing" | "done" | "failed";
  progress: number;
  phase?: "queued" | "tts" | "imagegen" | "codegen" | "bundling" | "rendering" | "qa" | "done" | "failed" | null;
  topic: string | null;
  createdAt: string | null;
  actualDurationSeconds?: number | null;
  qa?: RenderQaResult | null;
  error: string | null;
  videoUrl?: string | null;
}

export interface AppSettingsView {
  saved: Record<string, unknown>;
  effective: {
    llm_base_url: string;
    llm_model: string;
    coder_model: string;
    imagegen_provider: string;
    imagegen_base_url: string;
    imagegen_model: string;
    cloud_text2video_base_url: string;
    cloud_text2video_model: string;
    local_text2image_available: boolean;
    local_text2video_base_url: string;
    local_text2video_model: string;
  };
}

export interface Text2VideoGenerateResult {
  ok: boolean;
  filename: string;
  videoUrl: string;
  sizeBytes: number;
  elapsedSeconds: number;
  baseUrl: string;
  model: string;
}

export interface Text2VideoTestResult {
  ok: boolean;
  baseUrl: string;
  probes: Array<{ path: string; status?: number; error?: string }>;
}

export interface RenderJobStatus {
  job_id: string;
  status: "processing" | "done" | "failed";
  progress: number;
  phase?: "queued" | "tts" | "imagegen" | "codegen" | "bundling" | "rendering" | "qa" | "done" | "failed" | null;
  video_url?: string | null;
  error?: string | null;
  createdAt?: string | null;
  actualDurationSeconds?: number | null;
  qa?: RenderQaResult | null;
}

export interface BackgroundMusicTrack {
  id: string;
  name: string;
  url: string;
  size: number;
}

export interface AuthUser {
  username: string;
  display_name: string | null;
  created_at: number | null;
}

export interface AuthResponse {
  token: string;
  user: AuthUser;
}
