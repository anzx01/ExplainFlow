/**
 * scene-strategy.mjs — 场景分类、策略判断、本地图像读取
 * 依赖: config.mjs
 */
import { existsSync, readFileSync } from "fs";
import { resolve } from "path";
import {
  DIRECT_IMAGE_STROKE_THRESHOLD,
  ENABLE_SEEDREAM_REFERENCE_IMAGES,
  GOLPO_VIDEO_STYLES,
  SEEDREAM_REFERENCE_RENDER_MODE,
  VIDEO_STYLE_ALIASES,
} from "./config.mjs";

export function sceneTextForStrategy(scene) {
  return [
    scene?.title, scene?.image_description, scene?.imageDescription,
    scene?.learning_goal, scene?.learningGoal,
    scene?.render_strategy, scene?.renderStrategy,
    scene?.visual_mode, scene?.visualMode,
    scene?.teaching_density, scene?.teachingDensity,
    scene?.visual_anchor, scene?.visualAnchor,
    scene?.visual_complexity, scene?.visualComplexity,
    scene?.board_mode, scene?.boardMode,
    scene?.hand_usage, scene?.handUsage,
    scene?.video_style, scene?.videoStyle,
    scene?.visual_style, scene?.visualStyle,
    scene?.teacher_board_strategy, scene?.teacherBoardStrategy,
    scene?.diagram_plan?.kind, scene?.diagramPlan?.kind,
    scene?.diagram_plan?.layout, scene?.diagramPlan?.layout,
    ...(Array.isArray(scene?.diagram_plan?.required_labels) ? scene.diagram_plan.required_labels : []),
    ...(Array.isArray(scene?.diagramPlan?.requiredLabels) ? scene.diagramPlan.requiredLabels : []),
    ...(Array.isArray(scene?.annotation_plan) ? scene.annotation_plan : []).flatMap((item) => [
      item?.type, item?.label, item?.target, item?.beat_id,
    ]),
    ...(Array.isArray(scene?.annotationPlan) ? scene.annotationPlan : []).flatMap((item) => [
      item?.type, item?.label, item?.target, item?.beatId,
    ]),
    ...(Array.isArray(scene?.visual_beats) ? scene.visual_beats : []).flatMap((beat) => [
      beat?.draw_intent, beat?.drawIntent, beat?.narration,
      ...(Array.isArray(beat?.required_labels) ? beat.required_labels : []),
      ...(Array.isArray(beat?.requiredLabels) ? beat.requiredLabels : []),
    ]),
  ].filter(Boolean).join(" ").toLowerCase();
}

export function countPatternMatches(text, patterns) {
  return patterns.reduce((sum, pattern) => sum + (pattern.test(text) ? 1 : 0), 0);
}

export function countSceneLabels(scene) {
  const labels = new Set();
  const add = (value) => {
    const label = String(value ?? "").trim().toLowerCase();
    if (label) labels.add(label);
  };
  for (const label of scene?.diagram_plan?.required_labels ?? []) add(label);
  for (const label of scene?.diagramPlan?.requiredLabels ?? []) add(label);
  for (const beat of scene?.visual_beats ?? []) {
    for (const label of beat?.required_labels ?? []) add(label);
    for (const label of beat?.requiredLabels ?? []) add(label);
  }
  const quotedLabels = sceneTextForStrategy(scene).match(/'[^']{1,28}'|"[^"]{1,28}"/g) ?? [];
  for (const label of quotedLabels) add(label.slice(1, -1));
  return labels.size;
}

export function explicitRasterStrategy(scene) {
  const value = String(
    scene?.render_strategy ?? scene?.renderStrategy ??
    scene?.visual_mode ?? scene?.visualMode ??
    scene?.raster_render_strategy ?? scene?.rasterRenderStrategy ??
    scene?.teacher_board_strategy ?? scene?.teacherBoardStrategy ??
    scene?.diagram_plan?.render_strategy ?? scene?.diagramPlan?.renderStrategy ?? "",
  ).trim().toLowerCase();
  if (!value) return null;
  if (/(direct|finished|static|reference|present|photo|show)/i.test(value)) return "direct";
  if (/(trace|progressive|draw|write|stroke|reveal|board)/i.test(value)) return "trace";
  if (/(hybrid|mixed|annotation|callout)/i.test(value)) return "direct";
  return null;
}

