/**
 * config.mjs — 所有常量与环境变量读取
 * 无外部依赖
 */
import { createServer as createNetServer } from "net";
import { existsSync, readdirSync, readFileSync } from "fs";
import { dirname, join, resolve } from "path";
import { fileURLToPath } from "url";
import { availableParallelism } from "os";

export const __dirname = dirname(fileURLToPath(import.meta.url));
export const PORT = Number(process.env.RENDER_PORT ?? 3001);
export const FPS = 30;
export const WIDTH = 1920;
export const HEIGHT = 1080;
export const OUTPUT_DIR = join(__dirname, "../../outputs");
export const AUDIO_DIR = join(OUTPUT_DIR, "audio");
export const MUSIC_DIR = resolve(process.env.EXPLAINFLOW_MUSIC_DIR ?? join(OUTPUT_DIR, "music"));
export const JOBS_FILE = join(OUTPUT_DIR, "jobs.json");
export const GENERATED_DIR = join(__dirname, "generated");
export const PUBLIC_DIR = join(__dirname, "public");
export const PUBLIC_GENERATED_DIR = join(PUBLIC_DIR, "generated");
export const PYTHON_API = process.env.PYTHON_API_URL ?? "http://localhost:8000";
export const COMPOSITION_ID = "GeneratedVideo";
export const STATIC_PORT_START = Number(process.env.REMOTION_STATIC_PORT ?? 3100);
export const DEFAULT_RENDER_CONCURRENCY = Math.min(8, Math.max(4, availableParallelism() - 2));
export const RENDER_CONCURRENCY = Number.isFinite(Number(process.env.REMOTION_CONCURRENCY))
  ? Math.max(1, Number(process.env.REMOTION_CONCURRENCY))
  : DEFAULT_RENDER_CONCURRENCY;
export const RENDER_CRF = Number.isFinite(Number(process.env.REMOTION_CRF))
  ? Math.max(1, Math.min(51, Number(process.env.REMOTION_CRF)))
  : 8;
export const RENDER_X264_PRESET = process.env.REMOTION_X264_PRESET || "slow";
export const RENDER_PIXEL_FORMAT = process.env.REMOTION_PIXEL_FORMAT || "yuv444p";
export const ENABLE_IMAGE_TRACE = process.env.REMOTION_IMAGE_TRACE !== "0";
export const SKIP_IMAGE_TRACE = process.env.SKIP_IMAGE_TRACE === "1";
export const ENABLE_SEEDREAM_REFERENCE_IMAGES = process.env.REMOTION_SEEDREAM_REFERENCES !== "0";
export const REQUIRE_SEEDREAM_REFERENCE_IMAGES = process.env.REMOTION_REQUIRE_SEEDREAM_REFERENCES !== "0";
export const SEEDREAM_REFERENCE_RENDER_MODE = String(process.env.REMOTION_SEEDREAM_REFERENCE_MODE ?? "auto")
  .trim()
  .toLowerCase();
