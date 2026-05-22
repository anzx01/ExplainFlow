/**
 * trace.mjs — raster reveal 图像追踪（PNG 骨架描绘）
 * 依赖: config.mjs, utils.mjs, scene-strategy.mjs, trace-algo.mjs
 *
 * SVG 路径追踪 → trace-whiteboard.mjs
 * Seedream 候选评分 + injectImageTraces → trace-inject.mjs
 */
import { mkdirSync, writeFileSync } from "fs";
import { join } from "path";
import sharp from "sharp";
import {
  PUBLIC_GENERATED_DIR,
  RASTER_REVEAL_ASSET_MAX_SIZE,
  RASTER_REVEAL_MAX_STROKES,
  RASTER_REVEAL_TRACE_HEIGHT,
  RASTER_REVEAL_TRACE_WIDTH,
} from "./config.mjs";
import { safeAssetSegment } from "./utils.mjs";
import { sceneShouldDirectRender } from "./scene-strategy.mjs";
import {
  clamp,
  cleanMaskComponents,
  estimateRevealWidth,
  pathMetrics,
  polylineLength,
  samplePath,
  selectRevealPaths,
  simplifyPolyline,
  sortRevealPaths,
  traceSkeletonPaths,
  zhangSuenThin,
} from "./trace-algo.mjs";

// Re-export algorithms for callers that import from trace.mjs
export {
  clamp, distance, polylineLength, samplePath,
  pixelNeighbors, cleanMaskComponents, zhangSuenThin,
  edgeKey, pathMetrics, traceSkeletonPaths,
  perpendicularDistanceToLine, simplifyPolyline,
  distanceToBackground, estimateRevealWidth,
  selectRevealPaths, sortRevealPaths,
} from "./trace-algo.mjs";

// ---------------------------------------------------------------------------
// raster reveal
// ---------------------------------------------------------------------------

export async function traceRasterRevealImage(imageBuffer) {
  const { data, info } = await sharp(imageBuffer, { failOn: "none" })
    .resize({ width: RASTER_REVEAL_TRACE_WIDTH, height: RASTER_REVEAL_TRACE_HEIGHT, fit: "inside", withoutEnlargement: false })
    .flatten({ background: "#ffffff" })
    .grayscale()
    .raw()
    .toBuffer({ resolveWithObject: true });

  const { width, height } = info;
  const mask = new Uint8Array(width * height);
  let darkPixels = 0;
  for (let i = 0; i < width * height; i += 1) {
    if (data[i] < 205) { mask[i] = 1; darkPixels += 1; }
  }
  if (darkPixels < 40) {
    return { strokes: [], traceWidth: width, traceHeight: height, darkPixels, skeletonPixels: 0 };
  }
  const cleanMask = cleanMaskComponents(mask, width, height);
  const skeleton = zhangSuenThin(cleanMask, width, height);
  let skeletonPixels = 0;
  for (const value of skeleton) { if (value) skeletonPixels += 1; }
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
    strokes, traceWidth: width, traceHeight: height, darkPixels, skeletonPixels,
    maskCoverage: Number((darkPixels / Math.max(1, width * height)).toFixed(5)),
  };
}

export async function makeTransparentLineArtAsset(imageBuffer) {
  const { data, info } = await sharp(imageBuffer, { failOn: "none" })
    .rotate()
    .resize({ width: RASTER_REVEAL_ASSET_MAX_SIZE, height: RASTER_REVEAL_ASSET_MAX_SIZE, fit: "inside", withoutEnlargement: true })
    .flatten({ background: "#ffffff" })
    .raw()
    .toBuffer({ resolveWithObject: true });
  const { width, height, channels } = info;
  const rgba = Buffer.alloc(width * height * 4);
  for (let i = 0; i < width * height; i += 1) {
    const source = i * channels;
    const target = i * 4;
    const r = data[source], g = data[source + 1], b = data[source + 2];
    const luminance = 0.299 * r + 0.587 * g + 0.114 * b;
    const chroma = Math.max(r, g, b) - Math.min(r, g, b);
    const darkAlpha = clamp(Math.round((225 - luminance) * 6.0), 0, 255);
    const colorInkAlpha = chroma > 70 && luminance < 235
      ? clamp(Math.round((chroma - 45) * 3.5 + (235 - luminance) * 1.4), 0, 255) : 0;
    const paperLike = luminance > 230 && chroma < 75;
    const alpha = paperLike ? 0 : Math.max(darkAlpha, colorInkAlpha);
    rgba[target] = alpha === 0 ? 255 : r;
    rgba[target + 1] = alpha === 0 ? 255 : g;
    rgba[target + 2] = alpha === 0 ? 255 : b;
    rgba[target + 3] = alpha;
  }
  const buffer = await sharp(rgba, { raw: { width, height, channels: 4 } })
    .png({ compressionLevel: 9 })
    .toBuffer();
  return { buffer, width, height };
}

export async function buildRasterRevealFromBuffer(imageBuffer, jobId, scene) {
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
      asset, renderMode,
      imageWidth: transparentAsset.width, imageHeight: transparentAsset.height,
      transparentBackground: true,
      traceWidth: trace.traceWidth, traceHeight: trace.traceHeight,
      maskCoverage: trace.maskCoverage, skeletonPixels: trace.skeletonPixels,
      strokeCount: trace.strokes.length,
      strokes: renderMode === "direct" ? [] : trace.strokes,
    },
    trace_strokes: renderMode === "direct" ? [] : trace.strokes.map((stroke) => stroke.points),
  };
}
