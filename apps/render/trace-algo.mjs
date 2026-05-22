/**
 * trace-algo.mjs — 像素/拓扑算法：骨架提取、路径追踪、路径简化
 * 无外部依赖
 */

// ---------------------------------------------------------------------------
// 内部工具
// ---------------------------------------------------------------------------

export function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

export function distance(a, b) {
  return Math.hypot(a.x - b.x, a.y - b.y);
}

export function polylineLength(points) {
  let total = 0;
  for (let i = 1; i < points.length; i += 1) total += distance(points[i - 1], points[i]);
  return total;
}

export function samplePath(path, maxPoints = 80) {
  if (path.length <= maxPoints) return path;
  const sampled = [];
  const step = (path.length - 1) / (maxPoints - 1);
  for (let i = 0; i < maxPoints; i += 1) sampled.push(path[Math.round(i * step)]);
  return sampled;
}

// ---------------------------------------------------------------------------
// 像素连通组件清理
// ---------------------------------------------------------------------------

export function pixelNeighbors(index, width, height, pixels) {
  const x = index % width;
  const y = Math.floor(index / width);
  const neighbors = [];
  for (let dy = -1; dy <= 1; dy += 1) {
    for (let dx = -1; dx <= 1; dx += 1) {
      if (dx === 0 && dy === 0) continue;
      const nx = x + dx, ny = y + dy;
      if (nx < 0 || ny < 0 || nx >= width || ny >= height) continue;
      const next = ny * width + nx;
      if (pixels[next]) neighbors.push(next);
    }
  }
  return neighbors;
}

export function cleanMaskComponents(mask, width, height) {
  const visited = new Uint8Array(mask.length);
  const cleaned = new Uint8Array(mask.length);
  const stack = [];
  for (let start = 0; start < mask.length; start += 1) {
    if (!mask[start] || visited[start]) continue;
    const component = [];
    visited[start] = 1;
    stack.push(start);
    while (stack.length > 0) {
      const current = stack.pop();
      component.push(current);
      for (const next of pixelNeighbors(current, width, height, mask)) {
        if (visited[next]) continue;
        visited[next] = 1;
        stack.push(next);
      }
    }
    if (component.length >= 5) for (const index of component) cleaned[index] = 1;
  }
  return cleaned;
}

// ---------------------------------------------------------------------------
// Zhang-Suen 骨架细化
// ---------------------------------------------------------------------------

export function zhangSuenThin(mask, width, height) {
  const image = new Uint8Array(mask);
  const toRemove = [];
  const transitions = (p2, p3, p4, p5, p6, p7, p8, p9) => {
    const values = [p2, p3, p4, p5, p6, p7, p8, p9, p2];
    let count = 0;
    for (let i = 0; i < values.length - 1; i += 1) { if (values[i] === 0 && values[i + 1] === 1) count += 1; }
    return count;
  };
  let changed = true, iterations = 0;
  while (changed && iterations < 80) {
    changed = false; iterations += 1;
    for (let pass = 0; pass < 2; pass += 1) {
      toRemove.length = 0;
      for (let y = 1; y < height - 1; y += 1) {
        for (let x = 1; x < width - 1; x += 1) {
          const i = y * width + x;
          if (!image[i]) continue;
          const p2 = image[i - width] ? 1 : 0, p3 = image[i - width + 1] ? 1 : 0;
          const p4 = image[i + 1] ? 1 : 0, p5 = image[i + width + 1] ? 1 : 0;
          const p6 = image[i + width] ? 1 : 0, p7 = image[i + width - 1] ? 1 : 0;
          const p8 = image[i - 1] ? 1 : 0, p9 = image[i - width - 1] ? 1 : 0;
          const neighborCount = p2 + p3 + p4 + p5 + p6 + p7 + p8 + p9;
          if (neighborCount < 2 || neighborCount > 6) continue;
          if (transitions(p2, p3, p4, p5, p6, p7, p8, p9) !== 1) continue;
          if (pass === 0) { if (p2 * p4 * p6 !== 0 || p4 * p6 * p8 !== 0) continue; }
          else if (p2 * p4 * p8 !== 0 || p2 * p6 * p8 !== 0) continue;
          toRemove.push(i);
        }
      }
      if (toRemove.length > 0) { changed = true; for (const index of toRemove) image[index] = 0; }
    }
  }
  return image;
}

// ---------------------------------------------------------------------------
// 路径追踪
// ---------------------------------------------------------------------------

export function edgeKey(a, b) {
  return a < b ? `${a}:${b}` : `${b}:${a}`;
}

export function pathMetrics(path) {
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity, length = 0;
  for (let i = 0; i < path.length; i += 1) {
    const point = path[i];
    minX = Math.min(minX, point.x); minY = Math.min(minY, point.y);
    maxX = Math.max(maxX, point.x); maxY = Math.max(maxY, point.y);
    if (i > 0) length += distance(path[i - 1], point);
  }
  return { minX, minY, maxX, maxY, length, centerX: (minX + maxX) / 2, centerY: (minY + maxY) / 2 };
}

