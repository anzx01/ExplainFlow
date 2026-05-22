/**
 * glyph.mjs — OpenType 字形加载、路径采样、字形片段构建与注入
 * 依赖: config.mjs
 */
import { existsSync, readFileSync } from "fs";
import opentype from "opentype.js";
import { GLYPH_FONT_CANDIDATES, LATIN_GLYPH_FONT_CANDIDATES } from "./config.mjs";

// ---------------------------------------------------------------------------
// Font loading
// ---------------------------------------------------------------------------

let glyphFontCache;
let latinGlyphFontCache;

function parseFontFile(fontPath) {
  const buffer = readFileSync(fontPath);
  const arrayBuffer = buffer.buffer.slice(buffer.byteOffset, buffer.byteOffset + buffer.byteLength);
  return opentype.parse(arrayBuffer);
}

export function loadGlyphFont() {
  if (glyphFontCache !== undefined) return glyphFontCache;
  for (const fontPath of GLYPH_FONT_CANDIDATES) {
    if (!existsSync(fontPath)) continue;
    try {
      glyphFontCache = { font: parseFontFile(fontPath), fontPath };
      console.log(`[glyph] Loaded outline font: ${fontPath}`);
      return glyphFontCache;
    } catch (err) {
      console.warn(`[glyph] Failed to load outline font ${fontPath}:`, err.message);
    }
  }
  glyphFontCache = null;
  return glyphFontCache;
}

export function loadLatinGlyphFont() {
  if (latinGlyphFontCache !== undefined) return latinGlyphFontCache;
  for (const fontPath of LATIN_GLYPH_FONT_CANDIDATES) {
    if (!existsSync(fontPath)) continue;
    try {
      latinGlyphFontCache = { font: parseFontFile(fontPath), fontPath };
      console.log(`[glyph] Loaded latin outline font: ${fontPath}`);
      return latinGlyphFontCache;
    } catch (err) {
      console.warn(`[glyph] Failed to load latin outline font ${fontPath}:`, err.message);
    }
  }
  latinGlyphFontCache = null;
  return latinGlyphFontCache;
}

// ---------------------------------------------------------------------------
// Geometry helpers
// ---------------------------------------------------------------------------

function rounded(value, places = 1) {
  if (!Number.isFinite(value)) return 0;
  return Number(value.toFixed(places));
}

function addPoint(points, x, y) {
  const point = { x: rounded(x), y: rounded(y) };
  const prev = points[points.length - 1];
  if (!prev || prev.x !== point.x || prev.y !== point.y) points.push(point);
}

function distance(a, b) {
  return Math.hypot(a.x - b.x, a.y - b.y);
}

function polylineLength(points) {
  let total = 0;
  for (let i = 1; i < points.length; i += 1) total += distance(points[i - 1], points[i]);
  return total;
}

function quadraticPoint(p0, p1, p2, t) {
  const mt = 1 - t;
  return {
    x: mt * mt * p0.x + 2 * mt * t * p1.x + t * t * p2.x,
    y: mt * mt * p0.y + 2 * mt * t * p1.y + t * t * p2.y,
  };
}

function cubicPoint(p0, p1, p2, p3, t) {
  const mt = 1 - t;
  return {
    x: mt * mt * mt * p0.x + 3 * mt * mt * t * p1.x + 3 * mt * t * t * p2.x + t * t * t * p3.x,
    y: mt * mt * mt * p0.y + 3 * mt * mt * t * p1.y + 3 * mt * t * t * p2.y + t * t * t * p3.y,
  };
}

function curveSteps(from, to) {
  return Math.max(5, Math.min(14, Math.ceil(distance(from, to) / 16)));
}

