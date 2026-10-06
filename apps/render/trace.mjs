/**
 * trace.mjs — raster reveal 图像追踪（PNG 骨架描绘）
 * 依赖: config.mjs, utils.mjs, scene-strategy.mjs, trace-algo.mjs
 *
 * SVG 路径追踪 → trace-whiteboard.mjs
 * Seedream 候选评分 + injectImageTraces → trace-inject.mjs
 */
import { mkdirSync, writeFileSync } from "fs";
import { createHash } from "crypto";
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

function median(values) {
  if (values.length === 0) return 255;
  values.sort((a, b) => a - b);
  return values[Math.floor(values.length / 2)];
}

function sampleCornerBackground(data, width, height, channels) {
  const margin = Math.max(3, Math.min(24, Math.round(Math.min(width, height) / 50)));
  const samples = [[], [], []];
  const corners = [
    [0, 0], [Math.max(0, width - margin), 0],
    [0, Math.max(0, height - margin)], [Math.max(0, width - margin), Math.max(0, height - margin)],
  ];
  for (const [left, top] of corners) {
    for (let y = top; y < Math.min(height, top + margin); y += 1) {
      for (let x = left; x < Math.min(width, left + margin); x += 1) {
        const offset = (y * width + x) * channels;
        samples[0].push(data[offset]);
        samples[1].push(data[offset + 1]);
        samples[2].push(data[offset + 2]);
      }
    }
  }
  return samples.map(median);
}

function adaptiveInkAlpha(data, width, height, channels) {
  const gray = new Float32Array(width * height);
  const integral = new Float64Array((width + 1) * (height + 1));
  for (let y = 0; y < height; y += 1) {
    let rowSum = 0;
    for (let x = 0; x < width; x += 1) {
      const source = (y * width + x) * channels;
      const value = 0.299 * data[source] + 0.587 * data[source + 1] + 0.114 * data[source + 2];
      gray[y * width + x] = value;
      rowSum += value;
      integral[(y + 1) * (width + 1) + x + 1] = integral[y * (width + 1) + x + 1] + rowSum;
    }
  }
  const alpha = new Uint8Array(width * height);
  const radius = 7;
  for (let y = 0; y < height; y += 1) {
    const top = Math.max(0, y - radius), bottom = Math.min(height - 1, y + radius);
    for (let x = 0; x < width; x += 1) {
      const left = Math.max(0, x - radius), right = Math.min(width - 1, x + radius);
      const area = (right - left + 1) * (bottom - top + 1);
      const sum = integral[(bottom + 1) * (width + 1) + right + 1]
        - integral[top * (width + 1) + right + 1]
        - integral[(bottom + 1) * (width + 1) + left]
        + integral[top * (width + 1) + left];
      const localMean = sum / Math.max(1, area);
      const contrast = localMean - 8 - gray[y * width + x];
      alpha[y * width + x] = clamp(Math.round(contrast * 22), 0, 255);
    }
  }
  return alpha;
}

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

async function makeHanddrawnMaster(imageBuffer) {
  // Keep the generated reference as the single source for both line art and
  // color. The old palette reduction made detailed references collapse into
  // flat geometric icons before tracing even started.
  const normalized = await sharp(imageBuffer, { failOn: "none" })
    .rotate()
    .resize({ width: RASTER_REVEAL_ASSET_MAX_SIZE, height: RASTER_REVEAL_ASSET_MAX_SIZE, fit: "inside", withoutEnlargement: true })
    .modulate({ saturation: 0.78, brightness: 1.03 })
    .sharpen({ sigma: 0.55, m1: 0.7, m2: 2.5 })
    .png({ compressionLevel: 9 })
    .toBuffer();

  // Generated references often contain a large blank border. Trim only the
  // near-white border, then restore a small white margin so the subject grows
  // on the board without touching the canvas edge.
  const trimmed = await sharp(normalized, { failOn: "none" })
    .trim({ background: "#ffffff", threshold: 12 })
    .toBuffer();
  const metadata = await sharp(trimmed).metadata();
  const width = Number(metadata.width ?? RASTER_REVEAL_ASSET_MAX_SIZE);
  const height = Number(metadata.height ?? RASTER_REVEAL_ASSET_MAX_SIZE);
  const side = Math.max(width, height);
  const margin = Math.max(12, Math.round(side * 0.08));
  return sharp(trimmed)
    .extend({
      top: Math.round((side - height) / 2) + margin,
      bottom: Math.ceil((side - height) / 2) + margin,
      left: Math.round((side - width) / 2) + margin,
      right: Math.ceil((side - width) / 2) + margin,
      background: "#ffffff",
    })
    .png({ compressionLevel: 9 })
    .toBuffer();
}

export async function makeTransparentLineArtAsset(imageBuffer) {
  const master = await makeHanddrawnMaster(imageBuffer);
  const { data, info } = await sharp(master, { failOn: "none" })
    .rotate()
    .flatten({ background: "#ffffff" })
    .greyscale()
    .normalise()
    .linear(1.12, -18)
    .raw()
    .toBuffer({ resolveWithObject: true });
  const { width, height, channels } = info;
  const inkAlpha = adaptiveInkAlpha(data, width, height, channels);
  let minX = width, minY = height, maxX = -1, maxY = -1;
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      if (inkAlpha[y * width + x] < 18) continue;
      minX = Math.min(minX, x); minY = Math.min(minY, y);
      maxX = Math.max(maxX, x); maxY = Math.max(maxY, y);
    }
  }
  const bounds = maxX >= minX && maxY >= minY
    ? { x: minX, y: minY, width: maxX - minX + 1, height: maxY - minY + 1 }
    : null;
  const rgba = Buffer.alloc(width * height * 4);
  for (let i = 0; i < width * height; i += 1) {
    const source = i * channels;
    const target = i * 4;
    rgba[target] = 45;
    rgba[target + 1] = 45;
    rgba[target + 2] = 45;
    rgba[target + 3] = inkAlpha[i];
  }
  const buffer = await sharp(rgba, { raw: { width, height, channels: 4 } })
    .png({ compressionLevel: 9 })
    .toBuffer();
  return { buffer, width, height, bounds };
}

