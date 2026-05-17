import { mkdirSync, writeFileSync } from "fs";
import { dirname } from "path";
import sharp from "../apps/render/node_modules/sharp/lib/index.js";

const input = process.argv[2];
const output = process.argv[3];
const maxPaths = Number(process.argv[4] ?? 140);

if (!input || !output) {
  throw new Error("Usage: node .tmp/trace-image-to-json.mjs <image> <output-json> [maxPaths]");
}

function samplePath(path, maxPoints = 90) {
  if (path.length <= maxPoints) return path;
  const sampled = [];
  const step = (path.length - 1) / (maxPoints - 1);
  for (let i = 0; i < maxPoints; i += 1) sampled.push(path[Math.round(i * step)]);
  return sampled;
}

function traceEdgePaths(edge, width, height, maxPathsValue) {
  const visited = new Uint8Array(edge.length);
  const offsets = [
    [-1, -1],
    [0, -1],
    [1, -1],
    [-1, 0],
    [1, 0],
    [-1, 1],
    [0, 1],
    [1, 1],
  ];
  const paths = [];

  const neighbors = (x, y) => {
    const out = [];
    for (const [dx, dy] of offsets) {
      const nx = x + dx;
      const ny = y + dy;
      if (nx < 0 || ny < 0 || nx >= width || ny >= height) continue;
      const index = ny * width + nx;
      if (edge[index]) out.push(index);
    }
    return out;
  };

  for (let start = 0; start < edge.length && paths.length < maxPathsValue; start += 1) {
    if (!edge[start] || visited[start]) continue;
    let current = start;
    let previous = -1;
    const path = [];

    while (current >= 0 && !visited[current] && path.length < 1800) {
      visited[current] = 1;
      const x = current % width;
      const y = Math.floor(current / width);
      path.push({ x, y });

      const candidates = neighbors(x, y).filter((index) => !visited[index]);
      if (candidates.length === 0) break;
      if (previous < 0 || candidates.length === 1) {
        previous = current;
        current = candidates[0];
        continue;
      }

      const px = previous % width;
      const py = Math.floor(previous / width);
      const vx = x - px;
      const vy = y - py;
      let best = candidates[0];
      let bestScore = -Infinity;
      for (const candidate of candidates) {
        const cx = candidate % width;
        const cy = Math.floor(candidate / width);
        const score = vx * (cx - x) + vy * (cy - y);
        if (score > bestScore) {
          best = candidate;
          bestScore = score;
        }
      }
      previous = current;
      current = best;
    }

    if (path.length >= 9) paths.push(path);
  }

  return paths;
}

const { data, info } = await sharp(input)
  .resize({ width: 520, height: 520, fit: "inside", withoutEnlargement: true })
  .flatten({ background: "#ffffff" })
  .grayscale()
  .raw()
  .toBuffer({ resolveWithObject: true });

const { width, height } = info;
const mask = new Uint8Array(width * height);
for (let i = 0; i < width * height; i += 1) {
  if (data[i] < 202) mask[i] = 1;
}

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

const traceStrokes = traceEdgePaths(edge, width, height, maxPaths)
  .sort((a, b) => b.length - a.length)
  .slice(0, maxPaths)
  .map((path) =>
    samplePath(path, 90).map((point) => ({
      x: Number((point.x / Math.max(1, width - 1)).toFixed(4)),
      y: Number((point.y / Math.max(1, height - 1)).toFixed(4)),
    })),
  );

mkdirSync(dirname(output), { recursive: true });
writeFileSync(output, JSON.stringify({ width, height, pathCount: traceStrokes.length, trace_strokes: traceStrokes }, null, 2));
console.log(JSON.stringify({ width, height, pathCount: traceStrokes.length }));
