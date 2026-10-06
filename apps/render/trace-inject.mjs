/**
 * trace-inject.mjs — Seedream 候选评分 + injectImageTraces 编排
 * 依赖: config.mjs, utils.mjs, scene-strategy.mjs, trace.mjs, trace-whiteboard.mjs
 */
import { copyFileSync, existsSync, mkdirSync, readFileSync, writeFileSync } from "fs";
import { createHash } from "crypto";
import { join } from "path";
import {
  ENABLE_IMAGE_TRACE,
  IMAGE_TRACE_MAX_SCENES,
  PYTHON_API,
  REQUIRE_SEEDREAM_REFERENCE_IMAGES,
  PUBLIC_GENERATED_DIR,
  SKIP_IMAGE_TRACE,
  __dirname,
} from "./config.mjs";
import { postJson } from "./utils.mjs";
import {
  countPatternMatches,
  countSceneLabels,
  normalizeBase64Image,
  sceneBoardMode,
  sceneHandUsage,
  sceneLocalImageBuffer,
  sceneVisualStyle,
  shouldGenerateReferenceImage,
} from "./scene-strategy.mjs";
import { buildRasterRevealFromBuffer } from "./trace.mjs";
import { traceWhiteboardImageBuffer, traceWhiteboardImageBase64 } from "./trace-whiteboard.mjs";

const IMAGE_CACHE_DIR = join(PUBLIC_GENERATED_DIR, "_cache");
const HANDDRAW_TOPIC_ASSET_DIR = join(__dirname, "public", "handdraw");

function isShortVideoTopic(storyboard) {
  const text = `${storyboard?.topic ?? ""} ${(storyboard?.scenes ?? []).map((scene) => `${scene?.title ?? ""} ${scene?.narration ?? ""}`).join(" ")}`;
  if (/[\u77ed\u89c6\u9891\u77ed\u8996\u983b]/u.test(text) || /short[\s-]?video/i.test(text)) return true;
  return /短视频|short[\s-]?video/i.test(text);
}

// The project already contains approved topic-specific hand-drawn plates. Use
// them as local references so a rerender can reuse the existing visual work and
// still pass through the normal raster trace and hand-following pipeline.
function topicHanddrawImageBuffer(storyboard, scene, sceneIndex) {
  if (!isShortVideoTopic(storyboard)) return null;
  const idMatch = String(scene?.id ?? "").match(/(\d+)$/);
  const sceneNumber = Number(idMatch?.[1] ?? sceneIndex);
  if (!Number.isInteger(sceneNumber) || sceneNumber < 0 || sceneNumber > 5) return null;
  const imagePath = join(HANDDRAW_TOPIC_ASSET_DIR, `scene${sceneNumber}.png`);
  return existsSync(imagePath) ? readFileSync(imagePath) : null;
}

function imageCacheKey(storyboard, scene) {
  const payload = {
    topic: storyboard?.topic ?? "",
    id: scene?.id ?? "",
    title: scene?.title ?? "",
    imageDescription: scene?.image_description ?? scene?.imageDescription ?? "",
    visualStyle: scene?.visual_style ?? scene?.visualStyle ?? "",
    videoStyle: scene?.video_style ?? scene?.videoStyle ?? "",
  };
  return createHash("sha256").update(JSON.stringify(payload)).digest("hex").slice(0, 24);
}

function rewriteCachedPaths(value, fromPrefix, toPrefix) {
  if (Array.isArray(value)) return value.map((item) => rewriteCachedPaths(item, fromPrefix, toPrefix));
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, rewriteCachedPaths(item, fromPrefix, toPrefix)]));
  }
  return typeof value === "string" && value.startsWith(fromPrefix) ? `${toPrefix}${value.slice(fromPrefix.length)}` : value;
}

function loadImageCache(storyboard, scene, jobId) {
  const key = imageCacheKey(storyboard, scene);
  const cacheDir = join(IMAGE_CACHE_DIR, key);
  const manifestPath = join(cacheDir, "manifest.json");
  if (!existsSync(manifestPath)) return null;
  try {
    const manifest = JSON.parse(readFileSync(manifestPath, "utf8"));
    const targetDir = join(PUBLIC_GENERATED_DIR, jobId);
    mkdirSync(targetDir, { recursive: true });
    for (const filename of manifest.files ?? []) {
      const source = join(cacheDir, filename);
      if (!existsSync(source)) return null;
      copyFileSync(source, join(targetDir, filename));
    }
    const fromPrefix = `generated/_cache/${key}/`;
    const toPrefix = `generated/${jobId}/`;
    return rewriteCachedPaths(manifest.result, fromPrefix, toPrefix);
  } catch (err) {
    console.warn(`[image-trace] cache read skipped for ${scene.id}: ${err.message}`);
    return null;
  }
}

