import { execFile } from "child_process";
import { promisify } from "util";
import { createHash } from "crypto";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "fs";
import { join } from "path";
import { fileURLToPath } from "url";
import { AUDIO_DIR, FPS, PORT, FFMPEG_BINARY } from "./config.mjs";
import { cleanNarrationText, probeAudioDurationSeconds } from "./tts-core.mjs";

const run = promisify(execFile);
export function narrationPhrases(text) {
  return (cleanNarrationText(text).match(/[^，。！？；]+[，。！？；]?/g) ?? []).map(s => s.trim()).filter(Boolean);
}

export function speechBookmarkTimes(parts, marks, audioDurationSeconds) {
  const byId = new Map(marks.map(mark => [mark.id, mark.ms]));
  const ordered = [...parts.map(part => byId.get(part.id)), byId.get("end")];
  if (!ordered.length || ordered.some((ms, index) => !Number.isFinite(ms) || ms < 0 || (index > 0 && ms <= ordered[index - 1]))) {
    throw new Error("Speech bookmarks missing or out of order; refusing unaligned narration");
  }
  // SAPI's implicit WAV format can report bookmark times on a different
  // sample clock. Reject that audio before cutting it or displaying captions.
  if (!(audioDurationSeconds > 0) || Math.abs(byId.get("end") - audioDurationSeconds * 1000) > 300) {
    throw new Error(`Speech bookmark/audio duration mismatch: ${byId.get("end")}ms vs ${audioDurationSeconds * 1000}ms`);
  }
  byId.set("end", audioDurationSeconds * 1000);
  return byId;
}

export async function continuousNarration(storyboard) {
  if (!storyboard.scenes.length || storyboard.scenes.some(s => !narrationPhrases(s.narration).length)) throw new Error("Each scene requires spoken text for continuous narration");
  mkdirSync(AUDIO_DIR, { recursive: true });
  const parts = storyboard.scenes.flatMap((scene, i) => narrationPhrases(scene.narration).map((text, j) => ({ id: `s${i}p${j}`, text, scene: i })));
  if (!parts.length) throw new Error("Continuous narration requires spoken text");
  const key = createHash("sha256").update(JSON.stringify(parts) + ":sapi-full-v3-normal-rate-lufs16").digest("hex").slice(0, 20);
  const base = join(AUDIO_DIR, `continuous_${key}`);
  const wav = `${base}.wav`, timing = `${base}.json`, input = `${base}-text.json`;
  if (!existsSync(wav) || !existsSync(timing)) {
    writeFileSync(input, JSON.stringify(parts));
    const raw = `${base}-raw.wav`;
    await run("powershell.exe", ["-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", fileURLToPath(new URL("./continuous-narration.ps1", import.meta.url)), input, raw, timing], { windowsHide: true, timeout: 180000 });
    // Normalize the full recording before cutting so scene volumes stay consistent.
    await run(FFMPEG_BINARY, ["-y", "-hide_banner", "-loglevel", "error", "-i", raw, "-af", "loudnorm=I=-16:TP=-1.5:LRA=11", "-ar", "16000", "-ac", "1", wav], { windowsHide: true, timeout: 30000 });
  }
  const marks = JSON.parse(readFileSync(timing, "utf8"));
  const byId = speechBookmarkTimes(parts, marks, await probeAudioDurationSeconds(wav));
  let total = 0;
  const scenes = [];
  for (const [i, scene] of storyboard.scenes.entries()) {
    const local = parts.filter(p => p.scene === i);
    const start = byId.get(local[0].id);
    const next = parts.find(p => p.scene === i + 1);
    const end = byId.get(next?.id ?? "end");
    const frames = Math.max(1, Math.round((end - start) * FPS / 1000));
    const filename = `continuous_${key}_scene_${i}_${frames}f.wav`;
    const file = join(AUDIO_DIR, filename);
    if (!existsSync(file)) await run(FFMPEG_BINARY, ["-y", "-hide_banner", "-loglevel", "error", "-ss", String(start / 1000), "-i", wav, "-t", String(frames / FPS), "-af", `apad=whole_dur=${frames / FPS}`, file], { windowsHide: true, timeout: 30000 });
    const url = `http://localhost:${PORT}/audio/${filename}`;
    const cues = local.map((p, j) => ({ text: p.text, startFrame: Math.round((byId.get(p.id) - start) * FPS / 1000), endFrame: Math.min(frames, Math.round(((j + 1 < local.length ? byId.get(local[j + 1].id) : end) - start) * FPS / 1000)) }));
    const segment = { id: "continuous", startFrame: 0, endFrame: frames, audioStartFrame: 0, audioEndFrame: frames, audioDurationFrames: frames, audioSequenceDuration: frames, duration: frames, audioUrl: url, subtitleText: cleanNarrationText(scene.narration), drawBudgetFrames: Math.min(frames, FPS * 9) };
    scenes.push({ ...scene, narration: cleanNarrationText(scene.narration), audioUrl: url, audioSegments: [segment], subtitleCues: cues, duration_estimate: frames / FPS, timingPlan: { fps: FPS, durationFrames: frames, transitionFrames: 0, segments: [segment] } });
    total += frames;
  }
  return { ...storyboard, scenes, total_duration_estimate: total / FPS, timingPlan: { fps: FPS, durationFrames: total } };
}
