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
import { mkdirSync, createReadStream, statSync, readFileSync, writeFileSync, existsSync, unlinkSync } from "fs";
import { join, dirname, basename } from "path";
import { fileURLToPath } from "url";
import { randomUUID } from "crypto";
import { bundle } from "@remotion/bundler";
import { renderMedia, selectComposition, RenderInternals } from "@remotion/renderer";

const __dirname = dirname(fileURLToPath(import.meta.url));
const PORT = 3001;
const REMOTION_PORT = 3002;
const OUTPUT_DIR = join(__dirname, "../../outputs");
const AUDIO_DIR = join(__dirname, "../../outputs/audio");
const JOBS_FILE = join(__dirname, "../../outputs/jobs.json");
const ENTRY = join(__dirname, "src/index.ts");
const CHROME = "C:\\Users\\DELL\\AppData\\Local\\ms-playwright\\chromium_headless_shell-1223\\chrome-headless-shell-win64\\chrome-headless-shell.exe";
const PYTHON_API = "http://localhost:8000";

mkdirSync(OUTPUT_DIR, { recursive: true });
mkdirSync(AUDIO_DIR, { recursive: true });

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
  console.log(`[tts] Synthesizing ${storyboard.scenes.length} scenes...`);
  const storyboardWithAudio = await injectAudio(storyboard, voice);
  console.log("[tts] Done");

  const serveUrl = await getServeUrl();

  const composition = await selectComposition({
    serveUrl,
    id: "WhiteboardVideo",
    inputProps: { storyboard: storyboardWithAudio },
    browserExecutable: CHROME,
  });

  await renderMedia({
    composition,
    serveUrl,
    codec: "h264",
    outputLocation: outputPath,
    inputProps: { storyboard: storyboardWithAudio },
    browserExecutable: CHROME,
    concurrency: 2,
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
    res.end(JSON.stringify({ status: job.status, progress: job.progress ?? 0, error: job.error ?? null }));
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
    // Remove video file if it exists
    if (job.outputPath && existsSync(job.outputPath)) {
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
