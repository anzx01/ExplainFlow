/**
 * trace-inject.mjs — Seedream 候选评分 + injectImageTraces 编排
 * 依赖: config.mjs, utils.mjs, scene-strategy.mjs, trace.mjs, trace-whiteboard.mjs
 */
import { copyFileSync, existsSync, mkdirSync, readFileSync, writeFileSync } from "fs";
import { fileURLToPath } from "url";
import sharp from "sharp";
import { createHash } from "crypto";
import { join } from "path";
import {
  ENABLE_IMAGE_TRACE,
  IMAGEGEN_REQUEST_TIMEOUT_MS,
  IMAGE_TRACE_MAX_SCENES,
  PYTHON_API,
  REQUIRE_SEEDREAM_REFERENCE_IMAGES,
  PUBLIC_GENERATED_DIR,
  SKIP_IMAGE_TRACE,
  __dirname,
} from "./config.mjs";
import { getJson, postJson } from "./utils.mjs";
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
  return /短视频|short[\s-]?video/i.test(text);
}

export function topicHanddrawImageBuffer(storyboard, scene, sceneIndex) {
  // Keep the checked-in plates available for diagnostics, but let the image
  // provider create the final subject artwork. The plates are intentionally
  // icon-like and are too sparse for the finished video.
  if (!isShortVideoTopic(storyboard) || process.env.EXPLAINFLOW_USE_TOPIC_PLATES !== "1") return null;
  const idMatch = String(scene?.id ?? "").match(/(\d+)$/);
  const sceneNumber = Number(idMatch?.[1] ?? sceneIndex);
  if (!Number.isInteger(sceneNumber) || sceneNumber < 0 || sceneNumber > 5) return null;
  const imagePath = join(HANDDRAW_TOPIC_ASSET_DIR, `semantic-scene${sceneNumber}.png`);
  return existsSync(imagePath) ? readFileSync(imagePath) : null;
}

export function imagegenRequestTimeoutMs(providerStatus, sceneCount, overrideMs = 0) {
  if (Number(overrideMs) > 0) return Number(overrideMs);
  const provider = String(providerStatus?.provider ?? "local").trim().toLowerCase();
  const local = provider === "local" || provider === "local_then_ark";
  const localSeconds = local
    ? Number(providerStatus?.timeoutSeconds ?? 600) * Math.max(1, Number(providerStatus?.maxAttempts ?? 3))
    : 0;
  const fallbackSeconds = provider === "local_then_ark" ? 120 : 0;
  const providerSeconds = local ? localSeconds + fallbackSeconds : 180;
  return Math.max(180000, Math.max(1, sceneCount) * providerSeconds * 1000 + 120000);
}

export function imageCacheKey(storyboard, scene) {
  const payload = {
    renderAssetMode: "scene-authored-artwork-v24-lesson-fidelity",
    imageMode: storyboard?.image_generation_mode ?? storyboard?.imageGenerationMode ?? "default",
    authoredPrompt: imageGenerationDescription(storyboard, scene),
    sourceImage: createHash("sha256").update(sceneLocalImageBuffer(scene) ?? Buffer.alloc(0)).digest("hex"),
    topicPlates: process.env.EXPLAINFLOW_USE_TOPIC_PLATES === "1",
    topic: storyboard?.topic ?? "",
    id: scene?.id ?? "",
    title: scene?.title ?? "",
    imageDescription: scene?.image_description ?? scene?.imageDescription ?? "",
    imageShots: scene?.image_shots ?? scene?.imageShots ?? null,
    imageIcons: scene?.image_icons ?? scene?.imageIcons ?? null,
    imageStyle: scene?.image_style ?? scene?.imageStyle ?? storyboard?.image_style ?? storyboard?.imageStyle ?? null,
    visualStyle: scene?.visual_style ?? scene?.visualStyle ?? "",
    videoStyle: scene?.video_style ?? scene?.videoStyle ?? "",
    lineArtColorMode: storyboard?.line_art_color_mode ?? storyboard?.lineArtColorMode ?? "color",
  };
  return createHash("sha256").update(JSON.stringify(payload)).digest("hex").slice(0, 24);
}

