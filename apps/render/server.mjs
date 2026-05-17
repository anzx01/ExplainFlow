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
import { createServer as createNetServer } from "net";
import {
  createReadStream,
  existsSync,
  mkdirSync,
  readFileSync,
  rmSync,
  statSync,
  unlinkSync,
  writeFileSync,
} from "fs";
import { basename, dirname, join, resolve } from "path";
import { createHash, randomUUID } from "crypto";
import { fileURLToPath } from "url";
import { availableParallelism } from "os";
import opentype from "opentype.js";
import sharp from "sharp";
import { bundle } from "@remotion/bundler";
import { renderMedia, selectComposition, RenderInternals } from "@remotion/renderer";

const __dirname = dirname(fileURLToPath(import.meta.url));
const PORT = Number(process.env.RENDER_PORT ?? 3001);
const FPS = 30;
const WIDTH = 1920;
const HEIGHT = 1080;
const OUTPUT_DIR = join(__dirname, "../../outputs");
const AUDIO_DIR = join(OUTPUT_DIR, "audio");
const JOBS_FILE = join(OUTPUT_DIR, "jobs.json");
const GENERATED_DIR = join(__dirname, "generated");
const PYTHON_API = process.env.PYTHON_API_URL ?? "http://localhost:8000";
const DEFAULT_CHROME =
  "C:\\Users\\DELL\\AppData\\Local\\ms-playwright\\chromium_headless_shell-1223\\chrome-headless-shell-win64\\chrome-headless-shell.exe";
const BROWSER_EXECUTABLE = process.env.REMOTION_CHROME_HEADLESS_SHELL || DEFAULT_CHROME;
const COMPOSITION_ID = "GeneratedVideo";
const STATIC_PORT_START = Number(process.env.REMOTION_STATIC_PORT ?? 3002);
const DEFAULT_RENDER_CONCURRENCY = Math.min(8, Math.max(4, availableParallelism() - 2));
const RENDER_CONCURRENCY = Number.isFinite(Number(process.env.REMOTION_CONCURRENCY))
  ? Math.max(1, Number(process.env.REMOTION_CONCURRENCY))
  : DEFAULT_RENDER_CONCURRENCY;
const ENABLE_IMAGE_TRACE = process.env.REMOTION_IMAGE_TRACE !== "0";
const IMAGE_TRACE_MAX_SCENES = Math.max(0, Number(process.env.REMOTION_IMAGE_TRACE_MAX_SCENES ?? 3));
const IMAGE_TRACE_MAX_PATHS = Math.max(16, Number(process.env.REMOTION_IMAGE_TRACE_MAX_PATHS ?? 90));
const HAND_ASSET = "hand-real-pen.png";
const GLYPH_FONT_CANDIDATES = [
  process.env.EXPLAINFLOW_GLYPH_FONT,
  "C:\\Windows\\Fonts\\simkai.ttf",
  "C:\\Windows\\Fonts\\simfang.ttf",
  "C:\\Windows\\Fonts\\msyh.ttc",
  "C:\\Windows\\Fonts\\simsun.ttc",
].filter(Boolean);
const ttsInFlight = new Map();

mkdirSync(OUTPUT_DIR, { recursive: true });
mkdirSync(AUDIO_DIR, { recursive: true });
mkdirSync(GENERATED_DIR, { recursive: true });

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

function saveJobs() {
  try {
    writeFileSync(JOBS_FILE, JSON.stringify(jobs, null, 2), "utf8");
  } catch (err) {
    console.warn("[jobs] Failed to save jobs.json:", err.message);
  }
}

function updateJob(jobId, patch) {
  jobs[jobId] = { ...jobs[jobId], ...patch };
  saveJobs();
}

for (const [id, job] of Object.entries(jobs)) {
  if (job.status === "processing") {
    jobs[id].status = "failed";
    jobs[id].error = "Server restarted during render";
  }
}
saveJobs();

