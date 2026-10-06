import test from "node:test";
import assert from "node:assert/strict";
import { descriptionForScene } from "./trace-inject.mjs";
import { joinConnectedPaths } from "./trace-algo.mjs";

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
