import {test} from "node:test";
import assert from "node:assert/strict";
import {sceneBeatSpecs, cleanNarrationText, injectAudio} from "./tts.mjs";
import {distributeNarrationAcrossBeats, ttsCacheFilename} from "./tts-core.mjs";
import {mkdirSync, writeFileSync, unlinkSync} from "node:fs";
import {join} from "node:path";
import {randomUUID} from "node:crypto";
import {AUDIO_DIR} from "./config.mjs";

test("TTS includes the current lesson instead of stale visual beat summaries", () => {
  const narration = "球打不远，是只用手臂在抡。右脚蹬地，转腰，重心从右移到左，前臂收缩。击球点在身体右前方。";
  const beats = sceneBeatSpecs({narration, visual_beats: [
    {id: "problem", narration: "球打不远，是只用手臂在抡。", draw_intent: "准备姿势"},
    {id: "action", narration: "击球点在身体右前方。", draw_intent: "发力动作"},
  ]});
  assert.equal(beats.map(b => b.text).join(""), narration);
  assert.deepEqual(beats.map(b => b.drawIntent), ["准备姿势", "发力动作"]);
});

test("matching authored beats keep their exact boundaries", () => {
  const visualBeats = [{id: "a", narration: "先站好。再转腰。"}, {id: "b", narration: "最后收前臂。"}];
  const beats = sceneBeatSpecs({narration: visualBeats.map(b => b.narration).join(""), visualBeats});
  assert.deepEqual(beats.map(b => b.text), visualBeats.map(b => b.narration));
});

test("long scripts are not silently truncated to a character budget", () => {
  const narration = "膝盖微屈，重心放在前脚掌。".repeat(30) + "最后练习连续还原。";
  assert.equal(sceneBeatSpecs({narration})[0].text, cleanNarrationText(narration));
});

test("too many beats do not duplicate a short script", () => {
  const narration = "抛球至少16厘米。";
  assert.equal(sceneBeatSpecs({narration, visualBeats: [{id: "a"}, {id: "b"}, {id: "c"}]}).map(b => b.text).join(""), narration);
});

test("redistribution preserves sentence text and fills available beats", () => {
  const narration = "第一句比较长，要解释清楚怎样站好和握拍。第二句。第三句。";
  const chunks = distributeNarrationAcrossBeats(narration, 3);
  assert.equal(chunks.length, 3);
  assert.equal(chunks.join(""), narration);
});

test("beat-only legacy storyboards still have narration", () => {
  assert.equal(sceneBeatSpecs({visual_beats: [{narration: "蹬地转腰。"}, {narration: "回到准备姿势。"}]}).map(b => b.text).join(""), "蹬地转腰。回到准备姿势。");
});

test("malformed visual beats still use the complete script", () => {
  assert.equal(sceneBeatSpecs({narration: "先转腰。", visual_beats: "旧草稿"})[0].text, "先转腰。");
});

test("cached scene audio is reused only when it contains the current script", async (t) => {
  const narration = `先转腰，再收前臂。校验${randomUUID()}。`;
  const filename = ttsCacheFilename(narration, "xiaoxiao");
  const path = join(AUDIO_DIR, filename);
  const wav = Buffer.alloc(44 + 16000);
  wav.write("RIFF"); wav.writeUInt32LE(wav.length - 8, 4); wav.write("WAVEfmt ", 8);
  wav.writeUInt32LE(16, 16); wav.writeUInt16LE(1, 20); wav.writeUInt16LE(1, 22);
  wav.writeUInt32LE(8000, 24); wav.writeUInt32LE(16000, 28);
  wav.writeUInt16LE(2, 32); wav.writeUInt16LE(16, 34);
  wav.write("data", 36); wav.writeUInt32LE(16000, 40);
  mkdirSync(AUDIO_DIR, {recursive: true});
  writeFileSync(path, wav);
  t.after(() => unlinkSync(path));
  const oldSegment = {id: "old", narration: "先转腰。", audioUrl: `http://localhost:3002/audio/${filename}`, startFrame: 0, endFrame: 192};
  const storyboard = {scenes: [{id: "cache-check", narration, audioSegments: [oldSegment]}]};
  const repaired = await injectAudio(storyboard, "xiaoxiao");
  assert.equal(repaired.scenes[0].audioSegments.map(s => s.narration).join(""), narration);
  assert.notEqual(repaired.scenes[0].audioSegments[0].id, "old");

  oldSegment.narration = narration;
  const unchanged = await injectAudio(storyboard, "xiaoxiao");
  assert.equal(unchanged.scenes[0].audioSegments[0].id, "old");
});
