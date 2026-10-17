import { test } from "node:test";
import assert from "node:assert/strict";
import {
  enforceSceneFinalHold,
  FINAL_HOLD_TAIL_FRAMES,
  FINAL_HOLD_TAIL_MAX_FRAMES,
} from "./codegen.mjs";

function sceneWithDuration(durationFrames, lastOpEnd) {
  return {
    title: "场景",
    audioSegments: [{ duration: durationFrames, endFrame: durationFrames, startFrame: 0 }],
    drawOps: [
      { id: "a", startFrame: 0, endFrame: Math.round(lastOpEnd / 2) },
      { id: "b", startFrame: Math.round(lastOpEnd / 2), endFrame: lastOpEnd },
    ],
  };
}

function expectedTail(durationFrames) {
  return Math.max(FINAL_HOLD_TAIL_FRAMES, Math.min(FINAL_HOLD_TAIL_MAX_FRAMES, Math.round(durationFrames * 0.12)));
}

test("compresses drawOps that spill into the protected scene tail", () => {
  const code = `const HAND = 1;\nconst scenes = ${JSON.stringify([sceneWithDuration(415, 414)])};\nexport const X = 2;`;
  const result = enforceSceneFinalHold(code);
  const parsed = JSON.parse(result.slice(result.indexOf("["), result.lastIndexOf("]") + 1));
  const maxEnd = Math.max(...parsed[0].drawOps.map((op) => op.endFrame));
  assert.ok(maxEnd <= 415 - expectedTail(415), `maxEnd ${maxEnd} must keep a ${expectedTail(415)}f tail`);
  assert.ok(parsed[0].audioSegments[0].duration === 415, "audio segment timing must stay untouched");
  assert.ok(code.includes("const HAND = 1;") && result.includes("const HAND = 1;"), "surrounding code preserved");
});

test("longer scenes keep a proportional tail", () => {
  const scenes = [sceneWithDuration(567, 566)];
  const result = enforceSceneFinalHold(`const scenes = ${JSON.stringify(scenes)};`);
  const parsed = JSON.parse(result.slice(result.indexOf("["), result.lastIndexOf("]") + 1));
  const maxEnd = Math.max(...parsed[0].drawOps.map((op) => op.endFrame));
  const tail = expectedTail(567);
  assert.equal(tail, 68); // 12% of a 567f scene, under the 90f cap.
  assert.ok(maxEnd <= 567 - tail, `maxEnd ${maxEnd}`);
});

test("leaves already-compliant schedules unchanged", () => {
  const scenes = [sceneWithDuration(400, 300)];
  const code = `const scenes = ${JSON.stringify(scenes)};`;
  assert.equal(enforceSceneFinalHold(code), code);
});

test("handles several scenes with different durations", () => {
  const scenes = [sceneWithDuration(350, 349), sceneWithDuration(404, 403), sceneWithDuration(415, 200)];
  const result = enforceSceneFinalHold(`const scenes = ${JSON.stringify(scenes)};`);
  const parsed = JSON.parse(result.slice(result.indexOf("["), result.lastIndexOf("]") + 1));
  const limits = [350, 404, 415];
  parsed.forEach((scene, index) => {
    const maxEnd = Math.max(...scene.drawOps.map((op) => op.endFrame));
    assert.ok(maxEnd <= limits[index] - expectedTail(limits[index]), `scene ${index} maxEnd ${maxEnd}`);
  });
});

test("ignores arrays that are not pure JSON scene data", () => {
  const code = 'const whatever = [{ id: "x", start: 3 }];\nconst note = "not json ] here";';
  assert.equal(enforceSceneFinalHold(code), code);
});

test("ignores scene arrays without drawOps", () => {
  const code = `const scenes = ${JSON.stringify([{ title: "t", audioSegments: [{ duration: 100, endFrame: 100 }] }])};`;
  assert.equal(enforceSceneFinalHold(code), code);
});

test("keeps positive-length ops strictly increasing after rounding", () => {
  const scene = {
    title: "t",
    audioSegments: [{ duration: 400, endFrame: 400, startFrame: 0 }],
    drawOps: Array.from({ length: 80 }, (_, i) => ({
      id: `op${i}`,
      startFrame: i * 5,
      endFrame: i * 5 + 2,
    })),
  };
  const result = enforceSceneFinalHold(`const scenes = ${JSON.stringify([scene])};`);
  const parsed = JSON.parse(result.slice(result.indexOf("["), result.lastIndexOf("]") + 1));
  for (const op of parsed[0].drawOps) {
    assert.ok(op.endFrame > op.startFrame, `op ${op.id} collapsed to [${op.startFrame},${op.endFrame}]`);
    assert.ok(op.endFrame <= 400 - expectedTail(400) + 1, `op ${op.id} endFrame ${op.endFrame} too late`);
  }
});
