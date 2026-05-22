/**
 * render-qa.mjs — 渲染后 QA 检查（视频文件、音频流、时长、帧亮度、Storyboard 内容）
 * 依赖: config.mjs, jobs.mjs, utils.mjs, tts.mjs
 */
import { execFile } from "child_process";
import { existsSync, statSync, unlinkSync } from "fs";
import { join } from "path";
import { promisify } from "util";
import sharp from "sharp";
import {
  ACTIVE_VIDEO_STYLE,
  FFMPEG_BINARY,
  MIN_RENDER_FRAME_STDDEV,
  MIN_RENDER_OUTPUT_BYTES,
  OUTPUT_DIR,
} from "./config.mjs";
import { updateJob } from "./jobs.mjs";
import { cleanUserText, sceneLocalImageBuffer, sceneVideoStyle, shouldGenerateReferenceImage } from "./utils.mjs";
import { probeMediaInfo } from "./tts.mjs";

const execFileAsync = promisify(execFile);

// ---------------------------------------------------------------------------
// Internal QA helpers
// ---------------------------------------------------------------------------

function qaCheck(id, ok, severity, message, details = null, suggestion = null) {
  return {
    id, ok: Boolean(ok), severity, message,
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
  checks.push(qaCheck(
    "natural_chinese", !badTerm, badTerm ? "error" : "info",
    badTerm ? `Storyboard contains hard translation term: ${badTerm}` : "No known hard-translation blacklist terms found",
    badTerm ? { term: badTerm } : null,
    badTerm ? "Regenerate or edit narration/labels with natural Chinese phrasing before rendering." : null,
  ));

  const missingTextFree = scenes
    .filter((scene) => {
      const desc = String(scene?.image_description ?? scene?.imageDescription ?? "").toLowerCase();
      if (!desc) return false;
      return !desc.includes("text-free") && !desc.includes("no readable");
    })
    .map((scene) => scene?.id ?? scene?.title ?? "scene");
  checks.push(qaCheck(
    "text_free_image_prompts", missingTextFree.length === 0, missingTextFree.length ? "warning" : "info",
    missingTextFree.length ? `${missingTextFree.length} scene image prompt(s) do not explicitly request text-free artwork` : "Scene image prompts request text-free artwork",
    missingTextFree.length ? { scenes: missingTextFree.slice(0, 8) } : null,
    missingTextFree.length ? "Add text-free/no-readable-text wording so labels stay renderer-controlled." : null,
  ));

  const missingReferences = scenes
    .filter((scene) =>
      shouldGenerateReferenceImage(scene) &&
      !scene?.referenceImageAsset && !scene?.reference_image_asset &&
      !scene?.rasterReveal && !scene?.raster_reveal &&
      !sceneLocalImageBuffer(scene),
    )
    .map((scene) => scene?.id ?? scene?.title ?? "scene");
  checks.push(qaCheck(
    "reference_images", missingReferences.length === 0, missingReferences.length ? "warning" : "info",
    missingReferences.length ? `${missingReferences.length} direct/hybrid scene(s) have no reference image asset` : "Direct/hybrid scenes have reference image assets or local images",
    missingReferences.length ? { scenes: missingReferences.slice(0, 8) } : null,
    missingReferences.length ? "Regenerate scene images or check Seedream credentials and /imagegen/scenes logs." : null,
  ));

  const whiteboardScenes = scenes.filter((scene) => sceneVideoStyle(scene, storyboard) === ACTIVE_VIDEO_STYLE);
  const missingVisualAnchors = whiteboardScenes
    .filter((scene) => !cleanUserText(scene?.visual_anchor ?? scene?.visualAnchor, ""))
    .map((scene) => scene?.id ?? scene?.title ?? "scene");
  checks.push(qaCheck(
    "visual_teaching_anchor", missingVisualAnchors.length === 0, missingVisualAnchors.length ? "warning" : "info",
    missingVisualAnchors.length ? `${missingVisualAnchors.length} scene(s) are missing visual_anchor` : "Whiteboard scenes include visual anchors",
    missingVisualAnchors.length ? { scenes: missingVisualAnchors.slice(0, 8) } : null,
    missingVisualAnchors.length ? "Regenerate/repair storyboard so each scene has one concrete visual anchor." : null,
  ));

  const weakAnnotationPlans = whiteboardScenes
    .filter((scene) => {
      const plan = scene?.annotation_plan ?? scene?.annotationPlan ?? [];
      if (!Array.isArray(plan) || plan.length < 3) return true;
      const types = new Set(plan.map((item) => item?.type).filter(Boolean));
      return types.size < 3 || plan.some((item) => !item?.label || !item?.target);
    })
    .map((scene) => scene?.id ?? scene?.title ?? "scene");
  checks.push(qaCheck(
    "annotation_plan", weakAnnotationPlans.length === 0, weakAnnotationPlans.length ? "warning" : "info",
    weakAnnotationPlans.length ? `${weakAnnotationPlans.length} scene(s) have weak annotation_plan` : "Whiteboard scenes include varied semantic annotation plans",
    weakAnnotationPlans.length ? { scenes: weakAnnotationPlans.slice(0, 8) } : null,
    weakAnnotationPlans.length ? "Add at least 3 labeled renderer annotations with different types per scene." : null,
  ));

  const topicBlob = String(storyboard?.topic ?? "").toLowerCase();
  const isMapo = /mapo|麻婆|豆腐|tofu/.test(topicBlob);
  if (isMapo) {
    const promptBlob = scenes
      .map((scene) => `${scene?.title ?? ""} ${scene?.image_description ?? scene?.imageDescription ?? ""}`)
      .join(" ").toLowerCase();
    const cookingNeedles = ["wok", "red", "tofu", "minced", "scallion"];
    const missing = cookingNeedles.filter((needle) => !promptBlob.includes(needle));
    checks.push(qaCheck(
      "mapo_visual_terms", missing.length === 0, missing.length ? "warning" : "info",
      missing.length ? `Mapo tofu storyboard is missing cooking visual terms: ${missing.join(", ")}` : "Mapo tofu storyboard contains key cooking visual terms",
      missing.length ? { missing } : null,
      missing.length ? "Regenerate/repair images with red chili oil, tofu cubes, minced meat, scallions, steam, and a wide wok." : null,
    ));
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
  let sum = 0, sumSquares = 0, opaque = 0;
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
    width: info.width, height: info.height,
    meanBrightness: Math.round(mean * 10) / 10,
    brightnessStdDev: Math.round(Math.sqrt(variance) * 10) / 10,
    opaqueRatio: Math.round((opaque / pixels) * 1000) / 1000,
  };
}

// ---------------------------------------------------------------------------
// Public export
// ---------------------------------------------------------------------------

export async function runRenderQa(jobId, outputPath, storyboard, options = {}) {
  updateJob(jobId, { phase: "qa", progress: 100 });
  const checks = [];
  const suggestions = [];
  const addCheck = (check) => {
    checks.push(check);
    if (!check.ok && check.suggestion) suggestions.push(check.suggestion);
  };

  const exists = existsSync(outputPath);
  const fileSize = exists ? statSync(outputPath).size : 0;
  addCheck(qaCheck(
    "output_file", exists && fileSize >= MIN_RENDER_OUTPUT_BYTES, "error",
    exists ? `Output file size is ${fileSize} bytes` : "Output video file is missing",
    { fileSizeBytes: fileSize, minBytes: MIN_RENDER_OUTPUT_BYTES },
    "Render again and inspect Remotion/ffmpeg logs; the output file was missing or too small.",
  ));
  if (!exists) {
    const result = { ok: false, checkedAt: new Date().toISOString(), checks, suggestions: [...new Set(suggestions)] };
    updateJob(jobId, { qa: result });
    throw new Error("Render QA failed: Output video file is missing");
  }

  let mediaInfo = null;
  try {
    mediaInfo = await probeMediaInfo(outputPath);
    addCheck(qaCheck(
      "video_stream", mediaInfo.hasVideo && mediaInfo.durationSeconds > 0, "error",
      `Video duration is ${Math.round(mediaInfo.durationSeconds * 10) / 10}s`,
      { durationSeconds: mediaInfo.durationSeconds, hasVideo: mediaInfo.hasVideo },
      "Regenerate Remotion output; ffprobe could not find a playable video stream.",
    ));
    addCheck(qaCheck(
      "audio_stream", mediaInfo.hasAudio, "error",
      mediaInfo.hasAudio ? "Audio stream exists" : "Rendered MP4 has no audio stream",
      null, "Retry TTS and render; audio is required and silent videos are blocked.",
    ));

    const explicitExpectedDuration = Number(options?.expectedDurationSeconds ?? 0);
    const expectedDuration =
      Number.isFinite(explicitExpectedDuration) && explicitExpectedDuration > 0
        ? explicitExpectedDuration
        : storyboardExpectedDuration(storyboard);
    if (expectedDuration > 0 && mediaInfo.durationSeconds > 0) {
      const delta = Math.abs(mediaInfo.durationSeconds - expectedDuration);
      const tolerance = Math.max(4, expectedDuration * 0.25);
      addCheck(qaCheck(
        "duration_match", delta <= tolerance, delta <= tolerance ? "info" : "warning",
        `Rendered duration ${Math.round(mediaInfo.durationSeconds)}s vs expected ${Math.round(expectedDuration)}s`,
        {
          renderedSeconds: mediaInfo.durationSeconds,
          expectedSeconds: expectedDuration,
          storyboardSeconds: expectedDuration,
          deltaSeconds: delta,
        },
        delta > tolerance ? "Review audio segment timings and scene duration estimates before publishing." : null,
      ));
    }
  } catch (err) {
    addCheck(qaCheck("ffprobe", false, "error", `ffprobe failed: ${err.message}`, null, "Check ffprobe installation and regenerate the MP4."));
  }

  if (mediaInfo?.durationSeconds) {
    let framePath = null;
    try {
      framePath = await extractQaFrame(outputPath, mediaInfo.durationSeconds, jobId);
      const frame = await analyzeFrameNonBlank(framePath);
      const isNonBlank = frame.opaqueRatio > 0.9 && frame.brightnessStdDev >= MIN_RENDER_FRAME_STDDEV;
      addCheck(qaCheck(
        "nonblank_frame", isNonBlank, "error",
        isNonBlank ? `Frame has brightness stddev ${frame.brightnessStdDev}` : `Frame looks blank or flat; brightness stddev ${frame.brightnessStdDev}`,
        { ...frame, minStdDev: MIN_RENDER_FRAME_STDDEV },
        "Regenerate scene images/code; verify the composition renders visible board content and reference assets.",
      ));
    } catch (err) {
      addCheck(qaCheck("frame_extract", false, "error", `Could not extract QA frame: ${err.message}`, null, "Check ffmpeg installation and render again."));
    } finally {
      if (framePath) { try { unlinkSync(framePath); } catch {} }
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
