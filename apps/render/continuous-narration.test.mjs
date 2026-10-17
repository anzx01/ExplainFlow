import { test } from "node:test";
import assert from "node:assert/strict";
import { narrationPhrases, speechBookmarkTimes, continuousNarration } from "./continuous-narration.mjs";
import { probeAudioDurationSeconds } from "./tts-core.mjs";
import { AUDIO_DIR, FPS } from "./config.mjs";
import { join } from "node:path";
import { readFileSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { FFMPEG_BINARY } from "./config.mjs";

test("narration uses normal speech speed rather than an accelerated prosody", () => {
  const script = readFileSync(new URL("./continuous-narration.ps1", import.meta.url), "utf8");
  assert(script.includes('prosody rate="medium"'));
  assert(!script.includes('rate="+10%"'));
});

test("keywords are visual metadata, never appended spoken labels", () => {
  assert.deepEqual(narrationPhrases("先保护睡眠。关键词要点是：睡眠、注意力。再设定时间。"), ["先保护睡眠。", "再设定时间。"]);
});

test("phrase boundaries preserve spoken punctuation", () => {
  assert.deepEqual(narrationPhrases("先停下来，再想一想。"), ["先停下来，", "再想一想。"]);
});

test("spoken visual directions survive cleaning and remain usable as timing anchors",()=>{
  assert.deepEqual(narrationPhrases("先看左边，汤汁还是稀的。再看右边，浓汁裹住肉。"),
    ["先看左边，","汤汁还是稀的。","再看右边，","浓汁裹住肉。"]);
});

test("rejects the 197-second bookmark clock on the actual 143-second recording", () => {
  const parts = [{id: "s0p0"}];
  assert.throws(() => speechBookmarkTimes(parts, [{id: "s0p0", ms: 0}, {id: "end", ms: 197441.6875}], 143.45034), /duration mismatch/);
  const aligned = speechBookmarkTimes(parts, [{id: "s0p0", ms: 0}, {id: "end", ms: 7732.125}], 7.914125);
  assert.equal(aligned.get("end"), 7914.125);
  assert.throws(() => speechBookmarkTimes(parts, [{id: "end", ms: 1000}], 1), /missing/);
});

test("actual Windows speech bookmarks match the WAV clock", {skip: process.platform !== "win32"}, async () => {
  const result = await continuousNarration({scenes: [{id: "alignment-check", narration: "手机。你是否只想刷五分钟，却刷了半小时？再看右边的大脑。"}]});
  const scene = result.scenes[0];
  const filename = new URL(scene.audioUrl).pathname.split("/").at(-1);
  const seconds = await probeAudioDurationSeconds(join(AUDIO_DIR, filename));
  const originalSeconds = await probeAudioDurationSeconds(join(AUDIO_DIR, filename.replace(/_scene_0_\d+f\.wav$/, ".wav")));
  assert(Math.abs(seconds - scene.timingPlan.durationFrames / FPS) <= 1 / FPS);
  assert(Math.abs(originalSeconds - seconds) <= 1 / FPS);
  assert.equal(scene.subtitleCues.map(cue => cue.text).join(""), scene.narration);
  assert.equal(scene.subtitleCues.at(-1).endFrame, scene.timingPlan.durationFrames);
  const volume = spawnSync(FFMPEG_BINARY, ["-hide_banner", "-i", join(AUDIO_DIR, filename), "-af", "volumedetect", "-f", "null", "-"], {encoding: "utf8", windowsHide: true});
  assert.equal(volume.status, 0, volume.stderr);
  const mean = Number(volume.stderr.match(/mean_volume: ([\d.-]+) dB/)?.[1]);
  const peak = Number(volume.stderr.match(/max_volume: ([\d.-]+) dB/)?.[1]);
  assert(mean > -24 && mean < -10, `Unexpected narration loudness: ${mean} dB`);
  assert(peak > -5 && peak < 0, `Silent or clipped narration: ${peak} dB`);
});
