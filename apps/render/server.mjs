/**
 * ExplainFlow Render Server
 * POST /render  { storyboard } → { jobId }
 * GET  /job/:id → { status, error? }
 * GET  /download/:id → MP4 stream (supports Range for browser <video> seek)
 *
 * Jobs are persisted to jobs.json so they survive server restarts.
 * Bundle is served on port 3002 to avoid conflicting with Next.js on 3000.
 */
import http from "http";
import { mkdirSync, createReadStream, createWriteStream, statSync, readFileSync, writeFileSync, existsSync, unlinkSync } from "fs";
import { join, dirname, basename } from "path";
import { fileURLToPath } from "url";
import { randomUUID } from "crypto";
import { bundle } from "@remotion/bundler";
import { renderMedia, selectComposition, RenderInternals } from "@remotion/renderer";
import sharp from "sharp";
import opentype from "opentype.js";

const __dirname = dirname(fileURLToPath(import.meta.url));
const PORT = 3001;
const REMOTION_PORT = 3002;
const OUTPUT_DIR = join(__dirname, "../../outputs");
const AUDIO_DIR = join(__dirname, "../../outputs/audio");
const IMAGES_DIR = join(__dirname, "../../outputs/images");
const JOBS_FILE = join(__dirname, "../../outputs/jobs.json");
const ENTRY = join(__dirname, "src/index.ts");
const CHROME = "C:\\Users\\DELL\\AppData\\Local\\ms-playwright\\chromium_headless_shell-1223\\chrome-headless-shell-win64\\chrome-headless-shell.exe";
const PYTHON_API = "http://localhost:8000";

mkdirSync(OUTPUT_DIR, { recursive: true });
mkdirSync(AUDIO_DIR, { recursive: true });
mkdirSync(IMAGES_DIR, { recursive: true });

// ── 字体加载（opentype.js，用于文字 → SVG path）──
const FONTS_DIR = join(__dirname, "public/fonts");
let fontRegular = null;
let fontBold = null;
try {
  const bufR = readFileSync(join(FONTS_DIR, "Caveat.ttf"));
  fontRegular = opentype.parse(bufR.buffer);
  fontBold = fontRegular; // 可变字体，用同一个文件
  console.log("[font] Caveat loaded,", fontRegular.numGlyphs, "glyphs");
} catch (e) {
  console.warn("[font] Failed to load Caveat.ttf:", e.message);
}

/**
 * 将文字转为 SVG path 数据。
 * @param {string} text
 * @param {number} fontSize
 * @param {boolean} bold
 * @returns {{ d: string, bbox: {x1,y1,x2,y2}, width: number } | null}
 */
function textToSvgPath(text, fontSize, bold = false) {
  const font = bold ? fontBold : fontRegular;
  if (!font || !text?.trim()) return null;
  try {
    // 逐字符生成 path，跳过字体不含的字符（.notdef），避免 NaN 污染整段路径
    const pathSegments = [];
    let x = 0;
    for (const char of text) {
      if (char === " " || char === "\t") {
        x += fontSize * 0.3;
        continue;
      }
      const glyph = font.charToGlyph(char);
      const advance = glyph.advanceWidth
        ? (glyph.advanceWidth / font.unitsPerEm) * fontSize
        : fontSize * 0.55;
      if (glyph.name === ".notdef" || glyph.unicode === undefined) {
        x += advance;
        continue;
      }
      const p = font.getPath(char, x, fontSize, fontSize);
      const d = p.toPathData(2);
      if (d && d.length > 3 && !d.includes("NaN") && !d.includes("Infinity")) {
        pathSegments.push(d);
      }
      x += advance;
    }
    if (pathSegments.length === 0) return null;
    const combined = pathSegments.join(" ");
    // 从路径数据中提取 bbox
    const allNums = combined.match(/-?\d+\.?\d*/g)?.map(Number) ?? [];
    if (allNums.length < 4) return null;
    const xs = [], ys = [];
    let isX = true;
    for (const n of allNums) {
      if (isX) xs.push(n); else ys.push(n);
      isX = !isX;
    }
    const bbox = {
      x1: Math.min(...xs), y1: Math.min(...ys),
      x2: Math.max(...xs), y2: Math.max(...ys),
    };
    return { d: combined, bbox, width: x };
  } catch {
    return null;
  }
}

