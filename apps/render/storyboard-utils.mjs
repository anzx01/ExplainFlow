/**
 * storyboard-utils.mjs — Storyboard 文本清洗、编码校验、视觉规则提示
 * 依赖: config.mjs, utils.mjs
 */
import { VISUAL_TEACHING_RULES } from "./config.mjs";
import {
  canonicalVideoStyle,
  cleanUserText,
  looksLikeMojibake,
  normalizePenStyle,
  ruleList,
} from "./utils.mjs";

// ---------------------------------------------------------------------------
// Storyboard 文本清洗
// ---------------------------------------------------------------------------

export function sanitizeStoryboardText(storyboard) {
  const scenes = Array.isArray(storyboard?.scenes) ? storyboard.scenes : [];
  const storyboardVideoStyle = canonicalVideoStyle(storyboard?.video_style ?? storyboard?.videoStyle, "whiteboard");
  const storyboardPenStyle = normalizePenStyle(storyboard?.pen_style ?? storyboard?.penStyle, "marker");
  return {
    ...storyboard,
    topic: cleanUserText(storyboard?.topic, "Untitled"),
    video_style: storyboardVideoStyle,
    pen_style: storyboardPenStyle,
    scenes: scenes.map((scene) => {
      const sceneVideoStyle = canonicalVideoStyle(scene?.video_style ?? scene?.videoStyle, storyboardVideoStyle);
      const scenePenStyle = normalizePenStyle(scene?.pen_style ?? scene?.penStyle, storyboardPenStyle);
      return {
        ...scene,
        title: cleanUserText(scene?.title, "场景"),
        narration: cleanUserText(scene?.narration, ""),
        learning_goal: cleanUserText(scene?.learning_goal ?? scene?.learningGoal, ""),
        image_description: cleanUserText(scene?.image_description ?? scene?.imageDescription, "", 1800),
        video_style: sceneVideoStyle,
        pen_style: scenePenStyle,
        visual_mode: cleanUserText(scene?.visual_mode ?? scene?.visualMode, "trace"),
        teaching_density: cleanUserText(scene?.teaching_density ?? scene?.teachingDensity, "rich"),
        visual_anchor: cleanUserText(scene?.visual_anchor ?? scene?.visualAnchor, ""),
        annotation_plan: Array.isArray(scene?.annotation_plan ?? scene?.annotationPlan)
          ? (scene.annotation_plan ?? scene.annotationPlan).map((item) => ({
              ...item,
              type: cleanUserText(item?.type, ""),
              label: cleanUserText(item?.label, ""),
              target: cleanUserText(item?.target, ""),
              beat_id: cleanUserText(item?.beat_id ?? item?.beatId, "beat_0"),
              layer: cleanUserText(item?.layer, "renderer"),
            })).filter((item) => item.type && item.label && item.target)
          : [],
        subtitleText: scene?.subtitleText == null ? scene?.subtitleText : cleanUserText(scene.subtitleText, ""),
        visual_beats: Array.isArray(scene?.visual_beats)
          ? scene.visual_beats.map((beat) => ({
              ...beat,
              draw_intent: cleanUserText(beat?.draw_intent ?? beat?.drawIntent, ""),
              narration: cleanUserText(beat?.narration, ""),
              required_labels: Array.isArray(beat?.required_labels)
                ? beat.required_labels.map((label) => cleanUserText(label, "")).filter(Boolean)
                : beat?.required_labels,
            }))
          : scene?.visual_beats,
        diagram_plan: scene?.diagram_plan
          ? {
              ...scene.diagram_plan,
              kind: cleanUserText(scene.diagram_plan.kind, "process"),
              layout: cleanUserText(scene.diagram_plan.layout, ""),
              required_labels: Array.isArray(scene.diagram_plan.required_labels)
                ? scene.diagram_plan.required_labels.map((label) => cleanUserText(label, "")).filter(Boolean)
                : scene.diagram_plan.required_labels,
            }
          : scene?.diagram_plan,
      };
    }),
  };
}

export function collectStoryboardMojibake(storyboard) {
  const bad = [];
  const check = (path, value) => {
    if (looksLikeMojibake(value)) bad.push(path);
  };
  check("topic", storyboard?.topic);
  for (const [sceneIndex, scene] of (storyboard?.scenes ?? []).entries()) {
    check(`scenes[${sceneIndex}].title`, scene?.title);
    check(`scenes[${sceneIndex}].narration`, scene?.narration);
    for (const [beatIndex, beat] of (scene?.visual_beats ?? []).entries()) {
      check(`scenes[${sceneIndex}].visual_beats[${beatIndex}].narration`, beat?.narration);
      check(`scenes[${sceneIndex}].visual_beats[${beatIndex}].draw_intent`, beat?.draw_intent ?? beat?.drawIntent);
    }
  }
  return bad;
}

export function assertStoryboardEncodingHealthy(storyboard) {
  const bad = collectStoryboardMojibake(storyboard);
  if (bad.length > 0) {
    throw new Error(`检测到中文编码异常，已停止渲染。请重新生成 storyboard 后再试。位置：${bad.slice(0, 4).join(", ")}`);
  }
}

// ---------------------------------------------------------------------------
// 视觉规则提示
// ---------------------------------------------------------------------------

export function visualTeachingRulesPrompt(context = "render") {
  const rules = VISUAL_TEACHING_RULES || {};
  const mode = rules.mode_policy || {};
  const density =
    (rules.visual_density || {})[mode.default_density || "rich"] || {};
  const style = rules.style_tokens || {};
  const baked = rules.baked_image_policy || {};
  const annotationTypes = (rules.annotation_templates || [])
    .map((item) => item?.type)
    .filter(Boolean)
    .join(", ");
  const lines = [
    `Project visual teaching rules v${rules.version || 1} (${rules.teaching_feel || "illustrated_tutorial_handdrawn"}).`,
    `Active style only: video_style=${rules.active_style || "whiteboard"}; pen_style=${rules.active_pen_style || "marker"}. Other style entries are visible but unavailable.`,
    `Default density: ${mode.default_density || "rich"}; ${density.rule || ""}`,
    `Style tokens: canvas=${style.canvas || "warm off-white classroom whiteboard"}; line=${style.main_line || "thick imperfect black marker"}; title=${style.title || "blue handwritten title"}; risk=${style.risk || "red risk marks"}; safe=${style.safe || "green checks"}; emphasis=${style.emphasis || "yellow wavy underlines"}; hand=${style.hand || "visible marker hand"}.`,
    `Mode split: trace for ${ruleList(mode.simple_trace?.use_for)}; direct_reference for ${ruleList(mode.direct_reference?.use_for)}.`,
    `Annotation plan: follow scene.annotation_plan with at least 3 different types from ${annotationTypes}. Bind every circle, box, arrow, bracket, tick, underline, ray, check, or crossout to a readable label or beat target.`,
    `Baked image policy: ${baked.image_model_role || ""} ${baked.prompt_rule || ""}`,
  ];
  if (context === "render") {
    lines.push("If a scene has referenceImageAsset, preserve and render it with RasterRevealImage/RasterFinalOverlay or staticFile(scene.referenceImageAsset); never redraw the complex reference as SVG-only.");
  }
  return lines.filter((line) => line.trim()).join(" ");
}