function saveImageCache(storyboard, scene, jobId, result) {
  const key = imageCacheKey(storyboard, scene);
  const cacheDir = join(IMAGE_CACHE_DIR, key);
  mkdirSync(cacheDir, { recursive: true });
  const assetPrefix = `generated/${jobId}/`;
  const files = [];
  for (const asset of [result?.assetContract?.masterAsset, result?.assetContract?.inkAsset, result?.assetContract?.colorAsset]) {
    if (!asset || !asset.startsWith(assetPrefix)) continue;
    const filename = asset.slice(assetPrefix.length);
    const source = join(PUBLIC_GENERATED_DIR, jobId, filename);
    if (existsSync(source)) {
      copyFileSync(source, join(cacheDir, filename));
      files.push(filename);
    }
  }
  if (files.length === 0) return;
  const normalized = rewriteCachedPaths(result, assetPrefix, `generated/_cache/${key}/`);
  writeFileSync(join(cacheDir, "manifest.json"), JSON.stringify({ files, result: normalized }), "utf8");
}

function selectSeedreamCandidates(scenes, localImageSceneIds, rasterBySceneId) {
  return scenes
    .filter(
      (scene) =>
        scene.image_description && shouldGenerateReferenceImage(scene) &&
        sceneHandUsage(scene) !== "none" && sceneBoardMode(scene) !== "chalkboard" &&
        sceneVisualStyle(scene) !== "math_chalkboard" &&
        !localImageSceneIds.has(scene.id) && !rasterBySceneId[scene.id] &&
        !scene.rasterReveal && !scene.raster_reveal && !scene.trace_strokes && !scene.traceStrokes,
    )
    .map((scene, index) => {
      const text = `${scene.title ?? ""} ${scene.learning_goal ?? ""} ${scene.image_description ?? ""} ${
        scene.diagram_plan?.kind ?? scene.diagramPlan?.kind ?? ""
      } ${scene.diagram_plan?.layout ?? scene.diagramPlan?.layout ?? ""}`.toLowerCase();
      const visualComplexity = String(scene.visual_complexity ?? scene.visualComplexity ?? "").toLowerCase();
      const strategy = String(scene.render_strategy ?? scene.renderStrategy ?? "").toLowerCase();
      const boardMode = String(scene.board_mode ?? scene.boardMode ?? "").toLowerCase();
      const handUsage = String(scene.hand_usage ?? scene.handUsage ?? "").toLowerCase();
      const videoStyle = String(scene.video_style ?? scene.videoStyle ?? "").trim().toLowerCase();
      const visualStyle = String(scene.visual_style ?? scene.visualStyle ?? "").toLowerCase();
      const visualRelationScore = countPatternMatches(text, [
        /\boverview(?:[_\s-]?map)?\b/i, /\bcomparison|compare|versus|before|after|state|contrast\b/i,
        /\bprocess|flow|mechanism|cause|effect|simulation|journey\b/i,
        /\bstructure|component|part[-\s]?whole|cross[-\s]?section\b/i,
        /\binteraction|relationship|mutual|communication|collaboration|exchange\b/i,
        /\btradeoff|priority|quadrant|2x2|matrix\b/i, /\bgoal|target|path|roadmap|milestone|backcast\b/i,
        /\bcycle|loop|feedback|iteration|renewal\b/i,
        /概览|地图|对比|状态|过程|流程|机制|因果|结构|组成|截面|互动|关系|协作|交换|取舍|优先|象限|目标|路径|路线|循环|闭环|反馈|迭代/i,
      ]);
      const score =
        (strategy === "hybrid" ? 5 : strategy === "direct" ? 4 : strategy === "trace" ? 1 : 0) +
        (handUsage === "annotate" ? 6 : 0) + (boardMode === "reference" ? 6 : 0) +
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
}

export async function injectImageTraces(storyboard, jobId) {
  if (SKIP_IMAGE_TRACE) {
    console.log("[image-trace] SKIP_IMAGE_TRACE enabled, skipping trace generation");
    return storyboard;
  }
  if (!ENABLE_IMAGE_TRACE || IMAGE_TRACE_MAX_SCENES <= 0) return storyboard;

  const rasterBySceneId = {};
  const tracesBySceneId = {};
  const localImageSceneIds = new Set();
  for (const [sceneIndex, scene] of storyboard.scenes.entries()) {
    if (scene.rasterReveal || scene.raster_reveal) continue;
    const cached = loadImageCache(storyboard, scene, jobId);
    if (cached?.rasterReveal) {
      rasterBySceneId[scene.id] = cached;
      console.log(`[image-trace] ${scene.id}: reused cached raster assets`);
      continue;
    }
    // Only storyboard-provided local images are eligible. Generic topic plates
    // are not substitutes for images derived from the scene script.
    const imageBuffer = sceneLocalImageBuffer(scene);
    if (!imageBuffer) continue;
    localImageSceneIds.add(scene.id);
    try {
      const raster = await buildRasterRevealFromBuffer(imageBuffer, jobId, scene, { forceTrace: true });
      rasterBySceneId[scene.id] = raster;
      saveImageCache(storyboard, scene, jobId, raster);
      const sourceLabel = "storyboard local image";
      console.log(`[image-trace] ${scene.id}: ${raster.rasterReveal.renderMode} raster from ${sourceLabel}, ${raster.rasterReveal.strokes.length} reveal path(s)`);
    } catch (err) {
      console.warn(`[image-trace] ${scene.id}: local raster reveal skipped: ${err.message}`);
      const traceStrokes = await traceWhiteboardImageBuffer(imageBuffer);
      if (traceStrokes.length > 0) {
        tracesBySceneId[scene.id] = traceStrokes;
        console.log(`[image-trace] ${scene.id}: ${traceStrokes.length} local fallback drawable path(s)`);
      }
    }
  }

  const candidates = selectSeedreamCandidates(storyboard.scenes, localImageSceneIds, rasterBySceneId);

  if (candidates.length === 0 && Object.keys(rasterBySceneId).length === 0 && Object.keys(tracesBySceneId).length === 0) {
    return storyboard;
  }

  const mergeResults = (rasterResults, traceResults) => ({
    ...storyboard,
    scenes: storyboard.scenes.map((scene) => ({
      ...scene,
      ...(rasterResults[scene.id] ?? {}),
      assetContract:
        rasterResults[scene.id]?.assetContract ??
        scene.assetContract ?? scene.asset_contract ?? null,
      trace_strokes:
        rasterResults[scene.id]?.trace_strokes ??
        traceResults[scene.id] ??
        scene.trace_strokes ?? scene.traceStrokes ?? null,
    })),
  });

  try {
    let response = { images: {} };
    if (candidates.length > 0) {
      console.log(`[image-trace] Generating ${candidates.length} Seedream reference image(s)...`);
      response = await postJson(`${PYTHON_API}/imagegen/scenes`, {
        scenes: candidates.map((scene) => ({
          scene_id: scene.id, topic: storyboard.topic ?? "",
          title: scene.title ?? "", image_description: scene.image_description,
          board_mode: scene.board_mode ?? scene.boardMode ?? "whiteboard",
          hand_usage: scene.hand_usage ?? scene.handUsage ?? "trace",
          video_style: String(scene.video_style ?? scene.videoStyle ?? "").trim().toLowerCase(),
          visual_style: scene.visual_style ?? scene.visualStyle ?? "teacher_whiteboard",
          pen_style: scene.pen_style ?? scene.penStyle ?? storyboard.pen_style ?? storyboard.penStyle ?? "marker",
          quality: "final",
        })),
      }, 180000);
      const generatedCount = candidates.filter((scene) => response.images?.[scene.id]).length;
      if (REQUIRE_SEEDREAM_REFERENCE_IMAGES && generatedCount === 0) {
        throw new Error(`Seedream reference image generation returned 0/${candidates.length} images. Check ARK_API_KEY, ARK_BASE_URL, SEEDREAM_MODEL, and /imagegen/scenes logs.`);
      }
      if (generatedCount < candidates.length) {
        throw new Error(`Image generation returned ${generatedCount}/${candidates.length} storyboard reference images; refusing to render scenes without matching artwork.`);
      }
    }

    for (const scene of candidates) {
      const imageBase64 = response.images?.[scene.id];
      if (!imageBase64) continue;
      try {
        const raster = await buildRasterRevealFromBuffer(Buffer.from(normalizeBase64Image(imageBase64), "base64"), jobId, scene, { forceTrace: true });
        rasterBySceneId[scene.id] = raster;
        saveImageCache(storyboard, scene, jobId, raster);
        console.log(`[image-trace] ${scene.id}: ${raster.rasterReveal.renderMode} raster from Seedream, ${raster.rasterReveal.strokes.length} reveal path(s)`);
      } catch (err) {
        console.warn(`[image-trace] ${scene.id}: raster reveal skipped, falling back to SVG trace: ${err.message}`);
        const traceStrokes = await traceWhiteboardImageBase64(imageBase64);
        if (traceStrokes.length > 0) {
          tracesBySceneId[scene.id] = traceStrokes;
          console.log(`[image-trace] ${scene.id}: ${traceStrokes.length} drawable path(s)`);
        }
      }
    }

    if (Object.keys(tracesBySceneId).length === 0 && Object.keys(rasterBySceneId).length === 0) return storyboard;
    return mergeResults(rasterBySceneId, tracesBySceneId);
  } catch (err) {
    console.warn(`[image-trace] Seedream trace skipped: ${err.message}`);
    if (Object.keys(rasterBySceneId).length === 0 && Object.keys(tracesBySceneId).length === 0) return storyboard;
    return mergeResults(rasterBySceneId, tracesBySceneId);
  }
}
