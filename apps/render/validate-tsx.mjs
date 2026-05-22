/**
 * validate-tsx.mjs — 生成的 Remotion TSX 代码验证
 * 依赖: config.mjs
 */
import { HAND_ASSET } from "./config.mjs";

// ---------------------------------------------------------------------------
// Sub-validators (private)
// ---------------------------------------------------------------------------

function validateStrokeFollowingTimeline(code) {
  const required = ["drawOps", "startFrame", "endFrame", "points", "pointOnPolyline", "getActiveDrawOp", "getPenPosition"];
  for (const token of required) {
    if (!new RegExp(`\\b${token}\\b`).test(code)) {
      throw new Error("Generated TSX must define drawOps with points plus getPenPosition() so the hand follows the active text/path stroke");
    }
  }
  if (!/\b["']?kind["']?\s*:\s*["']text["']/.test(code)) throw new Error("drawOps must include text operations with kind: 'text'");
  const pathOps = [...code.matchAll(/\b["']?kind["']?\s*:\s*["'](?:path|stroke|shape|arrow|box|circle|line)["']/gi)];
  if (pathOps.length < 8) throw new Error(`drawOps must include at least 8 path/stroke operations for diagrams (found ${pathOps.length}). Each scene needs 3-5 distinct diagram elements.`);
  const textOps = [...code.matchAll(/\b["']?kind["']?\s*:\s*["']text["']/gi)];
  if (textOps.length < 5) throw new Error(`drawOps must include at least 5 text operations (found ${textOps.length}). Each scene needs title, labels, and conclusion text.`);
  const pointCount = [...code.matchAll(/\{\s*["']?x["']?\s*:\s*-?\d+(?:\.\d+)?\s*,\s*["']?y["']?\s*:\s*-?\d+(?:\.\d+)?\s*\}/g)].length;
  if (pointCount < 16) throw new Error("drawOps must contain at least 16 explicit {x, y} points so the pen traces strokes smoothly");
  if (!/\bgetPenPosition\s*\(\s*frame\s*\)/.test(code)) throw new Error("Generated TSX must call getPenPosition(frame) for the hand position");
  if (/\bconst\s+(?:tipX|tipY|penX|penY)\s*=\s*interpolate\s*\(\s*frame\s*,\s*\[[^\]]+\]\s*,\s*\[[^\]]+\]/.test(code)) {
    throw new Error("Pen tip coordinates must not use coarse scene-level interpolate(frame, [...]); derive the tip from active drawOp points");
  }
  if (/<\s*text\b/i.test(code)) throw new Error("Do not use static SVG <text>; render handwriting text with glyphPaths driven by drawOps");
}

function validateGlyphOutlineText(code) {
  if (!/\bglyphPaths\b/.test(code) || !/\b(DrawGlyphPath|GlyphText)\b/.test(code)) {
    throw new Error("Generated TSX must render Chinese text through preprocessed glyphPaths/GlyphText, not HTML text reveal only");
  }
  if (/\bHandText\b/.test(code) && !/\bGlyphText\b/.test(code)) {
    throw new Error("Generated TSX must replace HandText slice rendering with GlyphText outline path drawing");
  }
}

function validateHandwrittenWhiteboardStyle(code) {
  if (!/\b(STXingkai|Xingkai|KaiTi|STKaiti|Kaiti|楷体|华文行楷|华文楷体)\b/i.test(code)) {
    throw new Error("Generated TSX must use an explicit Chinese handwriting font stack such as STXingkai/华文行楷/KaiTi/STKaiti");
  }
  if (/\bfontWeight\s*:\s*["']?(?:700|800|900|bold)\b/i.test(code)) throw new Error("Handwritten text must not use bold sans-serif styling");
  if (!/\b(Diagram|Doodle|Callout|Sketch|Whiteboard)\b/i.test(code)) {
    throw new Error("Generated TSX must include whiteboard diagram/callout helpers, not only captions or slide labels");
  }
}

function validateNoPaperSurface(code, allowReferenceAssets = false) {
  const forbidden = [
    ["washD", "paper-like wash layers are not allowed behind drawings"],
    ["boxShadow", "shadowed paper/card surfaces are not allowed"],
    ["drop-shadow", "drop-shadow effects create a paper-like backing"],
    ["textShadow", "text shadows create a grey backing behind handwriting"],
  ];
  for (const [token, reason] of forbidden) {
    if (code.toLowerCase().includes(token.toLowerCase())) {
      throw new Error(`Generated TSX contains forbidden paper-surface styling: ${token} (${reason})`);
    }
  }
  const paperSurfaceProps = [
    /[{(]\s*\bpaper\s*:/i, /[{(]\s*\bcard\s*:/i, /[{(]\s*\bpanel\s*:/i,
    /[{(]\s*\bsurface\s*:/i, /[{(]\s*\bsheet\s*:/i, /[{(]\s*\bposter\s*:/i,
    /[{(]\s*\bslide\s*:/i, /[{(]\s*\bboardShadow\s*:/i,
    /[{(]\s*\bshadow\b\s*:/i, /[{(]\s*\bwash\s*:/i,
  ];
  for (const pattern of paperSurfaceProps) {
    if (pattern.test(code)) throw new Error("Generated TSX must not define paper/card/panel/surface/shadow/wash helpers or variables");
  }
  if (/\bfilter\s*:\s*["'][^"']+["']/i.test(code)) throw new Error("Generated TSX must not use CSS filter effects");
  if (!allowReferenceAssets && /\brasterReveal\s*:\s*\{|\breferenceImageAsset\s*:\s*["']generated\//i.test(code)) {
    throw new Error("Generated TSX must not bake rasterReveal/referenceImageAsset into normal generated whiteboard scenes");
  }
  const lightSurface = /background(?:Color)?\s*:\s*["'](?:#fff(?:fff)?|white|#f7f7f2|#f8f8f0|#fafafa|#f5f5f5|rgb\(\s*255\s*,\s*255\s*,\s*255\s*\))["'][\s\S]{0,220}\b(?:borderRadius|boxShadow|position\s*:\s*["']absolute["'])/i;
  if (lightSurface.test(code)) throw new Error("Generated TSX must not create an inner white/light rectangle behind drawings or text");
  if (/\b(?:linear-gradient|radial-gradient)\s*\(/i.test(code)) throw new Error("Generated TSX must not use gradient washes or panel backgrounds");
}

function validateRequiredReferenceRendering(code, storyboard) {
  const assets = storyboardReferenceAssets(storyboard);
  if (assets.length === 0) return;
  for (const asset of assets) {
    if (!code.includes(asset)) throw new Error(`Generated TSX must preserve and render storyboard referenceImageAsset: ${asset}`);
  }
  const rendersReference =
    /\bstaticFile\s*\(\s*(?:scene\.)?referenceImageAsset\s*\)/.test(code) ||
    /\bstaticFile\s*\(\s*["']generated\/[a-zA-Z0-9_-]+\/[a-zA-Z0-9_.-]+\.(?:png|jpg|jpeg|webp)["']\s*\)/.test(code) ||
    /\b(RasterRevealImage|RasterFinalOverlay)\b/.test(code);
  if (!rendersReference) throw new Error("Generated TSX must render referenceImageAsset with staticFile(); do not redraw it manually");
  const allNull = /referenceImageAsset\s*:\s*null/.test(code) && !/referenceImageAsset\s*:\s*["']generated\//.test(code);
  if (allNull) throw new Error("Generated TSX must not set all referenceImageAsset values to null");
}

function validateStaticFileUsage(code) {
  const allowedAsset = /^(?:hand-real-pen\.png|generated\/[a-zA-Z0-9_-]+\/[a-zA-Z0-9_.-]+\.(?:png|jpg|jpeg|webp))$/;
  for (const match of [...code.matchAll(/\bstaticFile\s*\(\s*["']([^"']+)["']\s*\)/g)]) {
    if (!allowedAsset.test(match[1])) throw new Error(`Generated TSX references disallowed static asset: ${match[1]}`);
  }
  for (const match of [...code.matchAll(/\bstaticFile\s*\(([^)]*)\)/g)]) {
    const arg = match[1].trim();
    if (/^["']/.test(arg)) continue;
    if (!/^(?:HAND_ASSET|referenceImageAsset|scene\.referenceImageAsset|reveal\.asset)$/.test(arg)) {
      throw new Error(`Generated TSX uses uncontrolled staticFile() argument: ${arg}`);
    }
  }
}

// ---------------------------------------------------------------------------
// Public exports
// ---------------------------------------------------------------------------

export function storyboardReferenceAssets(storyboard) {
  return (Array.isArray(storyboard?.scenes) ? storyboard.scenes : [])
    .map((scene) => scene?.referenceImageAsset ?? scene?.reference_image_asset)
    .filter((asset) => typeof asset === "string" && asset.trim())
    .map((asset) => asset.trim());
}

export function validateGeneratedTsx(tsx, storyboard = null) {
  let code = String(tsx ?? "").trim().replace(/^```(?:tsx|ts)?\s*/, "").replace(/\s*```$/, "");
  const hasReferenceAssets = storyboardReferenceAssets(storyboard).length > 0;
  const hasNamedExport = () =>
    /export\s+const\s+GeneratedVideo\b/.test(code) ||
    /export\s+function\s+GeneratedVideo\b/.test(code) ||
    /export\s*\{\s*GeneratedVideo\s*\}/.test(code);

  if (!hasNamedExport()) code = code.replace(/export\s+default\s+function\s+GeneratedVideo\s*\(/, "export function GeneratedVideo(");
  if (!hasNamedExport()) {
    const defaultFn = code.match(/export\s+default\s+function\s+([A-Z]\w*)\s*\(/);
    if (defaultFn) {
      code = code.replace(new RegExp(`export\\s+default\\s+function\\s+${defaultFn[1]}\\s*\\(`), `function ${defaultFn[1]}(`);
      code = `${code.trim()}\n\nexport const GeneratedVideo = ${defaultFn[1]};\n`;
    }
  }
  if (!hasNamedExport() && /\b(function|const|let|var)\s+GeneratedVideo\b/.test(code)) {
    code = code.replace(/export\s+default\s+GeneratedVideo\s*;?/, "");
    code = `${code.trim()}\n\nexport { GeneratedVideo };\n`;
  }
  if (!hasNamedExport()) {
    const defaultId = code.match(/export\s+default\s+([A-Z]\w*)\s*;?/);
    if (defaultId) {
      code = code.replace(new RegExp(`export\\s+default\\s+${defaultId[1]}\\s*;?`), "");
      code = `${code.trim()}\n\nexport const GeneratedVideo = ${defaultId[1]};\n`;
    }
  }
  if (!hasNamedExport()) throw new Error("Generated TSX must export GeneratedVideo");
  if (!/\buseCurrentFrame\b/.test(code)) throw new Error("Generated TSX must use useCurrentFrame()");
  if (!/\b(interpolate|spring)\s*\(/.test(code)) throw new Error("Generated TSX must animate with interpolate() or spring()");
  if (!/\bSequence\b/.test(code)) throw new Error("Generated TSX must use Sequence for scene timing");
  if (!/\bstrokeDasharray\b/.test(code) || !/\bstrokeDashoffset\b/.test(code)) {
    throw new Error("Generated TSX must draw SVG strokes with strokeDasharray/strokeDashoffset");
  }
  const hasTextReveal = /\bglyphPaths\b/.test(code) || /\bspec\.text\.(?:slice|substring)\s*\(/.test(code) || /\bclipPath\b/.test(code);
  if (!hasTextReveal) throw new Error("Generated TSX must reveal text progressively");

  validateStrokeFollowingTimeline(code);
  validateGlyphOutlineText(code);
  validateHandwrittenWhiteboardStyle(code);
  validateNoPaperSurface(code, hasReferenceAssets);
  validateRequiredReferenceRendering(code, storyboard);

  if (!/\b(KaiTi|STKaiti|Kaiti|楷体)\b/i.test(code)) throw new Error("Generated TSX must use a Chinese handwriting-style font family such as KaiTi/STKaiti");
  const hasWatercolorAccent = [...code.matchAll(/#[0-9a-fA-F]{6}\b/g)].some((match) => {
    const value = match[0].toLowerCase();
    if (value === "#000000" || value === "#ffffff") return false;
    const r = Number.parseInt(value.slice(1, 3), 16);
    const g = Number.parseInt(value.slice(3, 5), 16);
    const b = Number.parseInt(value.slice(5, 7), 16);
    return !(Math.max(r, g, b) - Math.min(r, g, b) < 24) && !(Math.min(r, g, b) > 238) && !(Math.max(r, g, b) < 48);
  });
  if (!hasWatercolorAccent && !/\brgba?\s*\(/i.test(code)) throw new Error("Generated TSX must include purposeful teaching accent colors");
  if (!code.includes(HAND_ASSET)) throw new Error(`Generated TSX must use staticFile("${HAND_ASSET}") for the visible hand holding a pen`);
  if (!/\bstaticFile\s*\(/.test(code)) throw new Error("Generated TSX must reference the hand asset with staticFile()");
  validateStaticFileUsage(code);
  if (!/\bImg\b/.test(code)) throw new Error("Generated TSX must render the visible hand with Remotion <Img>");
  if (!/\bHandPen\b/.test(code)) throw new Error("Generated TSX must define and render a HandPen component");
  if (!/\b(tip|pen)(X|Y)\b/.test(code)) throw new Error("Generated TSX must compute pen tip coordinates for the hand overlay");
  if (!/\bvisible\b/.test(code)) throw new Error("HandPen must receive a visible flag and hide during non-drawing holds");
  if (!/\bHAND_WIDTH\s*=\s*(?:2[2-9]\d|[3-9]\d\d)\b/.test(code)) throw new Error("Generated TSX must size the hand image with HAND_WIDTH >= 220");
  if (!/\bPEN_TIP_(?:X|Y)\b/.test(code)) throw new Error("Generated TSX must use fixed PEN_TIP_X/PEN_TIP_Y offsets to align the marker tip");
  if (/<svg(?:(?!<\/svg>)[\s\S])*<HandPen(?:(?!<\/svg>)[\s\S])*<\/svg>/i.test(code)) {
    throw new Error("Generated TSX must render HandPen outside SVG as an HTML overlay sibling");
  }
  if (!/HandPen[\s\S]*?<div[\s\S]*?<Img/i.test(code)) {
    throw new Error("Generated TSX must wrap the hand <Img> in an absolutely positioned HTML <div>");
  }
  if (/<path(?=[^>]*strokeDash)(?=[^>]*fill=['"](?!none['"])[^'"]+['"])[^>]*>/i.test(code)) {
    throw new Error("Generated TSX must not fill animated stroke paths; use separate closed wash shapes behind strokes");
  }

  const forbiddenTokens = [
    "from \"./", "from './", "from \"../", "from '../",
    "require(", "eval(", "new Function", "child_process", "node:",
    "process.", "document.", "window.", "localStorage", "sessionStorage",
    "XMLHttpRequest", "fetch(", "dangerouslySetInnerHTML",
  ];
  const lower = code.toLowerCase();
  for (const token of forbiddenTokens) {
    if (lower.includes(token.toLowerCase())) throw new Error(`Generated TSX contains forbidden token: ${token}`);
  }

  const forbiddenPatterns = [
    /\bfs\./i, /\bfs\/promises\b/i, /\bimport\s*\(/i, /<\s*animate\b/i,
    /\btransition\s*:/i,
    /\banimation(?:Name|Duration|TimingFunction|Delay|IterationCount|Direction|FillMode|PlayState)?\s*:/i,
    /@keyframes\b/i, /\bclassName\s*=\s*['"][^'"]*\banimate-/i,
    /\bsetTimeout\s*\(/i, /\bsetInterval\s*\(/i, /\brequestAnimationFrame\s*\(/i,
    /\bDate\.now\s*\(/i, /\bMath\.random\s*\(/i,
  ];
  for (const pattern of forbiddenPatterns) {
    if (pattern.test(code)) throw new Error(`Generated TSX contains forbidden pattern: ${pattern}`);
  }

  for (const line of code.split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed.startsWith("import ")) continue;
    const match = trimmed.match(/from\s+["']([^"']+)["']/);
    if (!match || !["react", "remotion"].includes(match[1])) {
      throw new Error(`Generated TSX has disallowed import: ${trimmed}`);
    }
  }
  return code;
}
