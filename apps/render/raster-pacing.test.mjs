import {test} from "node:test";
import assert from "node:assert/strict";
import {enforceRasterRevealPacing} from "./codegen.mjs";

test("dense raster ink and color finish before the final hold", () => {
  const strokes = Array.from({length: 500}, (_, i) => ({opId: `ink${i}`, colorOpId: `color${i}`, dashLength: i + 6}));
  const scene = {duration: 192, rasterReveal: {strokes}, drawOps: strokes.flatMap(s => [
    {id: s.opId, startFrame: 0, endFrame: 1}, {id: s.colorOpId, startFrame: 1, endFrame: 2},
  ])};
  const code = `const scenes = ${JSON.stringify([scene])};`;
  const result = JSON.parse(enforceRasterRevealPacing(code).match(/const scenes = (.*);/)[1])[0];
  for (const [i, stroke] of strokes.entries()) {
    const ink = result.drawOps[i * 2], color = result.drawOps[i * 2 + 1];
    assert(ink.endFrame > ink.startFrame, stroke.opId);
    assert(color.endFrame > color.startFrame, stroke.colorOpId);
    assert.equal(ink.endFrame, color.startFrame);
    assert(color.endFrame <= 169, "completed artwork must hold for 23 frames");
  }
});

test("authored object timing is not replaced by global raster pacing", () => {
  const scene = {duration: 240, rasterReveal: {strokes: [{opId: "phone", dashLength: 10}]},
    drawOps: [{id: "phone", contractElementId: "phone", startFrame: 150, endFrame: 200}]};
  const code = `const scenes = ${JSON.stringify([scene])};`;
  assert.equal(enforceRasterRevealPacing(code), code);
});
