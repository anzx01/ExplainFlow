import type { PenStyleId, VideoStyleId } from "./types";

export const RENDER_URL = process.env.NEXT_PUBLIC_RENDER_URL ?? "http://localhost:3001";

export interface VideoStyleOption {
  id: VideoStyleId;
  label: string;
  fit: string;
  swatch: string;
  tone: string;
}

export const VIDEO_STYLE_OPTIONS: VideoStyleOption[] = [
  {
    id: "chalkboard_bw",
    label: "Chalkboard B/W",
    fit: "黑白粉笔、概念",
    swatch: "bg-zinc-200",
    tone: "黑板黑白",
  },
  {
    id: "chalkboard_color",
    label: "Chalkboard Color",
    fit: "彩色粉笔、故事",
    swatch: "bg-yellow-300",
    tone: "黑板彩色",
  },
  {
    id: "modern_minimal",
    label: "Modern Minimal",
    fit: "商务、课程摘要",
    swatch: "bg-sky-400",
    tone: "现代极简",
  },
  {
    id: "technical_blueprint",
    label: "Technical",
    fit: "结构、工程、器件",
    swatch: "bg-blue-500",
    tone: "技术蓝图",
  },
  {
    id: "editorial",
    label: "Editorial",
    fit: "商业、品牌、观点",
    swatch: "bg-orange-500",
    tone: "编辑叙事",
  },
  {
    id: "whiteboard",
    label: "Whiteboard",
    fit: "图文并茂、教程",
    swatch: "bg-emerald-400",
    tone: "白板手绘",
  },
  {
    id: "playful",
    label: "Playful",
    fit: "儿童、轻松、类比",
    swatch: "bg-pink-400",
    tone: "彩色趣味",
  },
  {
    id: "sharpie",
    label: "Sharpie",
    fit: "醒目标注、营销",
    swatch: "bg-cyan-400",
    tone: "Sharpie 手绘",
  },
];

export interface PenStyleOption {
  id: PenStyleId;
  label: string;
  fit: string;
}

export const PEN_STYLE_OPTIONS: PenStyleOption[] = [
  {
    id: "marker",
    label: "Marker",
    fit: "粗线、强调、白板",
  },
  {
    id: "pen",
    label: "Pen Style",
    fit: "细线、草图、说明",
  },
  {
    id: "fountain_pen",
    label: "Stylus",
    fit: "书写、纸面、编辑",
  },
  {
    id: "no_hand",
    label: "No Hand",
    fit: "黑板/极简显现",
  },
];

export function videoStyleLabel(style: VideoStyleId | string | null | undefined) {
  const legacy: Record<string, string> = {
    colorful_story: "Whiteboard",
    teacher_whiteboard: "Whiteboard",
    math_chalkboard: "Chalkboard Color",
    technical_reference: "Technical",
    howto_demo: "Whiteboard",
    editorial_blue: "Editorial",
    editorial_paper: "Editorial",
    whiteboard_bw: "Whiteboard",
    whiteboard_color: "Whiteboard",
    sharpie_color: "Sharpie",
    sharpie_bw: "Sharpie",
  };
  return VIDEO_STYLE_OPTIONS.find((option) => option.id === style)?.label ?? legacy[String(style ?? "")] ?? "智能推荐";
}

export function penStyleLabel(style: PenStyleId | string | null | undefined) {
  return PEN_STYLE_OPTIONS.find((option) => option.id === style)?.label ?? "Marker";
}
