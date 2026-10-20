/**
 * codegen.mjs — Remotion 代码生成编排、风格指令、音频追踪、项目写入
 * 依赖: config.mjs, utils.mjs, glyph.mjs, validate-tsx.mjs
 */
import { mkdirSync, writeFileSync } from "fs";
import { join } from "path";
import {
  ACTIVE_PEN_STYLE,
  ACTIVE_VIDEO_STYLE,
  COMPOSITION_ID,
  FPS,
  GENERATED_DIR,
  HEIGHT,
  PYTHON_API,
  WIDTH,
} from "./config.mjs";
import {
  canonicalVideoStyle,
  clampNumber,
  normalizePenStyle,
  postJson,
  sleep,
} from "./utils.mjs";
import { injectGlyphOutlineDrawing } from "./glyph.mjs";
import { injectSceneMotion } from "./motion-inject.mjs";
import { buildStylePrompt, getStyleInstructions } from "./style-prompt.mjs";
export { storyboardReferenceAssets, validateGeneratedTsx } from "./validate-tsx.mjs";
export { getStyleInstructions } from "./style-prompt.mjs";

// ---------------------------------------------------------------------------
// Audio tracking helpers
// ---------------------------------------------------------------------------

export function generatedTsxAudioTags(code) {
  return [...String(code || "").matchAll(/<\s*Audio\b[^>]*>/g)].map((match) => match[0]);
}

