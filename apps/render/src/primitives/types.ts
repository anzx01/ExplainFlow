export type AnimationType =
  | "write_title"       // 大标题手写（带下划线）
  | "write_text"        // 正文手写文本
  | "write_formula"     // 公式手写（monospace，带矩形框）
  | "draw_arrow"        // 画箭头
  | "draw_box"          // 画矩形框
  | "draw_underline"    // 画下划线（高亮关键词）
  | "concept_bubble"    // 概念气泡（彩色边框卡片）
  | "bullet_list"       // 要点列表逐条出现
  | "step_reveal"       // 步骤编号依次显现
  | "highlight_word"    // 彩色文字强调（如 STRONGER 红色）
  // legacy aliases
  | "whiteboard_draw"
  | "formula_reveal"
  | "concept_node"
  | "arrow_connect"
  | "text_narration"
  | "highlight"
  | "highlight_region"
  | "particle_flow"
  | "network_layer";

/** server.mjs 用 opentype.js 预处理后注入的 SVG 路径数据 */
export interface SvgTextPath {
  d: string;
  bbox: { x1: number; y1: number; x2: number; y2: number };
  width: number;
}

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
  color?: string | null;
  // 由 server.mjs injectTextPaths() 注入
  svgPath?: SvgTextPath | null;
  latexSvgPath?: SvgTextPath | null;
  itemPaths?: (SvgTextPath | null)[] | null;
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

export interface Scene {
  id: string;
  order: number;
  title: string;
  narration: string;
  duration_estimate: number;
  animations: AnimationInstruction[];
  node_ids: string[];
  audioUrl?: string | null;
  imageUrl?: string | null;
  image_description?: string | null;
  learning_goal?: string | null;
  visual_beats?: VisualBeat[];
  diagram_plan?: DiagramPlan | null;
  // 由 server.mjs injectTextPaths() 注入
  titlePath?: SvgTextPath | null;
}

export interface Storyboard {
  topic: string;
  total_duration_estimate: number;
  scenes: Scene[];
}

export const FPS = 30;
export const WIDTH = 1920;
export const HEIGHT = 1080;

export const COLORS = {
  bg: "#FDFCF8",
  ink: "#1A1A1A",
  inkLight: "#3A3A3A",
  red: "#E63946",
  blue: "#1D6FA4",
  orange: "#F4813A",
  green: "#2D9E5F",
  purple: "#7B4FBF",
  yellow: "#F5C842",
  lineGray: "#C8C4BC",
  shadow: "rgba(0,0,0,0.07)",
} as const;

export const FONT = {
  handwriting: "'Caveat', 'Comic Sans MS', cursive",
  mono: "'JetBrains Mono', 'Courier New', monospace",
  sans: "'Noto Sans SC', 'PingFang SC', sans-serif",
} as const;
