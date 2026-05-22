/**
 * server.mjs — HTTP 服务器入口
 * 只包含服务器启动、路由注册和请求处理逻辑
 *
 * Runtime model:
 * Storyboard -> cached TTS audio -> validated Remotion TSX -> per-job bundle -> MP4.
 */
import http from "http";
import { createReadStream, existsSync, mkdirSync, statSync } from "fs";
import { basename, join } from "path";
import { sendJson, serveStaticFile, serveMediaFile } from "./http-utils.mjs";
import { randomUUID } from "crypto";
import {
  AUDIO_DIR,
  GENERATED_DIR,
  MUSIC_DIR,
  OUTPUT_DIR,
  PORT,
  PUBLIC_GENERATED_DIR,
} from "./config.mjs";
import { jobs, saveJobsAsync, updateJob } from "./jobs.mjs";
import {
  assertStoryboardEncodingHealthy,
  cleanUserText,
  clampNumber,
  ensureLargeModelAvailable,
  listMusicTracks,
  makeSlug,
  readBody,
  resolveMusicTrack,
  sanitizeStoryboardText,
} from "./utils.mjs";
import { probePlayableAudio, normalizeMusicTrackForRemotion } from "./tts.mjs";
import { deleteJobRecord, isInside, renderVideo } from "./render-core.mjs";

// ---------------------------------------------------------------------------
// Startup: ensure required directories exist and reset stale jobs
// ---------------------------------------------------------------------------

mkdirSync(OUTPUT_DIR, { recursive: true });
mkdirSync(AUDIO_DIR, { recursive: true });
mkdirSync(MUSIC_DIR, { recursive: true });
mkdirSync(GENERATED_DIR, { recursive: true });
mkdirSync(PUBLIC_GENERATED_DIR, { recursive: true });

for (const [jobId, job] of Object.entries(jobs)) {
  if (job.status === "processing") {
    jobs[jobId] = { ...job, status: "failed", phase: "failed", error: "Server restarted" };
  }
}

// ---------------------------------------------------------------------------
// HTTP server
// ---------------------------------------------------------------------------

