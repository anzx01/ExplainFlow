import { test } from "node:test";
import assert from "node:assert/strict";
import { nvencArgs } from "./nvenc.mjs";

test("replace x264 settings without changing input, audio or output", () => {
  assert.deepEqual(nvencArgs({ args: ["-i", "-", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "18", "-c:a", "aac", "out.mp4"] }),
    ["-i", "-", "-c:v", "h264_nvenc", "-c:a", "aac", "-preset", "p4", "-cq", "20", "out.mp4"]);
});
test("leave copy/mux commands unchanged", () => {
  const args = ["-i", "in.mp4", "-c:v", "copy", "out.mp4"];
  assert.equal(nvencArgs({ args }), args);
});