export const IMAGE_TRACE_MAX_SCENES = Math.max(0, Number(process.env.REMOTION_IMAGE_TRACE_MAX_SCENES ?? 16));
export const IMAGE_TRACE_MAX_PATHS = Math.max(16, Number(process.env.REMOTION_IMAGE_TRACE_MAX_PATHS ?? 90));
export const RASTER_REVEAL_MAX_STROKES = Math.max(
  24,
  Number(process.env.REMOTION_RASTER_REVEAL_MAX_STROKES ?? 150),
);
export const RASTER_REVEAL_TRACE_WIDTH = Math.max(
  240,
  Number(process.env.REMOTION_RASTER_REVEAL_TRACE_WIDTH ?? 960),
);
export const RASTER_REVEAL_TRACE_HEIGHT = Math.max(
  180,
  Number(process.env.REMOTION_RASTER_REVEAL_TRACE_HEIGHT ?? 540),
);
export const RASTER_REVEAL_ASSET_MAX_SIZE = Math.max(
  640,
  Number(process.env.REMOTION_RASTER_REVEAL_ASSET_MAX_SIZE ?? 896),
);
export const DIRECT_IMAGE_STROKE_THRESHOLD = Math.max(
  40,
  Number(process.env.REMOTION_DIRECT_IMAGE_STROKE_THRESHOLD ?? 280),
);
export const HAND_ASSET = "hand-real-pen.png";
export const MIN_RENDER_OUTPUT_BYTES = Math.max(1024, Number(process.env.RENDER_QA_MIN_BYTES ?? 50000) || 50000);
export const MIN_RENDER_FRAME_STDDEV = Math.max(0.5, Number(process.env.RENDER_QA_MIN_FRAME_STDDEV ?? 2.5) || 2.5);
export const SCENE_PREROLL_FRAMES = Math.max(0, Math.min(90, Number(process.env.SCENE_PREROLL_FRAMES ?? 0) || 0));
export const BEAT_AUDIO_LEAD_FRAMES = Math.max(0, Math.min(36, Number(process.env.BEAT_AUDIO_LEAD_FRAMES ?? 8) || 8));
export const MUSIC_EXTENSIONS = new Set([".mp3", ".wav", ".m4a", ".aac", ".ogg", ".webm"]);
export const MUSIC_MIME_TYPES = new Map([
  [".mp3", "audio/mpeg"],
  [".wav", "audio/wav"],
  [".m4a", "audio/mp4"],
  [".aac", "audio/aac"],
  [".ogg", "audio/ogg"],
  [".webm", "audio/webm"],
]);
export const GLYPH_FONT_CANDIDATES = [
  process.env.EXPLAINFLOW_GLYPH_FONT,
  "C:\\Windows\\Fonts\\simkai.ttf",
  "C:\\Windows\\Fonts\\simfang.ttf",
  "C:\\Windows\\Fonts\\msyh.ttc",
  "C:\\Windows\\Fonts\\simsun.ttc",
].filter(Boolean);
export const LATIN_GLYPH_FONT_CANDIDATES = [
  process.env.EXPLAINFLOW_LATIN_GLYPH_FONT,
  "C:\\Windows\\Fonts\\Inkfree.ttf",
  "C:\\Windows\\Fonts\\segoepr.ttf",
  "C:\\Windows\\Fonts\\comic.ttf",
].filter(Boolean);
export const TTS_CONCURRENCY = Math.max(1, Math.min(2, Number(process.env.TTS_CONCURRENCY ?? 1) || 1));
export const TTS_MAX_ATTEMPTS = Math.max(1, Math.min(5, Number(process.env.TTS_MAX_ATTEMPTS ?? 4) || 4));
export const ENABLE_ALL_STYLE_OPTIONS = process.env.EXPLAINFLOW_ENABLE_ALL_STYLES === "1";

// ffprobe/ffmpeg/chrome — 路径发现

function firstExistingPath(paths) {
  return paths.find((candidate) => candidate && existsSync(candidate)) || "";
}

function findWingetFfmpegBinary(binaryName) {
  const packagesDir = join(process.env.LOCALAPPDATA || "", "Microsoft", "WinGet", "Packages");
  if (!packagesDir || !existsSync(packagesDir)) return null;
  try {
    for (const entry of readdirSync(packagesDir)) {
      if (!entry.startsWith("Gyan.FFmpeg_")) continue;
      const packageDir = join(packagesDir, entry);
      for (const child of readdirSync(packageDir)) {
        const candidate = join(packageDir, child, "bin", `${binaryName}.exe`);
        if (existsSync(candidate)) return candidate;
      }
    }
  } catch {
    return null;
  }
  return null;
}

