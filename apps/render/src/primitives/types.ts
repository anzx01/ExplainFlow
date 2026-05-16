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

export const FPS = 30;
export const WIDTH = 1920;
export const HEIGHT = 1080;

// Khan Academy whiteboard color palette
export const COLORS = {
  bg: "#FAFAF7",
  chalk: "#1A1A1A",
  accent: "#1B6AC9",      // Khan blue
  green: "#1BAB1B",
  orange: "#D97706",
  purple: "#7C3AED",
  red: "#DC2626",
  gray: "#6B7280",
  highlight: "#FEF08A",
} as const;

export const FONT = {
  sans: "'Noto Sans SC', 'PingFang SC', sans-serif",
  mono: "'JetBrains Mono', 'Courier New', monospace",
} as const;
