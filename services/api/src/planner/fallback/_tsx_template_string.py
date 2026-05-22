# Auto-generated TSX template for fallback whiteboard video renderer.
# This file is intentionally larger than 300 lines: it is a static template string, not logic.

_WHITEBOARD_TSX_TEMPLATE = r'''
import React from "react";
import { AbsoluteFill, Audio, Easing, Img, interpolate, Sequence, staticFile, useCurrentFrame } from "remotion";

const HAND_WIDTH = 260;
const HAND_HEIGHT = 289;
const PEN_TIP_X = 15;
const PEN_TIP_Y = 78;
const VIDEO_WIDTH = __VIDEO_WIDTH__;
const VIDEO_HEIGHT = __VIDEO_HEIGHT__;
const BOARD_BACKGROUND = "#F7F7F2";
const BACKGROUND_MUSIC_URL: string | null = __BACKGROUND_MUSIC_URL__;
const BACKGROUND_MUSIC_VOLUME = __BACKGROUND_MUSIC_VOLUME__;
const FONT_FAMILY = "'STXingkai', '华文行楷', KaiTi, STKaiti, 'Kaiti SC', cursive";

type Point = { x: number; y: number };
type DrawOp = { id: string; kind: "text" | "path"; startFrame: number; endFrame: number; points: Point[]; pace?: "glyph" | "ease"; beatId?: string };
type TextSpec = { opId: string; text: string; x: number; y: number; fontSize: number; color: string; maxWidth: number; markerStrokeWidth?: number; markerFillOpacity?: number };
type GlyphPathSpec = { opId: string; sourceOpId: string; d: string; color: string; strokeWidth: number; dashLength: number; fontOutline: boolean; markerFillOpacity?: number };
type StrokeSpec = { opId: string; role: string; d: string; color: string; strokeWidth: number; dashLength: number };
type RasterStrokeSpec = { opId: string; d: string; revealWidth: number; dashLength: number };
type RasterRevealSpec = { asset: string; x: number; y: number; width: number; height: number; strokes: RasterStrokeSpec[]; renderMode?: "trace" | "direct"; fit?: "contain" | "cover"; directAppearFrame?: number };
type AudioSegmentSpec = { id: string; index?: number; startFrame: number; endFrame: number; duration: number; audioStartFrame?: number; audioEndFrame?: number; audioSequenceDuration?: number; audioUrl?: string | null; audioDurationFrames: number; drawBudgetFrames: number; subtitleText?: string | null; drawIntent?: string | null };
type SceneSpec = {
  title: string;
  diagramKind?: string;
  boardMode?: "whiteboard" | "chalkboard" | "clean_canvas" | "reference";
  handUsage?: "trace" | "annotate" | "none";
  videoStyle?: "auto" | "chalkboard_bw" | "chalkboard_color" | "modern_minimal" | "technical_blueprint" | "editorial" | "whiteboard" | "playful" | "sharpie";
  visualStyle?: "teacher_whiteboard" | "marketing_doodle" | "math_chalkboard" | "technical_reference" | "modern_minimal" | "editorial" | "playful" | "sharpie";
  duration: number;
  audioUrl?: string | null;
  audioSegments?: AudioSegmentSpec[];
  transitionFrames?: number;
  accent: string;
  drawOps: DrawOp[];
  texts: TextSpec[];
  glyphPaths?: GlyphPathSpec[];
  strokes: StrokeSpec[];
  referenceImageAsset?: string | null;
  rasterReveal?: RasterRevealSpec | null;
  subtitleText?: string | null;
};

const scenes = __SCENES_JSON__ as SceneSpec[];
const SUBTITLES_ENABLED = __SUBTITLES_ENABLED__;

const clamp01 = (value: number) => Math.max(0, Math.min(1, value));
const MIN_START_PROGRESS = 0.018;
const sceneBackground = (scene: SceneSpec) => {
  if (scene.boardMode === "chalkboard" || scene.visualStyle === "math_chalkboard") return "#050806";
  if (scene.videoStyle === "technical_blueprint") return "#18364A";
  if (scene.videoStyle === "modern_minimal") return "#F1F3F0";
  if (scene.videoStyle === "editorial") return "#FAF4EA";
  if (scene.videoStyle === "whiteboard") return "#FBFCF8";
  if (scene.videoStyle === "playful") return "#FBF7D8";
  if (scene.videoStyle === "sharpie") return "#FFFDF7";
  if (scene.boardMode === "clean_canvas") return "#F7F7F2";
  return BOARD_BACKGROUND;
};
const sceneCaptionColor = (scene: SceneSpec) =>
  scene.boardMode === "chalkboard" || scene.visualStyle === "math_chalkboard" ? "#F6F2E9" : "#111318";

const progressForOp = (frame: number, op: DrawOp) => {
  const baseConfig = {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  } as const;
  if (frame < op.startFrame) return 0;
  if (op.pace === "glyph") {
    return Math.max(MIN_START_PROGRESS, interpolate(frame, [op.startFrame, op.endFrame], [0, 1], baseConfig));
  }
  return Math.max(MIN_START_PROGRESS, interpolate(frame, [op.startFrame, op.endFrame], [0, 1], {
    ...baseConfig,
    easing: Easing.bezier(0.2, 0.8, 0.2, 1),
  }));
};

const pointOnPolyline = (points: Point[], progress: number): Point => {
  if (points.length === 0) return { x: -400, y: -400 };
  if (points.length === 1) return points[0];
  const lengths = points.slice(1).map((point, index) => {
    const prev = points[index];
    return Math.sqrt((point.x - prev.x) ** 2 + (point.y - prev.y) ** 2);
  });
  const total = lengths.reduce((sum, value) => sum + value, 0) || 1;
  let walked = clamp01(progress) * total;
  for (let i = 0; i < lengths.length; i += 1) {
    if (walked <= lengths[i]) {
      const prev = points[i];
      const next = points[i + 1];
      const t = lengths[i] === 0 ? 0 : walked / lengths[i];
      return {
        x: interpolate(t, [0, 1], [prev.x, next.x]),
        y: interpolate(t, [0, 1], [prev.y, next.y]),
      };
    }
    walked -= lengths[i];
  }
  return points[points.length - 1];
};

const HandPen = ({ tipX, tipY, visible }: { tipX: number; tipY: number; visible: boolean }) => (
  <div
    style={{
      position: "absolute",
      left: tipX - PEN_TIP_X,
      top: tipY - PEN_TIP_Y,
      width: HAND_WIDTH,
      height: HAND_HEIGHT,
      opacity: visible ? 1 : 0,
      pointerEvents: "none",
      zIndex: 20,
    }}
  >
    <Img src={staticFile("hand-real-pen.png")} style={{ width: HAND_WIDTH, height: HAND_HEIGHT }} />
  </div>
);

const captionWeight = (value: string) =>
  Array.from(value).reduce((sum, char) => sum + (char.charCodeAt(0) > 255 ? 2 : 1), 0);

const splitSubtitleText = (value: string): string[] => {
  const source = value.replace(/\s+/g, " ").trim();
  if (!source) return [];
  const sentences = source.match(/[^。！？.!?；;]+[。！？.!?；;]?/g) ?? [source];
  const chunks: string[] = [];
  for (const sentence of sentences) {
    const clean = sentence.trim();
    if (!clean) continue;
    const prev = chunks[chunks.length - 1];
    if (prev && captionWeight(prev + clean) <= 64) {
      chunks[chunks.length - 1] = prev + clean;
    } else {
      chunks.push(clean);
    }
  }
  return chunks.filter(Boolean);
};

const SubtitleOverlay = ({ scene }: { scene: SceneSpec }) => {
  if (!SUBTITLES_ENABLED) return null;
  const frame = useCurrentFrame();
  const segments = scene.audioSegments ?? [];
  const activeSegment = segments.find((segment) => {
    const audioStart = segment.audioStartFrame ?? segment.startFrame;
    const audioEnd = segment.audioEndFrame ?? segment.endFrame;
    return frame >= audioStart && frame < audioEnd;
  });
  if (segments.length > 0 && !activeSegment) return null;
  const text = (activeSegment ? activeSegment.subtitleText : scene.subtitleText)?.trim();
  if (!text) return null;
  const chunks = splitSubtitleText(text);
  if (chunks.length === 0) return null;
  const audioStart = activeSegment ? activeSegment.audioStartFrame ?? activeSegment.startFrame : 0;
  const audioEnd = activeSegment ? activeSegment.audioEndFrame ?? activeSegment.endFrame : scene.duration;
  const localFrame = activeSegment ? frame - audioStart : frame;
  const localDuration = activeSegment ? Math.max(1, audioEnd - audioStart) : scene.duration;
  const progress = clamp01(localFrame / Math.max(1, localDuration - 1));
  const index = Math.min(chunks.length - 1, Math.floor(progress * chunks.length));
  const opacity = interpolate(localFrame, [0, 8, Math.max(9, localDuration - 10), Math.max(10, localDuration - 2)], [0, 1, 1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  return (
    <div
      style={{
        position: "absolute",
        left: 0,
        right: 0,
        bottom: 42,
        display: "flex",
        justifyContent: "center",
        pointerEvents: "none",
        zIndex: 30,
        opacity,
      }}
    >
      <div
        style={{
          maxWidth: VIDEO_WIDTH * 0.78,
          padding: "0 24px",
          color: sceneCaptionColor(scene),
          fontFamily: "'Noto Sans SC', 'Microsoft YaHei', sans-serif",
          fontSize: 34,
          fontWeight: 500,
          lineHeight: 1.42,
          letterSpacing: 0,
          textAlign: "center",
          whiteSpace: "pre-wrap",
        }}
      >
        {chunks[index]}
      </div>
    </div>
  );
};

const DrawGlyphPath = ({ spec, op }: { spec: GlyphPathSpec; op: DrawOp }) => {
  const frame = useCurrentFrame();
  const progress = progressForOp(frame, op);
  const length = spec.dashLength;
  const fillOpacity = spec.fontOutline
    ? interpolate(progress, [0.68, 0.92], [0, spec.markerFillOpacity ?? 0.96], {
        extrapolateLeft: "clamp",
        extrapolateRight: "clamp",
      })
    : 0;
  return (
    <g>
      {fillOpacity > 0 ? <path d={spec.d} fill={spec.color} opacity={fillOpacity} stroke="none" /> : null}
      <path
        d={spec.d}
        fill="none"
        stroke={spec.color}
        strokeWidth={spec.strokeWidth}
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeDasharray={length}
        strokeDashoffset={length * (1 - progress)}
      />
    </g>
  );
};

const GlyphText = ({ scene }: { scene: SceneSpec }) => (
  <g data-font-family={FONT_FAMILY}>
    {(scene.glyphPaths ?? []).map((glyphPath) => {
      const op = scene.drawOps.find((drawOp) => drawOp.id === glyphPath.opId);
      return op ? <DrawGlyphPath key={glyphPath.opId} spec={glyphPath} op={op} /> : null;
    })}
  </g>
);

const DrawStroke = ({ spec, op }: { spec: StrokeSpec; op: DrawOp }) => {
  const frame = useCurrentFrame();
  const progress = progressForOp(frame, op);
  const length = spec.dashLength;
  return (
    <path
      d={spec.d}
      fill="none"
      stroke={spec.color}
      strokeWidth={spec.strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeDasharray={length}
      strokeDashoffset={length * (1 - progress)}
    />
  );
};

const RasterMaskStroke = ({ spec, op }: { spec: RasterStrokeSpec; op: DrawOp }) => {
  const frame = useCurrentFrame();
  const progress = progressForOp(frame, op);
  const length = spec.dashLength;
  return (
    <path
      d={spec.d}
      fill="none"
      stroke="white"
      strokeWidth={spec.revealWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeDasharray={length}
      strokeDashoffset={length * (1 - progress)}
    />
  );
};

const RasterRevealImage = ({ scene, sceneIndex }: { scene: SceneSpec; sceneIndex: number }) => {
  const frame = useCurrentFrame();
  const reveal = scene.rasterReveal;
  if (!reveal || !scene.referenceImageAsset) return null;
  if (reveal.renderMode === "direct") return null;
  const maskId = `raster-reveal-mask-${sceneIndex}`;
  const referenceImageAsset = scene.referenceImageAsset;
  const coverageStart = reveal.strokes.reduce((latest, stroke) => {
    const op = scene.drawOps.find((drawOp) => drawOp.id === stroke.opId);
    return op ? Math.max(latest, op.endFrame) : latest;
  }, 0);
  const finalCoverageOpacity = interpolate(frame, [coverageStart, coverageStart + 8], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  return (
    <g>
      <defs>
        <mask id={maskId} maskUnits="userSpaceOnUse">
          <rect x="0" y="0" width={VIDEO_WIDTH} height={VIDEO_HEIGHT} fill="black" />
          {reveal.strokes.map((stroke) => {
            const op = scene.drawOps.find((drawOp) => drawOp.id === stroke.opId);
            return op ? <RasterMaskStroke key={stroke.opId} spec={stroke} op={op} /> : null;
          })}
        </mask>
      </defs>
      <image
        href={staticFile(referenceImageAsset)}
        x={reveal.x}
        y={reveal.y}
        width={reveal.width}
        height={reveal.height}
        preserveAspectRatio="none"
        mask={`url(#${maskId})`}
        opacity={1 - finalCoverageOpacity}
      />
    </g>
  );
};

const RasterFinalOverlay = ({ scene }: { scene: SceneSpec }) => {
  const frame = useCurrentFrame();
  const reveal = scene.rasterReveal;
  if (!reveal || !scene.referenceImageAsset) return null;
  const referenceImageAsset = scene.referenceImageAsset;
  if (reveal.renderMode === "direct") {
    const appearFrame = reveal.directAppearFrame ?? 0;
    const opacity = interpolate(frame, [appearFrame, appearFrame + 10], [0, 1], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    });
    return (
      <Img
        src={staticFile(referenceImageAsset)}
        style={{
          position: "absolute",
          left: reveal.x,
          top: reveal.y,
          width: reveal.width,
          height: reveal.height,
          objectFit: reveal.fit === "cover" ? "cover" : "fill",
          opacity,
          pointerEvents: "none",
          zIndex: 4,
        }}
      />
    );
  }
  const coverageStart = reveal.strokes.reduce((latest, stroke) => {
    const op = scene.drawOps.find((drawOp) => drawOp.id === stroke.opId);
    return op ? Math.max(latest, op.endFrame) : latest;
  }, 0);
  const opacity = interpolate(frame, [coverageStart, coverageStart + 8], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  return (
    <Img
      src={staticFile(referenceImageAsset)}
      style={{
        position: "absolute",
        left: reveal.x,
        top: reveal.y,
        width: reveal.width,
        height: reveal.height,
        opacity,
        pointerEvents: "none",
        zIndex: 12,
      }}
    />
  );
};

const AnimeDoodle = ({ scene }: { scene: SceneSpec }) => {
  return (
    <>
      {scene.strokes
        .filter((stroke) => stroke.role === "doodle")
        .map((stroke) => {
          const op = scene.drawOps.find((drawOp) => drawOp.id === stroke.opId);
          return op ? <DrawStroke key={stroke.opId} spec={stroke} op={op} /> : null;
        })}
    </>
  );
};

const CartoonDiagram = ({ scene }: { scene: SceneSpec }) => (
  <>
    {scene.strokes
      .filter((stroke) => stroke.role !== "doodle")
      .map((stroke) => {
        const op = scene.drawOps.find((drawOp) => drawOp.id === stroke.opId);
        return op ? <DrawStroke key={stroke.opId} spec={stroke} op={op} /> : null;
      })}
  </>
);

const SceneAudio = ({ scene }: { scene: SceneSpec }) => {
  const segments = scene.audioSegments ?? [];
  if (segments.length > 0) {
    return (
      <>
        {segments.map((segment) =>
          segment.audioUrl ? (
            <Sequence key={segment.id} from={segment.audioStartFrame ?? segment.startFrame} durationInFrames={segment.audioSequenceDuration ?? Math.max(1, segment.endFrame - (segment.audioStartFrame ?? segment.startFrame))} layout="none">
              <Audio src={segment.audioUrl} />
            </Sequence>
          ) : null,
        )}
      </>
    );
  }
  return scene.audioUrl ? <Audio src={scene.audioUrl} /> : null;
};

const SceneTransitionWipe = ({ scene }: { scene: SceneSpec }) => {
  const frame = useCurrentFrame();
  if (scene.boardMode === "whiteboard" && scene.visualStyle === "teacher_whiteboard") return null;
  const transition = Math.max(0, scene.transitionFrames ?? 10);
  if (transition <= 0) return null;
  const start = Math.max(0, scene.duration - transition);
  const progress = interpolate(frame, [start, Math.max(start + 1, scene.duration - 1)], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  return (
    <div
      style={{
        position: "absolute",
        top: 0,
        bottom: 0,
        left: 0,
        width: `${progress * 100}%`,
        backgroundColor: sceneBackground(scene),
        pointerEvents: "none",
        zIndex: 40,
      }}
    />
  );
};

const WhiteboardScene = ({ scene, sceneIndex }: { scene: SceneSpec; sceneIndex: number }) => {
  const frame = useCurrentFrame();
  const drawOps = scene.drawOps;
  const orderedDrawOps = [...drawOps].sort((a, b) => a.startFrame - b.startFrame);
  const backgroundColor = sceneBackground(scene);
  const showHand = scene.handUsage !== "none" && scene.boardMode !== "chalkboard" && scene.visualStyle !== "math_chalkboard";
  const getActiveDrawOp = (frame: number) =>
    orderedDrawOps.find((op) => frame >= op.startFrame && frame <= op.endFrame);
  const getPenPosition = (frame: number) => {
    const active = getActiveDrawOp(frame);
    if (active) {
      const progress = progressForOp(frame, active);
      const point = pointOnPolyline(active.points, progress);
      return { x: point.x, y: point.y, visible: true };
    }
    const previous = [...orderedDrawOps].reverse().find((op) => op.endFrame < frame);
    const next = orderedDrawOps.find((op) => op.startFrame > frame);
    if (previous && next) {
      const gap = next.startFrame - previous.endFrame;
      if (gap > 0 && gap <= 26 && frame >= previous.endFrame && frame <= next.startFrame) {
        const from = pointOnPolyline(previous.points, 1);
        const to = pointOnPolyline(next.points, 0);
        const t = interpolate(frame, [previous.endFrame, next.startFrame], [0, 1], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
          easing: Easing.bezier(0.2, 0.8, 0.2, 1),
        });
        return {
          x: interpolate(t, [0, 1], [from.x, to.x]),
          y: interpolate(t, [0, 1], [from.y, to.y]),
          visible: true,
        };
      }
    }
    return { x: -400, y: -400, visible: false };
  };
  const pen = getPenPosition(frame);

  return (
    <AbsoluteFill style={{ backgroundColor, overflow: "hidden" }}>
      <SceneAudio scene={scene} />
      {scene.boardMode === "chalkboard" || scene.visualStyle === "math_chalkboard" ? (
        <div
          style={{
            position: "absolute",
            inset: 0,
            backgroundColor: backgroundColor,
            pointerEvents: "none",
            zIndex: 1,
          }}
        />
      ) : null}
      <svg style={{ position: "absolute", inset: 0, width: "100%", height: "100%", zIndex: 10 }} viewBox={`0 0 ${VIDEO_WIDTH} ${VIDEO_HEIGHT}`}>
        <RasterRevealImage scene={scene} sceneIndex={sceneIndex} />
        <AnimeDoodle scene={scene} />
        <CartoonDiagram scene={scene} />
        <GlyphText scene={scene} />
      </svg>
      <RasterFinalOverlay scene={scene} />
      <SubtitleOverlay scene={scene} />
      <HandPen tipX={pen.x} tipY={pen.y} visible={showHand && pen.visible} />
      <SceneTransitionWipe scene={scene} />
    </AbsoluteFill>
  );
};

export function GeneratedVideo() {
  let from = 0;
  return (
    <>
      {BACKGROUND_MUSIC_URL ? <Audio src={BACKGROUND_MUSIC_URL} volume={BACKGROUND_MUSIC_VOLUME} loop /> : null}
      {scenes.map((scene, index) => {
        const start = from;
        from += scene.duration;
        return (
          <Sequence key={`${scene.title}-${index}`} from={start} durationInFrames={scene.duration}>
            <WhiteboardScene scene={scene} sceneIndex={index} />
          </Sequence>
        );
      })}
    </>
  );
}
'''
