/**
 * ExplainFlow Render Server
 *
 * Runtime model:
 * Storyboard -> cached TTS audio -> validated Remotion TSX -> per-job bundle -> MP4.
 *
 * The generated TSX must be self-contained and may only import from React and
 * Remotion. It must not import the old local primitive/component library.
 */
import http from "http";
import { execFile } from "child_process";
import { createServer as createNetServer } from "net";
import {
  createReadStream,
  existsSync,
  mkdirSync,
  readdirSync,
  readFileSync,
  rmSync,
  statSync,
  unlinkSync,
  writeFileSync,
  writeFile as writeFileAsync,
} from "fs";
import { basename, dirname, extname, join, resolve } from "path";
import { createHash, randomUUID } from "crypto";
import { fileURLToPath } from "url";
import { promisify } from "util";
import { availableParallelism } from "os";
import opentype from "opentype.js";
import sharp from "sharp";
import { bundle } from "@remotion/bundler";
import { renderMedia, selectComposition, RenderInternals } from "@remotion/renderer";

const __dirname = dirname(fileURLToPath(import.meta.url));
const execFileAsync = promisify(execFile);
const PORT = Number(process.env.RENDER_PORT ?? 3001);
const FPS = 30;
const WIDTH = 1920;
const HEIGHT = 1080;
const OUTPUT_DIR = join(__dirname, "../../outputs");
const AUDIO_DIR = join(OUTPUT_DIR, "audio");
const MUSIC_DIR = resolve(process.env.EXPLAINFLOW_MUSIC_DIR ?? join(OUTPUT_DIR, "music"));
const JOBS_FILE = join(OUTPUT_DIR, "jobs.json");
const GENERATED_DIR = join(__dirname, "generated");
const PUBLIC_DIR = join(__dirname, "public");
const PUBLIC_GENERATED_DIR = join(PUBLIC_DIR, "generated");
const PYTHON_API = process.env.PYTHON_API_URL ?? "http://localhost:8000";
const DEFAULT_CHROME =
  "C:\\Users\\DELL\\AppData\\Local\\ms-playwright\\chromium_headless_shell-1223\\chrome-headless-shell-win64\\chrome-headless-shell.exe";
const BROWSER_EXECUTABLE = process.env.REMOTION_CHROME_HEADLESS_SHELL || DEFAULT_CHROME;
const FFPROBE_BINARY = process.env.FFPROBE_PATH || "ffprobe";
const FFMPEG_BINARY = process.env.FFMPEG_PATH || "ffmpeg";
const COMPOSITION_ID = "GeneratedVideo";
const STATIC_PORT_START = Number(process.env.REMOTION_STATIC_PORT ?? 3100);
const DEFAULT_RENDER_CONCURRENCY = Math.min(8, Math.max(4, availableParallelism() - 2));
const RENDER_CONCURRENCY = Number.isFinite(Number(process.env.REMOTION_CONCURRENCY))
  ? Math.max(1, Number(process.env.REMOTION_CONCURRENCY))
  : DEFAULT_RENDER_CONCURRENCY;
const RENDER_CRF = Number.isFinite(Number(process.env.REMOTION_CRF))
  ? Math.max(1, Math.min(51, Number(process.env.REMOTION_CRF)))
  : 8;
const RENDER_X264_PRESET = process.env.REMOTION_X264_PRESET || "slow";
const RENDER_PIXEL_FORMAT = process.env.REMOTION_PIXEL_FORMAT || "yuv444p";
const ENABLE_IMAGE_TRACE = process.env.REMOTION_IMAGE_TRACE !== "0";
const SKIP_IMAGE_TRACE = process.env.SKIP_IMAGE_TRACE === "1";
const ENABLE_SEEDREAM_REFERENCE_IMAGES = process.env.REMOTION_SEEDREAM_REFERENCES !== "0";
const REQUIRE_SEEDREAM_REFERENCE_IMAGES = process.env.REMOTION_REQUIRE_SEEDREAM_REFERENCES !== "0";
const SEEDREAM_REFERENCE_RENDER_MODE = String(process.env.REMOTION_SEEDREAM_REFERENCE_MODE ?? "direct")
  .trim()
  .toLowerCase();
const IMAGE_TRACE_MAX_SCENES = Math.max(0, Number(process.env.REMOTION_IMAGE_TRACE_MAX_SCENES ?? 16));
const IMAGE_TRACE_MAX_PATHS = Math.max(16, Number(process.env.REMOTION_IMAGE_TRACE_MAX_PATHS ?? 90));
const RASTER_REVEAL_MAX_STROKES = Math.max(
  24,
  Number(process.env.REMOTION_RASTER_REVEAL_MAX_STROKES ?? 150),
);
const RASTER_REVEAL_TRACE_WIDTH = Math.max(
  240,
  Number(process.env.REMOTION_RASTER_REVEAL_TRACE_WIDTH ?? 960),
);
const RASTER_REVEAL_TRACE_HEIGHT = Math.max(
  180,
  Number(process.env.REMOTION_RASTER_REVEAL_TRACE_HEIGHT ?? 540),
);
const RASTER_REVEAL_ASSET_MAX_SIZE = Math.max(
  640,
  Number(process.env.REMOTION_RASTER_REVEAL_ASSET_MAX_SIZE ?? 896),
);
const DIRECT_IMAGE_STROKE_THRESHOLD = Math.max(
  40,
  Number(process.env.REMOTION_DIRECT_IMAGE_STROKE_THRESHOLD ?? 280),
);
const HAND_ASSET = "hand-real-pen.png";
const MIN_RENDER_OUTPUT_BYTES = Math.max(1024, Number(process.env.RENDER_QA_MIN_BYTES ?? 50000) || 50000);
const MIN_RENDER_FRAME_STDDEV = Math.max(0.5, Number(process.env.RENDER_QA_MIN_FRAME_STDDEV ?? 2.5) || 2.5);
const GOLPO_STYLE_CONFIG = loadGolpoStyleConfig();
const VIDEO_STYLE_ALIASES = new Map(Object.entries(GOLPO_STYLE_CONFIG.aliases ?? {}));
const GOLPO_VIDEO_STYLES = new Set(GOLPO_STYLE_CONFIG.video_style_order ?? [
  "chalkboard_bw",
  "chalkboard_color",
  "modern_minimal",
  "technical_blueprint",
  "editorial",
  "whiteboard",
  "playful",
  "sharpie",
]);
const SCENE_PREROLL_FRAMES = Math.max(0, Math.min(90, Number(process.env.SCENE_PREROLL_FRAMES ?? 0) || 0));
const BEAT_AUDIO_LEAD_FRAMES = Math.max(0, Math.min(36, Number(process.env.BEAT_AUDIO_LEAD_FRAMES ?? 8) || 8));
const MUSIC_EXTENSIONS = new Set([".mp3", ".wav", ".m4a", ".aac", ".ogg", ".webm"]);
const MUSIC_MIME_TYPES = new Map([
  [".mp3", "audio/mpeg"],
  [".wav", "audio/wav"],
  [".m4a", "audio/mp4"],
  [".aac", "audio/aac"],
  [".ogg", "audio/ogg"],
  [".webm", "audio/webm"],
]);
const GLYPH_FONT_CANDIDATES = [
  process.env.EXPLAINFLOW_GLYPH_FONT,
  "C:\\Windows\\Fonts\\simkai.ttf",
  "C:\\Windows\\Fonts\\simfang.ttf",
  "C:\\Windows\\Fonts\\msyh.ttc",
  "C:\\Windows\\Fonts\\simsun.ttc",
].filter(Boolean);
const LATIN_GLYPH_FONT_CANDIDATES = [
  process.env.EXPLAINFLOW_LATIN_GLYPH_FONT,
  "C:\\Windows\\Fonts\\Inkfree.ttf",
  "C:\\Windows\\Fonts\\segoepr.ttf",
  "C:\\Windows\\Fonts\\comic.ttf",
].filter(Boolean);
const ttsInFlight = new Map();
const TTS_CONCURRENCY = Math.max(1, Math.min(2, Number(process.env.TTS_CONCURRENCY ?? 1) || 1));
const TTS_MAX_ATTEMPTS = Math.max(1, Math.min(5, Number(process.env.TTS_MAX_ATTEMPTS ?? 4) || 4));
let activeTtsRequests = 0;
const ttsWaiters = [];

mkdirSync(OUTPUT_DIR, { recursive: true });
mkdirSync(AUDIO_DIR, { recursive: true });
mkdirSync(MUSIC_DIR, { recursive: true });
mkdirSync(GENERATED_DIR, { recursive: true });
mkdirSync(PUBLIC_GENERATED_DIR, { recursive: true });

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

function loadJobs() {
  try {
    if (existsSync(JOBS_FILE)) {
      return JSON.parse(readFileSync(JOBS_FILE, "utf8"));
    }
  } catch (err) {
    console.warn("[jobs] Failed to read jobs.json:", err.message);
  }
  return {};
}

const jobs = loadJobs();

// Track pending save operations to avoid concurrent writes
let saveOperation = null;

/**
 * Asynchronously save jobs to disk without blocking the event loop.
 * Debounces concurrent calls to avoid excessive disk I/O.
 */
async function saveJobsAsync() {
  // If a save is already in progress, wait for it instead of starting another
  if (saveOperation) {
    return saveOperation;
  }

  saveOperation = (async () => {
    try {
      const data = JSON.stringify(jobs, null, 2);
      await promisify(writeFileAsync)(JOBS_FILE, data, "utf8");
    } catch (err) {
      console.warn("[jobs] Failed to save jobs.json:", err.message);
    } finally {
      saveOperation = null;
    }
  })();

  return saveOperation;
}

/**
 * Synchronous save for use during startup/initialization only.
 * Should not be called after the server is fully started.
 */
function saveJobsSync() {
  try {
    writeFileSync(JOBS_FILE, JSON.stringify(jobs, null, 2), "utf8");
  } catch (err) {
    console.warn("[jobs] Failed to save jobs.json:", err.message);
  }
}

function looksLikeMojibake(value) {
  const text = String(value ?? "");
  if (!text) return false;
  const suspicious = (text.match(/[�€ÃÂåæçèéäöü\ue000-\uf8ff]/g) ?? []).length;
  const cjk = (text.match(/[\u3400-\u9fff]/g) ?? []).length;
  return suspicious >= 2 && suspicious > Math.max(1, Math.floor(cjk * 0.2));
}

function tryRepairMojibake(value) {
  const text = String(value ?? "");
  if (!looksLikeMojibake(text)) return text;
  const attempts = [
    () => Buffer.from(text, "latin1").toString("utf8"),
    () => Buffer.from(text, "binary").toString("utf8"),
  ];
  let best = text;
  let bestScore = mojibakeScore(text);
  for (const attempt of attempts) {
    try {
      const candidate = attempt();
      const score = mojibakeScore(candidate);
      if (score < bestScore && /[\u3400-\u9fff]/.test(candidate)) {
        best = candidate;
        bestScore = score;
      }
    } catch {}
  }
  return best;
}

function mojibakeScore(value) {
  const text = String(value ?? "");
  return (text.match(/[�€ÃÂåæçèéäöü\ue000-\uf8ff]/g) ?? []).length * 3 - (text.match(/[\u3400-\u9fff]/g) ?? []).length;
}

function localizeChineseTerms(text) {
  return String(text ?? "").replace(/相互依赖/g, "互相依赖").replace(/互赖/g, "互相依赖");
}

function canonicalVideoStyle(value, fallback = "whiteboard") {
  const raw = String(value ?? fallback ?? "whiteboard").trim().toLowerCase();
  const style = VIDEO_STYLE_ALIASES.get(raw) ?? raw;
  return GOLPO_VIDEO_STYLES.has(style) ? style : fallback;
}

function normalizePenStyle(value, fallback = "marker") {
  const style = String(value ?? fallback ?? "marker").trim().toLowerCase();
  return ["marker", "pen", "fountain_pen", "no_hand"].includes(style) ? style : fallback;
}

function cleanUserText(value, fallback = "") {
  return localizeChineseTerms(tryRepairMojibake(value))
    .replace(/\x1b\[[0-9;]*m/g, "")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, 500) || fallback;
}

function sanitizeStoryboardText(storyboard) {
  const scenes = Array.isArray(storyboard?.scenes) ? storyboard.scenes : [];
  const storyboardVideoStyle = canonicalVideoStyle(storyboard?.video_style ?? storyboard?.videoStyle, "whiteboard");
  const storyboardPenStyle = normalizePenStyle(storyboard?.pen_style ?? storyboard?.penStyle, "marker");
  return {
    ...storyboard,
    topic: cleanUserText(storyboard?.topic, "Untitled"),
    video_style: storyboardVideoStyle,
    videoStyle: storyboardVideoStyle,
    pen_style: storyboardPenStyle,
    penStyle: storyboardPenStyle,
    scenes: scenes.map((scene) => {
      const sceneVideoStyle = canonicalVideoStyle(scene?.video_style ?? scene?.videoStyle, storyboardVideoStyle);
      const scenePenStyle = normalizePenStyle(scene?.pen_style ?? scene?.penStyle, storyboardPenStyle);
      return {
        ...scene,
        title: cleanUserText(scene?.title, "场景"),
        narration: cleanUserText(scene?.narration, ""),
        learning_goal: cleanUserText(scene?.learning_goal ?? scene?.learningGoal, ""),
        learningGoal: cleanUserText(scene?.learningGoal ?? scene?.learning_goal, ""),
        image_description: cleanUserText(scene?.image_description ?? scene?.imageDescription, ""),
        imageDescription: cleanUserText(scene?.imageDescription ?? scene?.image_description, ""),
        video_style: sceneVideoStyle,
        videoStyle: sceneVideoStyle,
        pen_style: scenePenStyle,
        penStyle: scenePenStyle,
        subtitleText: scene?.subtitleText == null ? scene?.subtitleText : cleanUserText(scene.subtitleText, ""),
        visual_beats: Array.isArray(scene?.visual_beats)
          ? scene.visual_beats.map((beat) => ({
              ...beat,
              draw_intent: cleanUserText(beat?.draw_intent ?? beat?.drawIntent, ""),
              narration: cleanUserText(beat?.narration, ""),
              required_labels: Array.isArray(beat?.required_labels)
                ? beat.required_labels.map((label) => cleanUserText(label, "")).filter(Boolean)
                : beat?.required_labels,
            }))
          : scene?.visual_beats,
        diagram_plan: scene?.diagram_plan
          ? {
              ...scene.diagram_plan,
              kind: cleanUserText(scene.diagram_plan.kind, "process"),
              layout: cleanUserText(scene.diagram_plan.layout, ""),
              required_labels: Array.isArray(scene.diagram_plan.required_labels)
                ? scene.diagram_plan.required_labels.map((label) => cleanUserText(label, "")).filter(Boolean)
                : scene.diagram_plan.required_labels,
            }
          : scene?.diagram_plan,
      };
    }),
  };
}

function collectStoryboardMojibake(storyboard) {
  const bad = [];
  const check = (path, value) => {
    if (looksLikeMojibake(value)) bad.push(path);
  };
  check("topic", storyboard?.topic);
  for (const [sceneIndex, scene] of (storyboard?.scenes ?? []).entries()) {
    check(`scenes[${sceneIndex}].title`, scene?.title);
    check(`scenes[${sceneIndex}].narration`, scene?.narration);
    for (const [beatIndex, beat] of (scene?.visual_beats ?? []).entries()) {
      check(`scenes[${sceneIndex}].visual_beats[${beatIndex}].narration`, beat?.narration);
      check(`scenes[${sceneIndex}].visual_beats[${beatIndex}].draw_intent`, beat?.draw_intent ?? beat?.drawIntent);
    }
  }
  return bad;
}

function assertStoryboardEncodingHealthy(storyboard) {
  const bad = collectStoryboardMojibake(storyboard);
  if (bad.length > 0) {
    throw new Error(`检测到中文编码异常，已停止渲染。请重新生成 storyboard 后再试。位置：${bad.slice(0, 4).join(", ")}`);
  }
}

function updateJob(jobId, patch) {
  if (!jobs[jobId]) return;
  jobs[jobId] = { ...jobs[jobId], ...patch };
  saveJobsAsync();
}

for (const [id, job] of Object.entries(jobs)) {
  if (job.topic) jobs[id].topic = cleanUserText(job.topic, "Untitled");
  if (job.error) jobs[id].error = cleanUserText(job.error, job.error);
  if (job.status === "processing") {
    jobs[id].status = "failed";
    jobs[id].error = "Server restarted during render";
  }
}
saveJobsSync();

function readBody(req, limitBytes = 10 * 1024 * 1024) {
  return new Promise((resolvePromise, reject) => {
    const chunks = [];
    let totalBytes = 0;
    req.on("data", (chunk) => {
      const buffer = Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk);
      chunks.push(buffer);
      totalBytes += buffer.length;
      if (totalBytes > limitBytes) {
        reject(new Error("Request body too large"));
        req.destroy();
      }
    });
    req.on("end", () => resolvePromise(Buffer.concat(chunks).toString("utf8")));
    req.on("error", reject);
  });
}

function postJson(url, payload, timeoutMs = 300000) {
  const body = JSON.stringify(payload);
  return new Promise((resolvePromise, reject) => {
    const req = http.request(
      url,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Content-Length": Buffer.byteLength(body),
        },
      },
      (res) => {
        const chunks = [];
        res.on("data", (chunk) => chunks.push(chunk));
        res.on("end", () => {
          const text = Buffer.concat(chunks).toString("utf8");
          if (res.statusCode < 200 || res.statusCode >= 300) {
            reject(new Error(`${url} returned ${res.statusCode}: ${text}`));
            return;
          }
          try {
            resolvePromise(JSON.parse(text));
          } catch (err) {
            reject(new Error(`Invalid JSON from ${url}: ${err.message}`));
          }
        });
      },
    );
    req.setTimeout(timeoutMs, () => req.destroy(new Error(`${url} timed out`)));
    req.on("error", reject);
    req.write(body);
    req.end();
  });
}

function getJson(url, timeoutMs = 12000) {
  return new Promise((resolvePromise, reject) => {
    const req = http.request(url, { method: "GET" }, (res) => {
      const chunks = [];
      res.on("data", (chunk) => chunks.push(chunk));
      res.on("end", () => {
        const text = Buffer.concat(chunks).toString("utf8");
        let payload = {};
        try {
          payload = text ? JSON.parse(text) : {};
        } catch {}
        if (res.statusCode < 200 || res.statusCode >= 300) {
          const detail = payload.detail || payload.error || text || `HTTP ${res.statusCode}`;
          reject(new Error(String(detail)));
          return;
        }
        resolvePromise(payload);
      });
    });
    req.setTimeout(timeoutMs, () => req.destroy(new Error(`${url} timed out`)));
    req.on("error", reject);
    req.end();
  });
}

function clampNumber(value, min, max, fallback) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return fallback;
  return Math.max(min, Math.min(max, parsed));
}

function titleFromMusicFilename(filename) {
  const name = basename(filename, extname(filename)).replace(/-mixkit$/i, "");
  return name
    .split(/[-_]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function resolveMusicTrack(rawId) {
  let decoded = "";
  try {
    decoded = decodeURIComponent(String(rawId ?? ""));
  } catch {
    return null;
  }
  const filename = basename(decoded);
  if (!filename || filename !== decoded) return null;
  const ext = extname(filename).toLowerCase();
  if (!MUSIC_EXTENSIONS.has(ext)) return null;
  const filePath = resolve(MUSIC_DIR, filename);
  if (!isInside(filePath, MUSIC_DIR) || !existsSync(filePath)) return null;
  const stat = statSync(filePath);
  if (!stat.isFile() || stat.size <= 0) return null;
  return {
    id: filename,
    name: titleFromMusicFilename(filename),
    url: `http://localhost:${PORT}/music/${encodeURIComponent(filename)}`,
    size: stat.size,
    contentType: MUSIC_MIME_TYPES.get(ext) ?? "application/octet-stream",
    filePath,
  };
}

function listMusicTracks() {
  return readdirSync(MUSIC_DIR, { withFileTypes: true })
    .filter((entry) => entry.isFile())
    .map((entry) => resolveMusicTrack(entry.name))
    .filter(Boolean)
    .map(({ id, name, url, size }) => ({ id, name, url, size }))
    .sort((a, b) => a.name.localeCompare(b.name));
}

async function ensureLargeModelAvailable() {
  try {
    await getJson(`${PYTHON_API}/health/llm`);
  } catch (err) {
    throw new Error(
      `大模型暂时连接不上，已停止本次任务；请检查模型配置和网络后重试。${err.message ? ` 详情：${err.message}` : ""}`,
    );
  }
}

function postBuffer(url, payload, timeoutMs = 120000) {
  const body = JSON.stringify(payload);
  return new Promise((resolvePromise, reject) => {
    const req = http.request(
      url,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Content-Length": Buffer.byteLength(body),
        },
      },
      (res) => {
        const chunks = [];
        res.on("data", (chunk) => chunks.push(chunk));
        res.on("end", () => {
          const buffer = Buffer.concat(chunks);
          if (res.statusCode < 200 || res.statusCode >= 300) {
            reject(new Error(`${url} returned ${res.statusCode}: ${buffer.toString("utf8")}`));
            return;
          }
          resolvePromise(buffer);
        });
      },
    );
    req.setTimeout(timeoutMs, () => req.destroy(new Error(`${url} timed out`)));
    req.on("error", reject);
    req.write(body);
    req.end();
  });
}