async function makeTransparentColorAsset(imageBuffer) {
  // Normalize photographic references into one restrained whiteboard plate:
  // low-detail, flat colors, and no photographic grain competing with the ink.
  const stylizedBuffer = await makeHanddrawnMaster(imageBuffer);
  const { data, info } = await sharp(stylizedBuffer, { failOn: "none" })
    .rotate()
    .resize({ width: RASTER_REVEAL_ASSET_MAX_SIZE, height: RASTER_REVEAL_ASSET_MAX_SIZE, fit: "inside", withoutEnlargement: true })
    .flatten({ background: "#ffffff" })
    .raw()
    .toBuffer({ resolveWithObject: true });
  const { width, height, channels } = info;
  const background = sampleCornerBackground(data, width, height, channels);
  const rgba = Buffer.alloc(width * height * 4);
  for (let i = 0; i < width * height; i += 1) {
    const source = i * channels;
    const target = i * 4;
    const r = data[source], g = data[source + 1], b = data[source + 2];
    const luminance = 0.299 * r + 0.587 * g + 0.114 * b;
    const chroma = Math.max(r, g, b) - Math.min(r, g, b);
    const backgroundDistance = Math.abs(r - background[0]) + Math.abs(g - background[1]) + Math.abs(b - background[2]);
    const darkAlpha = clamp(Math.round((220 - luminance) * 5.0), 0, 255);
    const colorAlpha = clamp(Math.round((backgroundDistance - 18) * 4.5 + Math.max(0, chroma - 20) * 1.2), 0, 255);
    const paperLike = backgroundDistance < 22 || (luminance > 242 && chroma < 24);
    // Keep ink exclusively in the ink asset. The color plate must contain
    // chromatic pixels only so the drawn line and the fill share one source
    // image without a second, darker copy of the stroke.
    const alpha = paperLike ? 0 : colorAlpha;
    rgba[target] = r;
    rgba[target + 1] = g;
    rgba[target + 2] = b;
    rgba[target + 3] = alpha;
  }
  const buffer = await sharp(rgba, { raw: { width, height, channels: 4 } })
    .png({ compressionLevel: 9 })
    .toBuffer();
  return { buffer, width, height };
}

export async function buildRasterRevealFromBuffer(imageBuffer, jobId, scene, options = {}) {
  const assetDir = join(PUBLIC_GENERATED_DIR, jobId);
  mkdirSync(assetDir, { recursive: true });
  const handdrawnMaster = await makeHanddrawnMaster(imageBuffer);
  const transparentAsset = await makeTransparentLineArtAsset(handdrawnMaster);
  const assetBuffer = transparentAsset.buffer;
  const sceneId = scene?.id ?? "scene";
  const safeSceneId = safeAssetSegment(sceneId, "scene");
  const masterFilename = `${safeSceneId}-master.png`;
  const filename = `${safeSceneId}.png`;
  const colorFilename = `${safeSceneId}-color.png`;
  writeFileSync(join(assetDir, masterFilename), handdrawnMaster);
  writeFileSync(join(assetDir, filename), assetBuffer);
  const colorAssetData = await makeTransparentColorAsset(handdrawnMaster);
  writeFileSync(join(assetDir, colorFilename), colorAssetData.buffer);
  const trace = await traceRasterRevealImage(assetBuffer);
  // A generated reference is still valuable when its line-art skeleton is too
  // sparse to animate. Keep the complete normalized plate and render it
  // directly instead of discarding the image and falling back to text-only SVG.
  const hasEnoughTracePaths = trace.strokes.length >= 6;
  const asset = `generated/${jobId}/${filename}`;
  const masterAsset = `generated/${jobId}/${masterFilename}`;
  const colorAsset = `generated/${jobId}/${colorFilename}`;
  const forceTrace = options.forceTrace === true;
  const renderMode = !hasEnoughTracePaths
    ? "direct"
    : (forceTrace || !sceneShouldDirectRender(scene, trace) ? "trace" : "direct");
  const directAsset = masterAsset;
  return {
    assetContract: {
      mode: renderMode === "direct" ? "full" : "trace",
      masterAsset,
      inkAsset: asset,
      colorAsset: renderMode === "direct" ? directAsset : colorAsset,
      width: transparentAsset.width,
      height: transparentAsset.height,
      sourceHash: createHash("sha256").update(handdrawnMaster).digest("hex"),
      layers: renderMode === "direct" ? ["color"] : ["ink", "color"],
      observedContentBounds: transparentAsset.bounds,
      cropConfidence: transparentAsset.bounds ? 1 : 0,
      stage: "render-assets",
    },
    referenceImageAsset: renderMode === "direct" ? directAsset : asset,
    rasterReveal: {
      asset: renderMode === "direct" ? directAsset : asset,
      inkAsset: asset,
      colorAsset: renderMode === "direct" ? directAsset : colorAsset,
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