/** 根据动画类型推断合适的字号 */
function fontSizeForAnim(type, slotH) {
  switch (type) {
    case "write_title": return Math.min(120, Math.max(52, slotH * 0.55) * 1.2);
    case "write_formula":
    case "formula_reveal": return Math.max(56, Math.min(90, slotH * 0.45));
    case "bullet_list":
    case "step_reveal": return Math.max(42, Math.min(68, slotH * 0.6));
    default: return Math.max(52, Math.min(96, slotH * 0.55));
  }
}

/**
 * 为 storyboard 中每个场景的文字注入 SVG path 数据。
 * 在 Remotion 端直接用 evolvePath() 描绘，实现真正的手写效果。
 */
function injectTextPaths(storyboard) {
  if (!fontRegular) return storyboard;
  const FPS = 30;
  const CONTENT_H = 1080 - 130 - 130; // HEIGHT - TITLE_H - SUBTITLE_H
  const n = storyboard.scenes[0]?.animations?.length || 1;
  const slotH = CONTENT_H / Math.max(n, 1);

  for (const scene of storyboard.scenes) {
    const animCount = scene.animations.length;
    const perSlotH = CONTENT_H / Math.max(animCount, 1);

    // 场景标题
    scene.titlePath = textToSvgPath(scene.title, 52, true);

    for (let i = 0; i < scene.animations.length; i++) {
      const anim = scene.animations[i];
      const fs = fontSizeForAnim(anim.type, perSlotH);
      const isBold = anim.type === "write_title" || i === 0;

      if (anim.content) {
        anim.svgPath = textToSvgPath(anim.content, fs, isBold);
      }
      if (anim.latex) {
        anim.latexSvgPath = textToSvgPath(anim.latex, Math.max(56, Math.min(90, perSlotH * 0.45)), true);
      }
      if (anim.items?.length) {
        const itemFs = Math.max(42, Math.min(68, perSlotH / (anim.items.length + 1.5) * 0.85));
        anim.itemPaths = anim.items.map(item => textToSvgPath(item, itemFs, false));
      }
    }
  }
  return storyboard;
}

// Persist jobs to disk so they survive restarts
function loadJobs() {
  try {
    if (existsSync(JOBS_FILE)) return JSON.parse(readFileSync(JOBS_FILE, "utf8"));
  } catch {}
  return {};
}
function saveJobs() {
  try { writeFileSync(JOBS_FILE, JSON.stringify(jobs, null, 2)); } catch {}
}

const jobs = loadJobs();

// On startup, mark any "processing" jobs as failed (they were interrupted by restart)
for (const [id, job] of Object.entries(jobs)) {
  if (job.status === "processing") {
    jobs[id].status = "failed";
    jobs[id].error = "Server restarted during render";
  }
}
saveJobs();


// TTS: call Python API to synthesize a scene's narration, save to AUDIO_DIR
async function synthesizeScene(sceneId, text, voice) {
  const filename = `${sceneId}_${randomUUID().slice(0, 8)}.mp3`;
  const outPath = join(AUDIO_DIR, filename);
  const body = JSON.stringify({ text, voice });

  await new Promise((resolve, reject) => {
    const req = http.request(
      `${PYTHON_API}/narration/synthesize`,
      { method: "POST", headers: { "Content-Type": "application/json", "Content-Length": Buffer.byteLength(body) } },
      (res) => {
        if (res.statusCode !== 200) {
          reject(new Error(`TTS API returned ${res.statusCode}`));
          return;
        }
        const chunks = [];
        res.on("data", (c) => chunks.push(c));
        res.on("end", () => {
          writeFileSync(outPath, Buffer.concat(chunks));
          resolve();
        });
      }
    );
    req.on("error", reject);
    req.write(body);
    req.end();
  });

  return `http://localhost:${PORT}/audio/${filename}`;
}

// Synthesize all scenes in parallel, inject audioUrl into each scene
async function injectAudio(storyboard, voice) {
  const voiceKey = voice ?? "xiaoxiao";
  const results = await Promise.allSettled(
    storyboard.scenes.map((scene) => synthesizeScene(scene.id, scene.narration, voiceKey))
  );

  const scenes = storyboard.scenes.map((scene, i) => {
    const r = results[i];
    return { ...scene, audioUrl: r.status === "fulfilled" ? r.value : null };
  });

  const failed = results.filter((r) => r.status === "rejected");
  if (failed.length > 0) {
    console.warn(`[tts] ${failed.length} scene(s) failed:`, failed.map((r) => r.reason?.message));
  }

  return { ...storyboard, scenes };
}

