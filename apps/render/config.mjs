/**
 * config.mjs — 所有常量与环境变量读取
 * 无外部依赖
 */
import { existsSync, readdirSync, readFileSync } from "fs";
import { delimiter, dirname, extname, isAbsolute, join, relative, resolve, sep } from "path";
import { fileURLToPath } from "url";
import { availableParallelism, homedir } from "os";

export const __dirname = dirname(fileURLToPath(import.meta.url));
export const ROOT_DIR = resolve(__dirname, "../..");

const LOCKED_ENV_KEYS = new Set(Object.keys(process.env));

function parseEnvValue(rawValue) {
  let value = String(rawValue ?? "").trim();
  if (!value) return "";
  const quote = value[0];
  if ((quote === "\"" || quote === "'") && value.endsWith(quote)) {
    value = value.slice(1, -1);
    return quote === "\""
      ? value.replace(/\\n/g, "\n").replace(/\\r/g, "\r").replace(/\\t/g, "\t")
      : value;
  }
  return value.replace(/\s+#.*$/, "").trim();
}

function loadEnvFile(envPath, { overrideLoaded = false } = {}) {
  if (!existsSync(envPath)) return;
  try {
    for (const line of readFileSync(envPath, "utf8").split(/\r?\n/)) {
      const match = line.match(/^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$/);
      if (!match) continue;
      const [, key, rawValue] = match;
      if (LOCKED_ENV_KEYS.has(key)) continue;
      if (!overrideLoaded && process.env[key] !== undefined) continue;
      process.env[key] = parseEnvValue(rawValue);
    }
  } catch (err) {
    console.warn(`[env] Failed to load ${envPath}:`, err.message);
  }
}

loadEnvFile(join(ROOT_DIR, ".env"));
loadEnvFile(join(__dirname, ".env"), { overrideLoaded: true });
loadEnvFile(join(__dirname, ".env.local"), { overrideLoaded: true });

function configuredPath(value) {
  const raw = String(value ?? "").trim();
  if (!raw) return "";
  return isAbsolute(raw) ? raw : resolve(ROOT_DIR, raw);
}

function configuredPathList(envName) {
  return String(process.env[envName] ?? "")
    .split(delimiter)
    .map((value) => configuredPath(value))
    .filter(Boolean);
}

function resolveConfiguredPath(value, fallback) {
  return configuredPath(value) || fallback;
}

function isInsidePath(child, parent) {
  const rel = relative(resolve(parent), resolve(child));
  return rel === "" || (!!rel && rel !== ".." && !rel.startsWith(`..${sep}`) && !isAbsolute(rel));
}

export const PORT = Number(process.env.RENDER_PORT ?? 3001);
export const FPS = 30;
export const WIDTH = 1920;
export const HEIGHT = 1080;
export const OUTPUT_DIR = resolveConfiguredPath(process.env.EXPLAINFLOW_OUTPUT_DIR, join(ROOT_DIR, "outputs"));
export const AUDIO_DIR = join(OUTPUT_DIR, "audio");
export const MUSIC_DIR = resolveConfiguredPath(process.env.EXPLAINFLOW_MUSIC_DIR, join(OUTPUT_DIR, "music"));
export const JOBS_FILE = join(OUTPUT_DIR, "jobs.json");
export const GENERATED_DIR = resolveConfiguredPath(process.env.EXPLAINFLOW_RENDER_GENERATED_DIR, join(__dirname, "generated"));
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
function windowsFontCandidates(names) {
  if (process.platform !== "win32") return [];
  const windowsDir = process.env.WINDIR || process.env.SystemRoot;
  return windowsDir ? names.map((name) => join(windowsDir, "Fonts", name)) : [];
}

function platformFontCandidates() {
  return [
    ...windowsFontCandidates(["simkai.ttf", "simfang.ttf", "msyh.ttc", "simsun.ttc"]),
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/STHeiti Light.ttc",
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/Library/Fonts/Arial Unicode.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJKsc-Regular.otf",
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    "/usr/share/fonts/truetype/arphic/uming.ttc",
  ];
}

function platformLatinFontCandidates() {
  return [
    ...windowsFontCandidates(["Inkfree.ttf", "segoepr.ttf", "comic.ttf"]),
    "/System/Library/Fonts/Supplemental/Comic Sans MS.ttf",
    "/System/Library/Fonts/Supplemental/Bradley Hand Bold.ttf",
    "/Library/Fonts/Comic Sans MS.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
  ];
}

export const GLYPH_FONT_CANDIDATES = [
  configuredPath(process.env.EXPLAINFLOW_GLYPH_FONT),
  ...configuredPathList("EXPLAINFLOW_GLYPH_FONTS"),
  ...platformFontCandidates(),
].filter(Boolean);
export const LATIN_GLYPH_FONT_CANDIDATES = [
  configuredPath(process.env.EXPLAINFLOW_LATIN_GLYPH_FONT),
  ...configuredPathList("EXPLAINFLOW_LATIN_GLYPH_FONTS"),
  ...platformLatinFontCandidates(),
].filter(Boolean);
export const TTS_CONCURRENCY = Math.max(1, Math.min(2, Number(process.env.TTS_CONCURRENCY ?? 1) || 1));
export const TTS_MAX_ATTEMPTS = Math.max(1, Math.min(5, Number(process.env.TTS_MAX_ATTEMPTS ?? 4) || 4));
export const ENABLE_ALL_STYLE_OPTIONS = process.env.EXPLAINFLOW_ENABLE_ALL_STYLES === "1";

// ffprobe/ffmpeg/chrome — 路径发现

function firstExistingPath(paths) {
  return paths.find((candidate) => candidate && existsSync(candidate)) || "";
}

function uniquePaths(paths) {
  const seen = new Set();
  return paths.filter((candidate) => {
    if (!candidate || seen.has(candidate)) return false;
    seen.add(candidate);
    return true;
  });
}

function findExecutableOnPath(command) {
  const raw = String(command ?? "").trim();
  if (!raw) return "";
  if (raw.includes("/") || raw.includes("\\") || isAbsolute(raw)) {
    const candidate = configuredPath(raw);
    return existsSync(candidate) ? candidate : "";
  }
  const extensions = process.platform === "win32" && !extname(raw)
    ? String(process.env.PATHEXT || ".EXE;.CMD;.BAT;.COM").split(";")
    : [""];
  for (const dir of String(process.env.PATH || "").split(delimiter)) {
    if (!dir) continue;
    for (const ext of extensions) {
      const candidate = join(dir, `${raw}${ext}`);
      if (existsSync(candidate)) return candidate;
    }
  }
  return "";
}

function configuredExecutable(value) {
  const raw = String(value ?? "").trim();
  if (!raw) return "";
  if (raw.includes("/") || raw.includes("\\") || isAbsolute(raw)) {
    const candidate = configuredPath(raw);
    return existsSync(candidate) ? candidate : "";
  }
  return findExecutableOnPath(raw);
}

function findWingetFfmpegBinary(binaryName) {
  if (process.platform !== "win32") return null;
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

function playwrightBrowserRoots() {
  const roots = [];
  const configured = process.env.PLAYWRIGHT_BROWSERS_PATH;
  if (configured && configured !== "0") roots.push(configuredPath(configured));
  if (configured === "0") {
    roots.push(join(__dirname, "node_modules", "playwright-core", ".local-browsers"));
    roots.push(join(__dirname, "node_modules", "playwright", ".local-browsers"));
  }
  if (process.env.LOCALAPPDATA) roots.push(join(process.env.LOCALAPPDATA, "ms-playwright"));
  const home = homedir();
  if (home) {
    roots.push(join(home, "Library", "Caches", "ms-playwright"));
    roots.push(join(home, ".cache", "ms-playwright"));
  }
  return uniquePaths(roots).filter((root) => root && existsSync(root));
}

function playwrightExecutableCandidates(playwrightDir) {
  const candidates = [];
  try {
    for (const entry of readdirSync(playwrightDir)) {
      if (!entry.startsWith("chromium")) continue;
      const browserDir = join(playwrightDir, entry);
      candidates.push(
        join(browserDir, "chrome-headless-shell-win64", "chrome-headless-shell.exe"),
        join(browserDir, "chrome-headless-shell-linux64", "chrome-headless-shell"),
        join(browserDir, "chrome-headless-shell-mac-arm64", "chrome-headless-shell"),
        join(browserDir, "chrome-headless-shell-mac-x64", "chrome-headless-shell"),
        join(browserDir, "chrome-win", "chrome.exe"),
        join(browserDir, "chrome-linux", "chrome"),
        join(browserDir, "chrome-mac", "Chromium.app", "Contents", "MacOS", "Chromium"),
      );
    }
  } catch {
    return [];
  }
  return candidates;
}

function findNestedBrowserExecutable(root, maxDepth = 5) {
  const executableNames = new Set(
    process.platform === "win32"
      ? ["chrome-headless-shell.exe", "chrome.exe", "msedge.exe"]
      : ["chrome-headless-shell", "chrome", "Chromium", "Google Chrome", "Microsoft Edge"],
  );
  const stack = [{ dir: root, depth: 0 }];
  while (stack.length > 0) {
    const { dir, depth } = stack.pop();
    let entries = [];
    try {
      entries = readdirSync(dir, { withFileTypes: true });
    } catch {
      continue;
    }
    for (const entry of entries) {
      const candidate = join(dir, entry.name);
      if (entry.isFile() && executableNames.has(entry.name)) return candidate;
      if (entry.isDirectory() && depth < maxDepth && isInsidePath(candidate, root)) {
        stack.push({ dir: candidate, depth: depth + 1 });
      }
    }
  }
  return "";
}

function findPlaywrightChrome() {
  for (const root of playwrightBrowserRoots()) {
    const candidate = firstExistingPath(playwrightExecutableCandidates(root));
    if (candidate) return candidate;
    const nested = findNestedBrowserExecutable(root);
    if (nested) return nested;
  }
  return "";
}

function systemBrowserCandidates() {
  if (process.platform === "win32") {
    return [
      process.env.PROGRAMFILES && join(process.env.PROGRAMFILES, "Google", "Chrome", "Application", "chrome.exe"),
      process.env["PROGRAMFILES(X86)"] && join(process.env["PROGRAMFILES(X86)"], "Google", "Chrome", "Application", "chrome.exe"),
      process.env.LOCALAPPDATA && join(process.env.LOCALAPPDATA, "Google", "Chrome", "Application", "chrome.exe"),
      process.env.PROGRAMFILES && join(process.env.PROGRAMFILES, "Microsoft", "Edge", "Application", "msedge.exe"),
      process.env["PROGRAMFILES(X86)"] && join(process.env["PROGRAMFILES(X86)"], "Microsoft", "Edge", "Application", "msedge.exe"),
    ].filter(Boolean);
  }
  if (process.platform === "darwin") {
    return [
      "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
      "/Applications/Chromium.app/Contents/MacOS/Chromium",
      "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    ];
  }
  return [
    "/usr/bin/google-chrome-stable",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
    "/snap/bin/chromium",
  ];
}

export const BROWSER_EXECUTABLE = firstExistingPath([
  configuredExecutable(process.env.REMOTION_BROWSER_EXECUTABLE),
  configuredExecutable(process.env.REMOTION_CHROME_HEADLESS_SHELL),
  configuredExecutable(process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH),
  configuredExecutable(process.env.CHROME_PATH),
  configuredExecutable(process.env.GOOGLE_CHROME_BIN),
  findPlaywrightChrome(),
  ...systemBrowserCandidates(),
  findExecutableOnPath("google-chrome-stable"),
  findExecutableOnPath("google-chrome"),
  findExecutableOnPath("chromium"),
  findExecutableOnPath("chromium-browser"),
  findExecutableOnPath("chrome"),
  findExecutableOnPath("msedge"),
]);
export const FFPROBE_BINARY = configuredExecutable(process.env.FFPROBE_PATH) || findWingetFfmpegBinary("ffprobe") || findExecutableOnPath("ffprobe") || "ffprobe";
export const FFMPEG_BINARY = configuredExecutable(process.env.FFMPEG_PATH) || findWingetFfmpegBinary("ffmpeg") || findExecutableOnPath("ffmpeg") || "ffmpeg";

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