function shouldTraceReferenceScene(scene) {
  const handUsage = sceneHandUsage(scene);
  const boardMode = sceneBoardMode(scene);
  const strategy = String(scene.render_strategy ?? scene.renderStrategy ?? "").trim().toLowerCase();
  const visualStyle = sceneVisualStyle(scene);
  if (handUsage === "none") return false;
  if (boardMode === "chalkboard" || visualStyle === "math_chalkboard") return false;
  return boardMode === "whiteboard" || !/(direct|finished|static|present|photo|show|annotate)/i.test(strategy);
}

export function imageGenerationDescription(storyboard, scene) {
  const base = descriptionForScene(storyboard, scene);
  const intents = (scene.audioSegments ?? scene.audio_segments ?? [])
    .map((segment) => segment.drawIntent ?? segment.draw_intent)
    .filter(Boolean)
    .join("; ");
  const beats = (scene.visual_beats ?? scene.visualBeats ?? [])
    .map((beat) => beat.draw_intent ?? beat.drawIntent ?? beat.narration)
    .filter(Boolean)
    .join("; ");
  const context = [
    `topic: ${storyboard?.topic ?? ""}`,
    `scene title: ${scene?.title ?? ""}`,
    `learning goal: ${scene?.learning_goal ?? scene?.learningGoal ?? ""}`,
    scene.narration && `current explanation (meaning only, never draw as text): ${scene.narration}`,
    intents && `visual action: ${intents}`,
    beats && `visual beats: ${beats}`,
  ].filter(Boolean).join(". ");
  const monochrome = String(storyboard?.line_art_color_mode ?? storyboard?.lineArtColorMode ?? "color").toLowerCase() === "monochrome";
  return [
    `Required scene artwork: ${base}`,
    context,
    "The current explanation and learning goal determine what this image must teach. Preserve the action, physical contact, part counts, and before/after or cause/effect relationship; if an older visual draft conflicts with the explanation, follow the explanation. Keep the actual subject visible when using an analogy",
    "The image must visibly show the named subject, its action, and the cause/effect or relationship in this scene; build a complete classroom whiteboard composition preserving the specified objects, pose, lighting, and action, with clear foreground and background relationships and one readable central action",
    `Use detailed hand-drawn marker line art like a real teaching sketch: the specified subjects should be structurally recognizable and connected; ${monochrome ? "use only black, charcoal gray and white, with no colored accents" : "use solid subject-specific color fills and purposeful color accents"}; avoid isolated icon tiles and avoid an empty canvas`,
    "Do not use anime, manga, glossy digital illustration, photorealism, generic cute characters, a generic face substituted for the requested action, abstract icon-only diagrams, or unrelated stock art; no readable text, labels, logos, watermark, or baked callout boxes",
  ].join(". ");
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

export function selectSeedreamCandidates(scenes, localImageSceneIds, rasterBySceneId) {
  const scored = scenes
    .filter(
      (scene) =>
        (scene.image_description ?? scene.imageDescription) && shouldGenerateReferenceImage(scene) &&
        sceneHandUsage(scene) !== "none" && sceneBoardMode(scene) !== "chalkboard" &&
        sceneVisualStyle(scene) !== "math_chalkboard" &&
        !localImageSceneIds.has(scene.id) && !rasterBySceneId[scene.id] &&
        !scene.rasterReveal && !scene.raster_reveal,
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
  // Explicit reference/hybrid scenes are contractual: the default cap only
  // limits optional artwork so a low-latency setting cannot omit required art.
  const required = scored.filter((item) => isRequiredReferenceScene(item.scene));
  const optional = scored.filter((item) => !isRequiredReferenceScene(item.scene));
  return [
    ...required,
    ...optional.slice(0, Math.max(0, IMAGE_TRACE_MAX_SCENES - required.length)),
  ].map((item) => item.scene);
}

export function isRequiredReferenceScene(scene) {
  const mode = sceneBoardMode(scene);
  const strategy = String(scene.render_strategy ?? scene.renderStrategy ?? "").toLowerCase();
  const described = Boolean(scene.image_description ?? scene.imageDescription);
  return mode !== "chalkboard" && sceneVisualStyle(scene) !== "math_chalkboard" &&
    (described || mode === "reference" || strategy === "direct") &&
    sceneHandUsage(scene) !== "none" && !sceneLocalImageBuffer(scene);
}

export function descriptionForScene(storyboard, scene) {
  const existing = String(scene.image_description ?? scene.imageDescription ?? "").trim();
  if (existing) return existing;
  const visualIntent = (scene.audioSegments ?? scene.audio_segments ?? [])
    .map((segment) => segment.drawIntent ?? segment.draw_intent ?? segment.subtitleText ?? segment.subtitle_text)
    .filter(Boolean)
    .join("; ");
  const narration = String(scene.narration ?? scene.subtitleText ?? scene.subtitle_text ?? "").trim();
  const labels = [
    ...(scene.diagram_plan?.required_labels ?? []),
    ...(scene.diagramPlan?.requiredLabels ?? []),
    ...(scene.annotation_plan ?? []).map((item) => item?.label),
    ...(scene.annotationPlan ?? []).map((item) => item?.label),
  ].filter(Boolean).join(", ");
  const details = [visualIntent, narration, labels && `include these concepts: ${labels}`].filter(Boolean).join(". ");
  return `Hand-drawn educational illustration for ${storyboard.topic ?? "the topic"}. Scene: ${scene.title ?? "key idea"}. ${details}. One clear central visual metaphor based on this scene, colored marker line art on a clean whiteboard, no readable text, no labels, no watermark.`;
}

const ICON_LIBRARY_DIR = fileURLToPath(new URL("./node_modules/lucide-static/icons/", import.meta.url));
const OPENMOJI_DIR = fileURLToPath(new URL("./node_modules/openmoji/", import.meta.url));

function iconDiagramSvgBuffer(scene) {
  const icons = (scene.image_icons ?? scene.imageIcons ?? [])
    .map((item) => String(item ?? "").trim())
    .filter(Boolean);
  if (icons.length < 2) return null;
  const size = 460;
  const gap = 150;
  const margin = 90;
  const lucidePalette = ["#2E86C1", "#2E9E4F", "#E67E22", "#2f2f2f"];
  const groups = [];
  let x = margin;
  icons.forEach((name, i) => {
    const isEmojiCode = /^[0-9A-Fa-f]{4,6}$/.test(name);
    let inner = null;
    let viewSize = 24;
    if (isEmojiCode) {
      const file = join(OPENMOJI_DIR, "color", "svg", `${name.toUpperCase()}.svg`);
      if (!existsSync(file)) {
        console.warn(`[image-trace] openmoji "${name}" missing, skipped`);
        return;
      }
      inner = readFileSync(file, "utf8")
        .replace(/<svg[^>]*>/, "")
        .replace(/<\/svg>\s*$/, "");
      viewSize = 72;
    } else {
      const file = join(ICON_LIBRARY_DIR, `${name}.svg`);
      if (!existsSync(file)) {
        console.warn(`[image-trace] icon "${name}" missing from library, skipped`);
        return;
      }
      inner = readFileSync(file, "utf8")
        .replace(/<svg[^>]*>/, "")
        .replace(/<\/svg>\s*$/, "")
        .replace(/stroke-width="[^"]*"/, 'stroke-width="0.55"')
        .replaceAll('stroke="currentColor"', `stroke="${lucidePalette[i % lucidePalette.length]}"`);
    }
    const scale = size / viewSize;
    const rot = [-2.4, 1.8, -1.4, 2.2][i % 4];
    // 风格标志性的阳光黄高亮底斑,给图标加温度并融入板书风
    const blob = `<ellipse cx="${size / 2}" cy="${size * 0.62}" rx="${size * 0.5}" ry="${size * 0.26}" fill="#F7D96B" opacity="0.7" transform="rotate(-4 ${size / 2} ${size * 0.62})"/>`;
    groups.push(
      `<g transform="translate(${x} ${margin + 50})">` +
      `<g transform="rotate(${rot} ${size / 2} ${size / 2})">` +
      blob +
      `<g transform="scale(${scale})">${inner}</g>` +
      `</g></g>`
    );
    x += size + gap;
  });
  if (groups.length < 2) return null;
  const w = x - gap + margin;
  const h = size + margin * 2 + 50;
  const doc = `<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}"><rect width="${w}" height="${h}" fill="#ffffff"/>${groups.join("")}</svg>`;
  return Buffer.from(doc, "utf8");
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
    const iconBuffer = iconDiagramSvgBuffer(scene);
    if (iconBuffer) {
      try {
        const png = await sharp(iconBuffer).png().toBuffer();
        const raster = await buildRasterRevealFromBuffer(png, jobId, scene, { forceTrace: true });
        rasterBySceneId[scene.id] = raster;
        saveImageCache(storyboard, scene, jobId, raster);
        console.log(`[image-trace] ${scene.id}: ${raster.rasterReveal.renderMode} raster from icon library (${(scene.image_icons ?? scene.imageIcons ?? []).length} icons), ${raster.rasterReveal.strokes.length} reveal path(s)`);
        continue;
      } catch (err) {
        console.warn(`[image-trace] ${scene.id}: icon diagram raster skipped: ${err.message}`);
      }
    }
    // Only storyboard-provided local images are eligible. A generic topic
    // plate is not a substitute for artwork derived from the scene script.
    const imageBuffer = sceneLocalImageBuffer(scene) ?? topicHanddrawImageBuffer(storyboard, scene, sceneIndex);
    if (!imageBuffer) continue;
    localImageSceneIds.add(scene.id);
    try {
      const raster = await buildRasterRevealFromBuffer(imageBuffer, jobId, scene, { forceTrace: true });
      rasterBySceneId[scene.id] = raster;
      saveImageCache(storyboard, scene, jobId, raster);
      const sourceLabel = sceneLocalImageBuffer(scene) ? "storyboard local image" : "checked-in topic plate";
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

  const imageStoryboard = {
    ...storyboard,
    scenes: storyboard.scenes.map((scene) => ({
      ...scene,
      image_description: scene.image_description ?? scene.imageDescription ?? "",
      // Keep the original strategy absent when the storyboard did not set one.
      // A synthetic default here would make every ordinary whiteboard scene
      // look like a required direct-reference scene and defeat the scene cap.
      ...(scene.render_strategy || scene.renderStrategy
        ? { render_strategy: scene.render_strategy ?? scene.renderStrategy }
        : {}),
    })),
  };
  const candidates = selectSeedreamCandidates(imageStoryboard.scenes, localImageSceneIds, rasterBySceneId);

  const requiredReferenceScenes = imageStoryboard.scenes.filter((scene) => {
    return isRequiredReferenceScene(scene) &&
      !localImageSceneIds.has(scene.id) && !rasterBySceneId[scene.id] &&
      !scene.rasterReveal && !scene.raster_reveal;
  });
  if (candidates.length < requiredReferenceScenes.length) {
    const candidateIds = new Set(candidates.map((scene) => scene.id));
    const omitted = requiredReferenceScenes.filter((scene) => !candidateIds.has(scene.id));
    if (omitted.length > 0) {
      throw new Error(`Required reference artwork exceeds image generation capacity (${IMAGE_TRACE_MAX_SCENES}): ${omitted.map((scene) => scene.id).join(", ")}`);
    }
  }
  if (requiredReferenceScenes.length > 0 && candidates.length === 0) {
    throw new Error(`Required reference artwork has no generation candidates: ${requiredReferenceScenes.map((scene) => scene.id).join(", ")}`);
  }

  if (candidates.length === 0 && Object.keys(rasterBySceneId).length === 0 && Object.keys(tracesBySceneId).length === 0) {
    return storyboard;
  }

  const mergeResults = (rasterResults, traceResults) => ({
    ...storyboard,
    scenes: storyboard.scenes.map((scene) => ({
      ...scene,
      ...(rasterResults[scene.id] ?? {}),
      // Keep reference artwork in the raster contract. `imageUrl` is reserved
      // for an intentional storyboard thumbnail; promoting every generated
      // plate here turns a whiteboard scene into a floating image card and
      // leaves the actual board mostly empty.
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
      let providerStatus = {};
      try {
        providerStatus = await getJson(`${PYTHON_API}/imagegen/status`, 5000);
      } catch (err) {
        console.warn(`[image-trace] Could not read image provider status; using conservative local-generation timeout: ${err.message}`);
      }
      const timeoutMs = imagegenRequestTimeoutMs(providerStatus, candidates.length, IMAGEGEN_REQUEST_TIMEOUT_MS);
      console.log(`[image-trace] Generating ${candidates.length} reference image(s) with ${providerStatus.provider ?? "configured"} provider (timeout ${Math.ceil(timeoutMs / 60000)} min)...`);
      const imageMode = String(storyboard.image_generation_mode ?? storyboard.imageGenerationMode ?? "default");
      console.log(`[image-trace] image_mode resolved: "${imageMode}" (storyboard.image_generation_mode=${JSON.stringify(storyboard.image_generation_mode)}, storyboard.imageGenerationMode=${JSON.stringify(storyboard.imageGenerationMode)})`);
      const imageRequest = {
        scenes: candidates.map((scene) => ({
          scene_id: scene.id, topic: storyboard.topic ?? "",
          title: scene.title ?? "", image_description: imageGenerationDescription(storyboard, scene),
          board_mode: scene.board_mode ?? scene.boardMode ?? "whiteboard",
          hand_usage: scene.hand_usage ?? scene.handUsage ?? "trace",
          video_style: String(scene.video_style ?? scene.videoStyle ?? "").trim().toLowerCase(),
          visual_style: scene.visual_style ?? scene.visualStyle ?? "teacher_whiteboard",
          pen_style: scene.pen_style ?? scene.penStyle ?? storyboard.pen_style ?? storyboard.penStyle ?? "marker",
          quality: "final",
          image_mode: imageMode,
          line_art_color_mode: storyboard.line_art_color_mode ?? storyboard.lineArtColorMode ?? "color",
          image_shots: scene.image_shots ?? scene.imageShots ?? null,
          image_style: scene.image_style ?? scene.imageStyle ?? storyboard.image_style ?? storyboard.imageStyle ?? null,
        })),
      };
      const auditDir = join(PUBLIC_GENERATED_DIR, jobId);
      mkdirSync(auditDir, { recursive: true });
      writeFileSync(join(auditDir, "image-generation-request.json"), JSON.stringify(imageRequest, null, 2), "utf8");
      response = await postJson(`${PYTHON_API}/imagegen/scenes`, imageRequest, timeoutMs);
      writeFileSync(join(auditDir, "image-generation-diagnostics.json"), JSON.stringify(response.diagnostics ?? {}, null, 2), "utf8");
      const generatedCount = candidates.filter((scene) => response.images?.[scene.id]).length;
      if (REQUIRE_SEEDREAM_REFERENCE_IMAGES && generatedCount === 0) {
        const diagnostics = Object.entries(response.diagnostics ?? {})
          .map(([id, detail]) => `${id}: ${JSON.stringify(detail)}`)
          .join("; ");
        throw new Error(`Image generation returned 0/${candidates.length} images from the configured provider.${diagnostics ? ` Diagnostics: ${diagnostics}` : " Check /imagegen/status and /imagegen/scenes logs."}`);
      }
    }

    for (const scene of candidates) {
      const imageBase64 = response.images?.[scene.id];
      if (!imageBase64) continue;
      try {
        const traceScene = shouldTraceReferenceScene(scene);
        const raster = await buildRasterRevealFromBuffer(Buffer.from(normalizeBase64Image(imageBase64), "base64"), jobId, scene, {
          forceTrace: traceScene,
          forceDirect: !traceScene,
        });
        rasterBySceneId[scene.id] = raster;
        saveImageCache(storyboard, scene, jobId, raster);
        console.log(`[image-trace] ${scene.id}: ${raster.rasterReveal.renderMode} raster from configured image provider, ${raster.rasterReveal.strokes.length} reveal path(s)`);
      } catch (err) {
        console.warn(`[image-trace] ${scene.id}: raster reveal skipped, falling back to SVG trace: ${err.message}`);
        const traceStrokes = await traceWhiteboardImageBase64(imageBase64);
        if (traceStrokes.length > 0) {
          tracesBySceneId[scene.id] = traceStrokes;
          console.log(`[image-trace] ${scene.id}: ${traceStrokes.length} drawable path(s)`);
        }
      }
    }

    const missingCandidates = candidates.filter((scene) => !rasterBySceneId[scene.id] && !tracesBySceneId[scene.id]);
    if (missingCandidates.length > 0) {
      const details = missingCandidates.map(scene => {
        const errors = response.diagnostics?.[scene.id]?.attempts?.flatMap(attempt => attempt.errors ?? []) ?? [];
        return `${scene.id}: ${[...new Set(errors)].join(", ") || "no usable artwork"}`;
      }).join("; ");
      throw new Error(`Required scene artwork missing after image generation (${candidates.length-missingCandidates.length}/${candidates.length}); successful artwork cached for retry. ${details}`);
    }
    if (Object.keys(tracesBySceneId).length === 0 && Object.keys(rasterBySceneId).length === 0) return storyboard;
    return mergeResults(rasterBySceneId, tracesBySceneId);
  } catch (err) {
    console.error(`[image-trace] required artwork generation failed: ${err.message}`);
    throw err;
  }
}