export function sceneBoardMode(scene) {
  return String(scene?.board_mode ?? scene?.boardMode ?? "").trim().toLowerCase();
}

export function sceneHandUsage(scene) {
  return String(scene?.hand_usage ?? scene?.handUsage ?? "").trim().toLowerCase();
}

export function sceneVideoStyle(scene, storyboard = null) {
  const raw = String(
    scene?.video_style ?? scene?.videoStyle ?? storyboard?.video_style ?? storyboard?.videoStyle ?? "",
  ).trim().toLowerCase();
  const style = VIDEO_STYLE_ALIASES.get(raw) ?? raw;
  return GOLPO_VIDEO_STYLES.has(style) ? style : "whiteboard";
}

export function sceneVisualStyle(scene) {
  return String(scene?.visual_style ?? scene?.visualStyle ?? "").trim().toLowerCase();
}

export function sceneShouldDirectRender(scene, trace) {
  const explicit = explicitRasterStrategy(scene);
  if (explicit === "direct") return true;
  if (explicit === "trace") return false;
  if (SEEDREAM_REFERENCE_RENDER_MODE === "trace") return false;
  if (SEEDREAM_REFERENCE_RENDER_MODE === "direct") return true;
  const videoStyle = sceneVideoStyle(scene);
  if (sceneHandUsage(scene) === "annotate") return true;
  if (sceneBoardMode(scene) === "reference" || sceneVisualStyle(scene) === "technical_reference") return true;
  if (sceneBoardMode(scene) === "clean_canvas" || sceneVisualStyle(scene) === "marketing_doodle") return true;
  if (["technical_blueprint", "editorial", "whiteboard", "playful", "sharpie"].includes(videoStyle)) return true;
  if (videoStyle === "modern_minimal" && sceneHandUsage(scene) !== "trace") return true;
  if (sceneBoardMode(scene) === "chalkboard" || sceneVisualStyle(scene) === "math_chalkboard") return false;

  const text = sceneTextForStrategy(scene);
  const strokeCount = Number(trace?.strokes?.length ?? 0);
  const skeletonPixels = Number(trace?.skeletonPixels ?? 0);
  const maskCoverage = Number(trace?.maskCoverage ?? 0);
  const labelCount = countSceneLabels(scene);
  const beatCount = Array.isArray(scene?.visual_beats) ? scene.visual_beats.length : 0;

  const boardworkScore =
    countPatternMatches(text, [
      /\b(simple|schematic|line[-\s]?art|line diagram|whiteboard|sketch|diagram|flowchart|process|comparison|before|after|curve|axis|graph|formula|equation|single|two[-\s]?panel)\b/i,
      /(简单|示意|线稿|白板|草图|流程|对比|曲线|坐标轴|公式|单图|双图|少量|板书)/i,
      /\b(cross[-\s]?section|section view)\b/i,
    ]) +
    (beatCount >= 2 && beatCount <= 5 ? 1 : 0) +
    (labelCount <= 8 ? 1 : 0);

  const denseReferenceScore =
    countPatternMatches(text, [
      /\b(photo|realistic|reference|finished|full[-\s]?image|object|portrait|screenshot|map|cad|render|scan|microscope|medical|anatomy|isometric|3d|three[-\s]?dimensional|cutaway|exploded|multi[-\s]?layer|many labels|dense|detailed|complex)\b/i,
      /(照片|真实|参考图|成品图|直接呈现|实物|截图|地图|扫描|显微|医学|解剖|三维|立体|剖切|爆炸图|多层|密集|复杂|细节很多|标签很多)/i,
      /\b(left|center|right)\s*:/i,
      /(左[：:]|中[：:]|右[：:])/i,
    ]) + (labelCount >= 10 ? 1 : 0);

  const metricComplexity =
    (strokeCount >= DIRECT_IMAGE_STROKE_THRESHOLD ? 1 : 0) +
    (skeletonPixels >= 12000 ? 1 : 0) +
    (maskCoverage >= 0.115 ? 1 : 0);
  const extremeComplexity = skeletonPixels >= 24000 || maskCoverage >= 0.18;

  if (extremeComplexity && boardworkScore < 3) return true;
  if (denseReferenceScore >= 2 && (metricComplexity >= 1 || boardworkScore < 3)) return true;
  if (boardworkScore >= 3 && skeletonPixels <= 18000 && maskCoverage <= 0.14) return false;
  if (denseReferenceScore > boardworkScore && metricComplexity >= 1) return true;
  return metricComplexity >= 2;
}