function findPlaywrightChrome() {
  const localAppData = process.env.LOCALAPPDATA || "";
  if (!localAppData) return "";
  const playwrightDir = join(localAppData, "ms-playwright");
  if (!existsSync(playwrightDir)) return "";
  try {
    for (const entry of readdirSync(playwrightDir)) {
      if (!entry.startsWith("chromium")) continue;
      const candidate = join(
        playwrightDir,
        entry,
        "chrome-headless-shell-win64",
        "chrome-headless-shell.exe",
      );
      if (existsSync(candidate)) return candidate;
    }
  } catch {
    return "";
  }
  return "";
}

export const BROWSER_EXECUTABLE = firstExistingPath([
  process.env.REMOTION_CHROME_HEADLESS_SHELL,
  findPlaywrightChrome(),
  "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
  "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
]);
export const FFPROBE_BINARY = process.env.FFPROBE_PATH || findWingetFfmpegBinary("ffprobe") || "ffprobe";
export const FFMPEG_BINARY = process.env.FFMPEG_PATH || findWingetFfmpegBinary("ffmpeg") || "ffmpeg";

// 样式配置（需要在此处加载，因为后续常量依赖它们）

function loadGolpoStyleConfig() {
  const fallback = {
    video_style_order: [
      "chalkboard_bw",
      "chalkboard_color",
      "modern_minimal",
      "technical_blueprint",
      "editorial",
      "whiteboard",
      "playful",
      "sharpie",
    ],
    aliases: {
      colorful_story: "whiteboard",
      teacher_whiteboard: "whiteboard",
      howto_demo: "whiteboard",
      math_chalkboard: "chalkboard_color",
      technical_reference: "technical_blueprint",
      whiteboard_bw: "whiteboard",
      whiteboard_color: "whiteboard",
      sharpie_bw: "sharpie",
      sharpie_color: "sharpie",
      editorial_blue: "editorial",
      editorial_paper: "editorial",
      chalkboard_black_white: "chalkboard_bw",
      technical: "technical_blueprint",
    },
  };
  try {
    const configPath = resolve(__dirname, "../../services/api/src/core/golpo_styles.json");
    return JSON.parse(readFileSync(configPath, "utf8"));
  } catch (err) {
    console.warn("[style] Failed to load shared Golpo style config:", err.message);
    return fallback;
  }
}

function loadVisualTeachingRules() {
  const fallback = {
    version: 1,
    active_style: "whiteboard",
    active_pen_style: "marker",
    teaching_feel: "illustrated_tutorial_handdrawn",
    mode_policy: { default_density: "rich" },
    annotation_templates: [
      { type: "side_label" },
      { type: "short_arrow" },
      { type: "wavy_underline" },
      { type: "edge_tick" },
      { type: "risk_ray" },
      { type: "checkmark" },
      { type: "crossout" },
      { type: "route_trace" },
      { type: "labeled_zoom" },
    ],
  };
  try {
    const rulesPath = resolve(__dirname, "../../services/api/src/core/visual_teaching_rules.json");
    return JSON.parse(readFileSync(rulesPath, "utf8"));
  } catch (err) {
    console.warn("[style] Failed to load visual teaching rules:", err.message);
    return fallback;
  }
}

export const GOLPO_STYLE_CONFIG = loadGolpoStyleConfig();
export const VISUAL_TEACHING_RULES = loadVisualTeachingRules();
export const ACTIVE_VIDEO_STYLE = String(VISUAL_TEACHING_RULES.active_style || "whiteboard");
export const ACTIVE_PEN_STYLE = String(VISUAL_TEACHING_RULES.active_pen_style || "marker");
export const VIDEO_STYLE_ALIASES = new Map(Object.entries(GOLPO_STYLE_CONFIG.aliases ?? {}));
export const GOLPO_VIDEO_STYLES = new Set(GOLPO_STYLE_CONFIG.video_style_order ?? [
  "chalkboard_bw",
  "chalkboard_color",
  "modern_minimal",
  "technical_blueprint",
  "editorial",
  "whiteboard",
  "playful",
  "sharpie",
]);
