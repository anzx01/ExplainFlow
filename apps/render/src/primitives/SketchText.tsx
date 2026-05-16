import React from "react";
import { useCurrentFrame, interpolate, Easing } from "remotion";
import { evolvePath, getLength, getPointAtLength } from "@remotion/paths";
import { COLORS, FONT } from "./types";
import type { SvgTextPath } from "./types";

interface Props {
  text: string;
  startFrame: number;
  durationFrames: number;
  x?: number;
  y?: number;
  fontSize?: number;
  color?: string;
  bold?: boolean;
  align?: "left" | "center" | "right";
  maxWidth?: number;
  underline?: boolean;
  underlineColor?: string;
  /** 由 server.mjs 注入的 SVG path 数据，有则走真实描绘动画 */
  svgPath?: SvgTextPath | null;
}

/**
 * 返回当前进度下笔尖在 SVG 坐标系中的位置（相对于 svgPath 的 bbox 左上角）。
 * 供 WhiteboardScene 的 getHandPos 使用。
 */
export function getTextTipPosition(
  progress: number,
  svgPath: SvgTextPath,
): { x: number; y: number } {
  try {
    const len = getLength(svgPath.d);
    if (len === 0) return { x: svgPath.bbox.x1, y: svgPath.bbox.y1 };
    const pt = getPointAtLength(svgPath.d, Math.min(progress, 0.9999) * len);
    return { x: pt.x, y: pt.y };
  } catch {
    return { x: svgPath.bbox.x1, y: svgPath.bbox.y1 };
  }
}

/**
 * 手写文字组件。
 *
 * 当有 svgPath 时：用 evolvePath() 沿字形轮廓真实描绘（opentype.js 预处理）。
 * 无 svgPath 时：fallback 到 scaleX 逐字划出（兼容中文等无路径数据的字符）。
 */
export const SketchText: React.FC<Props> = ({
  text,
  startFrame,
  durationFrames,
  x = 100,
  y = 100,
  fontSize = 80,
  color = COLORS.ink,
  bold = false,
  align = "left",
  maxWidth = 1700,
  underline = false,
  underlineColor,
  svgPath,
}) => {
  const frame = useCurrentFrame();
  const localFrame = frame - startFrame;

  if (localFrame < 0 || localFrame > durationFrames) return null;

  const writeFrames = durationFrames * 0.7;
  const progress = interpolate(localFrame, [0, Math.max(writeFrames, 1)], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.inOut(Easing.ease),
  });

  // ── 有 SVG path：真实字形轮廓描绘 ──
  if (svgPath?.d) {
    let strokeDasharray: string;
    let strokeDashoffset: number;
    try {
      const evolved = evolvePath(progress, svgPath.d);
      strokeDasharray = evolved.strokeDasharray;
      strokeDashoffset = evolved.strokeDashoffset;
    } catch {
      // path 数据异常（如含 NaN 的 .notdef 字形），fallback 到 scaleX 方案
      return <SketchTextFallback
        text={text} startFrame={startFrame} durationFrames={durationFrames}
        x={x} y={y} fontSize={fontSize} color={color} bold={bold}
        align={align} maxWidth={maxWidth} underline={underline} underlineColor={underlineColor ?? color}
      />;
    }
    const bw = svgPath.bbox.x2 - svgPath.bbox.x1 + 20;
    const bh = svgPath.bbox.y2 - svgPath.bbox.y1 + 20;
    const vx = svgPath.bbox.x1 - 5;
    const vy = svgPath.bbox.y1 - 5;

    const underlineStart = writeFrames;
    const underlineProgress = interpolate(
      localFrame,
      [underlineStart, underlineStart + 18],
      [0, 1],
      { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.out(Easing.ease) },
    );
    const lineColor = underlineColor ?? color;
    const underlineW = svgPath.width;

    return (
      <svg
        style={{
          position: "absolute",
          left: align === "center" ? "50%" : x,
          top: y,
          transform: align === "center" ? "translateX(-50%)" : undefined,
          overflow: "visible",
        }}
        width={bw}
        height={bh}
        viewBox={`${vx} ${vy} ${bw} ${bh}`}
      >
        <path
          d={svgPath.d}
          fill="none"
          stroke={color}
          strokeWidth={bold ? 3.5 : 2.5}
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeDasharray={strokeDasharray}
          strokeDashoffset={strokeDashoffset}
        />
        {underline && underlineProgress > 0 && (
          <path
            d={`M ${svgPath.bbox.x1} ${svgPath.bbox.y2 + 8} Q ${svgPath.bbox.x1 + underlineW * 0.4} ${svgPath.bbox.y2 + 13} ${svgPath.bbox.x1 + underlineW * underlineProgress} ${svgPath.bbox.y2 + 8}`}
            stroke={lineColor}
            strokeWidth={Math.max(fontSize * 0.04, 3)}
            fill="none"
            strokeLinecap="round"
            strokeDasharray={underlineW * 1.05}
            strokeDashoffset={(underlineW * 1.05) * (1 - underlineProgress)}
          />
        )}
      </svg>
    );
  }

  // ── Fallback：scaleX 逐字划出（中文等无路径数据时使用）──
  return <SketchTextFallback
    text={text} startFrame={startFrame} durationFrames={durationFrames}
    x={x} y={y} fontSize={fontSize} color={color} bold={bold}
    align={align} maxWidth={maxWidth} underline={underline} underlineColor={underlineColor ?? color}
  />;
};

