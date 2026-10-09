/**
 * style-prompt.mjs — 视频风格指令与 LLM 提示构建
 * 依赖: config.mjs, utils.mjs
 */
import { ACTIVE_PEN_STYLE, ACTIVE_VIDEO_STYLE } from "./config.mjs";
import { canonicalVideoStyle, normalizePenStyle, visualTeachingRulesPrompt } from "./utils.mjs";

// ---------------------------------------------------------------------------
// Style instructions
// ---------------------------------------------------------------------------

export function getStyleInstructions(videoStyle, penStyle) {
  const style = canonicalVideoStyle(videoStyle || ACTIVE_VIDEO_STYLE, ACTIVE_VIDEO_STYLE);
  const pen = normalizePenStyle(penStyle || ACTIVE_PEN_STYLE, ACTIVE_PEN_STYLE);

  const visualStyles = {
    whiteboard: {
      base: "WHITEBOARD STYLE: Use warm off-white (#F7F7F2 or similar) classroom whiteboard background. Draw rich illustrated tutorial visuals with thick imperfect black marker lines, blue handwritten titles, red risk marks, green correct checks, yellow wavy underlines, and purple relationship notes. Visible marker hand follows active strokes.",
      elements: "Add concrete tutorial elements: one large visual anchor, 4-7 meaningful subject parts, 3-5 short labels, and varied semantic annotations driven by annotation_plan. Every arrow, circle, box, bracket, tick, underline, ray, check, or crossout must be tied to a label or beat target.",
    },
    sharpie: {
      base: "SHARPIE STYLE: Use bright white canvas with THICK black marker strokes (4-6px). Draw bold uppercase-style titles, rough quick sketches, and raw hand-drawn shapes. Use blue/yellow/red highlighter accents sparingly. A visible hand with thick marker must draw every element.",
      elements: "Use these sharpie elements: thick bold arrows, large rough circles/boxes, underline strokes, highlighter marks, and raw sketch icons. Every stroke should look bold and immediate, like a real sharpie on whiteboard.",
    },
    chalkboard_bw: {
      base: "CHALKBOARD B&W STYLE: Use dark black (#1a1a1a or similar) background with WHITE CHALK only. Draw sparse chalk-like line art, rough edges, and dusty chalk texture. NO visible hand - content appears line by line like chalk writing.",
      elements: "Use these chalkboard elements: rough chalk lines, sparse icon sketches, formula-like text, and subtle chalk dust texture. Content reveals progressively like someone writing on a real chalkboard.",
    },
    chalkboard_color: {
      base: "CHALKBOARD COLOR STYLE: Use dark black (#1a1a1a or similar) background. Draw with WHITE chalk main lines, CYAN for emphasis, YELLOW for conclusions/highlights. NO visible hand - content appears step by step.",
      elements: "Use these colored chalk elements: white main chalk strokes, cyan arrows/highlights, yellow key conclusions, subtle chalk texture. Color has meaning: white=main, cyan=emphasis, yellow=result.",
    },
    editorial: {
      base: "EDITORIAL STYLE: Use warm off-white paper-like canvas with BOLD BLACK INK illustrations and RED/ORANGE accent strokes. Draw magazine-quality sketchy illustrations with thick imperfect lines, paper sheet collage elements, and refined callouts.",
      elements: "Use these editorial elements: bold black ink drawings, red/orange arrows and callouts, paper/card collage shapes, media icons, and polished sketch illustrations. Each element should feel like quality editorial illustration.",
    },
    technical_blueprint: {
      base: "TECHNICAL BLUEPRINT STYLE: Use deep navy blue (#0a1628 or similar) canvas with PALE BLUE (#4a9eff) precise linework. Draw engineering-style diagrams with grid feel, measurement ticks, wireframe shapes, and structured panels.",
      elements: "Use these blueprint elements: precise blue lines, grid overlay, engineering symbols, wireframe boxes, measurement annotations, and structured technical diagrams. Add subtle cyan glow effects for emphasis.",
    },
    modern_minimal: {
      base: "MODERN MINIMAL STYLE: Use warm light grey (#f5f5f5) canvas with THIN BLACK lines and ONE cool accent color (blue or violet). Draw clean aligned icons, minimal shapes, and generous whitespace. Keep composition sparse and elegant.",
      elements: "Use these minimal elements: thin precise lines, aligned icon groups, minimal arrows, subtle color accents, and lots of white space. Each element should feel clean and intentional.",
    },
    playful: {
      base: "PLAYFUL STYLE: Use warm cream (#fff8e7) canvas with COLORFUL crayon-like strokes. Draw friendly rounded shapes, pastel accents, smiley marks, and bouncy compositions. Use visible hand with colorful markers.",
      elements: "Use these playful elements: rounded doodles, pastel colors (pink, mint, lavender, peach), smiley faces, music notes, bouncing shapes, and friendly character sketches. Make it approachable and fun.",
    },
  };

  const penStyles = {
    marker: "Use visible hand holding marker. Hand must follow each stroke path, moving up/down/left/right naturally.",
    pen: "Use visible hand holding pen. Hand should move smoothly, drawing fine strokes.",
    fountain_pen: "Use visible hand with fountain pen. Draw elegant thin strokes with occasional ink flow variation.",
    no_hand: "NO visible hand. Content appears through opacity reveals, not stroke animation.",
  };

  const selectedStyle = visualStyles[style] || visualStyles.whiteboard;
  const selectedPen = penStyles[pen] || penStyles.marker;
  return `${selectedStyle.base} ${selectedStyle.elements} ${selectedPen}`;
}