export function traceSkeletonPaths(skeleton, width, height) {
  const indices = [];
  const degrees = new Map();
  for (let i = 0; i < skeleton.length; i += 1) {
    if (!skeleton[i]) continue;
    indices.push(i);
    degrees.set(i, pixelNeighbors(i, width, height, skeleton).length);
  }
  const visitedEdges = new Set();
  const paths = [];
  const pointForIndex = (index) => ({ x: index % width, y: Math.floor(index / width) });
  const walk = (start, next) => {
    const path = [pointForIndex(start)];
    let previous = start, current = next, guard = 0;
    while (guard < 4000) {
      guard += 1;
      visitedEdges.add(edgeKey(previous, current));
      path.push(pointForIndex(current));
      const degree = degrees.get(current) ?? 0;
      if (degree !== 2) break;
      const candidates = pixelNeighbors(current, width, height, skeleton).filter((c) => c !== previous);
      const candidate = candidates.find((v) => !visitedEdges.has(edgeKey(current, v)));
      if (candidate === undefined) break;
      previous = current; current = candidate;
    }
    if (path.length >= 2) paths.push(path);
  };
  const starts = indices.filter((i) => (degrees.get(i) ?? 0) !== 2).sort((a, b) => Math.floor(a / width) - Math.floor(b / width) || (a % width) - (b % width));
  for (const start of starts) {
    for (const next of pixelNeighbors(start, width, height, skeleton)) {
      if (!visitedEdges.has(edgeKey(start, next))) walk(start, next);
    }
  }
  for (const start of indices) {
    for (const next of pixelNeighbors(start, width, height, skeleton)) {
      if (!visitedEdges.has(edgeKey(start, next))) walk(start, next);
    }
  }
  return paths;
}

// ---------------------------------------------------------------------------
// 路径简化
// ---------------------------------------------------------------------------

export function perpendicularDistanceToLine(point, start, end) {
  const dx = end.x - start.x, dy = end.y - start.y;
  const denominator = dx * dx + dy * dy;
  if (denominator === 0) return distance(point, start);
  const t = clamp(((point.x - start.x) * dx + (point.y - start.y) * dy) / denominator, 0, 1);
  return distance(point, { x: start.x + dx * t, y: start.y + dy * t });
}

export function simplifyPolyline(points, epsilon = 1.25) {
  if (points.length <= 3) return points;
  let maxDistance = 0, index = 0;
  const start = points[0], end = points[points.length - 1];
  for (let i = 1; i < points.length - 1; i += 1) {
    const value = perpendicularDistanceToLine(points[i], start, end);
    if (value > maxDistance) { index = i; maxDistance = value; }
  }
  if (maxDistance <= epsilon) return [start, end];
  const left = simplifyPolyline(points.slice(0, index + 1), epsilon);
  const right = simplifyPolyline(points.slice(index), epsilon);
  return left.slice(0, -1).concat(right);
}

// ---------------------------------------------------------------------------
// 笔画宽度估算与路径选择
// ---------------------------------------------------------------------------

export function distanceToBackground(mask, width, height, x, y, maxRadius = 18) {
  const cx = Math.round(x), cy = Math.round(y);
  for (let radius = 1; radius <= maxRadius; radius += 1) {
    for (let dy = -radius; dy <= radius; dy += 1) {
      for (let dx = -radius; dx <= radius; dx += 1) {
        if (Math.abs(dx) !== radius && Math.abs(dy) !== radius) continue;
        const nx = cx + dx, ny = cy + dy;
        if (nx < 0 || ny < 0 || nx >= width || ny >= height) return radius;
        if (!mask[ny * width + nx]) return radius;
      }
    }
  }
  return maxRadius;
}

export function estimateRevealWidth(mask, width, height, path) {
  const samples = [];
  const sampleCount = Math.min(28, path.length);
  for (let i = 0; i < sampleCount; i += 1) {
    const point = path[Math.round((i * (path.length - 1)) / Math.max(1, sampleCount - 1))];
    samples.push(distanceToBackground(mask, width, height, point.x, point.y));
  }
  samples.sort((a, b) => a - b);
  const median = samples[Math.floor(samples.length / 2)] || 2;
  const pixelWidth = clamp(median * 4 + 76, 72, 128);
  return Number((pixelWidth / Math.max(width, height)).toFixed(5));
}

export function selectRevealPaths(paths, maxPaths, width, height) {
  if (paths.length <= maxPaths) return paths;
  const bands = 8;
  const byBand = Array.from({ length: bands }, () => []);
  for (const path of paths) {
    const metric = pathMetrics(path);
    const band = clamp(Math.floor((metric.centerY / Math.max(1, height)) * bands), 0, bands - 1);
    byBand[band].push({ path, metric });
  }
  const selected = new Set();
  const perBand = Math.max(5, Math.floor(maxPaths / bands));
  for (const band of byBand) {
    band.sort((a, b) => b.metric.length - a.metric.length);
    for (const item of band.slice(0, perBand)) selected.add(item.path);
  }
  const remaining = paths.filter((p) => !selected.has(p)).map((p) => ({ path: p, metric: pathMetrics(p) })).sort((a, b) => b.metric.length - a.metric.length);
  for (const item of remaining) {
    if (selected.size >= maxPaths) break;
    selected.add(item.path);
  }
  return paths.filter((p) => selected.has(p));
}

export function sortRevealPaths(paths) {
  const pending = paths.map((path, id) => ({ id, path, metric: pathMetrics(path) }));
  pending.sort((a, b) => a.metric.minY - b.metric.minY || a.metric.minX - b.metric.minX);
  const sorted = [];
  let current = pending.shift();
  while (current) {
    sorted.push(current.path);
    const end = current.path[current.path.length - 1];
    if (pending.length === 0) break;
    let bestIndex = 0, bestScore = Infinity;
    const searchLimit = Math.min(36, pending.length);
    for (let i = 0; i < searchLimit; i += 1) {
      const candidate = pending[i];
      const start = candidate.path[0];
      const score = distance(end, start) + Math.abs(candidate.metric.centerY - current.metric.centerY) * 0.35 + Math.max(0, candidate.metric.minY - current.metric.minY) * 0.12;
      if (score < bestScore) { bestScore = score; bestIndex = i; }
    }
    current = pending.splice(bestIndex, 1)[0];
  }
  return sorted;
}
