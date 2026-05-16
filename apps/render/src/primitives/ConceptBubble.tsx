import React from "react";
import { useCurrentFrame, interpolate, spring, useVideoConfig, Easing } from "remotion";
import { COLORS, FONT } from "./types";

interface Props {
  label: string;
  subtitle?: string;
  nodeType?: "concept" | "formula" | "example" | "conclusion" | "process";
  startFrame: number;
  durationFrames: number;
  x?: number;
  y?: number;
  size?: "sm" | "md" | "lg";
}

const TYPE_CONFIG: Record<string, { color: string; bg: string }> = {
  concept:    { color: COLORS.accent,  bg: "rgba(79,195,247,0.12)" },
  formula:    { color: COLORS.purple,  bg: "rgba(206,147,216,0.12)" },
  example:    { color: COLORS.green,   bg: "rgba(129,199,132,0.12)" },
  conclusion: { color: COLORS.orange,  bg: "rgba(255,183,77,0.12)" },
  process:    { color: COLORS.gray,    bg: "rgba(144,164,174,0.10)" },
};

const SIZE_CONFIG = {
  sm: { fontSize: 28, padding: "14px 24px", minWidth: 160 },
  md: { fontSize: 38, padding: "20px 36px", minWidth: 220 },
  lg: { fontSize: 48, padding: "24px 44px", minWidth: 280 },
};

/**
 * 概念气泡：弹簧缩放入场，带颜色分类，圆角卡片样式。
 */
export const ConceptBubble: React.FC<Props> = ({
  label,
  subtitle,
  nodeType = "concept",
  startFrame,
  durationFrames,
  x = 960,
  y = 400,
  size = "md",
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const localFrame = frame - startFrame;

  const scale = spring({
    frame: localFrame,
    fps,
    config: { damping: 14, stiffness: 200 },
  });

  const opacity = interpolate(localFrame, [0, 8], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.out(Easing.ease),
  });

  if (localFrame < 0 || localFrame > durationFrames) return null;

  const { color, bg } = TYPE_CONFIG[nodeType] ?? TYPE_CONFIG.concept;
  const { fontSize, padding, minWidth } = SIZE_CONFIG[size];

  return (
    <div
      style={{
        position: "absolute",
        left: x,
        top: y,
        transform: `translate(-50%, -50%) scale(${scale})`,
        opacity,
        background: bg,
        border: `2px solid ${color}`,
        borderRadius: 16,
        padding,
        minWidth,
        textAlign: "center",
        boxShadow: `0 0 32px ${color}40`,
      }}
    >
      <div style={{ fontFamily: FONT.sans, fontSize, color: COLORS.chalk, fontWeight: 600, lineHeight: 1.3 }}>
        {label}
      </div>
      {subtitle && (
        <div style={{ fontFamily: FONT.mono, fontSize: fontSize * 0.5, color, marginTop: 6, letterSpacing: "0.08em" }}>
          {subtitle}
        </div>
      )}
    </div>
  );
};
