/**
 * trace-whiteboard.mjs — 旧式 SVG 路径追踪（traceWhiteboard*）
 * 依赖: config.mjs, trace-algo.mjs
 */
import sharp from "sharp";
import { IMAGE_TRACE_MAX_PATHS } from "./config.mjs";
import { normalizeBase64Image } from "./scene-strategy.mjs";
import { samplePath } from "./trace-algo.mjs";

function traceEdgePaths(edge, width, height, maxPaths) {
  const visited = new Uint8Array(edge.length);
  const offsets = [[-1,-1],[0,-1],[1,-1],[-1,0],[1,0],[-1,1],[0,1],[1,1]];
  const paths = [];
  const edgeNeighbors = (x, y) => {
    const neighbors = [];
    for (const [dx, dy] of offsets) {
      const nx = x + dx, ny = y + dy;
      if (nx < 0 || ny < 0 || nx >= width || ny >= height) continue;
      const nextIndex = ny * width + nx;
      if (edge[nextIndex]) neighbors.push(nextIndex);
    }
    return neighbors;
  };
  for (let startIndex = 0; startIndex < edge.length && paths.length < maxPaths; startIndex += 1) {
    if (!edge[startIndex] || visited[startIndex]) continue;
    let current = startIndex;
    const path = [];
    let previous = -1;
    while (current >= 0 && !visited[current] && path.length < 1600) {
      visited[current] = 1;
      const x = current % width, y = Math.floor(current / width);
      path.push({ x, y });
      const candidates = edgeNeighbors(x, y).filter((index) => !visited[index]);
      if (candidates.length === 0) break;
      if (previous < 0 || candidates.length === 1) { previous = current; current = candidates[0]; continue; }
      const px = previous % width, py = Math.floor(previous / width);
      const vx = x - px, vy = y - py;
      let best = candidates[0], bestScore = -Infinity;
      for (const candidate of candidates) {
        const cx = candidate % width, cy = Math.floor(candidate / width);
        const score = vx * (cx - x) + vy * (cy - y);
        if (score > bestScore) { best = candidate; bestScore = score; }
      }
      previous = current;
      current = best;
    }
    if (path.length >= 10) paths.push(path);
  }
  return paths;
}

export async function traceWhiteboardImageBuffer(image) {
  const { data, info } = await sharp(image, { failOn: "none" })
    .resize({ width: 420, height: 260, fit: "inside", withoutEnlargement: true })
    .flatten({ background: "#ffffff" })
    .grayscale()
    .raw()
    .toBuffer({ resolveWithObject: true });
  const { width, height } = info;
  const mask = new Uint8Array(width * height);
  let darkPixels = 0;
  for (let i = 0; i < width * height; i += 1) {
    if (data[i] < 196) { mask[i] = 1; darkPixels += 1; }
  }
  if (darkPixels < 40) return [];
  const edge = new Uint8Array(mask.length);
  for (let y = 1; y < height - 1; y += 1) {
    for (let x = 1; x < width - 1; x += 1) {
      const index = y * width + x;
      if (!mask[index]) continue;
      if (!mask[index - 1] || !mask[index + 1] || !mask[index - width] || !mask[index + width]) {
        edge[index] = 1;
      }
    }
  }
  return traceEdgePaths(edge, width, height, IMAGE_TRACE_MAX_PATHS)
    .sort((a, b) => b.length - a.length)
    .slice(0, IMAGE_TRACE_MAX_PATHS)
    .map((path) =>
      samplePath(path, 90).map((point) => ({
        x: Number((point.x / Math.max(1, width - 1)).toFixed(4)),
        y: Number((point.y / Math.max(1, height - 1)).toFixed(4)),
      })),
    )
    .filter((path) => path.length >= 2);
}

export async function traceWhiteboardImageBase64(imageBase64) {
  return traceWhiteboardImageBuffer(Buffer.from(normalizeBase64Image(imageBase64), "base64"));
}