function readBody(req, limitBytes = 10 * 1024 * 1024) {
  return new Promise((resolvePromise, reject) => {
    let body = "";
    req.on("data", (chunk) => {
      body += chunk;
      if (Buffer.byteLength(body) > limitBytes) {
        reject(new Error("Request body too large"));
        req.destroy();
      }
    });
    req.on("end", () => resolvePromise(body));
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

function ttsCacheFilename(text, voice) {
  const hash = createHash("sha1")
    .update(JSON.stringify({ text: String(text ?? ""), voice: String(voice ?? "") }))
    .digest("hex")
    .slice(0, 20);
  return `tts_${hash}.mp3`;
}

async function synthesizeScene(sceneId, text, voice) {
  const narration = String(text ?? "").trim();
  if (!narration) return null;
  const filename = ttsCacheFilename(narration, voice);
  const outPath = join(AUDIO_DIR, filename);
  const audioUrl = `http://localhost:${PORT}/audio/${filename}`;
  if (existsSync(outPath) && statSync(outPath).size > 0) {
    console.log(`[tts] cache hit: ${sceneId}`);
    return audioUrl;
  }
  if (ttsInFlight.has(filename)) {
    await ttsInFlight.get(filename);
    return audioUrl;
  }

  const pending = postBuffer(`${PYTHON_API}/narration/synthesize`, {
    text: narration,
    voice,
  }).then((audio) => {
    writeFileSync(outPath, audio);
  });
  ttsInFlight.set(filename, pending);
  try {
    await pending;
    return audioUrl;
  } finally {
    ttsInFlight.delete(filename);
  }
}

async function injectAudio(storyboard, voice) {
  const voiceKey = voice ?? "xiaoxiao";
  const results = await Promise.allSettled(
    storyboard.scenes.map((scene) =>
      synthesizeScene(scene.id, scene.narration || scene.title || "", voiceKey),
    ),
  );

  const scenes = storyboard.scenes.map((scene, index) => {
    const result = results[index];
    return {
      ...scene,
      audioUrl: result.status === "fulfilled" ? result.value : null,
    };
  });

  const failed = results.filter((result) => result.status === "rejected");
  if (failed.length > 0) {
    console.warn(
      `[tts] ${failed.length} scene(s) failed:`,
      failed.map((result) => result.reason?.message),
    );
  }

  return { ...storyboard, scenes };
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

async function traceWhiteboardImageBase64(imageBase64) {
  const image = Buffer.from(normalizeBase64Image(imageBase64), "base64");
  const { data, info } = await sharp(image)
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

async function injectImageTraces(storyboard) {
  if (!ENABLE_IMAGE_TRACE || IMAGE_TRACE_MAX_SCENES <= 0) return storyboard;

  const candidates = storyboard.scenes
    .filter((scene) => scene.image_description && !scene.trace_strokes && !scene.traceStrokes)
    .slice(0, IMAGE_TRACE_MAX_SCENES);
  if (candidates.length === 0) return storyboard;

  try {
    console.log(`[image-trace] Generating ${candidates.length} Seedream reference image(s)...`);
    const response = await postJson(
      `${PYTHON_API}/imagegen/scenes`,
      {
        scenes: candidates.map((scene) => ({
          scene_id: scene.id,
          topic: storyboard.topic ?? "",
          title: scene.title ?? "",
          image_description: scene.image_description,
        })),
      },
      180000,
    );

    const tracesBySceneId = {};
    for (const scene of candidates) {
      const imageBase64 = response.images?.[scene.id];
      if (!imageBase64) continue;
      const traceStrokes = await traceWhiteboardImageBase64(imageBase64);
      if (traceStrokes.length > 0) {
        tracesBySceneId[scene.id] = traceStrokes;
        console.log(`[image-trace] ${scene.id}: ${traceStrokes.length} drawable path(s)`);
      }
    }

    if (Object.keys(tracesBySceneId).length === 0) return storyboard;
    return {
      ...storyboard,
      scenes: storyboard.scenes.map((scene) => ({
        ...scene,
        trace_strokes: tracesBySceneId[scene.id] ?? scene.trace_strokes ?? scene.traceStrokes ?? null,
      })),
    };
  } catch (err) {
    console.warn(`[image-trace] Seedream trace skipped: ${err.message}`);
    return storyboard;
  }
}

let glyphFontCache;

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
          strokeWidth: rounded(Math.max(2.2, Math.min(5.2, fontSize * 0.045))),
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
  const loaded = loadGlyphFont();
  if (!loaded) {
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
          strokeWidth: fragment.strokeWidth,
          dashLength: fragment.dashLength,
          fontOutline: true,
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

  return { scenes: enhancedScenes, glyphCount, fontPath: loaded.fontPath };
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
  if (!/\b["']?kind["']?\s*:\s*["'](?:path|stroke|shape|arrow|box)["']/.test(code)) {
    throw new Error("drawOps must include path/stroke operations for diagrams");
  }
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

function validateHandwrittenAnimeStyle(code) {
  if (!/\b(STXingkai|Xingkai|KaiTi|STKaiti|Kaiti|楷体|华文行楷|华文楷体)\b/i.test(code)) {
    throw new Error(
      "Generated TSX must use an explicit Chinese handwriting font stack such as STXingkai/华文行楷/KaiTi/STKaiti",
    );
  }
  if (/\bfontWeight\s*:\s*["']?(?:700|800|900|bold)\b/i.test(code)) {
    throw new Error("Handwritten text must not use bold sans-serif styling");
  }
  if (!/\b(AnimeDoodle|CartoonDiagram|CartoonMascot|DoodleCharacter|anime|cartoon|doodle)\b/i.test(code)) {
    throw new Error("Generated TSX must include anime/cartoon whiteboard doodle graphics, not only charts or slide labels");
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
  validateHandwrittenAnimeStyle(code);
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
    throw new Error("Generated TSX must include muted watercolor-style accent colors");
  }
  if (!code.includes(HAND_ASSET)) {
    throw new Error(`Generated TSX must use staticFile("${HAND_ASSET}") for the visible hand holding a pen`);
  }
  if (!/\bstaticFile\s*\(/.test(code)) {
    throw new Error("Generated TSX must reference the hand asset with staticFile()");
  }
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

async function generateRemotionCode(storyboard) {
  const response = await postJson(`${PYTHON_API}/planner/remotion-code`, {
    storyboard,
    fps: FPS,
    width: WIDTH,
    height: HEIGHT,
    style_prompt:
      "Directly generate this lesson as a real whiteboard animation with a visible hand holding a marker. " +
      "Every visible text and diagram must be written or drawn live while the hand follows the actual stroke path. " +
      "Import Img and staticFile from remotion and render <Img src={staticFile(\"hand-real-pen.png\")} /> " +
      "inside a HandPen component positioned from getPenPosition(frame) coordinates. " +
      "Use exact constants: const HAND_WIDTH = 260; const HAND_HEIGHT = 289; const PEN_TIP_X = 15; const PEN_TIP_Y = 78; " +
      "position with left: tipX - PEN_TIP_X and top: tipY - PEN_TIP_Y so the marker tip touches the active stroke. " +
      "HandPen must return an absolutely positioned HTML div wrapping Img, and <HandPen> must be rendered as a sibling after the SVG, never inside SVG. " +
      "Define drawOps with kind/startFrame/endFrame/points, pointOnPolyline(), getActiveDrawOp(), and getPenPosition(frame). " +
      "The hand must move up/down/left/right within words, not slide on one text baseline; text ops need stroke-like zig-zag points. " +
      "Use glyphPaths/GlyphText/DrawGlyphPath for Chinese text so the renderer can preprocess opentype.js font outline paths, " +
      "and use strokeDasharray/strokeDashoffset SVG line drawing with matching drawOps. " +
      "Use a sparse off-white canvas, black marker outlines, blue marker titles, light washes only when useful, " +
      "animated dashed paths must use fill=\"none\"; use separate closed wash shapes behind strokes. " +
      "and lots of negative space. " +
      "For Chinese text use STXingkai/华文行楷/KaiTi/STKaiti/Kaiti SC/cursive first, not default bold sans-serif. " +
      "Make the graphics anime/cartoon whiteboard doodles with at least one simple mascot, face, or expressive icon. " +
      "Do not use SVG <animate>; all timing must be driven by Remotion frame values. " +
      "Do not use templates, local components, slide-deck cards, stock images, or component libraries.",
  });

  const validatedTsx = validateGeneratedTsx(response.tsx);
  const glyphTsx = injectGlyphOutlineDrawing(validatedTsx);

  return {
    tsx: validateGeneratedTsx(glyphTsx),
    durationInFrames: Math.max(FPS * 10, Number(response.duration_in_frames ?? FPS * 60)),
    fps: Number(response.fps ?? FPS),
    width: Number(response.width ?? WIDTH),
    height: Number(response.height ?? HEIGHT),
  };
}

function writeGeneratedProject(jobId, generated) {
  const projectDir = join(GENERATED_DIR, jobId);
  mkdirSync(projectDir, { recursive: true });

  const componentPath = join(projectDir, "GeneratedVideo.tsx");
  const entryPath = join(projectDir, "index.tsx");

  writeFileSync(componentPath, generated.tsx, "utf8");
  writeFileSync(
    entryPath,
    `import React from "react";
import { Composition, registerRoot } from "remotion";
import { GeneratedVideo } from "./GeneratedVideo";

const RemotionRoot: React.FC = () => {
  return (
    <Composition
      id="${COMPOSITION_ID}"
      component={GeneratedVideo}
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

async function renderVideo(jobId, storyboard, voice, outputPath) {
  updateJob(jobId, { phase: "tts", progress: 0 });
  console.log(`[tts] Synthesizing ${storyboard.scenes.length} scenes...`);
  const storyboardWithAudio = await injectAudio(storyboard, voice);
  console.log("[tts] Done");

  updateJob(jobId, { phase: "imagegen", progress: 0 });
  const storyboardWithTraces = await injectImageTraces(storyboardWithAudio);

  updateJob(jobId, { phase: "codegen", progress: 0 });
  console.log("[codegen] Generating Remotion TSX via LLM...");
  const generated = await generateRemotionCode(storyboardWithTraces);
  const { projectDir, entryPath } = writeGeneratedProject(jobId, generated);
  updateJob(jobId, { generatedDir: projectDir });
  console.log("[codegen] Generated project:", projectDir);

  await bundleAndRender(jobId, entryPath, outputPath);
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

const server = http.createServer(async (req, res) => {
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Access-Control-Allow-Methods", "GET, POST, PATCH, DELETE, OPTIONS");
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

  if (req.method === "POST" && url.pathname === "/render") {
    try {
      const { storyboard, voice } = JSON.parse(await readBody(req));
      if (!storyboard?.scenes?.length) {
        sendJson(res, 400, { error: "storyboard.scenes is required" });
        return;
      }
      try {
        await ensureLargeModelAvailable();
      } catch (err) {
        sendJson(res, 503, { error: err.message });
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
        topic: storyboard.topic ?? "Untitled",
        createdAt,
      };
      saveJobs();

      sendJson(res, 202, { jobId, createdAt });

      renderVideo(jobId, storyboard, voice, outputPath)
        .then(() => updateJob(jobId, { status: "done", progress: 100, phase: "done" }))
        .catch((err) => {
          updateJob(jobId, { status: "failed", error: err.message });
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
        error: job.error ?? null,
      }))
      .sort((a, b) => (b.createdAt ?? "").localeCompare(a.createdAt ?? ""));
    sendJson(res, 200, { jobs: list });
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
        job.topic = String(patch.topic).slice(0, 200);
      }
      saveJobs();
      sendJson(res, 200, { ok: true });
    } catch {
      sendJson(res, 400, { error: "invalid JSON" });
    }
    return;
  }

  if (req.method === "DELETE" && url.pathname.startsWith("/job/")) {
    const jobId = url.pathname.slice(5);
    const job = jobs[jobId];
    if (!job) {
      sendJson(res, 404, { error: "not found" });
      return;
    }
    if (job.outputPath) {
      try {
        unlinkSync(job.outputPath);
      } catch {}
    }
    removeGeneratedDir(job.generatedDir);
    delete jobs[jobId];
    saveJobs();
    sendJson(res, 200, { ok: true });
    return;
  }

  if (req.method === "GET" && url.pathname.startsWith("/audio/")) {
    const filename = basename(url.pathname.slice(7));
    serveStaticFile(res, join(AUDIO_DIR, filename), "audio/mpeg");
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
