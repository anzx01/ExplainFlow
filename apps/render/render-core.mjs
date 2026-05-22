/**
 * render-core.mjs — 渲染核心：FS 辅助、bundle/render、作业生命周期
 * 依赖: config.mjs, jobs.mjs, utils.mjs, tts.mjs, trace-inject.mjs, codegen.mjs, render-qa.mjs
 */
import { createServer as createNetServer } from "net";
import { existsSync, rmSync, unlinkSync } from "fs";
import { join, resolve } from "path";
import { bundle } from "@remotion/bundler";
import { renderMedia, selectComposition, RenderInternals } from "@remotion/renderer";
import {
  BROWSER_EXECUTABLE,
  COMPOSITION_ID,
  GENERATED_DIR,
  OUTPUT_DIR,
  PUBLIC_GENERATED_DIR,
  RENDER_CRF,
  RENDER_CONCURRENCY,
  RENDER_PIXEL_FORMAT,
  RENDER_X264_PRESET,
  STATIC_PORT_START,
} from "./config.mjs";
import { jobs, updateJob } from "./jobs.mjs";
import { assertStoryboardAudioComplete, injectAudio } from "./tts.mjs";
import { injectImageTraces } from "./trace-inject.mjs";
import { generateRemotionCode, writeGeneratedProject } from "./codegen.mjs";
import { runRenderQa } from "./render-qa.mjs";

// Re-export runRenderQa for callers that import from render-core
export { runRenderQa } from "./render-qa.mjs";

// ---------------------------------------------------------------------------
// File-system helpers
// ---------------------------------------------------------------------------

export function isInside(child, parent) {
  const resolvedChild = resolve(child);
  const resolvedParent = resolve(parent);
  return resolvedChild === resolvedParent || resolvedChild.startsWith(resolvedParent + "\\");
}

export function removeGeneratedDir(dir) {
  if (!dir) return;
  if (!isInside(dir, GENERATED_DIR)) return;
  try { rmSync(dir, { recursive: true, force: true }); } catch {}
}

export function removePublicGeneratedDir(dir) {
  if (!dir) return;
  if (!isInside(dir, PUBLIC_GENERATED_DIR)) return;
  try { rmSync(dir, { recursive: true, force: true }); } catch {}
}

export function deleteJobRecord(jobId) {
  const job = jobs[jobId];
  if (!job) return false;
  if (job.outputPath && isInside(job.outputPath, OUTPUT_DIR)) {
    try { unlinkSync(job.outputPath); } catch {}
  }
  removeGeneratedDir(job.generatedDir);
  removePublicGeneratedDir(job.publicAssetDir ?? join(PUBLIC_GENERATED_DIR, jobId));
  delete jobs[jobId];
  return true;
}

// ---------------------------------------------------------------------------
// Browser / port helpers
// ---------------------------------------------------------------------------

export function browserOptions() {
  return existsSync(BROWSER_EXECUTABLE) ? { browserExecutable: BROWSER_EXECUTABLE } : {};
}

export function canListen(port) {
  return new Promise((resolvePromise) => {
    const probe = createNetServer();
    probe.once("error", () => resolvePromise(false));
    probe.once("listening", () => { probe.close(() => resolvePromise(true)); });
    probe.listen(port, "127.0.0.1");
  });
}

export async function getStaticPort() {
  for (let port = STATIC_PORT_START; port < STATIC_PORT_START + 100; port += 1) {
    if (await canListen(port)) return port;
  }
  throw new Error(`No available Remotion static port from ${STATIC_PORT_START}`);
}

// ---------------------------------------------------------------------------
// Bundle and render
// ---------------------------------------------------------------------------

export async function bundleAndRender(jobId, entryPath, outputPath) {
  updateJob(jobId, { phase: "bundling", progress: 0 });
  console.log("[bundle] Bundling generated Remotion code...");
  const bundlePath = await bundle({
    entryPoint: entryPath,
    onProgress: (progress) => { process.stdout.write(`\r[bundle] ${progress}%`); },
  });
  console.log(`\n[bundle] Ready: ${bundlePath.slice(0, 100)}`);

  const downloadMap = RenderInternals.makeDownloadMap();
  const staticPort = await getStaticPort();
  const staticServer = await RenderInternals.serveStatic(bundlePath, {
    port: staticPort, downloadMap,
    remotionRoot: new URL(".", import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1"),
    offthreadVideoThreads: 2, logLevel: "warn", indent: false,
    offthreadVideoCacheSizeInBytes: null, binariesDirectory: null, forceIPv4: false,
  });

  try {
    const serveUrl = `http://localhost:${staticServer.port}`;
    console.log(`[serve] Remotion static server: ${serveUrl}`);
    console.log(`[render] Concurrency: ${RENDER_CONCURRENCY}`);
    updateJob(jobId, { phase: "rendering", progress: 0 });

    const composition = await selectComposition({ serveUrl, id: COMPOSITION_ID, ...browserOptions() });
    await renderMedia({
      composition, serveUrl, codec: "h264", imageFormat: "png",
      crf: RENDER_CRF, x264Preset: RENDER_X264_PRESET, pixelFormat: RENDER_PIXEL_FORMAT,
      outputLocation: outputPath, concurrency: RENDER_CONCURRENCY, ...browserOptions(),
      onProgress: ({ progress }) => {
        const percent = Math.round(progress * 100);
        process.stdout.write(`\r[render] ${percent}%`);
        updateJob(jobId, { progress: percent });
      },
    });
    console.log(`\n[render] Done: ${outputPath.split(/[\\/]/).pop()}`);
  } finally {
    await staticServer.close();
  }
}

// ---------------------------------------------------------------------------
// Top-level render pipeline
// ---------------------------------------------------------------------------

export async function renderVideo(jobId, storyboard, voice, outputPath, options = {}) {
  updateJob(jobId, { phase: "tts", progress: 0 });
  console.log(`[tts] Synthesizing ${storyboard.scenes.length} scenes...`);
  const storyboardWithAudio = await injectAudio(storyboard, voice);
  updateJob(jobId, { actualDurationSeconds: Math.round((storyboardWithAudio.total_duration_estimate ?? 0) * 10) / 10 });
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
  await runRenderQa(jobId, outputPath, storyboardWithTraces, {
    expectedDurationSeconds: generated.durationInFrames / generated.fps,
  });
}
