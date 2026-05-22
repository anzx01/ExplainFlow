/**
 * tts.mjs — TTS 合成、场景节拍规划、音频注入
 * 依赖: config.mjs, utils.mjs, tts-core.mjs
 */
import { existsSync, mkdirSync, statSync, unlinkSync, writeFileSync } from "fs";
import { basename, join } from "path";
import { createHash } from "crypto";
import {
  AUDIO_DIR,
  BEAT_AUDIO_LEAD_FRAMES,
  FPS,
  PORT,
  SCENE_PREROLL_FRAMES,
} from "./config.mjs";
import { safeAssetSegment } from "./utils.mjs";
import {
  cleanNarrationText,
  distributeNarrationAcrossBeats,
  estimateNarrationSeconds,
  normalizeVoiceKey,
  probeAudioDurationSeconds,
  requestTtsAudio,
  splitNarrationSentences,
  ttsInFlight,
  trimNarrationToChars,
  ttsCacheFilename,
} from "./tts-core.mjs";

// Re-export everything from tts-core so callers can import from one place
export {
  acquireTtsSlot, releaseTtsSlot, withTtsSlot,
  normalizeTextForTts, cleanNarrationText, trimNarrationToChars,
  splitNarrationSentences, distributeNarrationAcrossBeats, normalizeVoiceKey,
  requestTtsAudio, ttsCacheFilename, estimateNarrationSeconds,
  probeAudioDurationSeconds, probePlayableAudio, probeMediaInfo, normalizeMusicTrackForRemotion,
} from "./tts-core.mjs";

// ---------------------------------------------------------------------------
// TTS 合成（场景级，带缓存与去重）
// ---------------------------------------------------------------------------

function ensureAudioDir() {
  mkdirSync(AUDIO_DIR, { recursive: true });
}

export async function synthesizeScene(sceneId, text, voice) {
  const narration = String(text ?? "").trim();
  if (!narration) return null;
  ensureAudioDir();
  const filename = ttsCacheFilename(narration, voice);
  const outPath = join(AUDIO_DIR, filename);
  const audioUrl = `http://localhost:${PORT}/audio/${filename}`;
  if (existsSync(outPath) && statSync(outPath).size > 0) {
    console.log(`[tts] cache hit: ${sceneId}`);
    const durationSeconds = await probeAudioDurationSeconds(outPath);
    if (!durationSeconds) {
      try { unlinkSync(outPath); } catch {}
      throw new Error(`Cached TTS audio is empty or unreadable for ${sceneId}`);
    }
    return { audioUrl, filePath: outPath, durationSeconds, text: narration };
  }
  if (ttsInFlight.has(filename)) {
    await ttsInFlight.get(filename);
    const durationSeconds = await probeAudioDurationSeconds(outPath);
    if (!durationSeconds) throw new Error(`Shared TTS audio is empty or unreadable for ${sceneId}`);
    return { audioUrl, filePath: outPath, durationSeconds, text: narration };
  }

  const pending = requestTtsAudio(narration, voice, sceneId).then((audio) => { writeFileSync(outPath, audio); });
  ttsInFlight.set(filename, pending);
  try {
    await pending;
    const durationSeconds = await probeAudioDurationSeconds(outPath);
    if (!durationSeconds || !existsSync(outPath) || statSync(outPath).size <= 0) {
      throw new Error(`TTS audio is empty or unreadable for ${sceneId}`);
    }
    return { audioUrl, filePath: outPath, durationSeconds, text: narration };
  } finally {
    ttsInFlight.delete(filename);
  }
}

// ---------------------------------------------------------------------------
// 场景节拍规划
// ---------------------------------------------------------------------------

export function sceneBeatSpecs(scene) {
  const visualBeats = Array.isArray(scene.visual_beats) ? scene.visual_beats : [];
  const beats = visualBeats.length > 0
    ? visualBeats
    : [{ id: "beat_0", draw_intent: scene.image_description || scene.title || "", narration: scene.narration || scene.title || "", required_labels: [], duration_estimate: scene.duration_estimate || 8 }];
  const sceneBudget = Math.max(5, Number(scene?.duration_estimate ?? 0) || 0);
  const sceneNarration = cleanNarrationText(scene.narration || scene.title || "");
  const distributedSceneNarration = distributeNarrationAcrossBeats(sceneNarration, beats.length);
  return beats.map((beat, index) => {
    const beatNarration = cleanNarrationText(beat?.narration || "");
    const rawText = cleanNarrationText(beatNarration || distributedSceneNarration[index] || sceneNarration || scene.title || beat?.draw_intent || "");
    const beatEstimate = Math.max(1, estimateNarrationSeconds(rawText) + 0.8, Number(beat?.duration_estimate ?? beat?.duration ?? sceneBudget / Math.max(1, beats.length)) || 6);
    const maxChars = Math.max(120, Math.min(260, Math.floor(Math.max(beatEstimate, 8) * 9.5)));
    const text = trimNarrationToChars(rawText, maxChars);
    return { id: String(beat?.id || `beat_${index}`), index, text, drawIntent: String(beat?.draw_intent || beat?.drawIntent || scene.title || "").trim(), durationEstimate: beatEstimate };
  });
}

