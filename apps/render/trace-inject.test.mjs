import test from "node:test";
import assert from "node:assert/strict";
import { descriptionForScene, imageGenerationDescription, imagegenRequestTimeoutMs, selectSeedreamCandidates } from "./trace-inject.mjs";
import { joinConnectedPaths } from "./trace-algo.mjs";
import { shouldGenerateReferenceImage } from "./scene-strategy.mjs";

test("builds a scene-specific image description from visual intent and narration", () => {
  const description = descriptionForScene(
    { topic: "short video harms" },
    {
      id: "scene_1",
      title: "Attention and time cost",
      audioSegments: [
        { drawIntent: "show a person distracted by a phone beside a fast-moving clock" },
        { subtitleText: "Short clips fragment sustained attention." },
      ],
    },
  );

  assert.match(description, /Attention and time cost/);
  assert.match(description, /distracted by a phone/);
  assert.match(description, /fragment sustained attention/);
  assert.match(description, /no readable text/);
});

test("preserves an explicit storyboard image description", () => {
  const expected = "A hand-drawn brain reward loop, no text.";
  assert.equal(
    descriptionForScene({ topic: "short video harms" }, { title: "Reward", image_description: expected }),
    expected,
  );
});

test("adds scene subject, action, and relationship constraints to image generation", () => {
  const prompt = imageGenerationDescription(
    { topic: "短视频成瘾" },
    {
      id: "scene_3",
      title: "注意力被切碎",
      narration: "人不断滑动手机，时间被短视频循环吞掉。",
      learning_goal: "看见手机、人的动作和时间流失关系",
      image_description: "A hand-drawn educational illustration with a person and a phone.",
      audioSegments: [{ drawIntent: "show compulsive scrolling beside a clock" }],
    },
  );
  assert.match(prompt, /手机|phone/i);
  assert.match(prompt, /compulsive scrolling/);
  assert.match(prompt, /cause\/effect|relationship/i);
  assert.match(prompt, /generic face/i);
});

test("generates artwork for described whiteboard trace scenes", () => {
  assert.equal(shouldGenerateReferenceImage({
    image_description: "A phone, a distracted person, and a clock",
    board_mode: "whiteboard",
    hand_usage: "trace",
    visual_style: "teacher_whiteboard",
    video_style: "whiteboard",
  }), true);
  assert.equal(shouldGenerateReferenceImage({
    image_description: "A chalkboard formula",
    board_mode: "chalkboard",
    hand_usage: "trace",
    visual_style: "math_chalkboard",
  }), false);
});

test("keeps whiteboard trace scenes eligible for subject artwork when they already have line strokes", () => {
  const scene = {
    id: "scene_0",
    image_description: "A phone with a person compulsively scrolling and a clock",
    board_mode: "whiteboard",
    hand_usage: "trace",
    visual_style: "teacher_whiteboard",
    video_style: "whiteboard",
    trace_strokes: [{ d: "M 0 0 L 10 10" }],
  };

  assert.equal(shouldGenerateReferenceImage(scene), true);
  assert.deepEqual(selectSeedreamCandidates([scene], new Set(), {}), [scene]);
});

test("does not turn ordinary whiteboard scenes into required direct references", () => {
  const scenes = Array.from({ length: 4 }, (_, index) => ({
    id: `scene_${index}`,
    title: `Scene ${index}`,
    image_description: `A clear central subject illustration ${index}`,
    board_mode: "whiteboard",
    hand_usage: "trace",
    video_style: "whiteboard",
    visual_style: "teacher_whiteboard",
  }));

  assert.equal(selectSeedreamCandidates(scenes, new Set(), {}).length, 1);
  assert.equal(scenes.every((scene) => !scene.render_strategy), true);
});

test("keeps all explicit reference scenes above the optional image cap", () => {
  const scenes = [
    { id: "scene_3", image_description: "A dense reference diagram", board_mode: "reference", hand_usage: "annotate" },
    { id: "scene_4", image_description: "A finished subject plate", render_strategy: "direct", hand_usage: "trace" },
    { id: "scene_0", image_description: "An optional whiteboard illustration", board_mode: "whiteboard", hand_usage: "trace", video_style: "whiteboard" },
  ];

  assert.deepEqual(
    selectSeedreamCandidates(scenes, new Set(), {}).map((scene) => scene.id),
    ["scene_3", "scene_4"],
  );
});

test("allows enough time for serial local image generation and retries", () => {
  assert.equal(
    imagegenRequestTimeoutMs({ provider: "local", timeoutSeconds: 600, maxAttempts: 3 }, 4),
    7320000,
  );
});

test("includes the local-then-Ark fallback window", () => {
  assert.equal(
    imagegenRequestTimeoutMs({ provider: "local_then_ark", timeoutSeconds: 600, maxAttempts: 2 }, 2),
    2760000,
  );
});

test("uses a bounded cloud-provider default and honors explicit timeout overrides", () => {
  assert.equal(imagegenRequestTimeoutMs({ provider: "ark" }, 4), 840000);
  assert.equal(imagegenRequestTimeoutMs({ provider: "local" }, 4, 90000), 90000);
});

test("joins skeleton segments at shared endpoints without dropping paths", () => {
  const paths = [
    [{ x: 0, y: 0 }, { x: 1, y: 0 }],
    [{ x: 2, y: 0 }, { x: 1, y: 0 }],
    [{ x: 10, y: 10 }, { x: 11, y: 10 }],
  ];
  const joined = joinConnectedPaths(paths);
  assert.equal(joined.length, 2);
  assert.equal(joined.find((path) => path[0].x === 0)?.length, 3);
  assert.equal(joined.find((path) => path[0].x === 10)?.length, 2);
});

test("joins nearby endpoints within the skeleton sampling tolerance", () => {
  const joined = joinConnectedPaths([
    [{ x: 0, y: 0 }, { x: 2, y: 0 }],
    [{ x: 4, y: 1 }, { x: 6, y: 1 }],
  ]);
  assert.equal(joined.length, 1);
  assert.equal(joined[0].length, 3);
});