export function samplePathCommands(commands, includeMoveJumps = true) {
  const points = [];
  let cursor = { x: 0, y: 0 };
  let contourStart = null;
  for (const command of commands) {
    if (command.type === "M") {
      cursor = { x: command.x, y: command.y };
      contourStart = cursor;
      if (includeMoveJumps || points.length === 0) addPoint(points, cursor.x, cursor.y);
      continue;
    }
    if (command.type === "L") { cursor = { x: command.x, y: command.y }; addPoint(points, cursor.x, cursor.y); continue; }
    if (command.type === "Q") {
      const start = cursor;
      const ctrl = { x: command.x1, y: command.y1 };
      const end = { x: command.x, y: command.y };
      const steps = curveSteps(start, end);
      for (let i = 1; i <= steps; i += 1) { const p = quadraticPoint(start, ctrl, end, i / steps); addPoint(points, p.x, p.y); }
      cursor = end; continue;
    }
    if (command.type === "C") {
      const start = cursor;
      const c1 = { x: command.x1, y: command.y1 };
      const c2 = { x: command.x2, y: command.y2 };
      const end = { x: command.x, y: command.y };
      const steps = curveSteps(start, end);
      for (let i = 1; i <= steps; i += 1) { const p = cubicPoint(start, c1, c2, end, i / steps); addPoint(points, p.x, p.y); }
      cursor = end; continue;
    }
    if (command.type === "Z" && contourStart) { addPoint(points, contourStart.x, contourStart.y); cursor = contourStart; }
  }
  return points;
}

export function splitContours(commands) {
  const contours = [];
  let current = [];
  for (const command of commands) {
    if (command.type === "M") { if (current.length > 1) contours.push(current); current = [command]; continue; }
    if (current.length === 0) continue;
    current.push(command);
    if (command.type === "Z") { contours.push(current); current = []; }
  }
  if (current.length > 1) contours.push(current);
  return contours;
}

export function visiblePathLength(commands) {
  return splitContours(commands)
    .map((contour) => polylineLength(samplePathCommands(contour, false)))
    .reduce((sum, value) => sum + value, 0);
}

// ---------------------------------------------------------------------------
// Text layout
// ---------------------------------------------------------------------------

function measureText(font, text, fontSize) {
  try { return font.getAdvanceWidth(text, fontSize, { kerning: true }); }
  catch { return Array.from(text).length * fontSize * 0.72; }
}

function layoutTextLines(font, text, fontSize, maxWidth) {
  const safeMaxWidth = Number(maxWidth) > fontSize * 2 ? Number(maxWidth) : Number.POSITIVE_INFINITY;
  const lines = [];
  for (const paragraph of String(text ?? "").split(/\r?\n/)) {
    let current = "";
    for (const char of Array.from(paragraph)) {
      const candidate = current + char;
      if (current && measureText(font, candidate, fontSize) > safeMaxWidth) {
        lines.push(current.trimEnd()); current = char.trimStart();
      } else { current = candidate; }
    }
    if (current) lines.push(current);
  }
  return lines.length > 0 ? lines : [String(text ?? "")];
}

function pickFontForText(text) {
  const hasCjk = /[㐀-鿿]/u.test(String(text ?? ""));
  if (hasCjk) return loadGlyphFont();
  return loadLatinGlyphFont() || loadGlyphFont();
}

// ---------------------------------------------------------------------------
// Glyph fragment builder
// ---------------------------------------------------------------------------

export function buildGlyphFragments(font, textSpec) {
  const fontSize = Number(textSpec.fontSize) || 48;
  const x = Number(textSpec.x) || 0;
  const y = Number(textSpec.y) || 0;
  const lines = layoutTextLines(font, textSpec.text, fontSize, textSpec.maxWidth);
  const lineHeight = fontSize * 1.18;
  const fragments = [];
  const hasCjk = /[㐀-鿿]/u.test(String(textSpec.text ?? ""));
  const baseStrokeScale = hasCjk ? 0.04 : 0.034;

  lines.forEach((line, lineIndex) => {
    const baselineY = y + fontSize * 0.88 + lineIndex * lineHeight;
    font.forEachGlyph(line, x, baselineY, fontSize, { kerning: true }, (glyph, gX, gY, gSize) => {
      const path = glyph.getPath(gX, gY, gSize);
      if (!path.commands.length) return;
      const points = samplePathCommands(path.commands, true);
      const visibleLength = visiblePathLength(path.commands);
      if (points.length < 2 || visibleLength < 2) return;
      fragments.push({
        d: path.toPathData(1), points, dashLength: rounded(visibleLength),
        strokeWidth: rounded(Math.max(1.8, Math.min(4.4, fontSize * baseStrokeScale))),
      });
    });
  });
  return fragments;
}

