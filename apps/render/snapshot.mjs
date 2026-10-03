import { createHash } from "crypto";

// Bump whenever render semantics, image tracing, or stage-quality gates change.
// This prevents an older MP4 (for example one made from a stale noodle image)
// from being reused after the scene contract or source image is repaired.
export const SNAPSHOT_VERSION = 3;

function normalize(value) {
  if (Array.isArray(value)) return value.map(normalize);
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.keys(value).sort().map((key) => [key, normalize(value[key])]));
  }
  return value;
}

export function fingerprint(value, namespace = "explainflow") {
  const canonical = JSON.stringify(normalize(value));
  return createHash("sha256").update(`${namespace}:v${SNAPSHOT_VERSION}:${canonical}`).digest("hex");
}

export function buildProjectSnapshot(storyboard, renderOptions = {}) {
  const normalizedStoryboard = {
    topic: storyboard?.topic ?? null,
    videoStyle: storyboard?.video_style ?? storyboard?.videoStyle ?? null,
    penStyle: storyboard?.pen_style ?? storyboard?.penStyle ?? null,
    styleLock: storyboard?.style_lock ?? storyboard?.styleLock ?? null,
    characterLock: storyboard?.character_lock ?? storyboard?.characterLock ?? null,
    paletteId: storyboard?.palette_id ?? storyboard?.paletteId ?? null,
    scenes: storyboard?.scenes ?? [],
    imageQualityContractVersion: 3,
  };
  const storyboardFingerprint = fingerprint(normalizedStoryboard, "storyboard");
  const styleFingerprint = fingerprint({
    videoStyle: normalizedStoryboard.videoStyle,
    penStyle: normalizedStoryboard.penStyle,
  }, "style");
  const audioFingerprint = fingerprint({
    storyboard: storyboardFingerprint,
    voice: renderOptions.voice ?? "xiaoxiao",
  }, "audio");
  const imageFingerprint = fingerprint({ storyboard: storyboardFingerprint, style: styleFingerprint }, "images");
  const renderFingerprint = fingerprint({
    storyboard: storyboardFingerprint,
    style: styleFingerprint,
    audio: audioFingerprint,
    images: imageFingerprint,
    options: renderOptions,
  }, "render");
  return {
    snapshotVersion: SNAPSHOT_VERSION,
    storyboardFingerprint,
    styleFingerprint,
    sceneFingerprints: Object.fromEntries((storyboard?.scenes ?? []).map((scene, index) => [scene?.id ?? String(index), fingerprint(scene, "scene")])),
    stages: {
      storyboard: storyboardFingerprint,
      audio: audioFingerprint,
      images: imageFingerprint,
      render: renderFingerprint,
    },
  };
}