// Generate whiteboard sketch images for all scenes via Seedream API,
// then download them locally so Remotion doesn't hit remote URL timeouts
async function injectImages(storyboard, jobId) {
  const scenes = storyboard.scenes.filter((s) => s.image_description);
  if (scenes.length === 0) return storyboard;

  const body = JSON.stringify({
    scenes: scenes.map((s) => ({
      scene_id: s.id,
      topic: storyboard.topic,
      title: s.title,
      image_description: s.image_description,
    })),
  });

  let imageMap = {};
  try {
    const result = await new Promise((resolve, reject) => {
      const req = http.request(
        `${PYTHON_API}/imagegen/scenes`,
        { method: "POST", headers: { "Content-Type": "application/json", "Content-Length": Buffer.byteLength(body) } },
        (res) => {
          if (res.statusCode !== 200) {
            reject(new Error(`imagegen API returned ${res.statusCode}`));
            return;
          }
          let data = "";
          res.on("data", (c) => (data += c));
          res.on("end", () => resolve(JSON.parse(data)));
        }
      );
      req.on("error", reject);
      req.write(body);
      req.end();
    });

    const remoteImages = result.images ?? {};
    const generated = Object.values(remoteImages).filter(Boolean).length;
    console.log(`[imagegen] ${generated}/${scenes.length} remote images ready, downloading...`);

    // Download all images locally to avoid remote URL timeouts during Remotion render
    const downloads = await Promise.all(
      Object.entries(remoteImages).map(async ([sceneId, b64Data]) => {
        if (!b64Data) return [sceneId, null];
        const filename = `${jobId}_${sceneId}.jpg`;
        const localPath = join(IMAGES_DIR, filename);
        const tmpPath = localPath + '.tmp';
        try {
          // Python 已在服务端下载好图片，直接解码 base64 写本地文件
          writeFileSync(tmpPath, Buffer.from(b64Data, 'base64'));
          // 缩图到 512x512，手绘线条无需高分辨率
          await sharp(tmpPath).resize(512, 512, { fit: 'inside' }).jpeg({ quality: 75 }).toFile(localPath);
          try { unlinkSync(tmpPath); } catch {}
          return [sceneId, `http://localhost:${PORT}/images/${filename}`];
        } catch (err) {
          try { unlinkSync(tmpPath); } catch {}
          console.warn(`[imagegen] decode/resize failed for ${sceneId}: ${err.message}`);
          return [sceneId, null];
        }
      })
    );
    imageMap = Object.fromEntries(downloads);
    const localCount = Object.values(imageMap).filter(Boolean).length;
    console.log(`[imagegen] ${localCount}/${scenes.length} images saved locally`);
  } catch (err) {
    console.warn("[imagegen] failed, falling back to code animation:", err.message);
  }

  return {
    ...storyboard,
    scenes: storyboard.scenes.map((s) => ({ ...s, imageUrl: imageMap[s.id] ?? null })),
  };
}


let serveUrlCache = null;
let closeStaticServer = null;

async function getServeUrl() {
  if (serveUrlCache) return serveUrlCache;

  console.log("[render] Bundling Remotion project...");
  const bundlePath = await bundle({
    entryPoint: ENTRY,
    onProgress: (p) => process.stdout.write(`\r[bundle] ${p}%`),
  });
  console.log("\n[render] Bundle ready:", bundlePath.slice(0, 80));

  const downloadMap = RenderInternals.makeDownloadMap();
  const { port, close } = await RenderInternals.serveStatic(bundlePath, {
    port: REMOTION_PORT,
    downloadMap,
    offthreadVideoThreads: 2,
    logLevel: "warn",
    indent: false,
    offthreadVideoCacheSizeInBytes: null,
    binariesDirectory: null,
    forceIPv4: false,
  });
  closeStaticServer = close;
  serveUrlCache = `http://localhost:${port}`;
  console.log(`[render] Remotion static server → ${serveUrlCache}`);
  return serveUrlCache;
}