/** Fallback：scaleX 逐字划出，用于中文等无 SVG path 数据的字符 */
function SketchTextFallback({
  text, startFrame, durationFrames, x, y, fontSize, color, bold, align, maxWidth, underline, underlineColor,
}: Required<Omit<Props, "svgPath">>) {
  const frame = useCurrentFrame();
  const localFrame = frame - startFrame;

  const chars = Array.from(text);
  const writeFrames = durationFrames * 0.65;
  const perChar = writeFrames / Math.max(chars.length, 1);

  const underlineStart = writeFrames;
  const underlineLen = maxWidth;
  const underlineProgress = interpolate(
    localFrame,
    [underlineStart, underlineStart + 18],
    [0, 1],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.out(Easing.ease) },
  );
  const lineColor = underlineColor ?? color;

  return (
    <div style={{ position: "absolute", left: align === "center" ? "50%" : x, top: y, transform: align === "center" ? "translateX(-50%)" : undefined, maxWidth }}>
      <div style={{ display: "flex", flexWrap: "wrap", lineHeight: 1.25 }}>
        {chars.map((char, i) => {
          const charRevealStart = i * perChar;
          const scaleX = interpolate(localFrame, [charRevealStart, charRevealStart + Math.max(perChar * 0.6, 3)], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.out(Easing.cubic) });
          const opacity = interpolate(localFrame, [charRevealStart, charRevealStart + Math.max(perChar * 0.5, 2)], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
          const seed1 = (i * 13 + 7) % 17;
          const seed2 = (i * 7 + 3) % 11;
          const seed3 = (i * 11 + 5) % 13;
          const jitterY = (seed1 / 17 - 0.5) * fontSize * 0.3;
          const jitterRot = (seed2 / 11 - 0.5) * 10;
          const jitterSize = fontSize * (1 + (seed3 / 13 - 0.5) * 0.16);
          const translateY = interpolate(scaleX, [0, 1], [jitterY - fontSize * 0.25, jitterY]);
          return (
            <span key={i} style={{ fontFamily: FONT.handwriting, fontSize: jitterSize, fontWeight: bold ? 700 : 400, color, opacity, transform: `scaleX(${scaleX}) translateY(${translateY}px) rotate(${jitterRot * (1 - scaleX * 0.7)}deg)`, transformOrigin: "left center", display: "inline-block", whiteSpace: char === " " ? "pre" : undefined, marginRight: char === " " ? fontSize * 0.18 : fontSize * 0.01 }}>
              {char}
            </span>
          );
        })}
      </div>
      {underline && underlineProgress > 0 && (
        <svg style={{ position: "absolute", bottom: -10, left: 0, width: "100%", height: 16, overflow: "visible" }}>
          <path d={`M 0 6 Q ${underlineLen * 0.25} 10, ${underlineLen * 0.5} 6 Q ${underlineLen * 0.75} 2, ${underlineLen * underlineProgress} 6`} stroke={lineColor} strokeWidth={Math.max(fontSize * 0.045, 3)} fill="none" strokeLinecap="round" strokeDasharray={underlineLen * 1.05} strokeDashoffset={(underlineLen * 1.05) * (1 - underlineProgress)} />
        </svg>
      )}
    </div>
  );
}