const server = http.createServer(async (req, res) => {
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Access-Control-Allow-Methods", "GET, HEAD, POST, PATCH, DELETE, OPTIONS");
  res.setHeader("Access-Control-Allow-Headers", "Content-Type, Range");

  if (req.method === "OPTIONS") { res.writeHead(204); res.end(); return; }

  const url = new URL(req.url, `http://localhost:${PORT}`);

  // GET /health
  if (req.method === "GET" && url.pathname === "/health") {
    sendJson(res, 200, { status: "ok", mode: "llm-remotion" });
    return;
  }

  // GET /music
  if (req.method === "GET" && url.pathname === "/music") {
    sendJson(res, 200, { tracks: listMusicTracks() });
    return;
  }

  // POST /render
  if (req.method === "POST" && url.pathname === "/render") {
    try {
      const payload = JSON.parse(await readBody(req));
      let {
        storyboard, voice,
        subtitlesEnabled, subtitles_enabled,
        backgroundMusicEnabled, background_music_enabled,
        backgroundMusicId, background_music_id,
        backgroundMusicVolume, background_music_volume,
      } = payload;
      if (!storyboard?.scenes?.length) { sendJson(res, 400, { error: "storyboard.scenes is required" }); return; }

      const useBackgroundMusic = Boolean(backgroundMusicEnabled ?? background_music_enabled);
      let backgroundMusicTrack = null;
      let backgroundMusicVolumeValue = 0.12;
      if (useBackgroundMusic) {
        const requestedTrackId = backgroundMusicId ?? background_music_id;
        const availableTracks = listMusicTracks();
        const trackId = requestedTrackId || availableTracks[0]?.id;
        backgroundMusicTrack = trackId ? resolveMusicTrack(trackId) : null;
        if (!backgroundMusicTrack) { sendJson(res, 400, { error: "background music track not found" }); return; }
        if (!(await probePlayableAudio(backgroundMusicTrack.filePath))) {
          sendJson(res, 400, { error: `background music is not a playable audio file: ${backgroundMusicTrack.id}` });
          return;
        }
        backgroundMusicTrack = await normalizeMusicTrackForRemotion(backgroundMusicTrack);
        if (!(await probePlayableAudio(backgroundMusicTrack.filePath))) {
          sendJson(res, 400, { error: `background music could not be normalized: ${backgroundMusicTrack.id}` });
          return;
        }
        backgroundMusicVolumeValue = clampNumber(backgroundMusicVolume ?? background_music_volume, 0, 0.5, 0.12);
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
      const outputPath = join(OUTPUT_DIR, `${makeSlug(storyboard.topic)}_${jobId.slice(0, 8)}.mp4`);
      const createdAt = new Date().toISOString();
      jobs[jobId] = {
        status: "processing", outputPath, progress: 0, phase: "queued",
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

  // GET /jobs
  if (req.method === "GET" && url.pathname === "/jobs") {
    const list = Object.entries(jobs)
      .map(([id, job]) => ({
        id, status: job.status, progress: job.progress ?? 0, phase: job.phase ?? null,
        topic: job.topic ?? null, createdAt: job.createdAt ?? null,
        actualDurationSeconds: job.actualDurationSeconds ?? null, qa: job.qa ?? null, error: job.error ?? null,
      }))
      .sort((a, b) => (b.createdAt ?? "").localeCompare(a.createdAt ?? ""));
    sendJson(res, 200, { jobs: list });
    return;
  }

  // POST /jobs/delete
  if (req.method === "POST" && url.pathname === "/jobs/delete") {
    try {
      const payload = JSON.parse(await readBody(req, 1024 * 1024));
      const jobIds = Array.isArray(payload.jobIds) ? payload.jobIds : [];
      const deleted = [], missing = [];
      for (const rawId of jobIds) {
        const jobId = String(rawId);
        if (deleteJobRecord(jobId)) deleted.push(jobId);
        else missing.push(jobId);
      }
      saveJobsAsync();
      sendJson(res, 200, { ok: true, deleted, missing });
    } catch { sendJson(res, 400, { error: "invalid JSON" }); }
    return;
  }

  // GET /job/:id
  if (req.method === "GET" && url.pathname.startsWith("/job/")) {
    const jobId = url.pathname.slice(5);
    const job = jobs[jobId];
    if (!job) { sendJson(res, 404, { error: "not found" }); return; }
    sendJson(res, 200, {
      status: job.status, progress: job.progress ?? 0, phase: job.phase ?? null,
      createdAt: job.createdAt ?? null, actualDurationSeconds: job.actualDurationSeconds ?? null,
      qa: job.qa ?? null, error: job.error ?? null,
    });
    return;
  }

  // PATCH /job/:id
  if (req.method === "PATCH" && url.pathname.startsWith("/job/")) {
    const jobId = url.pathname.slice(5);
    const job = jobs[jobId];
    if (!job) { sendJson(res, 404, { error: "not found" }); return; }
    try {
      const patch = JSON.parse(await readBody(req, 1024 * 1024));
      if (patch.topic !== undefined) job.topic = cleanUserText(patch.topic, job.topic ?? "Untitled").slice(0, 200);
      saveJobsAsync();
      sendJson(res, 200, { ok: true });
    } catch { sendJson(res, 400, { error: "invalid JSON" }); }
    return;
  }

  // DELETE /job/:id
  if (req.method === "DELETE" && url.pathname.startsWith("/job/")) {
    const jobId = url.pathname.slice(5);
    if (!jobs[jobId]) { sendJson(res, 404, { error: "not found" }); return; }
    deleteJobRecord(jobId);
    saveJobsAsync();
    sendJson(res, 200, { ok: true });
    return;
  }

  // GET /audio/:filename
  if (req.method === "GET" && url.pathname.startsWith("/audio/")) {
    const filename = basename(url.pathname.slice(7));
    serveStaticFile(res, join(AUDIO_DIR, filename), "audio/mpeg");
    return;
  }

  // GET|HEAD /music/:trackId
  if ((req.method === "GET" || req.method === "HEAD") && url.pathname.startsWith("/music/")) {
    const track = resolveMusicTrack(url.pathname.slice(7));
    if (!track) { sendJson(res, 404, { error: "music track not found" }); return; }
    serveMediaFile(req, res, track.filePath, track.contentType);
    return;
  }

  // GET /download/:id
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
      if (!Number.isFinite(start) || start < 0 || end < start) { res.writeHead(416); res.end(); return; }
      const chunkSize = end - start + 1;
      res.writeHead(206, {
        "Content-Type": "video/mp4", "Content-Range": `bytes ${start}-${end}/${fileSize}`,
        "Accept-Ranges": "bytes", "Content-Length": chunkSize,
        "Content-Disposition": `inline; filename="video.mp4"; filename*=UTF-8''${encodedFilename}`,
      });
      createReadStream(job.outputPath, { start, end }).pipe(res);
      return;
    }

    res.writeHead(200, {
      "Content-Type": "video/mp4", "Content-Length": fileSize,
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