async function renderVideo(jobId, storyboard, voice, outputPath) {
  jobs[jobId].phase = "tts";
  console.log(`[tts] Synthesizing ${storyboard.scenes.length} scenes...`);
  const storyboardWithAudio = await injectAudio(storyboard, voice);
  console.log("[tts] Done");

  jobs[jobId].phase = "imagegen";
  console.log(`[imagegen] Generating images for ${storyboard.scenes.length} scenes...`);
  const storyboardWithImages = await injectImages(storyboardWithAudio, jobId);
  console.log("[imagegen] Done");

  // 注入文字 SVG path（用于真实手写描绘动画）
  const storyboardFinal = injectTextPaths(storyboardWithImages);
  console.log("[textpath] SVG paths injected");

  jobs[jobId].phase = "rendering";

  const serveUrl = await getServeUrl();

  const composition = await selectComposition({
    serveUrl,
    id: "WhiteboardVideo",
    inputProps: { storyboard: storyboardFinal },
    browserExecutable: CHROME,
  });

  await renderMedia({
    composition,
    serveUrl,
    codec: "h264",
    outputLocation: outputPath,
    inputProps: { storyboard: storyboardFinal },
    browserExecutable: CHROME,
    concurrency: 4,
    onProgress: ({ progress }) => {
      process.stdout.write(`\r[render] ${Math.round(progress * 100)}%`);
      jobs[jobId].progress = Math.round(progress * 100);
    },
  });
  console.log(`\n[render] done → ${basename(outputPath)}`);
}