export function generatedTsxRendersLiteralAudioSource(code, source) {
  if (!source) return false;
  const audioTags = generatedTsxAudioTags(code);
  if (audioTags.length === 0) return false;
  const raw = String(source);
  const escaped = raw.replace(/\//g, "\\/");
  return audioTags.some((tag) => tag.includes(raw) || tag.includes(escaped));
}

export function codeContainsAudioSource(code, source) {
  if (!source) return false;
  const raw = String(source);
  const escaped = raw.replace(/\//g, "\\/");
  const codeText = String(code || "");
  return codeText.includes(raw) || codeText.includes(escaped);
}

export function generatedTsxRendersSegmentAudio(code, source) {
  if (generatedTsxRendersLiteralAudioSource(code, source)) return true;
  if (!codeContainsAudioSource(code, source)) return false;
  const codeText = String(code || "");
  // A segment is covered only when its URL is actually used by an Audio tag.
  // A Sequence containing `{null}` is intentionally emitted for generated
  // scene audio that was stripped before the fallback track is injected.
  return /(?:audioSegments|audio_segments|segments)\s*(?:\?\?)?[\s\S]{0,900}\.map\s*\([\s\S]{0,1200}<\s*Audio\b[\s\S]{0,260}(?:segment|seg|audio)\.(?:audioUrl|audio_url)/i.test(codeText);
}

export function stripGeneratedSceneAudio(code) {
  return String(code || "")
    .replaceAll("<Audio src={segment.audioUrl} />", "{null}")
    .replaceAll("<Audio src={segment.audioUrl} volume={1} />", "{null}")
    .replaceAll("return scene.audioUrl ? <Audio src={scene.audioUrl} /> : null;", "return null;")
    .replaceAll("return scene.audioUrl ? <Audio src={scene.audioUrl} volume={1} /> : null;", "return null;")
    .replaceAll("return scene.audioUrl ?  : null;", "return null;");
}

function ensureReferenceImagesVisible(code) {
  return String(code || "");
}

/** Keep the pen on drawable geometry. Text glyph ops are reveal data, not a
 * reliable physical pen path, so including them makes the pen scribble. */
export function ensureHandFollowsTextGlyphs(code) {
  const source = String(code || "");
  const declarations = [...source.matchAll(/\nconst pointsForOp = \(scene: SceneSpec, op: DrawOp\): Point\[\] => \{[\s\S]*?\};/g)];
  const normalized = declarations.length > 1
    ? source.replace(/\nconst pointsForOp = \(scene: SceneSpec, op: DrawOp\): Point\[\] => \{[\s\S]*?\};/g, "").replace(
      /\nconst HandPen = /,
      `${declarations[0][0]}\nconst HandPen = `,
    )
    : declarations.length === 1
      ? source
      : source.replace(
        /\nconst HandPen = /,
        "\nconst pointsForOp = (scene: SceneSpec, op: DrawOp): Point[] => { const stroke = scene.rasterReveal?.strokes?.find((item) => item.opId === op.id || item.colorOpId === op.id); if (!stroke?.d) return op.points; const values = [...stroke.d.matchAll(/-?\\d+(?:\\.\\d+)?/g)].map((match) => Number(match[0])); const points = []; for (let index = 0; index + 1 < values.length; index += 2) points.push({ x: values[index], y: values[index + 1] }); return points.length > 0 ? points : op.points; };\n\nconst HandPen = ",
      );
  return normalized
    .replace(/pointOnPolyline\(active\.points, progress\)/g, "pointOnPolyline(pointsForOp(scene, active), progress)")
    .replace(/pointOnPolyline\(previous\.points, 1\)/g, "pointOnPolyline(pointsForOp(scene, previous), 1)")
    .replace(/pointOnPolyline\(next\.points, 0\)/g, "pointOnPolyline(pointsForOp(scene, next), 0)")
    .replace(
      /orderedDrawOps\.filter\(\(op\) => op\.kind === ["']path["'] && frame >= op\.startFrame && frame <= op\.endFrame\)/g,
      "orderedDrawOps.filter((op) => op.kind === \"path\" && (scene.rasterReveal?.strokes?.length ? String(op.id ?? \"\").includes(\"_raster_\") : !scene.rasterReveal || scene.rasterReveal.renderMode !== \"direct\") && frame >= op.startFrame && frame <= op.endFrame)",
    )
    .replace(
      /orderedDrawOps\.filter\(\(op\) => op\.kind === ["']path["']\)/g,
      "orderedDrawOps.filter((op) => op.kind === \"path\" && (scene.rasterReveal?.strokes?.length ? String(op.id ?? \"\").includes(\"_raster_\") : !scene.rasterReveal || scene.rasterReveal.renderMode !== \"direct\"))",
    )
    .replace(
      /orderedDrawOps\.filter\(drawable\)/g,
      "orderedDrawOps.filter((op) => op.kind === \"path\" && (scene.rasterReveal?.strokes?.length ? String(op.id ?? \"\").includes(\"_raster_\") : !scene.rasterReveal || scene.rasterReveal.renderMode !== \"direct\"))",
    )
    .replace(
      "orderedDrawOps.filter((op) => op.kind === \"path\" && (!String(op.id ?? \"\").includes(\"_raster_\") || (Array.isArray(scene.rasterReveal?.strokes) && scene.rasterReveal.strokes.some((stroke) => stroke.opId === op.id || stroke.colorOpId === op.id))) && frame >= op.startFrame && frame <= op.endFrame)",
      "orderedDrawOps.filter((op) => op.kind === \"path\" && (scene.rasterReveal?.strokes?.length ? String(op.id ?? \"\").includes(\"_raster_\") : !scene.rasterReveal || scene.rasterReveal.renderMode !== \"direct\") && frame >= op.startFrame && frame <= op.endFrame)",
    )
    .replace(
      "orderedDrawOps.filter((op) => op.kind === \"path\" && (!String(op.id ?? \"\").includes(\"_raster_\") || (Array.isArray(scene.rasterReveal?.strokes) && scene.rasterReveal.strokes.some((stroke) => stroke.opId === op.id || stroke.colorOpId === op.id))))",
      "orderedDrawOps.filter((op) => op.kind === \"path\" && (scene.rasterReveal?.strokes?.length ? String(op.id ?? \"\").includes(\"_raster_\") : !scene.rasterReveal || scene.rasterReveal.renderMode !== \"direct\"))",
    )
    .replace(
      /<HandPen\s+tipX=\{pen\.x\}\s+tipY=\{pen\.y\}\s+visible=\{showHand && pen\.visible\}\s*\/>/g,
      "{showHand && pen.visible ? <HandPen tipX={pen.x} tipY={pen.y} visible /> : null}",
    )
    .replace(
      "{showHand && !scene.rasterReveal && pen.visible ? <HandPen tipX={pen.x} tipY={pen.y} visible /> : null}",
      "{showHand && pen.visible ? <HandPen tipX={pen.x} tipY={pen.y} visible /> : null}",
    )
    .replace(
      /\s*<image\s+href=\{staticFile\(colorAsset\)\}[\s\S]*?opacity=\{0\.28\}\s*\/>/g,
      "",
    );
}

export function generatedTsxRendersSceneAudio(code, source) {
  if (generatedTsxRendersLiteralAudioSource(code, source)) return true;
  if (!codeContainsAudioSource(code, source)) return false;
  return generatedTsxAudioTags(code).some((tag) => /\bscene\.(?:audioUrl|audio_url)\b/.test(tag));
}

export function generatedTsxRendersBackgroundSource(code, source) {
  if (!source) return false;
  const audioTags = generatedTsxAudioTags(code);
  if (audioTags.length === 0) return false;
  const raw = String(source);
  const escaped = raw.replace(/\//g, "\\/");
  if (audioTags.some((tag) => tag.includes(raw) || tag.includes(escaped))) return true;
  const codeText = String(code || "");
  if (!codeText.includes(raw) && !codeText.includes(escaped)) return false;
  return audioTags.some((tag) => /\b(?:BACKGROUND_MUSIC|backgroundMusic|musicUrl|music_url|music)\b/.test(tag));
}

export function storyboardSceneDurationFrames(scene, { includeBreathingRoom = false } = {}) {
  const timingFrames = Number(scene?.timingPlan?.durationFrames ?? scene?.timing_plan?.durationFrames ?? 0);
  const estimateFrames = Math.ceil(Number(scene?.duration_estimate ?? 0) * FPS);
  const segmentFrames = Array.isArray(scene?.audioSegments ?? scene?.audio_segments)
    ? Math.max(0, ...(scene?.audioSegments ?? scene?.audio_segments).map((seg) => Number(seg?.endFrame ?? 0)))
    : 0;
  const planned = Math.max(timingFrames, estimateFrames, segmentFrames);
  return includeBreathingRoom ? Math.max(FPS * 2, planned) : Math.max(0, planned);
}

export function collectMissingVoiceTracks(storyboard, generatedTsx) {
  const tracks = [];
  let sceneOffset = 0;
  for (const [sceneIndex, scene] of (storyboard?.scenes ?? []).entries()) {
    const sceneDuration = storyboardSceneDurationFrames(scene, { includeBreathingRoom: true });
    const segments = scene?.audioSegments ?? scene?.audio_segments ?? [];
    const segmentTracks = [];
    const sceneAudioUrl = scene?.audioUrl ?? scene?.audio_url;
    const sceneAudioAlreadyRendered = generatedTsxRendersSceneAudio(generatedTsx, sceneAudioUrl);
    if (Array.isArray(segments)) {
      for (const [segmentIndex, segment] of segments.entries()) {
        const src = segment?.audioUrl ?? segment?.audio_url;
        if (!src || generatedTsxRendersSegmentAudio(generatedTsx, src)) continue;
        if (sceneAudioAlreadyRendered && String(src) === String(sceneAudioUrl)) continue;
        const localFrom = Math.max(0, Math.round(Number(
          segment?.audioStartFrame ?? segment?.audio_start_frame ?? segment?.startFrame ?? segment?.start_frame ?? 0,
        )));
        const sequenceDuration = Math.round(Number(
          segment?.audioSequenceDuration ?? segment?.audio_sequence_duration ??
          segment?.duration ?? segment?.audioDurationFrames ?? segment?.audio_duration_frames ?? FPS * 3,
        ));
        segmentTracks.push({
          id: `scene_${sceneIndex}_segment_${segmentIndex}`,
          from: sceneOffset + localFrom,
          durationInFrames: Math.max(1, sequenceDuration),
          src: String(src),
        });
      }
    }
    if (segmentTracks.length === 0 && sceneAudioUrl && !sceneAudioAlreadyRendered && !generatedTsxRendersSegmentAudio(generatedTsx, sceneAudioUrl)) {
      tracks.push({ id: `scene_${sceneIndex}_voice`, from: sceneOffset, durationInFrames: sceneDuration, src: String(sceneAudioUrl) });
    } else {
      tracks.push(...segmentTracks);
    }
    sceneOffset += sceneDuration;
  }
  return tracks;
}

// ---------------------------------------------------------------------------
// Code generation (LLM call + retry)
// ---------------------------------------------------------------------------

export async function generateRemotionCode(storyboard, options = {}) {
  const subtitlesEnabled = Boolean(options.subtitlesEnabled);
  const codegenStoryboard = subtitlesEnabled
    ? storyboard
    : {
        ...storyboard,
        scenes: (storyboard.scenes ?? []).map((scene) => ({
          ...scene,
          subtitleText: null, subtitle_text: null,
          audioSegments: (scene.audioSegments ?? scene.audio_segments ?? []).map((seg) => ({ ...seg, subtitleText: null, subtitle_text: null })),
          audio_segments: (scene.audio_segments ?? scene.audioSegments ?? []).map((seg) => ({ ...seg, subtitleText: null, subtitle_text: null })),
        })),
      };
  const backgroundMusicUrl = options.backgroundMusicUrl || null;
  const backgroundMusicVolume = clampNumber(options.backgroundMusicVolume, 0, 0.5, 0.12);

  const videoStyle = canonicalVideoStyle(storyboard?.video_style ?? storyboard?.videoStyle ?? ACTIVE_VIDEO_STYLE);
  const penStyle = normalizePenStyle(storyboard?.pen_style ?? storyboard?.penStyle ?? ACTIVE_PEN_STYLE);
  const styleInstructions = getStyleInstructions(videoStyle, penStyle);

  const { validateGeneratedTsx } = await import("./validate-tsx.mjs");

  const MAX_RETRIES = 2;
  let lastError = null;

  for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
    const validationHint = lastError ? ` Previous generation failed validation: ${lastError.message}. Fix that exact issue.` : "";
    const retryHint = attempt > 0
      ? ` IMPORTANT: The previous generation included a validation failure.${validationHint} CRITICAL: Do NOT define any variable named paper, card, panel, surface, sheet, poster, slide, boardShadow, shadow, or wash in your code. Do NOT use washD, boxShadow, textShadow, drop-shadow, or gradients. Only use AbsoluteFill for the canvas background.`
      : "";

    const response = await postJson(`${PYTHON_API}/planner/remotion-code`, {
      storyboard: codegenStoryboard,
      fps: FPS, width: WIDTH, height: HEIGHT,
      subtitles_enabled: subtitlesEnabled,
      background_music_url: backgroundMusicUrl,
      background_music_volume: backgroundMusicVolume,
      style_prompt: buildStylePrompt(videoStyle, penStyle, styleInstructions, subtitlesEnabled, backgroundMusicUrl, backgroundMusicVolume, retryHint),
    });

    try {
      const validatedTsx = validateGeneratedTsx(response.tsx, codegenStoryboard);
      const glyphTsx = injectGlyphOutlineDrawing(validatedTsx);
      // Compress stroke schedules that spill into the scene tail so the
      // finished-artwork overlay can fade in and hold before the cut.
      const heldTsx = enforceSceneFinalHold(glyphTsx);
      // LLM 会把栅格揭示挤到场景开头,导致"整图先出、手再补画";重排节奏。
      const pacedTsx = enforceRasterRevealPacing(heldTsx);
      // LLM 生成物会剥掉 scene.motion 且不实现动画层,这里确定性注入。
      const motionTsx = injectSceneMotion(pacedTsx, codegenStoryboard, {
        fps: Number(response.fps ?? FPS),
        width: Number(response.width ?? WIDTH),
        height: Number(response.height ?? HEIGHT),
      });
      const plannedSceneFrames = computePlannedFrames(codegenStoryboard);

      return {
        tsx: validateGeneratedTsx(motionTsx, codegenStoryboard),
        durationInFrames: Math.max(
          FPS,
          Math.ceil(Number(codegenStoryboard?.total_duration_estimate ?? 0) * FPS),
          plannedSceneFrames,
          Number(response.duration_in_frames ?? FPS * 60),
        ),
        fps: Number(response.fps ?? FPS),
        width: Number(response.width ?? WIDTH),
        height: Number(response.height ?? HEIGHT),
      };
    } catch (err) {
      lastError = err;
      console.warn(`[codegen] Validation failed (attempt ${attempt + 1}/${MAX_RETRIES + 1}): ${err.message}`);
      if (attempt < MAX_RETRIES) { await sleep(1500); continue; }
    }
  }

  throw lastError ?? new Error("generateRemotionCode failed after retries");
}

function computePlannedFrames(storyboard) {
  if (!Array.isArray(storyboard?.scenes)) return 0;
  return storyboard.scenes.reduce((sum, scene) => {
    const timingFrames = Number(scene?.timingPlan?.durationFrames ?? scene?.timing_plan?.durationFrames ?? 0);
    const estimateFrames = Math.ceil(Number(scene?.duration_estimate ?? 0) * FPS);
    const segmentFrames = Array.isArray(scene?.audioSegments ?? scene?.audio_segments)
      ? Math.max(0, ...(scene?.audioSegments ?? scene?.audio_segments).map((seg) => Number(seg?.endFrame ?? 0)))
      : 0;
    return sum + Math.max(0, timingFrames, estimateFrames, segmentFrames);
  }, 0);
}

// ---------------------------------------------------------------------------
// Final-hold enforcement
// ---------------------------------------------------------------------------

// The generated RasterFinalOverlay fades the finished artwork in over ~8
// frames after the last stroke ends. Every scene must keep a protected tail
// (fade + hold) with no scheduled drawing, otherwise the cut lands mid-sketch.
// Longer scenes keep a proportional tail (up to ~3.7s) so viewers spend more
// time on the finished board and less watching half-written characters.
export const FINAL_HOLD_TAIL_FRAMES = 20;
export const FINAL_HOLD_TAIL_MAX_FRAMES = 90;
const FINAL_HOLD_TAIL_RATIO = 0.12;

function finalHoldTailFrames(duration, { tailFrames = FINAL_HOLD_TAIL_FRAMES } = {}) {
  return Math.max(tailFrames, Math.min(FINAL_HOLD_TAIL_MAX_FRAMES, Math.round(duration * FINAL_HOLD_TAIL_RATIO)));
}

function sceneDurationFramesInGeneratedScene(scene) {
  const segments = Array.isArray(scene?.audioSegments) ? scene.audioSegments : [];
  const fromSegments = segments.reduce(
    (max, seg) => Math.max(max, Number(seg?.endFrame ?? 0), Number(seg?.duration ?? 0)),
    0,
  );
  return Math.max(0, Number(scene?.duration ?? 0), Number(scene?.timingPlan?.durationFrames ?? 0), fromSegments);
}

function rescaleSceneDrawOps(scene, options = {}) {
  const duration = sceneDurationFramesInGeneratedScene(scene);
  const ops = Array.isArray(scene?.drawOps) ? scene.drawOps : [];
  if (!duration || !ops.length) return scene;
  const tailFrames = finalHoldTailFrames(duration, options);
  const maxEnd = ops.reduce((max, op) => Math.max(max, Number(op?.endFrame ?? 0) || 0), 0);
  if (maxEnd <= 0 || maxEnd <= duration - tailFrames) return scene;
  const scale = Math.max(0.05, (duration - tailFrames) / maxEnd);
  const drawOps = ops.map((op) => {
    const start = Number(op?.startFrame ?? 0) || 0;
    const end = Number(op?.endFrame ?? 0) || 0;
    const scaledStart = Math.round(start * scale);
    let scaledEnd = Math.round(end * scale);
    // Rounding two nearby frames to the same integer makes interpolate()
    // ranges like [135,135] crash the render; keep positive-length ops
    // strictly increasing.
    if (end > start) scaledEnd = Math.max(scaledEnd, scaledStart + 1);
    return { ...op, startFrame: scaledStart, endFrame: scaledEnd };
  });
  return { ...scene, drawOps };
}

function findSceneArrayLiterals(code) {
  const spans = [];
  const declaration = /(?:const|let|var)\s+[A-Za-z_$][\w$]*\s*=\s*(?=\[)/g;
  for (const match of code.matchAll(declaration)) {
    const open = code.indexOf("[", match.index + match[0].length - 1);
    let depth = 0;
    let inString = false;
    let escaped = false;
    for (let i = open; i < code.length; i += 1) {
      const char = code[i];
      if (inString) {
        if (escaped) escaped = false;
        else if (char === "\\") escaped = true;
        else if (char === '"') inString = false;
      } else if (char === '"') inString = true;
      else if (char === "[") depth += 1;
      else if (char === "]") {
        depth -= 1;
        if (depth === 0) {
          const literal = code.slice(open, i + 1);
          try {
            const parsed = JSON.parse(literal);
            if (
              Array.isArray(parsed) &&
              parsed.length > 0 &&
              parsed.every((item) => item && typeof item === "object" && Array.isArray(item.drawOps))
            ) {
              spans.push({ start: open, end: i + 1, parsed });
            }
          } catch {
            // Not a pure JSON array literal; leave it untouched.
          }
          break;
        }
      }
    }
  }
  return spans;
}

// 栅格揭示节奏:LLM 常把几百条 _raster_ ops 挤在场景开头几秒,画面表现为
// "整图先出现,手再在图上补标注"。这里按 strokes 的笔迹长度加权,把每条
// 笔迹的窗口重排到 [开头引导, 结尾保护] 区间,墨线先画、色层紧随,让手绘
// 揭示真正铺满整个场景。
export function enforceRasterRevealPacing(code, options = {}) {
  const spans = findSceneArrayLiterals(code);
  if (!spans.length) return code;
  let result = code;
  for (const span of [...spans].reverse()) {
    const paced = span.parsed.map((scene) => paceSceneRasterOps(scene, options));
    result = result.slice(0, span.start) + JSON.stringify(paced) + result.slice(span.end);
  }
  return result;
}

function paceSceneRasterOps(scene, options = {}) {
  const duration = sceneDurationFramesInGeneratedScene(scene);
  const ops = Array.isArray(scene?.drawOps) ? scene.drawOps : [];
  const strokes = Array.isArray(scene?.rasterReveal?.strokes) ? scene.rasterReveal.strokes : [];
  if (!duration || !ops.length || !strokes.length) return scene;
  if (ops.some(op => op.contractElementId)) return scene;
  const inkIds = new Set(strokes.map((s) => String(s?.opId ?? "")));
  if (!inkIds.size) return scene;
  const tailFrames = finalHoldTailFrames(duration, options);
  const lead = Math.min(8, Math.max(2, Math.round(duration * 0.02)));
  const spanEnd = Math.max(lead + 1, duration - tailFrames);
  const lengthFor = new Map();
  for (const s of strokes) {
    const len = Math.max(6, Number(s?.dashLength) || 6);
    lengthFor.set(String(s?.opId ?? ""), len);
    if (s?.colorOpId) lengthFor.set(String(s.colorOpId), len);
  }
  const totalWeight = strokes.reduce((sum, s) => sum + (lengthFor.get(String(s?.opId ?? "")) || 6), 0);
  const opWindow = new Map();
  let t = lead;
  for (const s of strokes) {
    const w = lengthFor.get(String(s?.opId ?? "")) || 6;
    // Subframe windows keep dense traces inside the scene and its final hold.
    const dur = ((spanEnd - lead) * w) / totalWeight;
    const end = Math.min(spanEnd, t + dur);
    const inkEnd = s?.colorOpId ? t + (end - t) * 0.72 : end;
    opWindow.set(String(s?.opId ?? ""), { start: t, end: inkEnd });
    if (s?.colorOpId) {
      opWindow.set(String(s.colorOpId), { start: inkEnd, end });
    }
    t = end;
  }
  const drawOps = ops.map((op) => {
    const key = String(op?.id ?? "");
    const win = opWindow.get(key);
    if (!win) return op;
    return { ...op, startFrame: win.start, endFrame: win.end };
  });
  return { ...scene, drawOps };
}

export function enforceSceneFinalHold(code, options = {}) {
  const spans = findSceneArrayLiterals(code);
  if (!spans.length) return code;
  let result = code;
  for (const span of [...spans].reverse()) {
    const rescaled = span.parsed.map((scene) => rescaleSceneDrawOps(scene, options));
    result = result.slice(0, span.start) + JSON.stringify(rescaled) + result.slice(span.end);
  }
  return result;
}

// ---------------------------------------------------------------------------
// Project writer
// ---------------------------------------------------------------------------

export function writeGeneratedProject(jobId, generated, storyboard, options = {}) {
  const projectDir = join(GENERATED_DIR, jobId);
  mkdirSync(projectDir, { recursive: true });

  const componentPath = join(projectDir, "GeneratedVideo.tsx");
  const entryPath = join(projectDir, "index.tsx");
  // Scene audio is stripped from the generated component below. Calculate
  // fallback tracks from that stripped source so every TTS segment remains
  // rendered by the wrapper entrypoint.
  const strippedTsx = ensureHandFollowsTextGlyphs(ensureReferenceImagesVisible(stripGeneratedSceneAudio(generated.tsx)));
  // The component is stripped of all generated scene audio, so derive the
  // wrapper tracks against an empty source and inject every storyboard segment.
  const extraVoiceTracks = collectMissingVoiceTracks(storyboard, "");
  const backgroundMusicUrl =
    options.backgroundMusicUrl && !generatedTsxRendersBackgroundSource(generated.tsx, options.backgroundMusicUrl)
      ? String(options.backgroundMusicUrl) : null;
  const backgroundMusicVolume = clampNumber(options.backgroundMusicVolume, 0, 0.5, 0.12);

  writeFileSync(componentPath, strippedTsx, "utf8");
  writeFileSync(
    entryPath,
    `import React from "react";
import { Audio, Composition, Sequence, registerRoot } from "remotion";
import { GeneratedVideo } from "./GeneratedVideo";

const EXTRA_VOICE_TRACKS: Array<{ id: string; from: number; durationInFrames: number; src: string }> = ${JSON.stringify(extraVoiceTracks)};
const BACKGROUND_MUSIC_URL: string | null = ${JSON.stringify(backgroundMusicUrl)};
const BACKGROUND_MUSIC_VOLUME = ${JSON.stringify(backgroundMusicVolume)};

const GeneratedVideoWithAudio: React.FC = () => {
  return (
    <>
      <GeneratedVideo />
      {EXTRA_VOICE_TRACKS.map((track) => (
        <Sequence key={track.id} from={track.from} durationInFrames={track.durationInFrames}>
          <Audio src={track.src} volume={1} />
        </Sequence>
      ))}
      {BACKGROUND_MUSIC_URL ? <Audio src={BACKGROUND_MUSIC_URL} volume={BACKGROUND_MUSIC_VOLUME} loop /> : null}
    </>
  );
};

const RemotionRoot: React.FC = () => {
  return (
    <Composition
      id="${COMPOSITION_ID}"
      component={GeneratedVideoWithAudio}
      durationInFrames={${generated.durationInFrames}}
      fps={${generated.fps}}
      width={${generated.width}}
      height={${generated.height}}
    />
  );
};

registerRoot(RemotionRoot);
`,
    "utf8",
  );

  return { projectDir, entryPath };
}