// ---------------------------------------------------------------------------
// base64 / data URL
// ---------------------------------------------------------------------------

export function normalizeBase64DataUrl(value, expectedPrefix) {
  const text = String(value ?? "").trim();
  if (!text.startsWith(expectedPrefix)) return null;
  const comma = text.indexOf(",");
  if (comma < 0) return null;
  if (!text.slice(0, comma).toLowerCase().includes(";base64")) return null;
  return text.slice(comma + 1);
}

function audioFilenameFromUrl(url) {
  try {
    const parsed = new URL(String(url));
    if (parsed.pathname.startsWith("/audio/")) return decodeURIComponent(basename(parsed.pathname));
  } catch {}
  return null;
}

export async function persistSceneAudioDataUrl(scene, sceneIndex) {
  const audioUrl = String(scene?.audioUrl ?? scene?.audio_url ?? "").trim();
  const base64 = normalizeBase64DataUrl(audioUrl, "data:audio/");
  if (!base64) return null;
  ensureAudioDir();
  const sceneId = safeAssetSegment(scene?.id || `scene_${sceneIndex}`, "scene");
  const hash = createHash("sha1").update(base64).digest("hex").slice(0, 16);
  const outPath = join(AUDIO_DIR, `scene_${sceneId}_${hash}.mp3`);
  if (!existsSync(outPath) || statSync(outPath).size <= 0) writeFileSync(outPath, Buffer.from(base64, "base64"));
  const durationSeconds = await probeAudioDurationSeconds(outPath);
  if (!durationSeconds) {
    try { unlinkSync(outPath); } catch {}
    throw new Error(`User supplied scene audio is empty or unreadable for ${scene?.id || `scene_${sceneIndex}`}`);
  }
  return { audioUrl: `http://localhost:${PORT}/audio/${basename(outPath)}`, filePath: outPath, durationSeconds, text: cleanNarrationText(scene?.narration || scene?.title || "") };
}

export async function assertStoryboardAudioComplete(storyboard) {
  const missing = [];
  for (const [sceneIndex, scene] of (storyboard?.scenes ?? []).entries()) {
    const sceneId = scene?.id || `scene_${sceneIndex}`;
    const segments = scene?.audioSegments ?? scene?.audio_segments ?? [];
    if (!Array.isArray(segments) || segments.length === 0) { missing.push(`${sceneId}: no audioSegments`); continue; }
    for (const [segmentIndex, segment] of segments.entries()) {
      const src = segment?.audioUrl ?? segment?.audio_url;
      if (!src) { missing.push(`${sceneId}/segment_${segmentIndex}: missing audioUrl`); continue; }
      const filename = audioFilenameFromUrl(src);
      const localPath = filename ? join(AUDIO_DIR, filename) : null;
      if (!localPath || !existsSync(localPath) || statSync(localPath).size <= 0) {
        missing.push(`${sceneId}/segment_${segmentIndex}: audio file missing`); continue;
      }
      const duration = await probeAudioDurationSeconds(localPath);
      if (!duration) missing.push(`${sceneId}/segment_${segmentIndex}: duration is 0`);
    }
  }
  if (missing.length > 0) throw new Error(`缺少音频，已停止渲染：${missing.slice(0, 8).join("; ")}`);
}

// ---------------------------------------------------------------------------
// injectAudio
// ---------------------------------------------------------------------------

