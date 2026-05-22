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
  return (
    /(?:audioSegments|audio_segments|segments)\s*(?:\?\?)?[\s\S]{0,900}\.map\s*\([\s\S]{0,1200}<\s*Audio\b[\s\S]{0,260}(?:segment|seg|audio)\.(?:audioUrl|audio_url)/i.test(codeText) ||
    /(?:segment|seg|audio)\.(?:audioUrl|audio_url)[\s\S]{0,260}<\s*\/\s*Sequence\s*>/i.test(codeText)
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

export function storyboardSceneDurationFrames(scene) {
  const timingFrames = Number(scene?.timingPlan?.durationFrames ?? scene?.timing_plan?.durationFrames ?? 0);
  const estimateFrames = Math.ceil(Number(scene?.duration_estimate ?? 0) * FPS);
  const segmentFrames = Array.isArray(scene?.audioSegments ?? scene?.audio_segments)
    ? Math.max(0, ...(scene?.audioSegments ?? scene?.audio_segments).map((seg) => Number(seg?.endFrame ?? 0)))
    : 0;
  return Math.max(FPS * 8, timingFrames, estimateFrames, segmentFrames);
}

export function collectMissingVoiceTracks(storyboard, generatedTsx) {
  const tracks = [];
  let sceneOffset = 0;
  for (const [sceneIndex, scene] of (storyboard?.scenes ?? []).entries()) {
    const sceneDuration = storyboardSceneDurationFrames(scene);
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
      const plannedSceneFrames = computePlannedFrames(codegenStoryboard);

      return {
        tsx: validateGeneratedTsx(glyphTsx, codegenStoryboard),
        durationInFrames: Math.max(
          FPS * 10,
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
// Project writer
// ---------------------------------------------------------------------------

export function writeGeneratedProject(jobId, generated, storyboard, options = {}) {
  const projectDir = join(GENERATED_DIR, jobId);
  mkdirSync(projectDir, { recursive: true });

  const componentPath = join(projectDir, "GeneratedVideo.tsx");
  const entryPath = join(projectDir, "index.tsx");
  const extraVoiceTracks = collectMissingVoiceTracks(storyboard, generated.tsx);
  const backgroundMusicUrl =
    options.backgroundMusicUrl && !generatedTsxRendersBackgroundSource(generated.tsx, options.backgroundMusicUrl)
      ? String(options.backgroundMusicUrl) : null;
  const backgroundMusicVolume = clampNumber(options.backgroundMusicVolume, 0, 0.5, 0.12);

  writeFileSync(componentPath, generated.tsx, "utf8");
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
          <Audio src={track.src} />
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