function sleep(ms) {
  return new Promise((resolvePromise) => setTimeout(resolvePromise, ms));
}

async function acquireTtsSlot() {
  if (activeTtsRequests < TTS_CONCURRENCY) {
    activeTtsRequests += 1;
    return;
  }
  await new Promise((resolvePromise) => ttsWaiters.push(resolvePromise));
  activeTtsRequests += 1;
}

function releaseTtsSlot() {
  activeTtsRequests = Math.max(0, activeTtsRequests - 1);
  const next = ttsWaiters.shift();
  if (next) next();
}

async function withTtsSlot(fn) {
  await acquireTtsSlot();
  try {
    return await fn();
  } finally {
    releaseTtsSlot();
  }
}

function normalizeTextForTts(text) {
  return String(text ?? "")
    .replace(/\bV_G\b/g, "V G")
    .replace(/\bV_th\b/gi, "V threshold")
    .replace(/\bV_DS\b/g, "V D S")
    .replace(/\bI_D\b/g, "I D")
    .replace(/\bW_eff\b/g, "W effective")
    .replace(/>=/g, " greater than or equal to ")
    .replace(/<=/g, " less than or equal to ")
    .replace(/>/g, " greater than ")
    .replace(/</g, " less than ")
    .replace(/=/g, " equals ")
    .replace(/[{}[\]`*_#~^|\\]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function cleanNarrationText(text) {
  let value = cleanUserText(text, "").replace(/\s+/g, " ").trim();
  if (!value) return "";
  const replacements = [
    [/^\s*(?:首先|先|接着|然后|再|最后|这里|现在|我们|把|请)?\s*(?:先|再)?\s*(?:画|绘制|写|写上|标出|标注|圈出|框出|显示|展示|呈现|看|看到)\s*(?:左边|右边|上方|下方|中间|图中|画面中|这个图|这张图)?\s*(?:的|出|上)?\s*/i, ""],
    [/(?:先|再|然后|接着|最后)\s*(?:画|绘制|写|写上|标出|标注|圈出|框出|显示|展示|呈现)\s*/gi, ""],
    [/(?:左边|右边|上方|下方|中间|旁边|图中|画面中)\s*(?:画|绘制|写|写上|标出|标注|可以看到|看到)\s*/gi, ""],
    [/(?:这一步|这个 beat|此时)\s*(?:同步)?\s*(?:说|讲|说明|解释)\s*/gi, ""],
    [/(?:我们|这里|现在)\s*(?:来|可以)?\s*(?:画|绘制|写|写上|标出|标注|看)\s*/gi, ""],
  ];
  for (const [pattern, replacement] of replacements) {
    value = value.replace(pattern, replacement);
  }
  value = value.replace(/\s+/g, " ").replace(/^[ ：:，,。]+|[ ：:，,。]+$/g, "").trim();
  if (value && !/[。！？.!?]$/.test(value)) value += "。";
  return value;
}

function trimNarrationToChars(text, maxChars) {
  const limit = Math.max(0, Number(maxChars) || 0);
  const source = cleanNarrationText(text);
  if (!limit || source.length <= limit) return source;
  const sentences = source.match(/[^。！？.!?]+[。！？.!?]?/g) ?? [source];
  let result = "";
  for (const sentence of sentences) {
    const next = `${result}${sentence}`;
    if (next.length <= limit) {
      result = next;
    } else if (!result && limit >= 28) {
      let candidate = sentence.slice(0, limit);
      const cut = Math.max(candidate.lastIndexOf("，"), candidate.lastIndexOf(","), candidate.lastIndexOf("；"), candidate.lastIndexOf(";"), candidate.lastIndexOf("："), candidate.lastIndexOf(":"), candidate.lastIndexOf("、"));
      if (cut > Math.floor(limit * 0.45)) candidate = candidate.slice(0, cut);
      result = candidate.replace(/[，,；;：:、\s]+$/g, "");
      break;
    } else {
      break;
    }
  }
  result = result.replace(/[，,；;：:、\s]+$/g, "");
  if (result && !/[。！？.!?]$/.test(result)) result += "。";
  if (result) return result;
  const firstSentence = sentences[0]?.trim() || source;
  if (firstSentence.length <= Math.max(limit * 2, 96)) return firstSentence;
  return `${source.slice(0, limit).replace(/[，,；;：:、\s]+$/g, "")}。`;
}

function splitNarrationSentences(text) {
  const source = cleanNarrationText(text);
  if (!source) return [];
  return (source.match(/[^。！？!?]+[。！？!?]?/g) ?? [source])
    .map((part) => cleanNarrationText(part))
    .filter(Boolean);
}

function distributeNarrationAcrossBeats(sceneNarration, beatCount) {
  const count = Math.max(1, Number(beatCount) || 1);
  const source = cleanNarrationText(sceneNarration);
  if (!source) return [];
  if (count === 1) return [source];
  const sentences = splitNarrationSentences(source);
  if (sentences.length === 0) return [source];
  const chunks = Array.from({ length: count }, () => []);
  const totalChars = sentences.reduce((sum, sentence) => sum + sentence.length, 0);
  const targetChars = Math.max(1, totalChars / count);
  let chunkIndex = 0;
  let chunkChars = 0;
  for (const [sentenceIndex, sentence] of sentences.entries()) {
    const remainingSentences = sentences.length - sentenceIndex;
    const remainingSlots = count - chunkIndex - 1;
    if (
      chunkIndex < count - 1 &&
      chunkChars > 0 &&
      chunkChars + sentence.length > targetChars &&
      remainingSentences > remainingSlots
    ) {
      chunkIndex += 1;
      chunkChars = 0;
    }
    chunks[chunkIndex].push(sentence);
    chunkChars += sentence.length;
  }
  return chunks.map((chunk) => cleanNarrationText(chunk.join(""))).filter(Boolean);
}

function normalizeVoiceKey(voice) {
  const value = String(voice ?? "").trim();
  if (!value) return "xiaoxiao";
  const normalized = value.toLowerCase().replace(/[^a-z0-9]/g, "");
  const aliases = new Map([
    ["xiaoxiao", "xiaoxiao"],
    ["zhcnxiaoxiaoneural", "xiaoxiao"],
    ["yunxi", "yunxi"],
    ["zhcnyunxineural", "yunxi"],
    ["xiaoyi", "xiaoyi"],
    ["zhcnxiaoyineural", "xiaoyi"],
  ]);
  return aliases.get(normalized) ?? value;
}

async function requestTtsAudio(narration, voice, sceneId) {
  const speechText = normalizeTextForTts(narration);
  let lastError = null;
  for (let attempt = 1; attempt <= TTS_MAX_ATTEMPTS; attempt += 1) {
    try {
      const audio = await withTtsSlot(() =>
        postBuffer(`${PYTHON_API}/narration/synthesize`, {
          text: speechText || narration,
          voice,
        }),
      );
      if (!Buffer.isBuffer(audio) || audio.length < 512) {
        throw new Error("No usable audio was received from TTS");
      }
      return audio;
    } catch (err) {
      lastError = err;
      if (attempt < TTS_MAX_ATTEMPTS) {
        console.warn(`[tts] retry ${attempt}/${TTS_MAX_ATTEMPTS - 1} for ${sceneId}: ${err.message}`);
        await sleep(1200 + attempt * 1800);
      }
    }
  }
  throw lastError ?? new Error("TTS failed");
}

function ttsCacheFilename(text, voice) {
  const hash = createHash("sha1")
    .update(JSON.stringify({ text: String(text ?? ""), voice: String(voice ?? "") }))
    .digest("hex")
    .slice(0, 20);
  return `tts_${hash}.mp3`;
}

function estimateNarrationSeconds(text) {
  const source = String(text ?? "").trim();
  if (!source) return 0;
  const cjk = [...source].filter((char) => /[\u3400-\u9fff]/.test(char)).length;
  const latinWords = (source.match(/[A-Za-z0-9]+/g) ?? []).length;
  const punctuationPauses = (source.match(/[。！？；.!?;]/g) ?? []).length * 0.25;
  return Math.max(2.0, cjk * 0.18 + latinWords * 0.32 + punctuationPauses + 0.8);
}

async function probeAudioDurationSeconds(filePath) {
  try {
    const { stdout } = await execFileAsync(
      FFPROBE_BINARY,
      [
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        filePath,
      ],
      { windowsHide: true, timeout: 30000 },
    );
    const parsed = Number.parseFloat(String(stdout).trim());
    return Number.isFinite(parsed) && parsed > 0 ? parsed : 0;
  } catch (err) {
    console.warn(`[tts] ffprobe failed for ${basename(filePath)}: ${err.message}`);
    return 0;
  }
}

async function probePlayableAudio(filePath) {
  try {
    const { stdout } = await execFileAsync(
      FFPROBE_BINARY,
      [
        "-v",
        "error",
        "-select_streams",
        "a:0",
        "-show_entries",
        "stream=codec_name,sample_rate,channels:format=duration",
        "-of",
        "json",
        filePath,
      ],
      { windowsHide: true, timeout: 30000 },
    );
    const parsed = JSON.parse(stdout || "{}");
    const stream = Array.isArray(parsed.streams) ? parsed.streams[0] : null;
    const duration = Number.parseFloat(String(parsed.format?.duration ?? "0"));
    return Boolean(stream?.codec_name && Number.isFinite(duration) && duration > 0);
  } catch (err) {
    console.warn(`[music] ffprobe rejected ${basename(filePath)}: ${err.message}`);
    return false;
  }
}

async function probeMediaInfo(filePath) {
  const { stdout } = await execFileAsync(
    FFPROBE_BINARY,
    [
      "-v",
      "error",
      "-show_entries",
      "format=duration:stream=codec_type,codec_name,width,height",
      "-of",
      "json",
      filePath,
    ],
    { windowsHide: true, timeout: 30000 },
  );
  const parsed = JSON.parse(stdout || "{}");
  const duration = Number.parseFloat(String(parsed.format?.duration ?? "0"));
  const streams = Array.isArray(parsed.streams) ? parsed.streams : [];
  return {
    durationSeconds: Number.isFinite(duration) && duration > 0 ? duration : 0,
    hasAudio: streams.some((stream) => stream.codec_type === "audio"),
    hasVideo: streams.some((stream) => stream.codec_type === "video"),
    streams,
  };
}

async function normalizeMusicTrackForRemotion(track) {
  if (!track) return null;
  const ext = extname(track.filePath).toLowerCase();
  if (ext !== ".mp3") return track;
  const safeName = `${basename(track.id, ext)}_remotion.wav`;
  const outPath = join(MUSIC_DIR, safeName);
  if (!existsSync(outPath) || statSync(outPath).size <= 0) {
    await execFileAsync(
      "ffmpeg",
      ["-y", "-i", track.filePath, "-vn", "-acodec", "pcm_s16le", "-ar", "48000", "-ac", "2", outPath],
      { windowsHide: true, timeout: 120000 },
    );
  }
  const normalized = resolveMusicTrack(safeName);
  return normalized || track;
}

async function synthesizeScene(sceneId, text, voice) {
  const narration = String(text ?? "").trim();
  if (!narration) return null;
  const filename = ttsCacheFilename(narration, voice);
  const outPath = join(AUDIO_DIR, filename);
  const audioUrl = `http://localhost:${PORT}/audio/${filename}`;
  if (existsSync(outPath) && statSync(outPath).size > 0) {
    console.log(`[tts] cache hit: ${sceneId}`);
    const durationSeconds = await probeAudioDurationSeconds(outPath);
    if (!durationSeconds) {
      try {
        unlinkSync(outPath);
      } catch {}
      throw new Error(`Cached TTS audio is empty or unreadable for ${sceneId}`);
    }
    return { audioUrl, filePath: outPath, durationSeconds, text: narration };
  }
  if (ttsInFlight.has(filename)) {
    await ttsInFlight.get(filename);
    const durationSeconds = await probeAudioDurationSeconds(outPath);
    if (!durationSeconds) {
      throw new Error(`Shared TTS audio is empty or unreadable for ${sceneId}`);
    }
    return { audioUrl, filePath: outPath, durationSeconds, text: narration };
  }

  const pending = requestTtsAudio(narration, voice, sceneId).then((audio) => {
    writeFileSync(outPath, audio);
  });
  ttsInFlight.set(filename, pending);
  try {
    await pending;
    const durationSeconds = await probeAudioDurationSeconds(outPath);
    if (!durationSeconds || !existsSync(outPath) || statSync(outPath).size <= 0) {
      throw new Error(`TTS audio is empty or unreadable for ${sceneId}`);
    }
    return { audioUrl, filePath: outPath, durationSeconds, text: narration };
  } finally {
    ttsInFlight.delete(filename);
  }
}

function sceneBeatSpecs(scene) {
  const visualBeats = Array.isArray(scene.visual_beats) ? scene.visual_beats : [];
  const beats = visualBeats.length > 0
    ? visualBeats
    : [
        {
          id: "beat_0",
          draw_intent: scene.image_description || scene.title || "",
          narration: scene.narration || scene.title || "",
          required_labels: [],
          duration_estimate: scene.duration_estimate || 8,
        },
      ];
  const sceneBudget = Math.max(5, Number(scene?.duration_estimate ?? 0) || 0);
  const sceneNarration = cleanNarrationText(scene.narration || scene.title || "");
  const distributedSceneNarration = distributeNarrationAcrossBeats(sceneNarration, beats.length);
  return beats.map((beat, index) => {
    const rawText = cleanNarrationText(
      distributedSceneNarration[index] ||
        beat?.narration ||
        sceneNarration ||
        scene.title ||
        beat?.draw_intent ||
        "",
    );
    const beatEstimate = Math.max(
      1,
      estimateNarrationSeconds(rawText) + 0.8,
      Number(beat?.duration_estimate ?? beat?.duration ?? sceneBudget / Math.max(1, beats.length)) || 6,
    );
    const maxChars = Math.max(120, Math.min(260, Math.floor(Math.max(beatEstimate, 8) * 9.5)));
    const text = trimNarrationToChars(rawText, maxChars);
    return {
      id: String(beat?.id || `beat_${index}`),
      index,
      text,
      drawIntent: String(beat?.draw_intent || beat?.drawIntent || scene.title || "").trim(),
      durationEstimate: beatEstimate,
    };
  });
}

async function injectAudio(storyboard, voice) {
  const voiceKey = normalizeVoiceKey(voice ?? "xiaoxiao");
  const sceneResults = await Promise.allSettled(
    storyboard.scenes.map(async (scene, sceneIndex) => {
      const suppliedAudio = await persistSceneAudioDataUrl(scene, sceneIndex);
      if (suppliedAudio) {
        const audioDurationFrames = Math.max(1, Math.ceil(suppliedAudio.durationSeconds * FPS));
        const durationFrames = Math.max(audioDurationFrames + Math.round(FPS * 0.65), FPS * 5);
        const segment = {
          id: "scene_audio",
          index: 0,
          startFrame: 0,
          endFrame: durationFrames,
          duration: durationFrames,
          audioStartFrame: 0,
          audioEndFrame: audioDurationFrames,
          audioSequenceDuration: durationFrames,
          audioUrl: suppliedAudio.audioUrl,
          audioDurationFrames,
          drawBudgetFrames: Math.max(1, durationFrames - 4),
          subtitleText: suppliedAudio.text,
          narration: suppliedAudio.text,
          drawIntent: scene.image_description || scene.title || "",
        };
        return {
          ...scene,
          audioUrl: suppliedAudio.audioUrl,
          audioSegments: [segment],
          timingPlan: {
            fps: FPS,
            durationFrames,
            transitionFrames: 0,
            allowOverTarget: true,
            segments: [segment],
          },
          duration_estimate: durationFrames / FPS,
        };
      }
      const beatSpecs = sceneBeatSpecs(scene);
      const segmentResults = await Promise.allSettled(
        beatSpecs.map((beat) =>
          synthesizeScene(`${scene.id || `scene_${sceneIndex}`}_${beat.id}`, beat.text, voiceKey),
        ),
      );

      let cursor = SCENE_PREROLL_FRAMES;
      const audioSegments = segmentResults.map((result, index) => {
        const beat = beatSpecs[index];
        const audio = result.status === "fulfilled" ? result.value : null;
        if (!audio?.audioUrl || !audio?.filePath || !audio?.durationSeconds) {
          const reason = result.status === "rejected" ? result.reason?.message : "empty audio";
          throw new Error(`缺少音频片段：${scene.id || `scene_${sceneIndex}`}/${beat.id} (${reason || "TTS failed"})`);
        }
        // Use actual audio duration for precise timing
        const actualAudioDurationSeconds = audio?.durationSeconds ?? estimateNarrationSeconds(beat.text);
        const audioDurationFrames = Math.max(1, Math.ceil(actualAudioDurationSeconds * FPS));
        const estimateFrames = Math.ceil(beat.durationEstimate * FPS);
        // No lead frames - audio starts immediately with visuals for better sync
        const audioLeadFrames = 0;
        const audioStartFrame = cursor;
        const minimumFrames = Math.max(FPS * 3, estimateFrames);
        const durationFrames = Math.max(minimumFrames, audioDurationFrames + 14);
        const startFrame = cursor;
        const endFrame = startFrame + durationFrames;
        cursor = endFrame;

        // Determine when this beat's audio should end - before next beat starts
        // Use audioDurationFrames as the authoritative duration
        const currentAudioDuration = audioDurationFrames;

        return {
          id: beat.id,
          index,
          startFrame,
          endFrame,
          duration: durationFrames,
          audioStartFrame,
          // audioEndFrame: when audio actually finishes playing
          audioEndFrame: audioStartFrame + currentAudioDuration,
          // audioSequenceDuration: how long to render the audio - use audioDurationFrames
          // This ensures audio doesn't overlap with next beat's audio
          audioSequenceDuration: currentAudioDuration,
          audioUrl: audio?.audioUrl ?? null,
          audioDurationFrames: currentAudioDuration,
          drawBudgetFrames: Math.max(1, durationFrames - 4),
          subtitleText: beat.text,
          narration: beat.text,
          drawIntent: beat.drawIntent,
        };
      });

      const transitionFrames = 0;
      const lastAudioEndFrame = audioSegments.reduce(
        (maxFrame, segment) => Math.max(maxFrame, Number(segment.audioEndFrame ?? segment.endFrame ?? 0) || 0),
        0,
      );
      const durationFrames = Math.max(cursor + transitionFrames, lastAudioEndFrame + Math.round(FPS * 0.65), FPS * 8);
      const fallbackAudio = audioSegments.find((segment) => segment.audioUrl)?.audioUrl ?? null;
      if (!fallbackAudio) {
        throw new Error(`缺少场景音频：${scene.id || `scene_${sceneIndex}`}`);
      }
      const failedSegments = segmentResults.filter((result) => result.status === "rejected");
      if (failedSegments.length > 0) {
        console.warn(
          `[tts] ${failedSegments.length} beat segment(s) failed for ${scene.id}:`,
          failedSegments.map((result) => result.reason?.message),
        );
      }
      return {
        ...scene,
        audioUrl: fallbackAudio,
        audioSegments,
        timingPlan: {
          fps: FPS,
          durationFrames,
          transitionFrames,
          allowOverTarget: true,
          segments: audioSegments,
        },
        duration_estimate: durationFrames / FPS,
      };
    }),
  );

  const scenes = storyboard.scenes.map((scene, index) => {
    const result = sceneResults[index];
    return result.status === "fulfilled" ? result.value : scene;
  });

  const failed = sceneResults.filter((result) => result.status === "rejected");
  if (failed.length > 0) {
    console.warn(
      `[tts] ${failed.length} scene(s) failed:`,
      failed.map((result) => result.reason?.message),
    );
    throw new Error(`缺少音频，已停止渲染：${failed.map((result) => result.reason?.message).join("; ")}`);
  }

  const totalFrames = scenes.reduce(
    (sum, scene) => sum + Math.max(FPS * 8, Number(scene.timingPlan?.durationFrames ?? Math.round((scene.duration_estimate || 0) * FPS))),
    0,
  );
  return {
    ...storyboard,
    scenes,
    total_duration_estimate: totalFrames / FPS,
    timingPlan: {
      fps: FPS,
      durationFrames: totalFrames,
      allowOverTarget: true,
    },
  };
}

function audioFilenameFromUrl(url) {
  try {
    const parsed = new URL(String(url));
    if (parsed.pathname.startsWith("/audio/")) return decodeURIComponent(basename(parsed.pathname));
  } catch {}
  return null;
}

function normalizeBase64DataUrl(value, expectedPrefix) {
  const text = String(value ?? "").trim();
  if (!text.startsWith(expectedPrefix)) return null;
  const comma = text.indexOf(",");
  if (comma < 0) return null;
  const meta = text.slice(0, comma).toLowerCase();
  if (!meta.includes(";base64")) return null;
  return text.slice(comma + 1);
}

async function persistSceneAudioDataUrl(scene, sceneIndex) {
  const audioUrl = String(scene?.audioUrl ?? scene?.audio_url ?? "").trim();
  const base64 = normalizeBase64DataUrl(audioUrl, "data:audio/");
  if (!base64) return null;
  const sceneId = safeAssetSegment(scene?.id || `scene_${sceneIndex}`, "scene");
  const hash = createHash("sha1").update(base64).digest("hex").slice(0, 16);
  const outPath = join(AUDIO_DIR, `scene_${sceneId}_${hash}.mp3`);
  if (!existsSync(outPath) || statSync(outPath).size <= 0) {
    writeFileSync(outPath, Buffer.from(base64, "base64"));
  }
  const durationSeconds = await probeAudioDurationSeconds(outPath);
  if (!durationSeconds) {
    try {
      unlinkSync(outPath);
    } catch {}
    throw new Error(`User supplied scene audio is empty or unreadable for ${scene?.id || `scene_${sceneIndex}`}`);
  }
  return {
    audioUrl: `http://localhost:${PORT}/audio/${basename(outPath)}`,
    filePath: outPath,
    durationSeconds,
    text: cleanNarrationText(scene?.narration || scene?.title || ""),
  };
}

async function assertStoryboardAudioComplete(storyboard) {
  const missing = [];
  for (const [sceneIndex, scene] of (storyboard?.scenes ?? []).entries()) {
    const sceneId = scene?.id || `scene_${sceneIndex}`;
    const segments = scene?.audioSegments ?? scene?.audio_segments ?? [];
    if (!Array.isArray(segments) || segments.length === 0) {
      missing.push(`${sceneId}: no audioSegments`);
      continue;
    }
    for (const [segmentIndex, segment] of segments.entries()) {
      const src = segment?.audioUrl ?? segment?.audio_url;
      if (!src) {
        missing.push(`${sceneId}/segment_${segmentIndex}: missing audioUrl`);
        continue;
      }
      const filename = audioFilenameFromUrl(src);
      const localPath = filename ? join(AUDIO_DIR, filename) : null;
      if (!localPath || !existsSync(localPath) || statSync(localPath).size <= 0) {
        missing.push(`${sceneId}/segment_${segmentIndex}: audio file missing`);
        continue;
      }
      const duration = await probeAudioDurationSeconds(localPath);
      if (!duration) {
        missing.push(`${sceneId}/segment_${segmentIndex}: duration is 0`);
      }
    }
  }
  if (missing.length > 0) {
    throw new Error(`缺少音频，已停止渲染：${missing.slice(0, 8).join("; ")}`);
  }
}

function qaCheck(id, ok, severity, message, details = null, suggestion = null) {
  return {
    id,
    ok: Boolean(ok),
    severity,
    message,
    ...(details ? { details } : {}),
    ...(suggestion ? { suggestion } : {}),
  };
}

function storyboardExpectedDuration(storyboard) {
  const fromStoryboard = Number(storyboard?.total_duration_estimate ?? storyboard?.totalDurationEstimate ?? 0);
  if (Number.isFinite(fromStoryboard) && fromStoryboard > 0) return fromStoryboard;
  return (storyboard?.scenes ?? []).reduce((sum, scene) => {
    const duration = Number(scene?.duration_estimate ?? scene?.durationEstimate ?? 0);
    return sum + (Number.isFinite(duration) && duration > 0 ? duration : 0);
  }, 0);
}

function collectStoryboardQaChecks(storyboard) {
  const checks = [];
  const scenes = Array.isArray(storyboard?.scenes) ? storyboard.scenes : [];
  const storyboardText = JSON.stringify(storyboard ?? {});
  const hardTranslationTerms = ["互赖", "相互依赖赖", "interdependence 的"];
  const badTerm = hardTranslationTerms.find((term) => storyboardText.includes(term));
  checks.push(
    qaCheck(
      "natural_chinese",
      !badTerm,
      badTerm ? "error" : "info",
      badTerm ? `Storyboard contains hard translation term: ${badTerm}` : "No known hard-translation blacklist terms found",
      badTerm ? { term: badTerm } : null,
      badTerm ? "Regenerate or edit narration/labels with natural Chinese phrasing before rendering." : null,
    ),
  );

  const missingTextFree = scenes
    .filter((scene) => {
      const desc = String(scene?.image_description ?? scene?.imageDescription ?? "").toLowerCase();
      if (!desc) return false;
      return !desc.includes("text-free") && !desc.includes("no readable");
    })
    .map((scene) => scene?.id ?? scene?.title ?? "scene");
  checks.push(
    qaCheck(
      "text_free_image_prompts",
      missingTextFree.length === 0,
      missingTextFree.length ? "warning" : "info",
      missingTextFree.length
        ? `${missingTextFree.length} scene image prompt(s) do not explicitly request text-free artwork`
        : "Scene image prompts request text-free artwork",
      missingTextFree.length ? { scenes: missingTextFree.slice(0, 8) } : null,
      missingTextFree.length ? "Add text-free/no-readable-text wording so labels stay renderer-controlled." : null,
    ),
  );

  const missingReferences = scenes
    .filter(
      (scene) =>
        shouldGenerateReferenceImage(scene) &&
        !scene?.referenceImageAsset &&
        !scene?.reference_image_asset &&
        !scene?.rasterReveal &&
        !scene?.raster_reveal &&
        !sceneLocalImageBuffer(scene),
    )
    .map((scene) => scene?.id ?? scene?.title ?? "scene");
  checks.push(
    qaCheck(
      "reference_images",
      missingReferences.length === 0,
      missingReferences.length ? "warning" : "info",
      missingReferences.length
        ? `${missingReferences.length} direct/hybrid scene(s) have no reference image asset`
        : "Direct/hybrid scenes have reference image assets or local images",
      missingReferences.length ? { scenes: missingReferences.slice(0, 8) } : null,
      missingReferences.length ? "Regenerate scene images or check Seedream credentials and /imagegen/scenes logs." : null,
    ),
  );

  const topicBlob = String(storyboard?.topic ?? "").toLowerCase();
  const isMapo = /mapo|麻婆|豆腐|tofu/.test(topicBlob);
  if (isMapo) {
    const promptBlob = scenes
      .map((scene) => `${scene?.title ?? ""} ${scene?.image_description ?? scene?.imageDescription ?? ""}`)
      .join(" ")
      .toLowerCase();
    const cookingNeedles = ["wok", "red", "tofu", "minced", "scallion"];
    const missing = cookingNeedles.filter((needle) => !promptBlob.includes(needle));
    checks.push(
      qaCheck(
        "mapo_visual_terms",
        missing.length === 0,
        missing.length ? "warning" : "info",
        missing.length
          ? `Mapo tofu storyboard is missing cooking visual terms: ${missing.join(", ")}`
          : "Mapo tofu storyboard contains key cooking visual terms",
        missing.length ? { missing } : null,
        missing.length ? "Regenerate/repair images with red chili oil, tofu cubes, minced meat, scallions, steam, and a wide wok." : null,
      ),
    );
  }

  return checks;
}

async function extractQaFrame(videoPath, durationSeconds, jobId) {
  const framePath = join(OUTPUT_DIR, `${jobId}_qa_frame.png`);
  const seekAt = Math.max(0.2, Math.min(Math.max(0.2, durationSeconds * 0.5), 3));
  await execFileAsync(
    FFMPEG_BINARY,
    ["-y", "-ss", String(seekAt), "-i", videoPath, "-frames:v", "1", "-vf", "scale=320:-1", framePath],
    { windowsHide: true, timeout: 60000 },
  );
  return framePath;
}

async function analyzeFrameNonBlank(framePath) {
  const image = sharp(framePath).ensureAlpha().raw();
  const { data, info } = await image.toBuffer({ resolveWithObject: true });
  const pixels = Math.max(1, info.width * info.height);
  let sum = 0;
  let sumSquares = 0;
  let opaque = 0;
  for (let offset = 0; offset < data.length; offset += 4) {
    const alpha = data[offset + 3] / 255;
    const brightness = (data[offset] + data[offset + 1] + data[offset + 2]) / 3;
    sum += brightness;
    sumSquares += brightness * brightness;
    if (alpha > 0.05) opaque += 1;
  }
  const mean = sum / pixels;
  const variance = Math.max(0, sumSquares / pixels - mean * mean);
  return {
    width: info.width,
    height: info.height,
    meanBrightness: Math.round(mean * 10) / 10,
    brightnessStdDev: Math.round(Math.sqrt(variance) * 10) / 10,
    opaqueRatio: Math.round((opaque / pixels) * 1000) / 1000,
  };
}

async function runRenderQa(jobId, outputPath, storyboard) {
  updateJob(jobId, { phase: "qa", progress: 100 });
  const checks = [];
  const suggestions = [];
  const addCheck = (check) => {
    checks.push(check);
    if (!check.ok && check.suggestion) suggestions.push(check.suggestion);
  };

  const exists = existsSync(outputPath);
  const fileSize = exists ? statSync(outputPath).size : 0;
  addCheck(
    qaCheck(
      "output_file",
      exists && fileSize >= MIN_RENDER_OUTPUT_BYTES,
      "error",
      exists ? `Output file size is ${fileSize} bytes` : "Output video file is missing",
      { fileSizeBytes: fileSize, minBytes: MIN_RENDER_OUTPUT_BYTES },
      "Render again and inspect Remotion/ffmpeg logs; the output file was missing or too small.",
    ),
  );
  if (!exists) {
    const result = {
      ok: false,
      checkedAt: new Date().toISOString(),
      checks,
      suggestions: [...new Set(suggestions)],
    };
    updateJob(jobId, { qa: result });
    throw new Error("Render QA failed: Output video file is missing");
  }

  let mediaInfo = null;
  try {
    mediaInfo = await probeMediaInfo(outputPath);
    addCheck(
      qaCheck(
        "video_stream",
        mediaInfo.hasVideo && mediaInfo.durationSeconds > 0,
        "error",
        `Video duration is ${Math.round(mediaInfo.durationSeconds * 10) / 10}s`,
        { durationSeconds: mediaInfo.durationSeconds, hasVideo: mediaInfo.hasVideo },
        "Regenerate Remotion output; ffprobe could not find a playable video stream.",
      ),
    );
    addCheck(
      qaCheck(
        "audio_stream",
        mediaInfo.hasAudio,
        "error",
        mediaInfo.hasAudio ? "Audio stream exists" : "Rendered MP4 has no audio stream",
        null,
        "Retry TTS and render; audio is required and silent videos are blocked.",
      ),
    );

    const expectedDuration = storyboardExpectedDuration(storyboard);
    if (expectedDuration > 0 && mediaInfo.durationSeconds > 0) {
      const delta = Math.abs(mediaInfo.durationSeconds - expectedDuration);
      const tolerance = Math.max(4, expectedDuration * 0.25);
      addCheck(
        qaCheck(
          "duration_match",
          delta <= tolerance,
          delta <= tolerance ? "info" : "warning",
          `Rendered duration ${Math.round(mediaInfo.durationSeconds)}s vs storyboard ${Math.round(expectedDuration)}s`,
          { renderedSeconds: mediaInfo.durationSeconds, storyboardSeconds: expectedDuration, deltaSeconds: delta },
          delta > tolerance ? "Review audio segment timings and scene duration estimates before publishing." : null,
        ),
      );
    }
  } catch (err) {
    addCheck(
      qaCheck(
        "ffprobe",
        false,
        "error",
        `ffprobe failed: ${err.message}`,
        null,
        "Check ffprobe installation and regenerate the MP4.",
      ),
    );
  }

  if (mediaInfo?.durationSeconds) {
    let framePath = null;
    try {
      framePath = await extractQaFrame(outputPath, mediaInfo.durationSeconds, jobId);
      const frame = await analyzeFrameNonBlank(framePath);
      const isNonBlank = frame.opaqueRatio > 0.9 && frame.brightnessStdDev >= MIN_RENDER_FRAME_STDDEV;
      addCheck(
        qaCheck(
          "nonblank_frame",
          isNonBlank,
          "error",
          isNonBlank
            ? `Frame has brightness stddev ${frame.brightnessStdDev}`
            : `Frame looks blank or flat; brightness stddev ${frame.brightnessStdDev}`,
          { ...frame, minStdDev: MIN_RENDER_FRAME_STDDEV },
          "Regenerate scene images/code; verify the composition renders visible board content and reference assets.",
        ),
      );
    } catch (err) {
      addCheck(
        qaCheck(
          "frame_extract",
          false,
          "error",
          `Could not extract QA frame: ${err.message}`,
          null,
          "Check ffmpeg installation and render again.",
        ),
      );
    } finally {
      if (framePath) {
        try {
          unlinkSync(framePath);
        } catch {}
      }
    }
  }

  for (const check of collectStoryboardQaChecks(storyboard)) addCheck(check);

  const blockingFailures = checks.filter((check) => !check.ok && check.severity === "error");
  const result = {
    ok: blockingFailures.length === 0,
    checkedAt: new Date().toISOString(),
    durationSeconds: mediaInfo?.durationSeconds ?? null,
    hasAudio: mediaInfo?.hasAudio ?? null,
    fileSizeBytes: fileSize,
    checks,
    suggestions: [...new Set(suggestions)],
  };
  updateJob(jobId, { qa: result });
  if (!result.ok) {
    throw new Error(`Render QA failed: ${blockingFailures.map((check) => check.message).slice(0, 3).join("; ")}`);
  }
  return result;
}

function normalizeBase64Image(value) {
  const text = String(value ?? "").trim();
  const comma = text.indexOf(",");
  return comma >= 0 && text.slice(0, comma).includes("base64") ? text.slice(comma + 1) : text;
}

function samplePath(path, maxPoints = 80) {
  if (path.length <= maxPoints) return path;
  const sampled = [];
  const step = (path.length - 1) / (maxPoints - 1);
  for (let i = 0; i < maxPoints; i += 1) {
    sampled.push(path[Math.round(i * step)]);
  }
  return sampled;
}

function traceEdgePaths(edge, width, height, maxPaths) {
  const visited = new Uint8Array(edge.length);
  const offsets = [
    [-1, -1],
    [0, -1],
    [1, -1],
    [-1, 0],
    [1, 0],
    [-1, 1],
    [0, 1],
    [1, 1],
  ];
  const paths = [];

  const edgeNeighbors = (x, y) => {
    const neighbors = [];
    for (const [dx, dy] of offsets) {
      const nx = x + dx;
      const ny = y + dy;
      if (nx < 0 || ny < 0 || nx >= width || ny >= height) continue;
      const nextIndex = ny * width + nx;
      if (edge[nextIndex]) neighbors.push(nextIndex);
    }
    return neighbors;
  };

  for (let startIndex = 0; startIndex < edge.length && paths.length < maxPaths; startIndex += 1) {
    if (!edge[startIndex] || visited[startIndex]) continue;
    let current = startIndex;
    const path = [];
    let previous = -1;

    while (current >= 0 && !visited[current] && path.length < 1600) {
      visited[current] = 1;
      const x = current % width;
      const y = Math.floor(current / width);
      path.push({ x, y });

      const candidates = edgeNeighbors(x, y).filter((index) => !visited[index]);
      if (candidates.length === 0) break;
      if (previous < 0 || candidates.length === 1) {
        previous = current;
        current = candidates[0];
        continue;
      }

      const px = previous % width;
      const py = Math.floor(previous / width);
      const vx = x - px;
      const vy = y - py;
      let best = candidates[0];
      let bestScore = -Infinity;
      for (const candidate of candidates) {
        const cx = candidate % width;
        const cy = Math.floor(candidate / width);
        const score = vx * (cx - x) + vy * (cy - y);
        if (score > bestScore) {
          best = candidate;
          bestScore = score;
        }
      }
      previous = current;
      current = best;
    }

    if (path.length >= 10) paths.push(path);
  }

  return paths;
}

async function traceWhiteboardImageBuffer(image) {
  const { data, info } = await sharp(image, { failOn: "none" })
    .resize({ width: 420, height: 260, fit: "inside", withoutEnlargement: true })
    .flatten({ background: "#ffffff" })
    .grayscale()
    .raw()
    .toBuffer({ resolveWithObject: true });

  const { width, height } = info;
  const mask = new Uint8Array(width * height);
  let darkPixels = 0;
  for (let i = 0; i < width * height; i += 1) {
    if (data[i] < 196) {
      mask[i] = 1;
      darkPixels += 1;
    }
  }
  if (darkPixels < 40) return [];

  const edge = new Uint8Array(mask.length);
  for (let y = 1; y < height - 1; y += 1) {
    for (let x = 1; x < width - 1; x += 1) {
      const index = y * width + x;
      if (!mask[index]) continue;
      if (
        !mask[index - 1] ||
        !mask[index + 1] ||
        !mask[index - width] ||
        !mask[index + width]
      ) {
        edge[index] = 1;
      }
    }
  }

  return traceEdgePaths(edge, width, height, IMAGE_TRACE_MAX_PATHS)
    .sort((a, b) => b.length - a.length)
    .slice(0, IMAGE_TRACE_MAX_PATHS)
    .map((path) =>
      samplePath(path, 90).map((point) => ({
        x: Number((point.x / Math.max(1, width - 1)).toFixed(4)),
        y: Number((point.y / Math.max(1, height - 1)).toFixed(4)),
      })),
    )
    .filter((path) => path.length >= 2);
}

async function traceWhiteboardImageBase64(imageBase64) {
  return traceWhiteboardImageBuffer(Buffer.from(normalizeBase64Image(imageBase64), "base64"));
}

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function safeAssetSegment(value, fallback) {
  return (
    String(value ?? fallback)
      .normalize("NFKC")
      .replace(/[^a-zA-Z0-9_-]+/g, "_")
      .replace(/^_+|_+$/g, "")
      .slice(0, 80) || fallback
  );
}

function isProbablyBase64Image(value) {
  const text = String(value ?? "").trim();
  if (text.startsWith("data:image/")) return true;
  if (text.length < 120) return false;
  return /^[a-zA-Z0-9+/=\r\n]+$/.test(text);
}

function sceneTextForStrategy(scene) {
  return [
    scene?.title,
    scene?.image_description,
    scene?.imageDescription,
    scene?.learning_goal,
    scene?.learningGoal,
    scene?.render_strategy,
    scene?.renderStrategy,
    scene?.visual_complexity,
    scene?.visualComplexity,
    scene?.board_mode,
    scene?.boardMode,
    scene?.hand_usage,
    scene?.handUsage,
    scene?.video_style,
    scene?.videoStyle,
    scene?.visual_style,
    scene?.visualStyle,
    scene?.teacher_board_strategy,
    scene?.teacherBoardStrategy,
    scene?.diagram_plan?.kind,
    scene?.diagramPlan?.kind,
    scene?.diagram_plan?.layout,
    scene?.diagramPlan?.layout,
    ...(Array.isArray(scene?.diagram_plan?.required_labels) ? scene.diagram_plan.required_labels : []),
    ...(Array.isArray(scene?.diagramPlan?.requiredLabels) ? scene.diagramPlan.requiredLabels : []),
    ...(Array.isArray(scene?.visual_beats) ? scene.visual_beats : []).flatMap((beat) => [
      beat?.draw_intent,
      beat?.drawIntent,
      beat?.narration,
      ...(Array.isArray(beat?.required_labels) ? beat.required_labels : []),
      ...(Array.isArray(beat?.requiredLabels) ? beat.requiredLabels : []),
    ]),
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
}

function countPatternMatches(text, patterns) {
  return patterns.reduce((sum, pattern) => sum + (pattern.test(text) ? 1 : 0), 0);
}

function countSceneLabels(scene) {
  const labels = new Set();
  const add = (value) => {
    const label = String(value ?? "").trim().toLowerCase();
    if (label) labels.add(label);
  };
  for (const label of scene?.diagram_plan?.required_labels ?? []) add(label);
  for (const label of scene?.diagramPlan?.requiredLabels ?? []) add(label);
  for (const beat of scene?.visual_beats ?? []) {
    for (const label of beat?.required_labels ?? []) add(label);
    for (const label of beat?.requiredLabels ?? []) add(label);
  }
  const quotedLabels = sceneTextForStrategy(scene).match(/'[^']{1,28}'|"[^"]{1,28}"/g) ?? [];
  for (const label of quotedLabels) add(label.slice(1, -1));
  return labels.size;
}

function explicitRasterStrategy(scene) {
  const value = String(
    scene?.render_strategy ??
      scene?.renderStrategy ??
      scene?.raster_render_strategy ??
      scene?.rasterRenderStrategy ??
      scene?.teacher_board_strategy ??
      scene?.teacherBoardStrategy ??
      scene?.diagram_plan?.render_strategy ??
      scene?.diagramPlan?.renderStrategy ??
      "",
  )
    .trim()
    .toLowerCase();
  if (!value) return null;
  if (/(direct|finished|static|reference|present|photo|show)/i.test(value)) return "direct";
  if (/(trace|progressive|draw|write|stroke|reveal|board)/i.test(value)) return "trace";
  if (/(hybrid|mixed|annotation|callout)/i.test(value)) return "direct";
  return null;
}

function sceneBoardMode(scene) {
  return String(scene?.board_mode ?? scene?.boardMode ?? "").trim().toLowerCase();
}

function sceneHandUsage(scene) {
  return String(scene?.hand_usage ?? scene?.handUsage ?? "").trim().toLowerCase();
}

function sceneVideoStyle(scene, storyboard = null) {
  const raw = String(
    scene?.video_style ?? scene?.videoStyle ?? storyboard?.video_style ?? storyboard?.videoStyle ?? "",
  )
    .trim()
    .toLowerCase();
  const style = VIDEO_STYLE_ALIASES.get(raw) ?? raw;
  return GOLPO_VIDEO_STYLES.has(style) ? style : "whiteboard";
}

function sceneVisualStyle(scene) {
  return String(scene?.visual_style ?? scene?.visualStyle ?? "").trim().toLowerCase();
}

function sceneShouldDirectRender(scene, trace) {
  if (SEEDREAM_REFERENCE_RENDER_MODE === "direct") return true;
  const videoStyle = sceneVideoStyle(scene);
  if (sceneHandUsage(scene) === "annotate") return true;
  if (sceneBoardMode(scene) === "reference" || sceneVisualStyle(scene) === "technical_reference") return true;
  if (sceneBoardMode(scene) === "clean_canvas" || sceneVisualStyle(scene) === "marketing_doodle") return true;
  if (["technical_blueprint", "editorial", "whiteboard", "playful", "sharpie"].includes(videoStyle)) return true;
  if (videoStyle === "modern_minimal" && sceneHandUsage(scene) !== "trace") return true;
  if (sceneBoardMode(scene) === "chalkboard" || sceneVisualStyle(scene) === "math_chalkboard") return false;
  const explicit = explicitRasterStrategy(scene);
  if (explicit === "direct") return true;
  if (explicit === "trace") return false;

  const text = sceneTextForStrategy(scene);
  const strokeCount = Number(trace?.strokes?.length ?? 0);
  const skeletonPixels = Number(trace?.skeletonPixels ?? 0);
  const maskCoverage = Number(trace?.maskCoverage ?? 0);
  const labelCount = countSceneLabels(scene);
  const beatCount = Array.isArray(scene?.visual_beats) ? scene.visual_beats.length : 0;

  const boardworkScore =
    countPatternMatches(text, [
      /\b(simple|schematic|line[-\s]?art|line diagram|whiteboard|sketch|diagram|flowchart|process|comparison|before|after|curve|axis|graph|formula|equation|single|two[-\s]?panel)\b/i,
      /(简单|示意|线稿|白板|草图|流程|对比|曲线|坐标轴|公式|单图|双图|少量|板书)/i,
      /\b(cross[-\s]?section|section view)\b/i,
    ]) +
    (beatCount >= 2 && beatCount <= 5 ? 1 : 0) +
    (labelCount <= 8 ? 1 : 0);

  const denseReferenceScore =
    countPatternMatches(text, [
      /\b(photo|realistic|reference|finished|full[-\s]?image|object|portrait|screenshot|map|cad|render|scan|microscope|medical|anatomy|isometric|3d|three[-\s]?dimensional|cutaway|exploded|multi[-\s]?layer|many labels|dense|detailed|complex)\b/i,
      /(照片|真实|参考图|成品图|直接呈现|实物|截图|地图|扫描|显微|医学|解剖|三维|立体|剖切|爆炸图|多层|密集|复杂|细节很多|标签很多)/i,
      /\b(left|center|right)\s*:/i,
      /(左[：:]|中[：:]|右[：:])/i,
    ]) + (labelCount >= 10 ? 1 : 0);

  const metricComplexity =
    (strokeCount >= DIRECT_IMAGE_STROKE_THRESHOLD ? 1 : 0) +
    (skeletonPixels >= 12000 ? 1 : 0) +
    (maskCoverage >= 0.115 ? 1 : 0);
  const extremeComplexity = skeletonPixels >= 24000 || maskCoverage >= 0.18;

  if (extremeComplexity && boardworkScore < 3) return true;
  if (denseReferenceScore >= 2 && (metricComplexity >= 1 || boardworkScore < 3)) return true;
  if (boardworkScore >= 3 && skeletonPixels <= 18000 && maskCoverage <= 0.14) return false;
  if (denseReferenceScore > boardworkScore && metricComplexity >= 1) return true;
  return metricComplexity >= 2;
}

function shouldGenerateReferenceImage(scene) {
  if (!ENABLE_SEEDREAM_REFERENCE_IMAGES) return false;
  const boardMode = sceneBoardMode(scene);
  const videoStyle = sceneVideoStyle(scene);
  const visualStyle = sceneVisualStyle(scene);
  const handUsage = sceneHandUsage(scene);
  const explicit = explicitRasterStrategy(scene);
  if (handUsage === "none") return false;
  if (boardMode === "chalkboard" || visualStyle === "math_chalkboard") return false;
  if (explicit === "direct") return true;
  if (["modern_minimal", "technical_blueprint", "editorial", "whiteboard", "playful", "sharpie"].includes(videoStyle)) {
    return true;
  }
  if (ENABLE_SEEDREAM_REFERENCE_IMAGES && scene?.image_description) return true;
  if (boardMode === "whiteboard" && visualStyle === "teacher_whiteboard" && handUsage === "trace") {
    return explicit === "direct";
  }
  if (boardMode === "reference" || boardMode === "clean_canvas") return true;
  if (visualStyle === "technical_reference" || visualStyle === "marketing_doodle") return true;

  const complexity = String(scene?.visual_complexity ?? scene?.visualComplexity ?? "").toLowerCase();
  if (complexity === "dense" || complexity === "reference") return true;

  const text = sceneTextForStrategy(scene);
  const labelCount = countSceneLabels(scene);
  const wantsFinishedSubject = countPatternMatches(text, [
    /\b(reference|photo|screenshot|finished|full[-\s]?image|3d|isometric|technical drawing|cad|anatomy|medical|mechanical|circuit|realistic|product interface)\b/i,
    /(参考图|成品图|截图|三维|立体|技术图|医学|解剖|机械|电路|真实|产品界面|复杂主体|直接呈现)/i,
  ]);
  return wantsFinishedSubject > 0 || labelCount >= 12;
}

function sceneLocalImageBuffer(scene) {
  const candidates = [
    scene.reference_image_path,
    scene.referenceImagePath,
    scene.image_path,
    scene.imagePath,
    scene.image_url,
    scene.imageUrl,
    scene.reference_image_base64,
    scene.referenceImageBase64,
    scene.image_base64,
    scene.imageBase64,
  ].filter(Boolean);

  for (const candidate of candidates) {
    const value = String(candidate).trim();
    if (!value) continue;
    if (isProbablyBase64Image(value)) {
      try {
        return Buffer.from(normalizeBase64Image(value), "base64");
      } catch {}
    }
    if (/^https?:\/\//i.test(value)) continue;

    const possiblePaths = [resolve(value), resolve(__dirname, "../..", value)];
    for (const possiblePath of possiblePaths) {
      if (existsSync(possiblePath)) {
        return readFileSync(possiblePath);
      }
    }
  }
  return null;
}

function pixelNeighbors(index, width, height, pixels) {
  const x = index % width;
  const y = Math.floor(index / width);
  const neighbors = [];
  for (let dy = -1; dy <= 1; dy += 1) {
    for (let dx = -1; dx <= 1; dx += 1) {
      if (dx === 0 && dy === 0) continue;
      const nx = x + dx;
      const ny = y + dy;
      if (nx < 0 || ny < 0 || nx >= width || ny >= height) continue;
      const next = ny * width + nx;
      if (pixels[next]) neighbors.push(next);
    }
  }
  return neighbors;
}

function cleanMaskComponents(mask, width, height) {
  const visited = new Uint8Array(mask.length);
  const cleaned = new Uint8Array(mask.length);
  const stack = [];
  for (let start = 0; start < mask.length; start += 1) {
    if (!mask[start] || visited[start]) continue;
    const component = [];
    visited[start] = 1;
    stack.push(start);
    while (stack.length > 0) {
      const current = stack.pop();
      component.push(current);
      for (const next of pixelNeighbors(current, width, height, mask)) {
        if (visited[next]) continue;
        visited[next] = 1;
        stack.push(next);
      }
    }
    if (component.length >= 5) {
      for (const index of component) cleaned[index] = 1;
    }
  }
  return cleaned;
}

function zhangSuenThin(mask, width, height) {
  const image = new Uint8Array(mask);
  const toRemove = [];
  const transitions = (p2, p3, p4, p5, p6, p7, p8, p9) => {
    const values = [p2, p3, p4, p5, p6, p7, p8, p9, p2];
    let count = 0;
    for (let i = 0; i < values.length - 1; i += 1) {
      if (values[i] === 0 && values[i + 1] === 1) count += 1;
    }
    return count;
  };

  let changed = true;
  let iterations = 0;
  while (changed && iterations < 80) {
    changed = false;
    iterations += 1;

    for (let pass = 0; pass < 2; pass += 1) {
      toRemove.length = 0;
      for (let y = 1; y < height - 1; y += 1) {
        for (let x = 1; x < width - 1; x += 1) {
          const i = y * width + x;
          if (!image[i]) continue;
          const p2 = image[i - width] ? 1 : 0;
          const p3 = image[i - width + 1] ? 1 : 0;
          const p4 = image[i + 1] ? 1 : 0;
          const p5 = image[i + width + 1] ? 1 : 0;
          const p6 = image[i + width] ? 1 : 0;
          const p7 = image[i + width - 1] ? 1 : 0;
          const p8 = image[i - 1] ? 1 : 0;
          const p9 = image[i - width - 1] ? 1 : 0;
          const neighborCount = p2 + p3 + p4 + p5 + p6 + p7 + p8 + p9;
          if (neighborCount < 2 || neighborCount > 6) continue;
          if (transitions(p2, p3, p4, p5, p6, p7, p8, p9) !== 1) continue;
          if (pass === 0) {
            if (p2 * p4 * p6 !== 0 || p4 * p6 * p8 !== 0) continue;
          } else if (p2 * p4 * p8 !== 0 || p2 * p6 * p8 !== 0) {
            continue;
          }
          toRemove.push(i);
        }
      }
      if (toRemove.length > 0) {
        changed = true;
        for (const index of toRemove) image[index] = 0;
      }
    }
  }
  return image;
}

function edgeKey(a, b) {
  return a < b ? `${a}:${b}` : `${b}:${a}`;
}

function pathMetrics(path) {
  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  let length = 0;
  for (let i = 0; i < path.length; i += 1) {
    const point = path[i];
    minX = Math.min(minX, point.x);
    minY = Math.min(minY, point.y);
    maxX = Math.max(maxX, point.x);
    maxY = Math.max(maxY, point.y);
    if (i > 0) length += distance(path[i - 1], point);
  }
  return {
    minX,
    minY,
    maxX,
    maxY,
    length,
    centerX: (minX + maxX) / 2,
    centerY: (minY + maxY) / 2,
  };
}

function traceSkeletonPaths(skeleton, width, height) {
  const indices = [];
  const degrees = new Map();
  for (let i = 0; i < skeleton.length; i += 1) {
    if (!skeleton[i]) continue;
    indices.push(i);
    degrees.set(i, pixelNeighbors(i, width, height, skeleton).length);
  }

  const visitedEdges = new Set();
  const paths = [];
  const pointForIndex = (index) => ({ x: index % width, y: Math.floor(index / width) });
  const walk = (start, next) => {
    const path = [pointForIndex(start)];
    let previous = start;
    let current = next;
    let guard = 0;
    while (guard < 4000) {
      guard += 1;
      visitedEdges.add(edgeKey(previous, current));
      path.push(pointForIndex(current));
      const degree = degrees.get(current) ?? 0;
      if (degree !== 2) break;
      const candidates = pixelNeighbors(current, width, height, skeleton).filter(
        (candidate) => candidate !== previous,
      );
      const candidate = candidates.find((value) => !visitedEdges.has(edgeKey(current, value)));
      if (candidate === undefined) break;
      previous = current;
      current = candidate;
    }
    if (path.length >= 2) paths.push(path);
  };

  const starts = indices
    .filter((index) => (degrees.get(index) ?? 0) !== 2)
    .sort((a, b) => Math.floor(a / width) - Math.floor(b / width) || (a % width) - (b % width));

  for (const start of starts) {
    for (const next of pixelNeighbors(start, width, height, skeleton)) {
      if (!visitedEdges.has(edgeKey(start, next))) walk(start, next);
    }
  }

  for (const start of indices) {
    for (const next of pixelNeighbors(start, width, height, skeleton)) {
      if (!visitedEdges.has(edgeKey(start, next))) walk(start, next);
    }
  }

  return paths;
}

function perpendicularDistanceToLine(point, start, end) {
  const dx = end.x - start.x;
  const dy = end.y - start.y;
  const denominator = dx * dx + dy * dy;
  if (denominator === 0) return distance(point, start);
  const t = clamp(((point.x - start.x) * dx + (point.y - start.y) * dy) / denominator, 0, 1);
  return distance(point, { x: start.x + dx * t, y: start.y + dy * t });
}

function simplifyPolyline(points, epsilon = 1.25) {
  if (points.length <= 3) return points;
  let maxDistance = 0;
  let index = 0;
  const start = points[0];
  const end = points[points.length - 1];
  for (let i = 1; i < points.length - 1; i += 1) {
    const value = perpendicularDistanceToLine(points[i], start, end);
    if (value > maxDistance) {
      index = i;
      maxDistance = value;
    }
  }
  if (maxDistance <= epsilon) return [start, end];
  const left = simplifyPolyline(points.slice(0, index + 1), epsilon);
  const right = simplifyPolyline(points.slice(index), epsilon);
  return left.slice(0, -1).concat(right);
}

function distanceToBackground(mask, width, height, x, y, maxRadius = 18) {
  const cx = Math.round(x);
  const cy = Math.round(y);
  for (let radius = 1; radius <= maxRadius; radius += 1) {
    for (let dy = -radius; dy <= radius; dy += 1) {
      for (let dx = -radius; dx <= radius; dx += 1) {
        if (Math.abs(dx) !== radius && Math.abs(dy) !== radius) continue;
        const nx = cx + dx;
        const ny = cy + dy;
        if (nx < 0 || ny < 0 || nx >= width || ny >= height) return radius;
        if (!mask[ny * width + nx]) return radius;
      }
    }
  }
  return maxRadius;
}

function estimateRevealWidth(mask, width, height, path) {
  const samples = [];
  const sampleCount = Math.min(28, path.length);
  for (let i = 0; i < sampleCount; i += 1) {
    const point = path[Math.round((i * (path.length - 1)) / Math.max(1, sampleCount - 1))];
    samples.push(distanceToBackground(mask, width, height, point.x, point.y));
  }
  samples.sort((a, b) => a - b);
  const median = samples[Math.floor(samples.length / 2)] || 2;
  const pixelWidth = clamp(median * 4 + 76, 72, 128);
  return Number((pixelWidth / Math.max(width, height)).toFixed(5));
}

function selectRevealPaths(paths, maxPaths, width, height) {
  if (paths.length <= maxPaths) return paths;
  const bands = 8;
  const byBand = Array.from({ length: bands }, () => []);
  for (const path of paths) {
    const metric = pathMetrics(path);
    const band = clamp(Math.floor((metric.centerY / Math.max(1, height)) * bands), 0, bands - 1);
    byBand[band].push({ path, metric });
  }

  const selected = new Set();
  const perBand = Math.max(5, Math.floor(maxPaths / bands));
  for (const band of byBand) {
    band.sort((a, b) => b.metric.length - a.metric.length);
    for (const item of band.slice(0, perBand)) selected.add(item.path);
  }

  const remaining = paths
    .filter((path) => !selected.has(path))
    .map((path) => ({ path, metric: pathMetrics(path) }))
    .sort((a, b) => b.metric.length - a.metric.length);
  for (const item of remaining) {
    if (selected.size >= maxPaths) break;
    selected.add(item.path);
  }

  return paths.filter((path) => selected.has(path));
}

function sortRevealPaths(paths) {
  const pending = paths.map((path, id) => ({ id, path, metric: pathMetrics(path) }));
  pending.sort((a, b) => a.metric.minY - b.metric.minY || a.metric.minX - b.metric.minX);
  const sorted = [];
  let current = pending.shift();
  while (current) {
    sorted.push(current.path);
    const end = current.path[current.path.length - 1];
    if (pending.length === 0) break;
    let bestIndex = 0;
    let bestScore = Infinity;
    const searchLimit = Math.min(36, pending.length);
    for (let i = 0; i < searchLimit; i += 1) {
      const candidate = pending[i];
      const start = candidate.path[0];
      const score =
        distance(end, start) +
        Math.abs(candidate.metric.centerY - current.metric.centerY) * 0.35 +
        Math.max(0, candidate.metric.minY - current.metric.minY) * 0.12;
      if (score < bestScore) {
        bestScore = score;
        bestIndex = i;
      }
    }
    current = pending.splice(bestIndex, 1)[0];
  }
  return sorted;
}

async function traceRasterRevealImage(imageBuffer) {
  const { data, info } = await sharp(imageBuffer, { failOn: "none" })
    .resize({
      width: RASTER_REVEAL_TRACE_WIDTH,
      height: RASTER_REVEAL_TRACE_HEIGHT,
      fit: "inside",
      withoutEnlargement: false,
    })
    .flatten({ background: "#ffffff" })
    .grayscale()
    .raw()
    .toBuffer({ resolveWithObject: true });

  const { width, height } = info;
  const mask = new Uint8Array(width * height);
  let darkPixels = 0;
  for (let i = 0; i < width * height; i += 1) {
    if (data[i] < 205) {
      mask[i] = 1;
      darkPixels += 1;
    }
  }
  if (darkPixels < 40) {
    return { strokes: [], traceWidth: width, traceHeight: height, darkPixels, skeletonPixels: 0 };
  }

  const cleanMask = cleanMaskComponents(mask, width, height);
  const skeleton = zhangSuenThin(cleanMask, width, height);
  let skeletonPixels = 0;
  for (const value of skeleton) {
    if (value) skeletonPixels += 1;
  }

  const rawPaths = traceSkeletonPaths(skeleton, width, height)
    .map((path) => simplifyPolyline(path, 1.35))
    .filter((path) => path.length >= 2 && pathMetrics(path).length >= 4);

  const selected = sortRevealPaths(selectRevealPaths(rawPaths, RASTER_REVEAL_MAX_STROKES, width, height));
  const strokes = selected
    .map((path, index) => {
      const sampled = samplePath(path, 86);
      const lengthPx = polylineLength(sampled);
      return {
        id: `reveal_${index}`,
        points: sampled.map((point) => ({
          x: Number((point.x / Math.max(1, width - 1)).toFixed(4)),
          y: Number((point.y / Math.max(1, height - 1)).toFixed(4)),
        })),
        revealWidth: estimateRevealWidth(cleanMask, width, height, path),
        dashLength: Number((lengthPx / Math.max(width, height)).toFixed(4)),
      };
    })
    .filter((stroke) => stroke.points.length >= 2);

  return {
    strokes,
    traceWidth: width,
    traceHeight: height,
    darkPixels,
    skeletonPixels,
    maskCoverage: Number((darkPixels / Math.max(1, width * height)).toFixed(5)),
  };
}

async function makeTransparentLineArtAsset(imageBuffer) {
  const { data, info } = await sharp(imageBuffer, { failOn: "none" })
    .rotate()
    .resize({
      width: RASTER_REVEAL_ASSET_MAX_SIZE,
      height: RASTER_REVEAL_ASSET_MAX_SIZE,
      fit: "inside",
      withoutEnlargement: true,
    })
    .flatten({ background: "#ffffff" })
    .raw()
    .toBuffer({ resolveWithObject: true });

  const { width, height, channels } = info;
  const rgba = Buffer.alloc(width * height * 4);
  for (let i = 0; i < width * height; i += 1) {
    const source = i * channels;
    const target = i * 4;
    const r = data[source];
    const g = data[source + 1];
    const b = data[source + 2];
    const luminance = 0.299 * r + 0.587 * g + 0.114 * b;
    const chroma = Math.max(r, g, b) - Math.min(r, g, b);
    const darkAlpha = clamp(Math.round((225 - luminance) * 6.0), 0, 255);
    const colorInkAlpha =
      chroma > 70 && luminance < 235
        ? clamp(Math.round((chroma - 45) * 3.5 + (235 - luminance) * 1.4), 0, 255)
        : 0;
    const paperLike = luminance > 230 && chroma < 75;
    const alpha = paperLike ? 0 : Math.max(darkAlpha, colorInkAlpha);
    rgba[target] = alpha === 0 ? 255 : r;
    rgba[target + 1] = alpha === 0 ? 255 : g;
    rgba[target + 2] = alpha === 0 ? 255 : b;
    rgba[target + 3] = alpha;
  }

  const buffer = await sharp(rgba, {
    raw: {
      width,
      height,
      channels: 4,
    },
  })
    .png({ compressionLevel: 9 })
    .toBuffer();

  return { buffer, width, height };
}

async function buildRasterRevealFromBuffer(imageBuffer, jobId, scene) {
  const assetDir = join(PUBLIC_GENERATED_DIR, jobId);
  mkdirSync(assetDir, { recursive: true });

  const transparentAsset = await makeTransparentLineArtAsset(imageBuffer);
  const assetBuffer = transparentAsset.buffer;
  const sceneId = scene?.id ?? "scene";
  const safeSceneId = safeAssetSegment(sceneId, "scene");
  const filename = `${safeSceneId}.png`;
  writeFileSync(join(assetDir, filename), assetBuffer);

  const trace = await traceRasterRevealImage(assetBuffer);
  if (trace.strokes.length < 6) {
    throw new Error(`raster reveal produced too few path(s): ${trace.strokes.length}`);
  }

  const asset = `generated/${jobId}/${filename}`;
  const renderMode = sceneShouldDirectRender(scene, trace) ? "direct" : "trace";
  return {
    referenceImageAsset: asset,
    rasterReveal: {
      asset,
      renderMode,
      imageWidth: transparentAsset.width,
      imageHeight: transparentAsset.height,
      transparentBackground: true,
      traceWidth: trace.traceWidth,
      traceHeight: trace.traceHeight,
      maskCoverage: trace.maskCoverage,
      skeletonPixels: trace.skeletonPixels,
      strokeCount: trace.strokes.length,
      strokes: renderMode === "direct" ? [] : trace.strokes,
    },
    trace_strokes: renderMode === "direct" ? [] : trace.strokes.map((stroke) => stroke.points),
  };
}

async function injectImageTraces(storyboard, jobId) {
  if (SKIP_IMAGE_TRACE) {
    console.log("[image-trace] SKIP_IMAGE_TRACE enabled, skipping trace generation");
    return storyboard;
  }
  if (!ENABLE_IMAGE_TRACE || IMAGE_TRACE_MAX_SCENES <= 0) return storyboard;

  const rasterBySceneId = {};
  const tracesBySceneId = {};
  const localImageSceneIds = new Set();
  for (const scene of storyboard.scenes) {
    if (scene.rasterReveal || scene.raster_reveal) continue;
    const imageBuffer = sceneLocalImageBuffer(scene);
    if (!imageBuffer) continue;
    localImageSceneIds.add(scene.id);
    try {
      const raster = await buildRasterRevealFromBuffer(imageBuffer, jobId, scene);
      rasterBySceneId[scene.id] = raster;
      console.log(
        `[image-trace] ${scene.id}: ${raster.rasterReveal.renderMode} raster from local image, ${raster.rasterReveal.strokes.length} reveal path(s)`,
      );
    } catch (err) {
      console.warn(`[image-trace] ${scene.id}: local raster reveal skipped: ${err.message}`);
      const traceStrokes = await traceWhiteboardImageBuffer(imageBuffer);
      if (traceStrokes.length > 0) {
        tracesBySceneId[scene.id] = traceStrokes;
        console.log(`[image-trace] ${scene.id}: ${traceStrokes.length} local fallback drawable path(s)`);
      }
    }
  }

  const candidates = storyboard.scenes
    .filter(
      (scene) =>
        scene.image_description &&
        shouldGenerateReferenceImage(scene) &&
        sceneHandUsage(scene) !== "none" &&
        sceneBoardMode(scene) !== "chalkboard" &&
        sceneVisualStyle(scene) !== "math_chalkboard" &&
        !localImageSceneIds.has(scene.id) &&
        !rasterBySceneId[scene.id] &&
        !scene.rasterReveal &&
        !scene.raster_reveal &&
        !scene.trace_strokes &&
        !scene.traceStrokes,
    )
    .map((scene, index) => {
      const text = `${scene.title ?? ""} ${scene.learning_goal ?? ""} ${scene.image_description ?? ""} ${
        scene.diagram_plan?.kind ?? scene.diagramPlan?.kind ?? ""
      } ${scene.diagram_plan?.layout ?? scene.diagramPlan?.layout ?? ""}`.toLowerCase();
      const visualComplexity = String(scene.visual_complexity ?? scene.visualComplexity ?? "").toLowerCase();
      const strategy = String(scene.render_strategy ?? scene.renderStrategy ?? "").toLowerCase();
      const boardMode = String(scene.board_mode ?? scene.boardMode ?? "").toLowerCase();
      const handUsage = String(scene.hand_usage ?? scene.handUsage ?? "").toLowerCase();
      const videoStyle = sceneVideoStyle(scene, storyboard);
      const visualStyle = String(scene.visual_style ?? scene.visualStyle ?? "").toLowerCase();
      const visualRelationScore = countPatternMatches(text, [
        /\boverview(?:[_\s-]?map)?\b/i,
        /\bcomparison|compare|versus|before|after|state|contrast\b/i,
        /\bprocess|flow|mechanism|cause|effect|simulation|journey\b/i,
        /\bstructure|component|part[-\s]?whole|cross[-\s]?section\b/i,
        /\binteraction|relationship|mutual|communication|collaboration|exchange\b/i,
        /\btradeoff|priority|quadrant|2x2|matrix\b/i,
        /\bgoal|target|path|roadmap|milestone|backcast\b/i,
        /\bcycle|loop|feedback|iteration|renewal\b/i,
        /概览|地图|对比|状态|过程|流程|机制|因果|结构|组成|截面|互动|关系|协作|交换|取舍|优先|象限|目标|路径|路线|循环|闭环|反馈|迭代/i,
      ]);
      const score =
        (strategy === "hybrid" ? 5 : strategy === "direct" ? 4 : strategy === "trace" ? 1 : 0) +
        (handUsage === "annotate" ? 6 : 0) +
        (boardMode === "reference" ? 6 : 0) +
        (["technical_blueprint", "editorial", "whiteboard", "playful", "sharpie"].includes(videoStyle) ? 5 : 0) +
        (videoStyle === "modern_minimal" ? 3 : 0) +
        (visualStyle === "technical_reference" ? 6 : visualStyle === "marketing_doodle" ? 4 : 0) +
        (visualComplexity === "dense" || visualComplexity === "reference" ? 5 : visualComplexity === "medium" ? 2 : 0) +
        Math.min(6, visualRelationScore * 2) +
        (countSceneLabels(scene) >= 6 ? 3 : countSceneLabels(scene) >= 3 ? 1 : 0) -
        (/(summary|checklist|formula|equation|bullet|list|总结|清单|公式)/i.test(text) ? 2 : 0);
      return { scene, index, score };
    })
    .sort((a, b) => b.score - a.score || a.index - b.index)
    .slice(0, IMAGE_TRACE_MAX_SCENES)
    .map((item) => item.scene);
  if (
    candidates.length === 0 &&
    Object.keys(rasterBySceneId).length === 0 &&
    Object.keys(tracesBySceneId).length === 0
  ) {
    return storyboard;
  }

  try {
    let response = { images: {} };
    if (candidates.length > 0) {
      console.log(`[image-trace] Generating ${candidates.length} Seedream reference image(s)...`);
      response = await postJson(
        `${PYTHON_API}/imagegen/scenes`,
        {
          scenes: candidates.map((scene) => ({
            scene_id: scene.id,
            topic: storyboard.topic ?? "",
            title: scene.title ?? "",
            image_description: scene.image_description,
            board_mode: scene.board_mode ?? scene.boardMode ?? "whiteboard",
            hand_usage: scene.hand_usage ?? scene.handUsage ?? "trace",
            video_style: sceneVideoStyle(scene, storyboard),
            visual_style: scene.visual_style ?? scene.visualStyle ?? "teacher_whiteboard",
            pen_style: scene.pen_style ?? scene.penStyle ?? storyboard.pen_style ?? storyboard.penStyle ?? "marker",
          })),
        },
        180000,
      );
      const generatedCount = candidates.filter((scene) => response.images?.[scene.id]).length;
      if (REQUIRE_SEEDREAM_REFERENCE_IMAGES && generatedCount === 0) {
        throw new Error(
          `Seedream reference image generation returned 0/${candidates.length} images. Check ARK_API_KEY, ARK_BASE_URL, SEEDREAM_MODEL, and /imagegen/scenes logs.`,
        );
      }
      if (generatedCount < candidates.length) {
        console.warn(`[image-trace] Seedream returned ${generatedCount}/${candidates.length} reference image(s)`);
      }
    }

    for (const scene of candidates) {
      const imageBase64 = response.images?.[scene.id];
      if (!imageBase64) continue;
      try {
        const raster = await buildRasterRevealFromBuffer(
          Buffer.from(normalizeBase64Image(imageBase64), "base64"),
          jobId,
          scene,
        );
        rasterBySceneId[scene.id] = raster;
        console.log(
          `[image-trace] ${scene.id}: ${raster.rasterReveal.renderMode} raster from Seedream, ${raster.rasterReveal.strokes.length} reveal path(s)`,
        );
      } catch (err) {
        console.warn(`[image-trace] ${scene.id}: raster reveal skipped, falling back to SVG trace: ${err.message}`);
        const traceStrokes = await traceWhiteboardImageBase64(imageBase64);
        if (traceStrokes.length > 0) {
          tracesBySceneId[scene.id] = traceStrokes;
          console.log(`[image-trace] ${scene.id}: ${traceStrokes.length} drawable path(s)`);
        }
      }
    }

    if (Object.keys(tracesBySceneId).length === 0 && Object.keys(rasterBySceneId).length === 0) {
      return storyboard;
    }
    return {
      ...storyboard,
      scenes: storyboard.scenes.map((scene) => ({
        ...scene,
        ...(rasterBySceneId[scene.id] ?? {}),
        trace_strokes:
          rasterBySceneId[scene.id]?.trace_strokes ??
          tracesBySceneId[scene.id] ??
          scene.trace_strokes ??
          scene.traceStrokes ??
          null,
      })),
    };
  } catch (err) {
    console.warn(`[image-trace] Seedream trace skipped: ${err.message}`);
    if (Object.keys(rasterBySceneId).length === 0 && Object.keys(tracesBySceneId).length === 0) return storyboard;
    return {
      ...storyboard,
      scenes: storyboard.scenes.map((scene) => ({
        ...scene,
        ...(rasterBySceneId[scene.id] ?? {}),
        trace_strokes:
          rasterBySceneId[scene.id]?.trace_strokes ??
          tracesBySceneId[scene.id] ??
          scene.trace_strokes ??
          scene.traceStrokes ??
          null,
      })),
    };
  }
}

let glyphFontCache;
let latinGlyphFontCache;

function parseFontFile(fontPath) {
  const buffer = readFileSync(fontPath);
  const arrayBuffer = buffer.buffer.slice(buffer.byteOffset, buffer.byteOffset + buffer.byteLength);
  return opentype.parse(arrayBuffer);
}

function loadGlyphFont() {
  if (glyphFontCache !== undefined) return glyphFontCache;
  for (const fontPath of GLYPH_FONT_CANDIDATES) {
    if (!existsSync(fontPath)) continue;
    try {
      glyphFontCache = { font: parseFontFile(fontPath), fontPath };
      console.log(`[glyph] Loaded outline font: ${fontPath}`);
      return glyphFontCache;
    } catch (err) {
      console.warn(`[glyph] Failed to load outline font ${fontPath}:`, err.message);
    }
  }
  glyphFontCache = null;
  return glyphFontCache;
}

function loadLatinGlyphFont() {
  if (latinGlyphFontCache !== undefined) return latinGlyphFontCache;
  for (const fontPath of LATIN_GLYPH_FONT_CANDIDATES) {
    if (!existsSync(fontPath)) continue;
    try {
      latinGlyphFontCache = { font: parseFontFile(fontPath), fontPath };
      console.log(`[glyph] Loaded latin outline font: ${fontPath}`);
      return latinGlyphFontCache;
    } catch (err) {
      console.warn(`[glyph] Failed to load latin outline font ${fontPath}:`, err.message);
    }
  }
  latinGlyphFontCache = null;
  return latinGlyphFontCache;
}

function rounded(value, places = 1) {
  if (!Number.isFinite(value)) return 0;
  return Number(value.toFixed(places));
}

function addPoint(points, x, y) {
  const point = { x: rounded(x), y: rounded(y) };
  const prev = points[points.length - 1];
  if (!prev || prev.x !== point.x || prev.y !== point.y) {
    points.push(point);
  }
}

function distance(a, b) {
  return Math.hypot(a.x - b.x, a.y - b.y);
}

function polylineLength(points) {
  let total = 0;
  for (let i = 1; i < points.length; i += 1) {
    total += distance(points[i - 1], points[i]);
  }
  return total;
}

function quadraticPoint(p0, p1, p2, t) {
  const mt = 1 - t;
  return {
    x: mt * mt * p0.x + 2 * mt * t * p1.x + t * t * p2.x,
    y: mt * mt * p0.y + 2 * mt * t * p1.y + t * t * p2.y,
  };
}

function cubicPoint(p0, p1, p2, p3, t) {
  const mt = 1 - t;
  return {
    x:
      mt * mt * mt * p0.x +
      3 * mt * mt * t * p1.x +
      3 * mt * t * t * p2.x +
      t * t * t * p3.x,
    y:
      mt * mt * mt * p0.y +
      3 * mt * mt * t * p1.y +
      3 * mt * t * t * p2.y +
      t * t * t * p3.y,
  };
}

function curveSteps(from, to) {
  return Math.max(5, Math.min(14, Math.ceil(distance(from, to) / 16)));
}

function samplePathCommands(commands, includeMoveJumps = true) {
  const points = [];
  let cursor = { x: 0, y: 0 };
  let contourStart = null;
  for (const command of commands) {
    if (command.type === "M") {
      cursor = { x: command.x, y: command.y };
      contourStart = cursor;
      if (includeMoveJumps || points.length === 0) addPoint(points, cursor.x, cursor.y);
      continue;
    }
    if (command.type === "L") {
      cursor = { x: command.x, y: command.y };
      addPoint(points, cursor.x, cursor.y);
      continue;
    }
    if (command.type === "Q") {
      const start = cursor;
      const control = { x: command.x1, y: command.y1 };
      const end = { x: command.x, y: command.y };
      const steps = curveSteps(start, end);
      for (let i = 1; i <= steps; i += 1) {
        const point = quadraticPoint(start, control, end, i / steps);
        addPoint(points, point.x, point.y);
      }
      cursor = end;
      continue;
    }
    if (command.type === "C") {
      const start = cursor;
      const control1 = { x: command.x1, y: command.y1 };
      const control2 = { x: command.x2, y: command.y2 };
      const end = { x: command.x, y: command.y };
      const steps = curveSteps(start, end);
      for (let i = 1; i <= steps; i += 1) {
        const point = cubicPoint(start, control1, control2, end, i / steps);
        addPoint(points, point.x, point.y);
      }
      cursor = end;
      continue;
    }
    if (command.type === "Z" && contourStart) {
      addPoint(points, contourStart.x, contourStart.y);
      cursor = contourStart;
    }
  }
  return points;
}

function splitContours(commands) {
  const contours = [];
  let current = [];
  for (const command of commands) {
    if (command.type === "M") {
      if (current.length > 1) contours.push(current);
      current = [command];
      continue;
    }
    if (current.length === 0) continue;
    current.push(command);
    if (command.type === "Z") {
      contours.push(current);
      current = [];
    }
  }
  if (current.length > 1) contours.push(current);
  return contours;
}

function visiblePathLength(commands) {
  return splitContours(commands)
    .map((contour) => polylineLength(samplePathCommands(contour, false)))
    .reduce((sum, value) => sum + value, 0);
}

function measureText(font, text, fontSize) {
  try {
    return font.getAdvanceWidth(text, fontSize, { kerning: true });
  } catch {
    return Array.from(text).length * fontSize * 0.72;
  }
}

function charWeight(char) {
  return /[\u3400-\u9fff]/u.test(char) ? 1 : 0.55;
}

function fallbackLineWidth(text, fontSize) {
  return Array.from(String(text ?? "")).reduce((sum, char) => sum + charWeight(char) * fontSize, 0);
}

function pickFontForText(text) {
  const hasCjk = /[\u3400-\u9fff]/u.test(String(text ?? ""));
  if (hasCjk) return loadGlyphFont();
  return loadLatinGlyphFont() || loadGlyphFont();
}

function layoutTextLines(font, text, fontSize, maxWidth) {
  const safeMaxWidth = Number(maxWidth) > fontSize * 2 ? Number(maxWidth) : Number.POSITIVE_INFINITY;
  const lines = [];
  for (const paragraph of String(text ?? "").split(/\r?\n/)) {
    let current = "";
    for (const char of Array.from(paragraph)) {
      const candidate = current + char;
      if (current && measureText(font, candidate, fontSize) > safeMaxWidth) {
        lines.push(current.trimEnd());
        current = char.trimStart();
      } else {
        current = candidate;
      }
    }
    if (current) lines.push(current);
  }
  return lines.length > 0 ? lines : [String(text ?? "")];
}

function buildGlyphFragments(font, textSpec) {
  const fontSize = Number(textSpec.fontSize) || 48;
  const x = Number(textSpec.x) || 0;
  const y = Number(textSpec.y) || 0;
  const lines = layoutTextLines(font, textSpec.text, fontSize, textSpec.maxWidth);
  const lineHeight = fontSize * 1.18;
  const fragments = [];
  const hasCjk = /[\u3400-\u9fff]/u.test(String(textSpec.text ?? ""));
  const baseStrokeScale = hasCjk ? 0.04 : 0.034;

  lines.forEach((line, lineIndex) => {
    const baselineY = y + fontSize * 0.88 + lineIndex * lineHeight;
    font.forEachGlyph(
      line,
      x,
      baselineY,
      fontSize,
      { kerning: true },
      (glyph, glyphX, glyphY, glyphSize) => {
        const path = glyph.getPath(glyphX, glyphY, glyphSize);
        if (!path.commands.length) return;
        const points = samplePathCommands(path.commands, true);
        const visibleLength = visiblePathLength(path.commands);
        if (points.length < 2 || visibleLength < 2) return;
        fragments.push({
          d: path.toPathData(1),
          points,
          dashLength: rounded(visibleLength),
          strokeWidth: rounded(Math.max(1.8, Math.min(4.4, fontSize * baseStrokeScale))),
        });
      },
    );
  });

  return fragments;
}

function glyphTimingWeights(fragments) {
  const totalLength = fragments.reduce((sum, fragment) => sum + (fragment.dashLength || 0), 0);
  const averageLength = totalLength / Math.max(1, fragments.length) || 1;
  return fragments.map((fragment) => {
    const length = Math.max(1, fragment.dashLength || averageLength);
    const softenedLength = Math.sqrt(length * averageLength);
    const clampedLength = Math.max(averageLength * 0.62, Math.min(averageLength * 1.42, softenedLength));
    return averageLength * 0.62 + clampedLength * 0.38;
  });
}

function upgradeScenesWithGlyphOutlines(scenes) {
  const defaultLoaded = loadGlyphFont();
  if (!defaultLoaded) {
    throw new Error(
      `No usable Chinese outline font found. Tried: ${GLYPH_FONT_CANDIDATES.join(", ")}`,
    );
  }

  let glyphCount = 0;
  const enhancedScenes = scenes.map((scene) => {
    const textsByOp = new Map((scene.texts ?? []).map((text) => [text.opId, text]));
    const glyphPaths = [];
    const nextDrawOps = [];

    for (const op of scene.drawOps ?? []) {
      if (op.kind !== "text" || !textsByOp.has(op.id)) {
        nextDrawOps.push(op);
        continue;
      }

      const textSpec = textsByOp.get(op.id);
      const loaded = pickFontForText(textSpec.text) || defaultLoaded;
      const fragments = buildGlyphFragments(loaded.font, textSpec);
      if (fragments.length === 0) {
        nextDrawOps.push(op);
        continue;
      }

      const startFrame = Number(op.startFrame) || 0;
      const endFrame = Number(op.endFrame) || startFrame + 1;
      const duration = Math.max(1, endFrame - startFrame);
      const timingWeights = glyphTimingWeights(fragments);
      const totalTimingWeight = timingWeights.reduce((sum, weight) => sum + weight, 0) || fragments.length;
      let timingCursor = 0;

      fragments.forEach((fragment, index) => {
        const opId = `${op.id}_glyph_${index}`;
        const fragmentStart = startFrame + duration * (timingCursor / totalTimingWeight);
        timingCursor += timingWeights[index] || 1;
        const fragmentEnd =
          index === fragments.length - 1
            ? endFrame
            : startFrame + duration * (timingCursor / totalTimingWeight);
        const glyphOp = {
          ...op,
          id: opId,
          pace: "glyph",
          startFrame: rounded(fragmentStart, 2),
          endFrame: rounded(Math.max(fragmentStart + 0.2, fragmentEnd), 2),
          points: fragment.points,
        };
        nextDrawOps.push(glyphOp);
        glyphPaths.push({
          opId,
          sourceOpId: op.id,
          d: fragment.d,
          color: textSpec.color || "#1D1D1F",
          strokeWidth: Number(textSpec.markerStrokeWidth) || fragment.strokeWidth,
          dashLength: fragment.dashLength,
          fontOutline: true,
          markerFillOpacity: Number.isFinite(Number(textSpec.markerFillOpacity))
            ? Number(textSpec.markerFillOpacity)
            : 0.96,
        });
      });
      glyphCount += fragments.length;
    }

    return {
      ...scene,
      drawOps: nextDrawOps,
      glyphPaths,
    };
  });

  return { scenes: enhancedScenes, glyphCount, fontPath: defaultLoaded.fontPath };
}

function injectGlyphOutlineDrawing(tsx) {
  const sceneMatch = tsx.match(/const\s+scenes\s*=\s*([\s\S]*?)\s+as\s+SceneSpec\[\]\s*;/);
  if (!sceneMatch) return tsx;

  let scenes;
  try {
    scenes = JSON.parse(sceneMatch[1]);
  } catch (err) {
    console.warn("[glyph] Could not parse scenes JSON for outline preprocessing:", err.message);
    return tsx;
  }

  if (!Array.isArray(scenes) || scenes.length === 0) return tsx;
  const hasTextSpecs = scenes.some((scene) => Array.isArray(scene.texts) && scene.texts.length > 0);
  if (!hasTextSpecs) return tsx;

  const enhanced = upgradeScenesWithGlyphOutlines(scenes);
  if (enhanced.glyphCount === 0) {
    throw new Error("Glyph outline preprocessing produced no drawable text paths");
  }

  const nextScenesLiteral = JSON.stringify(enhanced.scenes);
  console.log(
    `[glyph] Preprocessed ${enhanced.glyphCount} fontOutline glyph path(s) from ${enhanced.fontPath}`,
  );
  return tsx.replace(sceneMatch[0], `const scenes = ${nextScenesLiteral} as SceneSpec[];`);
}

function validateStrokeFollowingTimeline(code) {
  const required = [
    "drawOps",
    "startFrame",
    "endFrame",
    "points",
    "pointOnPolyline",
    "getActiveDrawOp",
    "getPenPosition",
  ];
  for (const token of required) {
    if (!new RegExp(`\\b${token}\\b`).test(code)) {
      throw new Error(
        "Generated TSX must define drawOps with points plus getPenPosition() so the hand follows the active text/path stroke",
      );
    }
  }
  if (!/\b["']?kind["']?\s*:\s*["']text["']/.test(code)) {
    throw new Error("drawOps must include text operations with kind: 'text'");
  }
  // Count path/stroke operations for diagrams - each scene needs 3-5 diagram elements
  const pathOps = [...code.matchAll(/\b["']?kind["']?\s*:\s*["'](?:path|stroke|shape|arrow|box|circle|line)["']/gi)];
  if (pathOps.length < 8) {
    throw new Error(
      `drawOps must include at least 8 path/stroke operations for diagrams (found ${pathOps.length}). Each scene needs 3-5 distinct diagram elements.`
    );
  }

  // Count text operations - each scene needs 2-4 text labels
  const textOps = [...code.matchAll(/\b["']?kind["']?\s*:\s*["']text["']/gi)];
  if (textOps.length < 5) {
    throw new Error(
      `drawOps must include at least 5 text operations (found ${textOps.length}). Each scene needs title, labels, and conclusion text.`
    );
  }

  // SVG element validation is relaxed - drawOps with path/stroke kinds provide visual content
  // The strokeDasharray animation and drawOps define the visual elements, not raw SVG tags
  const pointCount = [
    ...code.matchAll(/\{\s*["']?x["']?\s*:\s*-?\d+(?:\.\d+)?\s*,\s*["']?y["']?\s*:\s*-?\d+(?:\.\d+)?\s*\}/g),
  ].length;
  if (pointCount < 16) {
    throw new Error("drawOps must contain at least 16 explicit {x, y} points so the pen traces strokes smoothly");
  }
  if (!/\bgetPenPosition\s*\(\s*frame\s*\)/.test(code)) {
    throw new Error("Generated TSX must call getPenPosition(frame) for the hand position");
  }
  const coarseTip = /\bconst\s+(?:tipX|tipY|penX|penY)\s*=\s*interpolate\s*\(\s*frame\s*,\s*\[[^\]]+\]\s*,\s*\[[^\]]+\]/;
  if (coarseTip.test(code)) {
    throw new Error(
      "Pen tip coordinates must not use coarse scene-level interpolate(frame, [...]); derive the tip from active drawOp points",
    );
  }
  if (/<\s*text\b/i.test(code)) {
    throw new Error("Do not use static SVG <text>; render handwriting text with glyphPaths driven by drawOps");
  }
}

function validateGlyphOutlineText(code) {
  if (!/\bglyphPaths\b/.test(code) || !/\b(DrawGlyphPath|GlyphText)\b/.test(code)) {
    throw new Error(
      "Generated TSX must render Chinese text through preprocessed glyphPaths/GlyphText, not HTML text reveal only",
    );
  }
  if (/\bHandText\b/.test(code) && !/\bGlyphText\b/.test(code)) {
    throw new Error("Generated TSX must replace HandText slice rendering with GlyphText outline path drawing");
  }
}

function validateHandwrittenWhiteboardStyle(code) {
  if (!/\b(STXingkai|Xingkai|KaiTi|STKaiti|Kaiti|楷体|华文行楷|华文楷体)\b/i.test(code)) {
    throw new Error(
      "Generated TSX must use an explicit Chinese handwriting font stack such as STXingkai/华文行楷/KaiTi/STKaiti",
    );
  }
  if (/\bfontWeight\s*:\s*["']?(?:700|800|900|bold)\b/i.test(code)) {
    throw new Error("Handwritten text must not use bold sans-serif styling");
  }
  if (!/\b(Diagram|Doodle|Callout|Sketch|Whiteboard)\b/i.test(code)) {
    throw new Error("Generated TSX must include whiteboard diagram/callout helpers, not only captions or slide labels");
  }
}

function validateNoPaperSurface(code) {
  const forbidden = [
    ["washD", "paper-like wash layers are not allowed behind drawings"],
    ["boxShadow", "shadowed paper/card surfaces are not allowed"],
    ["drop-shadow", "drop-shadow effects create a paper-like backing"],
    ["textShadow", "text shadows create a grey backing behind handwriting"],
  ];
  for (const [token, reason] of forbidden) {
    if (code.toLowerCase().includes(token.toLowerCase())) {
      throw new Error(`Generated TSX contains forbidden paper-surface styling: ${token} (${reason})`);
    }
  }

  // Only reject CSS property assignments that create paper/card/panel effects
  // Allow variable names, comments, and descriptive terms
  // Match only style-object property shorthand (e.g. { paper: value }) by requiring a
  // preceding opening brace or parenthesis, avoiding false-positives on variable/param names
  const paperSurfaceProps = [
    /[{(]\s*\bpaper\s*:/i,
    /[{(]\s*\bcard\s*:/i,
    /[{(]\s*\bpanel\s*:/i,
    /[{(]\s*\bsurface\s*:/i,
    /[{(]\s*\bsheet\s*:/i,
    /[{(]\s*\bposter\s*:/i,
    /[{(]\s*\bslide\s*:/i,
    /[{(]\s*\bboardShadow\s*:/i,
    /[{(]\s*\bshadow\b\s*:/i,
    /[{(]\s*\bwash\s*:/i,
  ];
  for (const pattern of paperSurfaceProps) {
    if (pattern.test(code)) {
      throw new Error("Generated TSX must not define paper/card/panel/surface/shadow/wash helpers or variables");
    }
  }

  if (/\bfilter\s*:\s*["'][^"']+["']/i.test(code)) {
    throw new Error("Generated TSX must not use CSS filter effects");
  }

  if (/\brasterReveal\s*:\s*\{|\breferenceImageAsset\s*:\s*["']generated\//i.test(code)) {
    throw new Error("Generated TSX must not bake rasterReveal/referenceImageAsset into normal generated whiteboard scenes");
  }

  const lightSurfacePattern =
    /background(?:Color)?\s*:\s*["'](?:#fff(?:fff)?|white|#f7f7f2|#f8f8f0|#fafafa|#f5f5f5|rgb\(\s*255\s*,\s*255\s*,\s*255\s*\))["'][\s\S]{0,220}\b(?:borderRadius|boxShadow|position\s*:\s*["']absolute["'])/i;
  if (lightSurfacePattern.test(code)) {
    throw new Error("Generated TSX must not create an inner white/light rectangle behind drawings or text");
  }

  if (/\b(?:linear-gradient|radial-gradient)\s*\(/i.test(code)) {
    throw new Error("Generated TSX must not use gradient washes or panel backgrounds");
  }
}

function validateStaticFileUsage(code) {
  const allowedAsset = /^(?:hand-real-pen\.png|generated\/[a-zA-Z0-9_-]+\/[a-zA-Z0-9_.-]+\.(?:png|jpg|jpeg|webp))$/;
  const literalCalls = [...code.matchAll(/\bstaticFile\s*\(\s*["']([^"']+)["']\s*\)/g)];
  for (const match of literalCalls) {
    if (!allowedAsset.test(match[1])) {
      throw new Error(`Generated TSX references disallowed static asset: ${match[1]}`);
    }
  }

  const calls = [...code.matchAll(/\bstaticFile\s*\(([^)]*)\)/g)];
  for (const match of calls) {
    const arg = match[1].trim();
    if (/^["']/.test(arg)) continue;
    if (
      !/^(?:HAND_ASSET|referenceImageAsset|scene\.referenceImageAsset|reveal\.asset)$/.test(arg)
    ) {
      throw new Error(`Generated TSX uses uncontrolled staticFile() argument: ${arg}`);
    }
  }
}

function validateGeneratedTsx(tsx) {
  let code = String(tsx ?? "").trim().replace(/^```(?:tsx|ts)?\s*/, "").replace(/\s*```$/, "");
  const hasNamedExport = () =>
    /export\s+const\s+GeneratedVideo\b/.test(code) ||
    /export\s+function\s+GeneratedVideo\b/.test(code) ||
    /export\s*\{\s*GeneratedVideo\s*\}/.test(code);

  if (!hasNamedExport()) {
    code = code.replace(
      /export\s+default\s+function\s+GeneratedVideo\s*\(/,
      "export function GeneratedVideo(",
    );
  }
  if (!hasNamedExport()) {
    const defaultFunction = code.match(/export\s+default\s+function\s+([A-Z]\w*)\s*\(/);
    if (defaultFunction) {
      const name = defaultFunction[1];
      code = code.replace(
        new RegExp(`export\\s+default\\s+function\\s+${name}\\s*\\(`),
        `function ${name}(`,
      );
      code = `${code.trim()}\n\nexport const GeneratedVideo = ${name};\n`;
    }
  }
  if (!hasNamedExport() && /\b(function|const|let|var)\s+GeneratedVideo\b/.test(code)) {
    code = code.replace(/export\s+default\s+GeneratedVideo\s*;?/, "");
    code = `${code.trim()}\n\nexport { GeneratedVideo };\n`;
  }
  if (!hasNamedExport()) {
    const defaultIdentifier = code.match(/export\s+default\s+([A-Z]\w*)\s*;?/);
    if (defaultIdentifier) {
      code = code.replace(new RegExp(`export\\s+default\\s+${defaultIdentifier[1]}\\s*;?`), "");
      code = `${code.trim()}\n\nexport const GeneratedVideo = ${defaultIdentifier[1]};\n`;
    }
  }
  if (!hasNamedExport()) {
    throw new Error("Generated TSX must export GeneratedVideo");
  }
  if (!/\buseCurrentFrame\b/.test(code)) {
    throw new Error("Generated TSX must use useCurrentFrame()");
  }
  if (!/\b(interpolate|spring)\s*\(/.test(code)) {
    throw new Error("Generated TSX must animate with interpolate() or spring()");
  }
  if (!/\bSequence\b/.test(code)) {
    throw new Error("Generated TSX must use Sequence for scene timing");
  }
  if (!/\bstrokeDasharray\b/.test(code) || !/\bstrokeDashoffset\b/.test(code)) {
    throw new Error("Generated TSX must draw SVG strokes with strokeDasharray/strokeDashoffset");
  }
  const hasTextReveal =
    /\bglyphPaths\b/.test(code) ||
    /\bspec\.text\.(?:slice|substring)\s*\(/.test(code) ||
    /\bclipPath\b/.test(code);
  if (!hasTextReveal) {
    throw new Error("Generated TSX must reveal text progressively");
  }
  validateStrokeFollowingTimeline(code);
  validateGlyphOutlineText(code);
  validateHandwrittenWhiteboardStyle(code);
  validateNoPaperSurface(code);
  if (!/\b(KaiTi|STKaiti|Kaiti|楷体)\b/i.test(code)) {
    throw new Error("Generated TSX must use a Chinese handwriting-style font family such as KaiTi/STKaiti");
  }
  const hasWatercolorAccent = [...code.matchAll(/#[0-9a-fA-F]{6}\b/g)].some((match) => {
    const value = match[0].toLowerCase();
    if (value === "#000000" || value === "#ffffff") return false;
    const r = Number.parseInt(value.slice(1, 3), 16);
    const g = Number.parseInt(value.slice(3, 5), 16);
    const b = Number.parseInt(value.slice(5, 7), 16);
    const isNeutral = Math.max(r, g, b) - Math.min(r, g, b) < 24;
    const isTooLight = Math.min(r, g, b) > 238;
    const isTooDark = Math.max(r, g, b) < 48;
    return !isNeutral && !isTooLight && !isTooDark;
  });
  if (!hasWatercolorAccent && !/\brgba?\s*\(/i.test(code)) {
    throw new Error("Generated TSX must include purposeful teaching accent colors");
  }
  if (!code.includes(HAND_ASSET)) {
    throw new Error(`Generated TSX must use staticFile("${HAND_ASSET}") for the visible hand holding a pen`);
  }
  if (!/\bstaticFile\s*\(/.test(code)) {
    throw new Error("Generated TSX must reference the hand asset with staticFile()");
  }
  validateStaticFileUsage(code);
  if (!/\bImg\b/.test(code)) {
    throw new Error("Generated TSX must render the visible hand with Remotion <Img>");
  }
  if (!/\bHandPen\b/.test(code)) {
    throw new Error("Generated TSX must define and render a HandPen component");
  }
  if (!/\b(tip|pen)(X|Y)\b/.test(code)) {
    throw new Error("Generated TSX must compute pen tip coordinates for the hand overlay");
  }
  if (!/\bvisible\b/.test(code)) {
    throw new Error("HandPen must receive a visible flag and hide during non-drawing holds");
  }
  if (!/\bHAND_WIDTH\s*=\s*(?:2[2-9]\d|[3-9]\d\d)\b/.test(code)) {
    throw new Error("Generated TSX must size the hand image with HAND_WIDTH >= 220");
  }
  if (!/\bPEN_TIP_(?:X|Y)\b/.test(code)) {
    throw new Error("Generated TSX must use fixed PEN_TIP_X/PEN_TIP_Y offsets to align the marker tip");
  }
  if (/<svg(?:(?!<\/svg>)[\s\S])*<HandPen(?:(?!<\/svg>)[\s\S])*<\/svg>/i.test(code)) {
    throw new Error("Generated TSX must render HandPen outside SVG as an HTML overlay sibling");
  }
  if (!/HandPen[\s\S]*?<div[\s\S]*?<Img/i.test(code)) {
    throw new Error("Generated TSX must wrap the hand <Img> in an absolutely positioned HTML <div>");
  }
  if (/<path(?=[^>]*strokeDash)(?=[^>]*fill=['"](?!none['"])[^'"]+['"])[^>]*>/i.test(code)) {
    throw new Error("Generated TSX must not fill animated stroke paths; use separate closed wash shapes behind strokes");
  }

  const forbidden = [
    "from \"./",
    "from './",
    "from \"../",
    "from '../",
    "require(",
    "eval(",
    "new Function",
    "child_process",
    "node:",
    "process.",
    "document.",
    "window.",
    "localStorage",
    "sessionStorage",
    "XMLHttpRequest",
    "fetch(",
    "dangerouslySetInnerHTML",
  ];
  const lower = code.toLowerCase();
  for (const token of forbidden) {
    if (lower.includes(token.toLowerCase())) {
      throw new Error(`Generated TSX contains forbidden token: ${token}`);
    }
  }

  const forbiddenPatterns = [
    /\bfs\./i,
    /\bfs\/promises\b/i,
    /\bimport\s*\(/i,
    /<\s*animate\b/i,
    /\btransition\s*:/i,
    /\banimation(?:Name|Duration|TimingFunction|Delay|IterationCount|Direction|FillMode|PlayState)?\s*:/i,
    /@keyframes\b/i,
    /\bclassName\s*=\s*['"][^'"]*\banimate-/i,
    /\bsetTimeout\s*\(/i,
    /\bsetInterval\s*\(/i,
    /\brequestAnimationFrame\s*\(/i,
    /\bDate\.now\s*\(/i,
    /\bMath\.random\s*\(/i,
  ];
  for (const pattern of forbiddenPatterns) {
    if (pattern.test(code)) {
      throw new Error(`Generated TSX contains forbidden pattern: ${pattern}`);
    }
  }

  for (const line of code.split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed.startsWith("import ")) continue;
    const match = trimmed.match(/from\s+["']([^"']+)["']/);
    if (!match || !["react", "remotion"].includes(match[1])) {
      throw new Error(`Generated TSX has disallowed import: ${trimmed}`);
    }
  }
  return code;
}

// Get style-specific visual instructions based on user selection
function getStyleInstructions(videoStyle, penStyle) {
  const style = String(videoStyle || "auto").toLowerCase();
  const pen = String(penStyle || "marker").toLowerCase();

  const visualStyles = {
    whiteboard: {
      base: "WHITEBOARD STYLE: Use warm off-white (#F7F7F2 or similar) canvas background. Draw with black marker outlines (2-3px stroke), blue titles/labels, and small colored accents (coral-pink, yellow, green). Include doodle-style icons, arrows, circles, and callout boxes. Visible hand holding a marker must draw each element.",
      elements: "Add these whiteboard elements: hand-drawn arrows, doodle-style boxes/circles, starbursts for emphasis, small icon sketches (ear/headphones for listening, book/magnifier for reading, gears for process, scales for comparison), and teacher-style annotations.",
    },
    sharpie: {
      base: "SHARPIE STYLE: Use bright white canvas with THICK black marker strokes (4-6px). Draw bold uppercase-style titles, rough quick sketches, and raw hand-drawn shapes. Use blue/yellow/red highlighter accents sparingly. A visible hand with thick marker must draw every element.",
      elements: "Use these sharpie elements: thick bold arrows, large rough circles/boxes, underline strokes, highlighter marks, and raw sketch icons. Every stroke should look bold and immediate, like a real sharpie on whiteboard.",
    },
    chalkboard_bw: {
      base: "CHALKBOARD B&W STYLE: Use dark black (#1a1a1a or similar) background with WHITE CHALK only. Draw sparse chalk-like line art, rough edges, and dusty chalk texture. NO visible hand - content appears line by line like chalk writing.",
      elements: "Use these chalkboard elements: rough chalk lines, sparse icon sketches, formula-like text, and subtle chalk dust texture. Content reveals progressively like someone writing on a real chalkboard.",
    },
    chalkboard_color: {
      base: "CHALKBOARD COLOR STYLE: Use dark black (#1a1a1a or similar) background. Draw with WHITE chalk main lines, CYAN for emphasis, YELLOW for conclusions/highlights. NO visible hand - content appears step by step.",
      elements: "Use these colored chalk elements: white main chalk strokes, cyan arrows/highlights, yellow key conclusions, subtle chalk texture. Color has meaning: white=main, cyan=emphasis, yellow=result.",
    },
    editorial: {
      base: "EDITORIAL STYLE: Use warm off-white paper-like canvas with BOLD BLACK INK illustrations and RED/ORANGE accent strokes. Draw magazine-quality sketchy illustrations with thick imperfect lines, paper sheet collage elements, and refined callouts.",
      elements: "Use these editorial elements: bold black ink drawings, red/orange arrows and callouts, paper/card collage shapes, media icons, and polished sketch illustrations. Each element should feel like quality editorial illustration.",
    },
    technical_blueprint: {
      base: "TECHNICAL BLUEPRINT STYLE: Use deep navy blue (#0a1628 or similar) canvas with PALE BLUE (#4a9eff) precise linework. Draw engineering-style diagrams with grid feel, measurement ticks, wireframe shapes, and structured panels.",
      elements: "Use these blueprint elements: precise blue lines, grid overlay, engineering symbols, wireframe boxes, measurement annotations, and structured technical diagrams. Add subtle cyan glow effects for emphasis.",
    },
    modern_minimal: {
      base: "MODERN MINIMAL STYLE: Use warm light grey (#f5f5f5) canvas with THIN BLACK lines and ONE cool accent color (blue or violet). Draw clean aligned icons, minimal shapes, and generous whitespace. Keep composition sparse and elegant.",
      elements: "Use these minimal elements: thin precise lines, aligned icon groups, minimal arrows, subtle color accents, and lots of white space. Each element should feel clean and intentional.",
    },
    playful: {
      base: "PLAYFUL STYLE: Use warm cream (#fff8e7) canvas with COLORFUL crayon-like strokes. Draw friendly rounded shapes, pastel accents, smiley marks, and bouncy compositions. Use visible hand with colorful markers.",
      elements: "Use these playful elements: rounded doodles, pastel colors (pink, mint, lavender, peach), smiley faces, music notes, bouncing shapes, and friendly character sketches. Make it approachable and fun.",
    },
  };

  const penStyles = {
    marker: "Use visible hand holding marker. Hand must follow each stroke path, moving up/down/left/right naturally.",
    pen: "Use visible hand holding pen. Hand should move smoothly, drawing fine strokes.",
    fountain_pen: "Use visible hand with fountain pen. Draw elegant thin strokes with occasional ink flow variation.",
    no_hand: "NO visible hand. Content appears through opacity reveals, not stroke animation.",
  };

  const selectedStyle = visualStyles[style] || visualStyles.whiteboard;
  const selectedPen = penStyles[pen] || penStyles.marker;

  return `${selectedStyle.base} ${selectedStyle.elements} ${selectedPen}`;
}

async function generateRemotionCode(storyboard, options = {}) {
  const subtitlesEnabled = Boolean(options.subtitlesEnabled);
  const codegenStoryboard = subtitlesEnabled
    ? storyboard
    : {
        ...storyboard,
        scenes: (storyboard.scenes ?? []).map((scene) => ({
          ...scene,
          subtitleText: null,
          subtitle_text: null,
          audioSegments: (scene.audioSegments ?? scene.audio_segments ?? []).map((segment) => ({
            ...segment,
            subtitleText: null,
            subtitle_text: null,
          })),
          audio_segments: (scene.audio_segments ?? scene.audioSegments ?? []).map((segment) => ({
            ...segment,
            subtitleText: null,
            subtitle_text: null,
          })),
        })),
      };
  const backgroundMusicUrl = options.backgroundMusicUrl || null;
  const backgroundMusicVolume = clampNumber(options.backgroundMusicVolume, 0, 0.5, 0.12);

  // Extract video_style and pen_style from storyboard
  const videoStyle = storyboard?.video_style ?? storyboard?.videoStyle ?? "auto";
  const penStyle = storyboard?.pen_style ?? storyboard?.penStyle ?? "marker";

  // Generate style-specific visual instructions based on user selection
  const styleInstructions = getStyleInstructions(videoStyle, penStyle);

  // Retry logic for validation failures
  const MAX_RETRIES = 2;
  let lastError = null;

  for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
    const isRetry = attempt > 0;
    const retryHint = isRetry
      ? " IMPORTANT: The previous generation included forbidden paper/card/panel/surface/shadow/wash styling patterns. CRITICAL: Do NOT define any variable named paper, card, panel, surface, sheet, poster, slide, boardShadow, shadow, or wash in your code. Do NOT use washD, boxShadow, textShadow, drop-shadow, or gradients. Only use AbsoluteFill for the canvas background."
      : "";

    const response = await postJson(`${PYTHON_API}/planner/remotion-code`, {
      storyboard: codegenStoryboard,
      fps: FPS,
      width: WIDTH,
      height: HEIGHT,
      subtitles_enabled: subtitlesEnabled,
      background_music_url: backgroundMusicUrl,
      background_music_volume: backgroundMusicVolume,
      style_prompt:
        "Directly generate this lesson as a real whiteboard animation with a visible hand holding a marker. " +
        `USER SELECTED STYLE: ${videoStyle.toUpperCase()} with ${penStyle.toUpperCase()} pen. ${styleInstructions} ` +
        "Respect scene video_style as the Golpo Canvas visual layer: chalkboard_bw uses black canvas with white chalk only; chalkboard_color uses black canvas with white/cyan chalk and limited yellow/teal emphasis; modern_minimal uses warm light grey, thin lines and one cool accent; technical_blueprint uses deep navy blueprint styling; editorial uses warm off-white bold ink with red/orange accents; whiteboard uses off-white marker-board with blue labels and small colored fills; playful uses warm cream crayon-like pastel accents; sharpie uses bright white thick black marker and highlighter accents. " +
        "Respect scene board_mode, hand_usage and visual_style: whiteboard/trace scenes use a visible hand following the active stroke; reference or annotate scenes may present a complex finished subject directly and then use hand callouts; clean_canvas/marketing_doodle scenes may use colorful finished doodles plus hand annotations; chalkboard/math_chalkboard or hand_usage=none scenes hide the hand and reveal equations or steps line by line. " +
        "Use the default bold editorial hand-drawn explainer look when scenes include generated reference art: thick black crayon/marker artwork, coral-pink arrows/checks/starbursts/underlines, warm yellow highlight blobs, one large subject or at most three large step groups, and generous blank space. " +
        "Treat generated reference art as text-free artwork; add readable Chinese titles, labels, ticks, underlines and callouts in the renderer with large handwritten glyph text instead of relying on text baked into the image. " +
        "For hand-writing scenes, every visible board text and diagram must be written or drawn live while the hand follows the actual stroke path. " +
        (subtitlesEnabled
          ? "Render optional subtitles as a separate bottom HTML overlay, using each scene.narration as caption text; the hand should not write subtitles. "
          : "Do not render subtitles or caption overlays. ") +
        (backgroundMusicUrl
          ? `Add one global low-volume looping background music Audio track with src="${backgroundMusicUrl}" and volume=${backgroundMusicVolume}; keep it behind narration. `
          : "Do not add background music. ") +
        "Import Img and staticFile from remotion and render <Img src={staticFile(\"hand-real-pen.png\")} /> " +
        "inside a HandPen component positioned from getPenPosition(frame) coordinates. " +
        "Use exact constants: const HAND_WIDTH = 260; const HAND_HEIGHT = 289; const PEN_TIP_X = 15; const PEN_TIP_Y = 78; " +
        "position with left: tipX - PEN_TIP_X and top: tipY - PEN_TIP_Y so the marker tip touches the active stroke. " +
        "HandPen must return an absolutely positioned HTML div wrapping Img, and <HandPen> must be rendered as a sibling after the SVG, never inside SVG. " +
        "In chalkboard/no-hand scenes keep the HandPen component defined but pass visible={false}; do not show a decorative hand. " +
        "Define drawOps with kind/startFrame/endFrame/points, pointOnPolyline(), getActiveDrawOp(), and getPenPosition(frame). " +
        "When two drawOps are separated by a short gap, keep the hand visible and move it from the previous stroke endpoint to the next stroke start without drawing, like a teacher lifting the marker. " +
        "If scenes include audioSegments, render each segment's audioUrl in its own Sequence using audioStartFrame when present, and keep matching drawOps inside the same beat window. " +
        "The hand must move up/down/left/right within words, not slide on one text baseline; text ops need stroke-like zig-zag points. " +
        "Use glyphPaths/GlyphText/DrawGlyphPath for Chinese text so the renderer can preprocess opentype.js font outline paths, " +
        "after each large glyph outline finishes, a light same-color fill is allowed so handwriting does not look hollow, " +
        "final board text should look like solid marker handwriting, not hollow outlined lettering, " +
        "and use strokeDasharray/strokeDashoffset SVG line drawing with matching drawOps. " +
        "If storyboard scenes include rasterReveal and referenceImageAsset, obey rasterReveal.renderMode. For trace, reveal the original reference image through animated SVG masks " +
        "using staticFile(scene.referenceImageAsset) and drive the hand from the same raster drawOps centerline points. For direct, present the complex reference image directly and use the hand only for large readable side callouts, short underlines, and small edge ticks near the image; avoid pretending to know exact internal object locations, avoid long sweeping arrows, and avoid large circles covering the diagram. " +
        "Keep the transparent line-art image on a clean light grey-white whiteboard canvas without yellow panels or color washes, " +
        "and after all trace raster drawOps finish crossfade the masked SVG image out while a short final HTML <Img> overlay of the same transparent image fades in outside SVG, so the last frame fully matches the reference asset without turning transparent pixels black or double-darkening strokes. " +
        "Use a clean warm off-white whiteboard canvas close to #F7F7F2, strong readable marker outlines, blue or black handwritten titles with coral-pink underlines, and purposeful colored teaching strokes. " +
        "CRITICAL RESTRICTION - Do NOT use these variable names in your code: paper, card, panel, surface, sheet, poster, slide, boardShadow, shadow, wash. The canvas background is AbsoluteFill only. " +
        "CRITICAL RESTRICTION - Do NOT use these CSS patterns in your code: washD, boxShadow, textShadow, drop-shadow, dropShadow, CSS filter, linear-gradient, radial-gradient. " +
        "Every scene needs one primary visual anchor made from at least 3-6 meaningful diagram/icon/object elements such as a funnel, route map, balance scale, gear, clock, warning triangle, clipboard, person/group, chart, matrix, cross-section, or system stack. " +
        "Never render a scene as only a heading plus checklist, bullets, checkmarks, or generic text boxes; a checklist may only be a tiny note beside a larger visual anchor. " +
        "Use idiomatic natural Chinese for all board titles, labels, callouts, captions, and narration. If the source concept is English, transcreate it into a Chinese phrase a real teacher would say instead of translating word by word; keep English only for fixed technical terms, acronyms, formulas, code names, or search names, optionally in parentheses. Avoid awkward coined shorthand; for example dependence/independence/interdependence can become 依赖 → 独立 → 互相依赖/成熟协作/协作共赢 depending on context, never 互赖. " +
        "Use staged reveal like the reference videos: title or anchor first, main line-art object second, labels/arrows/callouts third, and one short conclusion last. " +
        "If a scene is a summary, render a visual synthesis such as a loop, roadmap, hub-and-spoke map, evidence chart, or metaphor object instead of a plain checklist. " +
        "When scene.referenceImageAsset and scene.rasterReveal exist, always render the generated reference image via RasterRevealImage/RasterFinalOverlay; do not silently replace it with simpler SVG-only shapes. " +
        "Never create an inner paper, card, panel, slide, sheet, poster, white rectangle, or separate board surface; the full AbsoluteFill background is the only whiteboard. " +
        "Do not use washD, boxShadow, textShadow, drop-shadow, CSS filter, gradients, or any shadow/backing behind drawings or board text. " +
        "follow a real teacher-board layout: short blue title near the top-left or top-center, one central diagram occupying roughly 45-65% of the width, large empty margins, short labels close to the object, no fixed left explanation column, no paragraphs on the board. " +
        "animated dashed paths must use fill=\"none\"; do not use colored background washes, paper tints, or colored panels behind diagrams. " +
        "and lots of negative space. " +
        "Start writing immediately in each scene and avoid blank boards after a cut; scene changes should feel like continuous board work. " +
        "For Chinese text use STXingkai/华文行楷/KaiTi/STKaiti/Kaiti SC/cursive first, not default bold sans-serif. " +
        "Use teacher-style whiteboard callouts such as arrows, circles, underlines, brackets, ticks, and local zoom boxes; make visuals lively with small humorous teaching metaphors like wrong-floor signs, tug-of-war choices, taxi route arrows, receipt/check tickets, tuning knobs, alarm marks, and marker annotations drawn directly on the board. Do not force mascots or decorative cartoon characters. " +
        (subtitlesEnabled
          ? "Use audioSegments subtitleText only for bottom subtitles. "
          : "Ignore audioSegments subtitleText and do not render any bottom subtitle overlay. ") +
        "For every drawOp that is tied to a beat, keep the beatId field and draw within that beat's time window, so the hand is emphasizing the same idea that the voice is explaining. " +
        "Do not use SVG <animate>; all timing must be driven by Remotion frame values. " +
        "Do not use templates, local components, slide-deck cards, stock images, or component libraries." +
        retryHint,
    });

    try {
      const validatedTsx = validateGeneratedTsx(response.tsx);
      const glyphTsx = injectGlyphOutlineDrawing(validatedTsx);
      const plannedSceneFrames = Array.isArray(codegenStoryboard?.scenes)
        ? codegenStoryboard.scenes.reduce((sum, scene) => {
            const timingFrames = Number(scene?.timingPlan?.durationFrames ?? scene?.timing_plan?.durationFrames ?? 0);
            const estimateFrames = Math.ceil(Number(scene?.duration_estimate ?? 0) * FPS);
            const segmentFrames = Array.isArray(scene?.audioSegments ?? scene?.audio_segments)
              ? Math.max(
                  0,
                  ...(scene?.audioSegments ?? scene?.audio_segments).map((segment) => Number(segment?.endFrame ?? 0)),
                )
              : 0;
            return sum + Math.max(0, timingFrames, estimateFrames, segmentFrames);
          }, 0)
        : 0;

      return {
        tsx: validateGeneratedTsx(glyphTsx),
        durationInFrames: Math.max(
          FPS * 10,
          Math.ceil(Number(codegenStoryboard?.total_duration_estimate ?? 0) * FPS),
          plannedSceneFrames,
          Number(response.duration_in_frames ?? FPS * 60),
        ),
        fps: Number(response.fps ?? FPS),
        width: Number(response.width ?? WIDTH),
        height: Number(response.height ?? HEIGHT),
      };
    } catch (err) {
      lastError = err;
      console.warn(`[codegen] Validation failed (attempt ${attempt + 1}/${MAX_RETRIES + 1}): ${err.message}`);
      if (attempt < MAX_RETRIES) {
        await sleep(1500); // Brief delay before retry
        continue;
      }
    }
  }

  throw lastError ?? new Error("generateRemotionCode failed after retries");
}

function generatedTsxAudioTags(code) {
  return [...String(code || "").matchAll(/<\s*Audio\b[^>]*>/g)].map((match) => match[0]);
}

function generatedTsxRendersLiteralAudioSource(code, source) {
  if (!source) return false;
  const audioTags = generatedTsxAudioTags(code);
  if (audioTags.length === 0) return false;
  const raw = String(source);
  const escaped = raw.replace(/\//g, "\\/");
  return audioTags.some((tag) => tag.includes(raw) || tag.includes(escaped));
}

function codeContainsAudioSource(code, source) {
  if (!source) return false;
  const raw = String(source);
  const escaped = raw.replace(/\//g, "\\/");
  const codeText = String(code || "");
  return codeText.includes(raw) || codeText.includes(escaped);
}

function generatedTsxRendersSegmentAudio(code, source) {
  if (generatedTsxRendersLiteralAudioSource(code, source)) return true;
  if (!codeContainsAudioSource(code, source)) return false;
  const codeText = String(code || "");
  return (
    /(?:audioSegments|audio_segments|segments)\s*(?:\?\?)?[\s\S]{0,900}\.map\s*\([\s\S]{0,1200}<\s*Audio\b[\s\S]{0,260}(?:segment|seg|audio)\.(?:audioUrl|audio_url)/i.test(codeText) ||
    /(?:segment|seg|audio)\.(?:audioUrl|audio_url)[\s\S]{0,260}<\s*\/\s*Sequence\s*>/i.test(codeText)
  );
}

function generatedTsxRendersSceneAudio(code, source) {
  if (generatedTsxRendersLiteralAudioSource(code, source)) return true;
  if (!codeContainsAudioSource(code, source)) return false;
  const audioTags = generatedTsxAudioTags(code);
  return audioTags.some((tag) => /\bscene\.(?:audioUrl|audio_url)\b/.test(tag));
}

function generatedTsxRendersBackgroundSource(code, source) {
  if (!source) return false;
  const audioTags = generatedTsxAudioTags(code);
  if (audioTags.length === 0) return false;
  const raw = String(source);
  const escaped = raw.replace(/\//g, "\\/");
  if (audioTags.some((tag) => tag.includes(raw) || tag.includes(escaped))) return true;
  const codeText = String(code || "");
  if (!codeText.includes(raw) && !codeText.includes(escaped)) return false;
  return audioTags.some((tag) => /\b(?:BACKGROUND_MUSIC|backgroundMusic|musicUrl|music_url|music)\b/.test(tag));
}

function storyboardSceneDurationFrames(scene) {
  const timingFrames = Number(scene?.timingPlan?.durationFrames ?? scene?.timing_plan?.durationFrames ?? 0);
  const estimateFrames = Math.ceil(Number(scene?.duration_estimate ?? 0) * FPS);
  const segmentFrames = Array.isArray(scene?.audioSegments ?? scene?.audio_segments)
    ? Math.max(0, ...(scene?.audioSegments ?? scene?.audio_segments).map((segment) => Number(segment?.endFrame ?? 0)))
    : 0;
  return Math.max(FPS * 8, timingFrames, estimateFrames, segmentFrames);
}

function collectMissingVoiceTracks(storyboard, generatedTsx) {
  const tracks = [];
  let sceneOffset = 0;
  for (const [sceneIndex, scene] of (storyboard?.scenes ?? []).entries()) {
    const sceneDuration = storyboardSceneDurationFrames(scene);
    const segments = scene?.audioSegments ?? scene?.audio_segments ?? [];
    const segmentTracks = [];
    const sceneAudioUrl = scene?.audioUrl ?? scene?.audio_url;
    const sceneAudioAlreadyRendered = generatedTsxRendersSceneAudio(generatedTsx, sceneAudioUrl);
    if (Array.isArray(segments)) {
      for (const [segmentIndex, segment] of segments.entries()) {
        const src = segment?.audioUrl ?? segment?.audio_url;
        if (!src || generatedTsxRendersSegmentAudio(generatedTsx, src)) continue;
        if (sceneAudioAlreadyRendered && String(src) === String(sceneAudioUrl)) continue;
        const localFrom = Math.max(0, Math.round(Number(segment?.audioStartFrame ?? segment?.audio_start_frame ?? segment?.startFrame ?? segment?.start_frame ?? 0)));
        const sequenceDuration = Math.round(
          Number(
            segment?.audioSequenceDuration ??
              segment?.audio_sequence_duration ??
              segment?.duration ??
              segment?.audioDurationFrames ??
              segment?.audio_duration_frames ??
              FPS * 3,
          ),
        );
        segmentTracks.push({
          id: `scene_${sceneIndex}_segment_${segmentIndex}`,
          from: sceneOffset + localFrom,
          durationInFrames: Math.max(1, sequenceDuration),
          src: String(src),
        });
      }
    }
    if (segmentTracks.length === 0 && sceneAudioUrl && !sceneAudioAlreadyRendered && !generatedTsxRendersSegmentAudio(generatedTsx, sceneAudioUrl)) {
      tracks.push({
        id: `scene_${sceneIndex}_voice`,
        from: sceneOffset,
        durationInFrames: sceneDuration,
        src: String(sceneAudioUrl),
      });
    } else {
      tracks.push(...segmentTracks);
    }
    sceneOffset += sceneDuration;
  }
  return tracks;
}

function writeGeneratedProject(jobId, generated, storyboard, options = {}) {
  const projectDir = join(GENERATED_DIR, jobId);
  mkdirSync(projectDir, { recursive: true });

  const componentPath = join(projectDir, "GeneratedVideo.tsx");
  const entryPath = join(projectDir, "index.tsx");
  const extraVoiceTracks = collectMissingVoiceTracks(storyboard, generated.tsx);
  const backgroundMusicUrl =
    options.backgroundMusicUrl && !generatedTsxRendersBackgroundSource(generated.tsx, options.backgroundMusicUrl)
      ? String(options.backgroundMusicUrl)
      : null;
  const backgroundMusicVolume = clampNumber(options.backgroundMusicVolume, 0, 0.5, 0.12);

  writeFileSync(componentPath, generated.tsx, "utf8");
  writeFileSync(
    entryPath,
    `import React from "react";
import { Audio, Composition, Sequence, registerRoot } from "remotion";
import { GeneratedVideo } from "./GeneratedVideo";

const EXTRA_VOICE_TRACKS: Array<{ id: string; from: number; durationInFrames: number; src: string }> = ${JSON.stringify(extraVoiceTracks)};
const BACKGROUND_MUSIC_URL: string | null = ${JSON.stringify(backgroundMusicUrl)};
const BACKGROUND_MUSIC_VOLUME = ${JSON.stringify(backgroundMusicVolume)};

const GeneratedVideoWithAudio: React.FC = () => {
  return (
    <>
      <GeneratedVideo />
      {EXTRA_VOICE_TRACKS.map((track) => (
        <Sequence key={track.id} from={track.from} durationInFrames={track.durationInFrames}>
          <Audio src={track.src} />
        </Sequence>
      ))}
      {BACKGROUND_MUSIC_URL ? <Audio src={BACKGROUND_MUSIC_URL} volume={BACKGROUND_MUSIC_VOLUME} loop /> : null}
    </>
  );
};

const RemotionRoot: React.FC = () => {
  return (
    <Composition
      id="${COMPOSITION_ID}"
      component={GeneratedVideoWithAudio}
      durationInFrames={${generated.durationInFrames}}
      fps={${generated.fps}}
      width={${generated.width}}
      height={${generated.height}}
    />
  );
};

registerRoot(RemotionRoot);
`,
    "utf8",
  );

  return { projectDir, entryPath };
}

function browserOptions() {
  return existsSync(BROWSER_EXECUTABLE)
    ? { browserExecutable: BROWSER_EXECUTABLE }
    : {};
}

function canListen(port) {
  return new Promise((resolvePromise) => {
    const probe = createNetServer();
    probe.once("error", () => resolvePromise(false));
    probe.once("listening", () => {
      probe.close(() => resolvePromise(true));
    });
    probe.listen(port, "127.0.0.1");
  });
}

async function getStaticPort() {
  for (let port = STATIC_PORT_START; port < STATIC_PORT_START + 100; port += 1) {
    if (await canListen(port)) return port;
  }
  throw new Error(`No available Remotion static port from ${STATIC_PORT_START}`);
}

async function bundleAndRender(jobId, entryPath, outputPath) {
  updateJob(jobId, { phase: "bundling", progress: 0 });
  console.log("[bundle] Bundling generated Remotion code...");
  const bundlePath = await bundle({
    entryPoint: entryPath,
    onProgress: (progress) => {
      process.stdout.write(`\r[bundle] ${progress}%`);
    },
  });
  console.log(`\n[bundle] Ready: ${bundlePath.slice(0, 100)}`);

  const downloadMap = RenderInternals.makeDownloadMap();
  const staticPort = await getStaticPort();
  const staticServer = await RenderInternals.serveStatic(bundlePath, {
    port: staticPort,
    downloadMap,
    remotionRoot: __dirname,
    offthreadVideoThreads: 2,
    logLevel: "warn",
    indent: false,
    offthreadVideoCacheSizeInBytes: null,
    binariesDirectory: null,
    forceIPv4: false,
  });

  try {
    const serveUrl = `http://localhost:${staticServer.port}`;
    console.log(`[serve] Remotion static server: ${serveUrl}`);
    console.log(`[render] Concurrency: ${RENDER_CONCURRENCY}`);
    updateJob(jobId, { phase: "rendering", progress: 0 });

    const composition = await selectComposition({
      serveUrl,
      id: COMPOSITION_ID,
      ...browserOptions(),
    });

    await renderMedia({
      composition,
      serveUrl,
      codec: "h264",
      imageFormat: "png",
      crf: RENDER_CRF,
      x264Preset: RENDER_X264_PRESET,
      pixelFormat: RENDER_PIXEL_FORMAT,
      outputLocation: outputPath,
      concurrency: RENDER_CONCURRENCY,
      ...browserOptions(),
      onProgress: ({ progress }) => {
        const percent = Math.round(progress * 100);
        process.stdout.write(`\r[render] ${percent}%`);
        updateJob(jobId, { progress: percent });
      },
    });
    console.log(`\n[render] Done: ${basename(outputPath)}`);
  } finally {
    await staticServer.close();
  }
}

async function renderVideo(jobId, storyboard, voice, outputPath, options = {}) {
  updateJob(jobId, { phase: "tts", progress: 0 });
  console.log(`[tts] Synthesizing ${storyboard.scenes.length} scenes...`);
  const storyboardWithAudio = await injectAudio(storyboard, voice);
  updateJob(jobId, {
    actualDurationSeconds: Math.round((storyboardWithAudio.total_duration_estimate ?? 0) * 10) / 10,
  });
  await assertStoryboardAudioComplete(storyboardWithAudio);
  console.log("[tts] Done");

  updateJob(jobId, { phase: "imagegen", progress: 0 });
  updateJob(jobId, { publicAssetDir: join(PUBLIC_GENERATED_DIR, jobId) });
  const storyboardWithTraces = await injectImageTraces(storyboardWithAudio, jobId);

  updateJob(jobId, { phase: "codegen", progress: 0 });
  console.log("[codegen] Generating Remotion TSX via LLM...");
  const generated = await generateRemotionCode(storyboardWithTraces, options);
  const { projectDir, entryPath } = writeGeneratedProject(jobId, generated, storyboardWithTraces, options);
  updateJob(jobId, {
    generatedDir: projectDir,
    actualDurationSeconds: Math.round((generated.durationInFrames / generated.fps) * 10) / 10,
  });
  console.log("[codegen] Generated project:", projectDir);

  await bundleAndRender(jobId, entryPath, outputPath);
  await runRenderQa(jobId, outputPath, storyboardWithTraces);
}

function makeSlug(value) {
  return String(value || "video")
    .normalize("NFKC")
    .replace(/[^\p{L}\p{N}_-]+/gu, "_")
    .replace(/^_+|_+$/g, "")
    .slice(0, 80) || "video";
}

function isInside(child, parent) {
  const resolvedChild = resolve(child);
  const resolvedParent = resolve(parent);
  return resolvedChild === resolvedParent || resolvedChild.startsWith(resolvedParent + "\\");
}

function removeGeneratedDir(dir) {
  if (!dir) return;
  if (!isInside(dir, GENERATED_DIR)) return;
  try {
    rmSync(dir, { recursive: true, force: true });
  } catch {}
}

function removePublicGeneratedDir(dir) {
  if (!dir) return;
  if (!isInside(dir, PUBLIC_GENERATED_DIR)) return;
  try {
    rmSync(dir, { recursive: true, force: true });
  } catch {}
}

function deleteJobRecord(jobId) {
  const job = jobs[jobId];
  if (!job) return false;
  if (job.outputPath && isInside(job.outputPath, OUTPUT_DIR)) {
    try {
      unlinkSync(job.outputPath);
    } catch {}
  }
  removeGeneratedDir(job.generatedDir);
  removePublicGeneratedDir(job.publicAssetDir ?? join(PUBLIC_GENERATED_DIR, jobId));
  delete jobs[jobId];
  return true;
}

function sendJson(res, statusCode, payload) {
  res.writeHead(statusCode, { "Content-Type": "application/json" });
  res.end(JSON.stringify(payload));
}

function serveStaticFile(res, filePath, contentType) {
  if (!existsSync(filePath)) {
    res.writeHead(404);
    res.end();
    return;
  }
  const stat = statSync(filePath);
  res.writeHead(200, {
    "Content-Type": contentType,
    "Content-Length": stat.size,
    "Accept-Ranges": "bytes",
  });
  createReadStream(filePath).pipe(res);
}

function serveMediaFile(req, res, filePath, contentType) {
  if (!existsSync(filePath)) {
    res.writeHead(404);
    res.end();
    return;
  }
  const stat = statSync(filePath);
  if (!stat.isFile()) {
    res.writeHead(404);
    res.end();
    return;
  }

  const commonHeaders = {
    "Content-Type": contentType,
    "Accept-Ranges": "bytes",
    "Cache-Control": "public, max-age=3600",
  };
  const range = req.headers.range;
  if (range) {
    const match = /^bytes=(\d*)-(\d*)$/.exec(String(range).trim());
    if (!match) {
      res.writeHead(416, { ...commonHeaders, "Content-Range": `bytes */${stat.size}` });
      res.end();
      return;
    }
    let start = match[1] ? Number(match[1]) : 0;
    let end = match[2] ? Number(match[2]) : stat.size - 1;
    if (!match[1] && match[2]) {
      const suffixLength = Number(match[2]);
      start = Math.max(0, stat.size - suffixLength);
      end = stat.size - 1;
    }
    if (!Number.isFinite(start) || !Number.isFinite(end) || start < 0 || end >= stat.size || start > end) {
      res.writeHead(416, { ...commonHeaders, "Content-Range": `bytes */${stat.size}` });
      res.end();
      return;
    }
    res.writeHead(206, {
      ...commonHeaders,
      "Content-Length": end - start + 1,
      "Content-Range": `bytes ${start}-${end}/${stat.size}`,
    });
    if (req.method === "HEAD") {
      res.end();
      return;
    }
    createReadStream(filePath, { start, end }).pipe(res);
    return;
  }

  res.writeHead(200, {
    ...commonHeaders,
    "Content-Length": stat.size,
  });
  if (req.method === "HEAD") {
    res.end();
    return;
  }
  createReadStream(filePath).pipe(res);
}

const server = http.createServer(async (req, res) => {
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Access-Control-Allow-Methods", "GET, HEAD, POST, PATCH, DELETE, OPTIONS");
  res.setHeader("Access-Control-Allow-Headers", "Content-Type, Range");

  if (req.method === "OPTIONS") {
    res.writeHead(204);
    res.end();
    return;
  }

  const url = new URL(req.url, `http://localhost:${PORT}`);

  if (req.method === "GET" && url.pathname === "/health") {
    sendJson(res, 200, { status: "ok", mode: "llm-remotion" });
    return;
  }

  if (req.method === "GET" && url.pathname === "/music") {
    sendJson(res, 200, { tracks: listMusicTracks() });
    return;
  }

  if (req.method === "POST" && url.pathname === "/render") {
    try {
      const payload = JSON.parse(await readBody(req));
      let {
        storyboard,
        voice,
        subtitlesEnabled,
        subtitles_enabled,
        backgroundMusicEnabled,
        background_music_enabled,
        backgroundMusicId,
        background_music_id,
        backgroundMusicVolume,
        background_music_volume,
      } = payload;
      if (!storyboard?.scenes?.length) {
        sendJson(res, 400, { error: "storyboard.scenes is required" });
        return;
      }
      const useBackgroundMusic = Boolean(backgroundMusicEnabled ?? background_music_enabled);
      let backgroundMusicTrack = null;
      let backgroundMusicVolumeValue = 0.12;
      if (useBackgroundMusic) {
        const requestedTrackId = backgroundMusicId ?? background_music_id;
        const availableTracks = listMusicTracks();
        const trackId = requestedTrackId || availableTracks[0]?.id;
        backgroundMusicTrack = trackId ? resolveMusicTrack(trackId) : null;
        if (!backgroundMusicTrack) {
          sendJson(res, 400, { error: "background music track not found" });
          return;
        }
        if (!(await probePlayableAudio(backgroundMusicTrack.filePath))) {
          sendJson(res, 400, { error: `background music is not a playable audio file: ${backgroundMusicTrack.id}` });
          return;
        }
        backgroundMusicTrack = await normalizeMusicTrackForRemotion(backgroundMusicTrack);
        if (!(await probePlayableAudio(backgroundMusicTrack.filePath))) {
          sendJson(res, 400, { error: `background music could not be normalized: ${backgroundMusicTrack.id}` });
          return;
        }
        backgroundMusicVolumeValue = clampNumber(
          backgroundMusicVolume ?? background_music_volume,
          0,
          0.5,
          0.12,
        );
      }
      try {
        storyboard = sanitizeStoryboardText(storyboard);
        assertStoryboardEncodingHealthy(storyboard);
        await ensureLargeModelAvailable();
      } catch (err) {
        sendJson(res, String(err.message ?? "").startsWith("检测到中文编码异常") ? 400 : 503, { error: err.message });
        return;
      }

      const jobId = randomUUID();
      const outputPath = join(
        OUTPUT_DIR,
        `${makeSlug(storyboard.topic)}_${jobId.slice(0, 8)}.mp4`,
      );

      const createdAt = new Date().toISOString();
      jobs[jobId] = {
        status: "processing",
        outputPath,
        progress: 0,
        phase: "queued",
        topic: cleanUserText(storyboard.topic, "Untitled"),
        backgroundMusicId: backgroundMusicTrack?.id ?? null,
        createdAt,
      };
      saveJobsAsync();

      sendJson(res, 202, { jobId, createdAt });

      renderVideo(jobId, storyboard, voice, outputPath, {
        subtitlesEnabled: Boolean(subtitlesEnabled ?? subtitles_enabled),
        backgroundMusicUrl: backgroundMusicTrack?.url ?? null,
        backgroundMusicVolume: backgroundMusicVolumeValue,
      })
        .then(() => updateJob(jobId, { status: "done", progress: 100, phase: "done" }))
        .catch((err) => {
          updateJob(jobId, { status: "failed", phase: "failed", error: err.message });
          console.error(`\n[render] Failed: ${err.stack || err.message}`);
        });
    } catch (err) {
      sendJson(res, 400, { error: err.message });
    }
    return;
  }

  if (req.method === "GET" && url.pathname === "/jobs") {
    const list = Object.entries(jobs)
      .map(([id, job]) => ({
        id,
        status: job.status,
        progress: job.progress ?? 0,
        phase: job.phase ?? null,
        topic: job.topic ?? null,
        createdAt: job.createdAt ?? null,
        actualDurationSeconds: job.actualDurationSeconds ?? null,
        qa: job.qa ?? null,
        error: job.error ?? null,
      }))
      .sort((a, b) => (b.createdAt ?? "").localeCompare(a.createdAt ?? ""));
    sendJson(res, 200, { jobs: list });
    return;
  }

  if (req.method === "POST" && url.pathname === "/jobs/delete") {
    try {
      const payload = JSON.parse(await readBody(req, 1024 * 1024));
      const jobIds = Array.isArray(payload.jobIds) ? payload.jobIds : [];
      const deleted = [];
      const missing = [];
      for (const rawId of jobIds) {
        const jobId = String(rawId);
        if (deleteJobRecord(jobId)) deleted.push(jobId);
        else missing.push(jobId);
      }
      saveJobsAsync();
      sendJson(res, 200, { ok: true, deleted, missing });
    } catch {
      sendJson(res, 400, { error: "invalid JSON" });
    }
    return;
  }

  if (req.method === "GET" && url.pathname.startsWith("/job/")) {
    const jobId = url.pathname.slice(5);
    const job = jobs[jobId];
    if (!job) {
      sendJson(res, 404, { error: "not found" });
      return;
    }
    sendJson(res, 200, {
      status: job.status,
      progress: job.progress ?? 0,
      phase: job.phase ?? null,
      createdAt: job.createdAt ?? null,
      actualDurationSeconds: job.actualDurationSeconds ?? null,
      qa: job.qa ?? null,
      error: job.error ?? null,
    });
    return;
  }

  if (req.method === "PATCH" && url.pathname.startsWith("/job/")) {
    const jobId = url.pathname.slice(5);
    const job = jobs[jobId];
    if (!job) {
      sendJson(res, 404, { error: "not found" });
      return;
    }
    try {
      const patch = JSON.parse(await readBody(req, 1024 * 1024));
      if (patch.topic !== undefined) {
        job.topic = cleanUserText(patch.topic, job.topic ?? "Untitled").slice(0, 200);
      }
      saveJobsAsync();
      sendJson(res, 200, { ok: true });
    } catch {
      sendJson(res, 400, { error: "invalid JSON" });
    }
    return;
  }

  if (req.method === "DELETE" && url.pathname.startsWith("/job/")) {
    const jobId = url.pathname.slice(5);
    if (!jobs[jobId]) {
      sendJson(res, 404, { error: "not found" });
      return;
    }
    deleteJobRecord(jobId);
    saveJobsAsync();
    sendJson(res, 200, { ok: true });
    return;
  }

  if (req.method === "GET" && url.pathname.startsWith("/audio/")) {
    const filename = basename(url.pathname.slice(7));
    serveStaticFile(res, join(AUDIO_DIR, filename), "audio/mpeg");
    return;
  }

  if ((req.method === "GET" || req.method === "HEAD") && url.pathname.startsWith("/music/")) {
    const track = resolveMusicTrack(url.pathname.slice(7));
    if (!track) {
      sendJson(res, 404, { error: "music track not found" });
      return;
    }
    serveMediaFile(req, res, track.filePath, track.contentType);
    return;
  }

  if (req.method === "GET" && url.pathname.startsWith("/download/")) {
    const jobId = url.pathname.slice(10);
    const job = jobs[jobId];
    if (!job || job.status !== "done" || !existsSync(job.outputPath)) {
      sendJson(res, 404, { error: "not ready" });
      return;
    }

    const stat = statSync(job.outputPath);
    const fileSize = stat.size;
    const filename = basename(job.outputPath);
    const encodedFilename = encodeURIComponent(filename);
    const rangeHeader = req.headers.range;

    if (rangeHeader) {
      const [startStr, endStr] = String(rangeHeader).replace("bytes=", "").split("-");
      const start = Number.parseInt(startStr, 10);
      const end = endStr ? Number.parseInt(endStr, 10) : fileSize - 1;
      if (!Number.isFinite(start) || start < 0 || end < start) {
        res.writeHead(416);
        res.end();
        return;
      }
      const chunkSize = end - start + 1;
      res.writeHead(206, {
        "Content-Type": "video/mp4",
        "Content-Range": `bytes ${start}-${end}/${fileSize}`,
        "Accept-Ranges": "bytes",
        "Content-Length": chunkSize,
        "Content-Disposition": `inline; filename="video.mp4"; filename*=UTF-8''${encodedFilename}`,
      });
      createReadStream(job.outputPath, { start, end }).pipe(res);
      return;
    }

    res.writeHead(200, {
      "Content-Type": "video/mp4",
      "Content-Length": fileSize,
      "Accept-Ranges": "bytes",
      "Content-Disposition": `inline; filename="video.mp4"; filename*=UTF-8''${encodedFilename}`,
    });
    createReadStream(job.outputPath).pipe(res);
    return;
  }

  res.writeHead(404);
  res.end();
});

process.on("SIGINT", () => process.exit(0));

server.listen(PORT, () => {
  console.log(`[render-server] http://localhost:${PORT} (LLM Remotion mode)`);
});