export function shouldGenerateReferenceImage(scene) {
  if (!ENABLE_SEEDREAM_REFERENCE_IMAGES) return false;
  const boardMode = sceneBoardMode(scene);
  const videoStyle = sceneVideoStyle(scene);
  const visualStyle = sceneVisualStyle(scene);
  const handUsage = sceneHandUsage(scene);
  const explicit = explicitRasterStrategy(scene);
  if (handUsage === "none") return false;
  if (boardMode === "chalkboard" || visualStyle === "math_chalkboard") return false;
  if (explicit === "direct") return true;
  if (
    explicit === "trace" ||
    (boardMode === "whiteboard" &&
      handUsage === "trace" &&
      ["", "teacher_whiteboard", "sharpie"].includes(visualStyle) &&
      ["", "simple", "medium"].includes(String(scene?.visual_complexity ?? scene?.visualComplexity ?? "").toLowerCase()))
  ) {
    return false;
  }
  if (["modern_minimal", "technical_blueprint", "editorial", "whiteboard", "playful", "sharpie"].includes(videoStyle)) {
    return true;
  }
  if (ENABLE_SEEDREAM_REFERENCE_IMAGES && scene?.image_description) return true;
  if (boardMode === "whiteboard" && visualStyle === "teacher_whiteboard" && handUsage === "trace") {
    return explicit === "direct";
  }
  if (boardMode === "reference" || boardMode === "clean_canvas") return true;
  if (visualStyle === "technical_reference" || visualStyle === "marketing_doodle") return true;
  const complexity = String(scene?.visual_complexity ?? scene?.visualComplexity ?? "").toLowerCase();
  if (complexity === "dense" || complexity === "reference") return true;
  const text = sceneTextForStrategy(scene);
  const labelCount = countSceneLabels(scene);
  const wantsFinishedSubject = countPatternMatches(text, [
    /\b(reference|photo|screenshot|finished|full[-\s]?image|3d|isometric|technical drawing|cad|anatomy|medical|mechanical|circuit|realistic|product interface)\b/i,
    /(参考图|成品图|截图|三维|立体|技术图|医学|解剖|机械|电路|真实|产品界面|复杂主体|直接呈现)/i,
  ]);
  return wantsFinishedSubject > 0 || labelCount >= 12;
}

export function normalizeBase64Image(value) {
  const text = String(value ?? "").trim();
  const comma = text.indexOf(",");
  return comma >= 0 && text.slice(0, comma).includes("base64") ? text.slice(comma + 1) : text;
}

export function isProbablyBase64Image(value) {
  const text = String(value ?? "").trim();
  if (text.startsWith("data:image/")) return true;
  if (text.length < 120) return false;
  return /^[a-zA-Z0-9+/=\r\n]+$/.test(text);
}

export function sceneLocalImageBuffer(scene) {
  const candidates = [
    scene.reference_image_path, scene.referenceImagePath,
    scene.image_path, scene.imagePath,
    scene.image_url, scene.imageUrl,
    scene.reference_image_base64, scene.referenceImageBase64,
    scene.image_base64, scene.imageBase64,
  ].filter(Boolean);
  for (const candidate of candidates) {
    const value = String(candidate).trim();
    if (!value) continue;
    if (isProbablyBase64Image(value)) {
      try {
        return Buffer.from(normalizeBase64Image(value), "base64");
      } catch {}
    }
    if (/^https?:\/\//i.test(value)) continue;
    const possiblePaths = [resolve(value)];
    for (const possiblePath of possiblePaths) {
      if (existsSync(possiblePath)) {
        return readFileSync(possiblePath);
      }
    }
  }
  return null;
}