// ---------------------------------------------------------------------------
// Full style prompt builder
// ---------------------------------------------------------------------------

export function buildStylePrompt(videoStyle, penStyle, styleInstructions, subtitlesEnabled, backgroundMusicUrl, backgroundMusicVolume, retryHint) {
  const visualRules = visualTeachingRulesPrompt("render");
  return (
    "Directly generate this lesson as a real whiteboard animation with a visible hand holding a marker. " +
    `USER SELECTED STYLE: ${videoStyle.toUpperCase()} with ${penStyle.toUpperCase()} pen. ${styleInstructions} ` +
    `${visualRules} ` +
    "Respect scene video_style as the Golpo Canvas visual layer: chalkboard_bw uses black canvas with white chalk only; chalkboard_color uses black canvas with white/cyan chalk and limited yellow/teal emphasis; modern_minimal uses warm light grey, thin lines and one cool accent; technical_blueprint uses deep navy blueprint styling; editorial uses warm off-white bold ink with red/orange accents; whiteboard uses off-white marker-board with blue labels and small colored fills; playful uses warm cream crayon-like pastel accents; sharpie uses bright white thick black marker and highlighter accents. " +
    "Respect scene board_mode, hand_usage and visual_style: whiteboard/trace scenes use a visible hand following the active stroke; reference or annotate scenes may present a complex finished subject directly and then use hand callouts; clean_canvas/marketing_doodle scenes may use colorful finished doodles plus hand annotations; chalkboard/math_chalkboard or hand_usage=none scenes hide the hand and reveal equations or steps line by line. " +
    "Use the default bold editorial hand-drawn explainer look when scenes include generated reference art: thick black crayon/marker artwork, subject-integral color accents only, warm yellow highlight blobs behind the subject, one large subject or at most three large step groups, and generous blank space. Do not bake callout arrows, pointing arrows, warning marks, starbursts, underlines, labels, or title marks into reference art. " +
    "Treat generated reference art as text-free artwork with open whitespace only; add readable Chinese titles, labels, ticks, underlines and callouts in the renderer with large handwritten glyph text instead of relying on text baked into the image. Do not use or preserve empty callout boxes, empty circles, placeholder bubbles, blank legend panels, baked label containers, or other ambiguous annotation placeholders from the reference art. " +
    "Generalize the mixed visual policy across topics: simple graphics are hand-drawn stroke by stroke; especially complex/dense/reference-like graphics are shown directly as finished hand-drawn reference art and then annotated. Both modes must look like the same marker/crayon whiteboard artist made them. " +
    "For hand-writing scenes, every visible board text and diagram must be written or drawn live while the hand follows the actual stroke path. Every circle, box, bracket, arrow, tick, and emphasis mark must either contain/read next to a short Chinese label or point to a clearly named concept in the same beat; never draw unlabeled decorative geometry. " +
    (subtitlesEnabled ? "Render optional subtitles as a separate bottom HTML overlay, using each scene.narration as caption text; the hand should not write subtitles. " : "Do not render subtitles or caption overlays. ") +
    (backgroundMusicUrl ? `Add one global low-volume looping background music Audio track with src="${backgroundMusicUrl}" and volume=${backgroundMusicVolume}; keep it behind narration. ` : "Do not add background music. ") +
    "Import Img and staticFile from remotion and render <Img src={staticFile(\"hand-real-pen.png\")} /> inside a HandPen component positioned from getPenPosition(frame) coordinates. " +
    "Use exact constants: const HAND_WIDTH = 260; const HAND_HEIGHT = 289; const PEN_TIP_X = 15; const PEN_TIP_Y = 78; position with left: tipX - PEN_TIP_X and top: tipY - PEN_TIP_Y so the marker tip touches the active stroke. " +
    "HandPen must return an absolutely positioned HTML div wrapping Img, and <HandPen> must be rendered as a sibling after the SVG, never inside SVG. " +
    "In chalkboard/no-hand scenes keep the HandPen component defined but pass visible={false}; do not show a decorative hand. " +
    "Define drawOps with kind/startFrame/endFrame/points, pointOnPolyline(), getActiveDrawOp(), and getPenPosition(frame). " +
    "When two drawOps are separated by a short gap, keep the hand visible and move it from the previous stroke endpoint to the next stroke start without drawing, like a teacher lifting the marker. " +
    "If scenes include audioSegments, render each segment's audioUrl in its own Sequence using audioStartFrame when present, and keep matching drawOps inside the same beat window. " +
    "The hand must move up/down/left/right within words, not slide on one text baseline; text ops need stroke-like zig-zag points. " +
    "Use glyphPaths/GlyphText/DrawGlyphPath for Chinese text so the renderer can preprocess opentype.js font outline paths, after each large glyph outline finishes, a light same-color fill is allowed so handwriting does not look hollow, final board text should look like solid marker handwriting, not hollow outlined lettering, and use strokeDasharray/strokeDashoffset SVG line drawing with matching drawOps. " +
    "If storyboard scenes include rasterReveal and referenceImageAsset, obey rasterReveal.renderMode. For trace, reveal the original reference image through animated SVG masks using staticFile(scene.referenceImageAsset) and drive the hand from the same raster drawOps centerline points. For direct, present the complex reference image directly and use the hand only for large readable side callouts, wavy underlines, short arrows, edge ticks, and label-adjacent warning marks; avoid standalone brackets/circles/boxes, avoid pretending to know exact internal object locations, avoid long sweeping arrows, and avoid large circles covering the diagram. " +
    "CRITICAL: If a storyboard scene has referenceImageAsset, keep that generated/... asset path in the scene data and render it with staticFile(scene.referenceImageAsset) or staticFile(referenceImageAsset); never replace the reference scene with hand-drawn SVG-only shapes and never set referenceImageAsset to null. " +
    "Keep the transparent line-art image on a clean light grey-white whiteboard canvas without yellow panels or color washes, and after all trace raster drawOps finish crossfade the masked SVG image out while a short final HTML <Img> overlay of the same transparent image fades in outside SVG, so the last frame fully matches the reference asset without turning transparent pixels black or double-darkening strokes. " +
    "Use a clean warm off-white whiteboard canvas close to #F7F7F2, strong readable marker outlines, blue or black handwritten titles with coral-pink underlines, and purposeful colored teaching strokes. " +
    "CRITICAL RESTRICTION - Do NOT use these variable names in your code: paper, card, panel, surface, sheet, poster, slide, boardShadow, shadow, wash. The canvas background is AbsoluteFill only. " +
    "CRITICAL RESTRICTION - Do NOT use these CSS patterns in your code: washD, boxShadow, textShadow, drop-shadow, dropShadow, CSS filter, linear-gradient, radial-gradient. " +
    "Every scene needs one primary visual anchor made from at least 3-6 meaningful diagram/icon/object elements such as a funnel, route map, balance scale, gear, clock, warning triangle, clipboard, person/group, chart, matrix, cross-section, or system stack. " +
    "Never render a scene as only a heading plus checklist, bullets, checkmarks, or generic text boxes; a checklist may only be a tiny note beside a larger visual anchor. " +
    "Use idiomatic natural Chinese for all board titles, labels, callouts, captions, and narration. If the source concept is English, transcreate it into a Chinese phrase a real teacher would say instead of translating word by word; keep English only for fixed technical terms, acronyms, formulas, code names, or search names, optionally in parentheses. Avoid awkward coined shorthand; for example dependence/independence/interdependence can become 依赖 → 独立 → 互相依赖/成熟协作/协作共赢 depending on context, never 互赖. " +
    "Use staged reveal like the reference videos: title or anchor first, main line-art object second, labels/arrows/callouts third, and one short conclusion last. " +
    "If a scene is a summary, render a visual synthesis such as a loop, roadmap, hub-and-spoke map, evidence chart, or metaphor object instead of a plain checklist. " +
    "When scene.referenceImageAsset and scene.rasterReveal exist, always render the generated reference image via RasterRevealImage/RasterFinalOverlay; do not silently replace it with simpler SVG-only shapes. " +
    "Never create an inner paper, card, panel, slide, sheet, poster, white rectangle, or separate board surface; the full AbsoluteFill background is the only whiteboard. " +
    "Do not use washD, boxShadow, textShadow, drop-shadow, CSS filter, gradients, or any shadow/backing behind drawings or board text. " +
    "follow a real teacher-board layout: short blue title near the top-left or top-center, one central diagram occupying roughly 45-65% of the width, large empty margins, short labels close to the object, no fixed left explanation column, no paragraphs on the board. " +
    "animated dashed paths must use fill=\"none\"; do not use colored background washes, paper tints, or colored panels behind diagrams. and lots of negative space. " +
    "Start writing immediately in each scene and avoid blank boards after a cut; scene changes should feel like continuous board work. " +
    "For Chinese text use STXingkai/华文行楷/KaiTi/STKaiti/Kaiti SC/cursive first, not default bold sans-serif. " +
    "Use teacher-style whiteboard callouts such as arrows, underlines, ticks, and label-adjacent brackets/circles only when they clearly name what is being highlighted; make visuals lively with small humorous teaching metaphors like wrong-floor signs, tug-of-war choices, taxi route arrows, receipt/check tickets, tuning knobs, alarm marks, and marker annotations drawn directly on the board. Do not force mascots or decorative cartoon characters. " +
    (subtitlesEnabled ? "Use audioSegments subtitleText only for bottom subtitles. " : "Ignore audioSegments subtitleText and do not render any bottom subtitle overlay. ") +
    "For every drawOp that is tied to a beat, keep the beatId field and draw within that beat's time window, so the hand is emphasizing the same idea that the voice is explaining. " +
    "Do not use SVG <animate>; all timing must be driven by Remotion frame values. " +
    "Do not use templates, local components, slide-deck cards, stock images, or component libraries." +
    retryHint
  );
}
