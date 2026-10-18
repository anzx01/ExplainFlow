import test from "node:test";
import assert from "node:assert/strict";
import { injectSceneMotion } from "./motion-inject.mjs";

const MINIMAL_TSX = `
import { AbsoluteFill, Sequence, interpolate, useCurrentFrame } from "remotion";
const scenes = [{"title":"进气冲程","duration":456},{"title":"压缩冲程","duration":460}];
export function GeneratedVideo() {
  return (<AbsoluteFill>{scenes.map((scene) => (<Sequence key={scene.title}><div /></Sequence>))}</AbsoluteFill>);
}
`;

const STORYBOARD = {
  scenes: [
    { title: "进气冲程", motion: { elements: [{ type: "piston_crank", x: 0.5, y: 0.68, size: 0.16 }] } },
    { title: "压缩冲程", motion: { elements: [{ type: "pulse", x: 0.5, y: 0.3, size: 0.09 }] } },
  ],
};

test("injects motion layer and wraps GeneratedVideo", () => {
  const out = injectSceneMotion(MINIMAL_TSX, STORYBOARD, { fps: 24, width: 960, height: 540 });
  assert.notEqual(out, MINIMAL_TSX);
  assert.match(out, /function GeneratedVideoBase\(/);
  assert.match(out, /const SCENE_MOTION_BY_TITLE = \[/);
  assert.match(out, /export function GeneratedVideo\(\)/);
  assert.match(out, /<GeneratedVideoBase \/>/);
  assert.match(out, /SceneMotionOverlay sceneList=\{scenes\}/);
  assert.match(out, /MOTION_FPS = 24/);
  // storyboard motion data survives into the injected constant
  assert.match(out, /piston_crank/);
  // exactly one new GeneratedVideo export, original renamed away
  assert.equal(out.match(/export function GeneratedVideo\(/g).length, 1);
});

test("returns unchanged when storyboard has no motion", () => {
  const sb = { scenes: [{ title: "进气冲程" }] };
  assert.equal(injectSceneMotion(MINIMAL_TSX, sb, {}), MINIMAL_TSX);
});

test("skips when the LLM already implemented scene.motion rendering", () => {
  const withLlmMotion = MINIMAL_TSX.replace(
    "<AbsoluteFill>",
    "<AbsoluteFill>{scene && scene.motion && scene.motion.elements ? null : null}",
  );
  assert.equal(injectSceneMotion(withLlmMotion, STORYBOARD, {}), withLlmMotion);
});

test("injection is idempotent", () => {
  const once = injectSceneMotion(MINIMAL_TSX, STORYBOARD, {});
  const twice = injectSceneMotion(once, STORYBOARD, {});
  assert.equal(twice, once);
});

test("handles export const GeneratedVideo form", () => {
  const constForm = MINIMAL_TSX.replace(
    "export function GeneratedVideo() {",
    "export const GeneratedVideo = () => {",
  );
  const out = injectSceneMotion(constForm, STORYBOARD, {});
  assert.match(out, /const GeneratedVideoBase = \(\) => \{/);
  assert.match(out, /export function GeneratedVideo\(\)/);
});

test("handles default-function export normalized form", () => {
  const normalized = MINIMAL_TSX.replace(
    "export function GeneratedVideo() {",
    "export default function GeneratedVideo() {",
  );
  const out = injectSceneMotion(normalized, STORYBOARD, {});
  assert.match(out, /function GeneratedVideoBase\(/);
  assert.match(out, /export function GeneratedVideo\(\)/);
});