export function glyphTimingWeights(fragments) {
  const totalLength = fragments.reduce((sum, f) => sum + (f.dashLength || 0), 0);
  const averageLength = totalLength / Math.max(1, fragments.length) || 1;
  return fragments.map((fragment) => {
    const length = Math.max(1, fragment.dashLength || averageLength);
    const softenedLength = Math.sqrt(length * averageLength);
    const clampedLength = Math.max(averageLength * 0.62, Math.min(averageLength * 1.42, softenedLength));
    return averageLength * 0.62 + clampedLength * 0.38;
  });
}

export function upgradeScenesWithGlyphOutlines(scenes) {
  const defaultLoaded = loadGlyphFont();
  if (!defaultLoaded) {
    throw new Error(`No usable Chinese outline font found. Tried: ${GLYPH_FONT_CANDIDATES.join(", ")}`);
  }

  let glyphCount = 0;
  const enhancedScenes = scenes.map((scene) => {
    const textsByOp = new Map((scene.texts ?? []).map((text) => [text.opId, text]));
    const glyphPaths = [];
    const nextDrawOps = [];

    for (const op of scene.drawOps ?? []) {
      if (op.kind !== "text" || !textsByOp.has(op.id)) { nextDrawOps.push(op); continue; }
      const textSpec = textsByOp.get(op.id);
      const loaded = pickFontForText(textSpec.text) || defaultLoaded;
      const fragments = buildGlyphFragments(loaded.font, textSpec);
      if (fragments.length === 0) { nextDrawOps.push(op); continue; }

      const startFrame = Number(op.startFrame) || 0;
      const endFrame = Number(op.endFrame) || startFrame + 1;
      const duration = Math.max(1, endFrame - startFrame);
      const timingWeights = glyphTimingWeights(fragments);
      const totalTimingWeight = timingWeights.reduce((sum, w) => sum + w, 0) || fragments.length;
      let timingCursor = 0;

      fragments.forEach((fragment, index) => {
        const opId = `${op.id}_glyph_${index}`;
        const fragmentStart = startFrame + duration * (timingCursor / totalTimingWeight);
        timingCursor += timingWeights[index] || 1;
        const fragmentEnd = index === fragments.length - 1
          ? endFrame
          : startFrame + duration * (timingCursor / totalTimingWeight);
        nextDrawOps.push({
          ...op, id: opId, pace: "glyph",
          startFrame: rounded(fragmentStart, 2),
          endFrame: rounded(Math.max(fragmentStart + 0.2, fragmentEnd), 2),
          points: fragment.points,
        });
        glyphPaths.push({
          opId, sourceOpId: op.id, d: fragment.d,
          color: textSpec.color || "#1D1D1F",
          strokeWidth: Number(textSpec.markerStrokeWidth) || fragment.strokeWidth,
          dashLength: fragment.dashLength, fontOutline: true,
          markerFillOpacity: Number.isFinite(Number(textSpec.markerFillOpacity))
            ? Number(textSpec.markerFillOpacity) : 0.96,
        });
      });
      glyphCount += fragments.length;
    }
    return { ...scene, drawOps: nextDrawOps, glyphPaths };
  });

  return { scenes: enhancedScenes, glyphCount, fontPath: defaultLoaded.fontPath };
}

export function injectGlyphOutlineDrawing(tsx) {
  const sceneMatch = tsx.match(/const\s+scenes\s*=\s*([\s\S]*?)\s+as\s+SceneSpec\[\]\s*;/);
  if (!sceneMatch) return tsx;

  let scenes;
  try { scenes = JSON.parse(sceneMatch[1]); }
  catch (err) { console.warn("[glyph] Could not parse scenes JSON for outline preprocessing:", err.message); return tsx; }

  if (!Array.isArray(scenes) || scenes.length === 0) return tsx;
  if (!scenes.some((scene) => Array.isArray(scene.texts) && scene.texts.length > 0)) return tsx;

  const enhanced = upgradeScenesWithGlyphOutlines(scenes);
  if (enhanced.glyphCount === 0) throw new Error("Glyph outline preprocessing produced no drawable text paths");

  console.log(`[glyph] Preprocessed ${enhanced.glyphCount} fontOutline glyph path(s) from ${enhanced.fontPath}`);
  return tsx.replace(sceneMatch[0], `const scenes = ${JSON.stringify(enhanced.scenes)} as SceneSpec[];`);
}