export async function injectAudio(storyboard, voice) {
  const voiceKey = normalizeVoiceKey(voice ?? "xiaoxiao");
  const sceneResults = await Promise.allSettled(
    storyboard.scenes.map(async (scene, sceneIndex) => {
      const suppliedAudio = await persistSceneAudioDataUrl(scene, sceneIndex);
      if (suppliedAudio) {
        const audioDurationFrames = Math.max(1, Math.ceil(suppliedAudio.durationSeconds * FPS));
        const durationFrames = Math.max(audioDurationFrames + Math.round(FPS * 0.65), FPS * 5);
        const segment = {
          id: "scene_audio", index: 0, startFrame: 0, endFrame: durationFrames, duration: durationFrames,
          audioStartFrame: 0, audioEndFrame: audioDurationFrames, audioSequenceDuration: durationFrames,
          audioUrl: suppliedAudio.audioUrl, audioDurationFrames,
          drawBudgetFrames: Math.max(1, durationFrames - 4),
          subtitleText: suppliedAudio.text, narration: suppliedAudio.text,
          drawIntent: scene.image_description || scene.title || "",
        };
        return { ...scene, audioUrl: suppliedAudio.audioUrl, audioSegments: [segment], timingPlan: { fps: FPS, durationFrames, transitionFrames: 0, allowOverTarget: true, segments: [segment] }, duration_estimate: durationFrames / FPS };
      }

      const beatSpecs = sceneBeatSpecs(scene);
      const segmentResults = await Promise.allSettled(
        beatSpecs.map((beat) => synthesizeScene(`${scene.id || `scene_${sceneIndex}`}_${beat.id}`, beat.text, voiceKey)),
      );

      let cursor = SCENE_PREROLL_FRAMES;
      const audioSegments = segmentResults.map((result, index) => {
        const beat = beatSpecs[index];
        const audio = result.status === "fulfilled" ? result.value : null;
        if (!audio?.audioUrl || !audio?.filePath || !audio?.durationSeconds) {
          const reason = result.status === "rejected" ? result.reason?.message : "empty audio";
          throw new Error(`缺少音频片段：${scene.id || `scene_${sceneIndex}`}/${beat.id} (${reason || "TTS failed"})`);
        }
        const actualAudioDurationSeconds = audio?.durationSeconds ?? estimateNarrationSeconds(beat.text);
        const audioDurationFrames = Math.max(1, Math.ceil(actualAudioDurationSeconds * FPS));
        const estimateFrames = Math.ceil(beat.durationEstimate * FPS);
        const audioStartFrame = cursor;
        const minimumFrames = Math.max(FPS * 3, estimateFrames);
        const durationFrames = Math.max(minimumFrames, audioDurationFrames + 14);
        const startFrame = cursor;
        const endFrame = startFrame + durationFrames;
        cursor = endFrame;
        return {
          id: beat.id, index, startFrame, endFrame, duration: durationFrames,
          audioStartFrame, audioEndFrame: audioStartFrame + audioDurationFrames,
          audioSequenceDuration: audioDurationFrames, audioUrl: audio?.audioUrl ?? null,
          audioDurationFrames, drawBudgetFrames: Math.max(1, durationFrames - 4),
          subtitleText: beat.text, narration: beat.text, drawIntent: beat.drawIntent,
        };
      });

      const lastAudioEndFrame = audioSegments.reduce((maxFrame, seg) => Math.max(maxFrame, Number(seg.audioEndFrame ?? seg.endFrame ?? 0) || 0), 0);
      const durationFrames = Math.max(cursor, lastAudioEndFrame + Math.round(FPS * 0.65), FPS * 8);
      const fallbackAudio = audioSegments.find((seg) => seg.audioUrl)?.audioUrl ?? null;
      if (!fallbackAudio) throw new Error(`缺少场景音频：${scene.id || `scene_${sceneIndex}`}`);
      const failedSegments = segmentResults.filter((r) => r.status === "rejected");
      if (failedSegments.length > 0) console.warn(`[tts] ${failedSegments.length} beat segment(s) failed for ${scene.id}:`, failedSegments.map((r) => r.reason?.message));
      return { ...scene, audioUrl: fallbackAudio, audioSegments, timingPlan: { fps: FPS, durationFrames, transitionFrames: 0, allowOverTarget: true, segments: audioSegments }, duration_estimate: durationFrames / FPS };
    }),
  );

  const scenes = storyboard.scenes.map((scene, index) => {
    const result = sceneResults[index];
    return result.status === "fulfilled" ? result.value : scene;
  });

  const failed = sceneResults.filter((r) => r.status === "rejected");
  if (failed.length > 0) {
    console.warn(`[tts] ${failed.length} scene(s) failed:`, failed.map((r) => r.reason?.message));
    throw new Error(`缺少音频，已停止渲染：${failed.map((r) => r.reason?.message).join("; ")}`);
  }

  const totalFrames = scenes.reduce((sum, scene) => sum + Math.max(FPS * 8, Number(scene.timingPlan?.durationFrames ?? Math.round((scene.duration_estimate || 0) * FPS))), 0);
  return { ...storyboard, scenes, total_duration_estimate: totalFrames / FPS, timingPlan: { fps: FPS, durationFrames: totalFrames, allowOverTarget: true } };
}
