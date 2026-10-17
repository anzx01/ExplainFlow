import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "fs";
import { ensureHandFollowsTextGlyphs } from "./codegen.mjs";
import { validateGeneratedTsx } from "./validate-tsx.mjs";

test("the shared fallback template passes the render-side validator at calibrated hand size", () => {
  const source=readFileSync(new URL("../../services/api/src/planner/fallback/_tsx_template_string.py",import.meta.url),"utf8");
  const scene={drawOps:Array.from({length:13},(_,i)=>({kind:i<5?"text":"path",startFrame:0,endFrame:24,points:[{x:0,y:0},{x:20,y:20}]}))};
  const code=source.slice(source.indexOf("import React"),source.lastIndexOf("'''"))
    .replace("__SCENES_JSON__",JSON.stringify([scene]));
  assert.doesNotThrow(()=>validateGeneratedTsx(code));
  assert.throws(()=>validateGeneratedTsx(code.replace("const HAND_WIDTH = 180;","const HAND_WIDTH = 160;")),/HAND_WIDTH >= 180/);
});

test("code generation preserves raster pen and does not inject full artwork", () => {
  const source = readFileSync(new URL("../../services/api/src/planner/fallback/_tsx_template_string.py", import.meta.url), "utf8");
  const result = ensureHandFollowsTextGlyphs(source);
  assert.match(result, /showHand && pen.visible/);
  assert.doesNotMatch(result, /showHand && !scene.rasterReveal/);
  assert.doesNotMatch(result, /opacity=\{0\.28\}/);
  assert.equal([...result.matchAll(/const pointsForOp =/g)].length, 1);
});

test("teaching layout has safe full titles, visual keywords, recap and acoustic captions", () => {
  const source = readFileSync(new URL("../../services/api/src/planner/fallback/_tsx_template_string.py", import.meta.url), "utf8");
  assert.match(source, /Array.from\(scene.title\).length/);
  assert.match(source, /scene.keywords\?\.map/);
  assert.match(source, /scene.keywords\?\.length \? <div/);
  assert.match(source, /scene.summaryPoints.map/);
  assert.match(source, /scene.subtitleCues\?\.find/);
  assert.match(source, /height: VIDEO_HEIGHT \* 0.16/);
});