const server = http.createServer(async (req, res) => {
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Access-Control-Allow-Methods", "GET, POST, OPTIONS");
  res.setHeader("Access-Control-Allow-Headers", "Content-Type, Range");

  if (req.method === "OPTIONS") { res.writeHead(204); res.end(); return; }

  const url = new URL(req.url, `http://localhost:${PORT}`);

  if (req.method === "GET" && url.pathname === "/health") {
    res.writeHead(200, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ status: "ok" }));
    return;
  }

  if (req.method === "POST" && url.pathname === "/render") {
    let body = "";
    req.on("data", (c) => (body += c));
    req.on("end", async () => {
      try {
        const { storyboard, voice } = JSON.parse(body);
        const jobId = randomUUID();
        const slug = (storyboard.topic ?? "video").replace(/[^\w一-鿿]/g, "_");
        const outputPath = join(OUTPUT_DIR, `${slug}_${jobId.slice(0, 8)}.mp4`);

        jobs[jobId] = {
          status: "processing",
          outputPath,
          progress: 0,
          topic: storyboard.topic ?? "未命名",
          createdAt: new Date().toISOString(),
        };
        saveJobs();

        res.writeHead(202, { "Content-Type": "application/json" });
        res.end(JSON.stringify({ jobId }));

        renderVideo(jobId, storyboard, voice, outputPath)
          .then(() => {
            jobs[jobId].status = "done";
            jobs[jobId].progress = 100;
            saveJobs();
          })
          .catch((err) => {
            jobs[jobId].status = "failed";
            jobs[jobId].error = err.message;
            saveJobs();
            console.error(`\n[render] failed: ${err.message}`);
          });
      } catch (err) {
        res.writeHead(400, { "Content-Type": "application/json" });
        res.end(JSON.stringify({ error: err.message }));
      }
    });
    return;
  }

  // List all jobs
  if (req.method === "GET" && url.pathname === "/jobs") {
    const list = Object.entries(jobs).map(([id, job]) => ({
      id,
      status: job.status,
      progress: job.progress ?? 0,
      topic: job.topic ?? null,
      createdAt: job.createdAt ?? null,
      error: job.error ?? null,
    }));
    list.sort((a, b) => (b.createdAt ?? "").localeCompare(a.createdAt ?? ""));
    res.writeHead(200, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ jobs: list }));
    return;
  }

  // Get single job status
  if (req.method === "GET" && url.pathname.startsWith("/job/")) {
    const jobId = url.pathname.slice(5);
    const job = jobs[jobId];
    if (!job) {
      res.writeHead(404, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ error: "not found" }));
      return;
    }
    res.writeHead(200, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ status: job.status, progress: job.progress ?? 0, phase: job.phase ?? null, error: job.error ?? null }));
    return;
  }

  // Delete job (and its video file)
  if (req.method === "DELETE" && url.pathname.startsWith("/job/")) {
    const jobId = url.pathname.slice(5);
    const job = jobs[jobId];
    if (!job) {
      res.writeHead(404, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ error: "not found" }));
      return;
    }
    if (job.outputPath) {
      try { unlinkSync(job.outputPath); } catch {}
    }
    delete jobs[jobId];
    saveJobs();
    res.writeHead(200, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ ok: true }));
    return;
  }

  // Update job metadata (topic)
  if (req.method === "PATCH" && url.pathname.startsWith("/job/")) {
    const jobId = url.pathname.slice(5);
    const job = jobs[jobId];
    if (!job) {
      res.writeHead(404, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ error: "not found" }));
      return;
    }
    let body = "";
    req.on("data", (c) => (body += c));
    req.on("end", () => {
      try {
        const patch = JSON.parse(body);
        if (patch.topic !== undefined) jobs[jobId].topic = String(patch.topic).slice(0, 200);
        saveJobs();
        res.writeHead(200, { "Content-Type": "application/json" });
        res.end(JSON.stringify({ ok: true }));
      } catch {
        res.writeHead(400, { "Content-Type": "application/json" });
        res.end(JSON.stringify({ error: "invalid JSON" }));
      }
    });
    return;
  }

  if (req.method === "GET" && url.pathname.startsWith("/images/")) {
    const filename = url.pathname.slice(8);
    const imagePath = join(IMAGES_DIR, filename);
    if (!existsSync(imagePath)) {
      res.writeHead(404); res.end(); return;
    }
    const stat = statSync(imagePath);
    res.writeHead(200, { "Content-Type": "image/jpeg", "Content-Length": stat.size });
    createReadStream(imagePath).pipe(res);
    return;
  }

  if (req.method === "GET" && url.pathname.startsWith("/audio/")) {
    const filename = url.pathname.slice(7);
    const audioPath = join(AUDIO_DIR, filename);
    if (!existsSync(audioPath)) {
      res.writeHead(404); res.end(); return;
    }
    const stat = statSync(audioPath);
    res.writeHead(200, {
      "Content-Type": "audio/mpeg",
      "Content-Length": stat.size,
      "Accept-Ranges": "bytes",
    });
    createReadStream(audioPath).pipe(res);
    return;
  }

  if (req.method === "GET" && url.pathname.startsWith("/download/")) {
    const jobId = url.pathname.slice(10);
    const job = jobs[jobId];
    if (!job || job.status !== "done") {
      res.writeHead(404, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ error: "not ready" }));
      return;
    }

    const stat = statSync(job.outputPath);
    const fileSize = stat.size;
    const filename = basename(job.outputPath);
    const encodedFilename = encodeURIComponent(filename);
    const rangeHeader = req.headers["range"];

    if (rangeHeader) {
      const [startStr, endStr] = rangeHeader.replace("bytes=", "").split("-");
      const start = parseInt(startStr, 10);
      const end = endStr ? parseInt(endStr, 10) : fileSize - 1;
      const chunkSize = end - start + 1;
      res.writeHead(206, {
        "Content-Type": "video/mp4",
        "Content-Range": `bytes ${start}-${end}/${fileSize}`,
        "Accept-Ranges": "bytes",
        "Content-Length": chunkSize,
        "Content-Disposition": `inline; filename="video.mp4"; filename*=UTF-8''${encodedFilename}`,
      });
      createReadStream(job.outputPath, { start, end }).pipe(res);
    } else {
      res.writeHead(200, {
        "Content-Type": "video/mp4",
        "Content-Length": fileSize,
        "Accept-Ranges": "bytes",
        "Content-Disposition": `inline; filename="video.mp4"; filename*=UTF-8''${encodedFilename}`,
      });
      createReadStream(job.outputPath).pipe(res);
    }
    return;
  }

  res.writeHead(404); res.end();
});

getServeUrl().catch((e) => console.error("[render] startup error:", e));

process.on("SIGINT", async () => {
  if (closeStaticServer) await closeStaticServer();
  process.exit(0);
});

server.listen(PORT, () => console.log(`[render-server] http://localhost:${PORT}`));
