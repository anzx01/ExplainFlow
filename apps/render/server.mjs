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
import { mkdirSync, createReadStream, statSync, readFileSync, writeFileSync, existsSync } from "fs";
import { join, dirname, basename } from "path";
import { fileURLToPath } from "url";
import { randomUUID } from "crypto";
import { bundle } from "@remotion/bundler";
import { renderMedia, selectComposition, RenderInternals } from "@remotion/renderer";

const __dirname = dirname(fileURLToPath(import.meta.url));
const PORT = 3001;
const REMOTION_PORT = 3002;
const OUTPUT_DIR = join(__dirname, "../../outputs");
const JOBS_FILE = join(__dirname, "../../outputs/jobs.json");
const ENTRY = join(__dirname, "src/index.ts");
const CHROME = "C:\\Users\\DELL\\AppData\\Local\\ms-playwright\\chromium_headless_shell-1223\\chrome-headless-shell-win64\\chrome-headless-shell.exe";

mkdirSync(OUTPUT_DIR, { recursive: true });

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

async function renderVideo(jobId, storyboard, outputPath) {
  const serveUrl = await getServeUrl();

  const composition = await selectComposition({
    serveUrl,
    id: "WhiteboardVideo",
    inputProps: { storyboard },
    browserExecutable: CHROME,
  });

  await renderMedia({
    composition,
    serveUrl,
    codec: "h264",
    outputLocation: outputPath,
    inputProps: { storyboard },
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
        const { storyboard } = JSON.parse(body);
        const jobId = randomUUID();
        const slug = (storyboard.topic ?? "video").replace(/[^\w一-鿿]/g, "_");
        const outputPath = join(OUTPUT_DIR, `${slug}_${jobId.slice(0, 8)}.mp4`);

        jobs[jobId] = { status: "processing", outputPath, progress: 0 };
        saveJobs();

        res.writeHead(202, { "Content-Type": "application/json" });
        res.end(JSON.stringify({ jobId }));

        renderVideo(jobId, storyboard, outputPath)
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

  if (req.method === "GET" && url.pathname.startsWith("/job/")) {
    const job = jobs[url.pathname.slice(5)];
    if (!job) {
      res.writeHead(404, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ error: "not found" }));
      return;
    }
    res.writeHead(200, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ status: job.status, progress: job.progress ?? 0, error: job.error ?? null }));
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
