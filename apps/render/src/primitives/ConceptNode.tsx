import React from "react";
import { useCurrentFrame, interpolate, spring, useVideoConfig, Easing } from "remotion";
import { COLORS, FONT } from "./types";

interface Props {
  label: string;
  nodeType?: "concept" | "formula" | "example" | "conclusion" | "process";
  startFrame: number;
  durationFrames: number;
  x?: number;
  y?: number;
}

const TYPE_COLORS: Record<string, string> = {
  concept: COLORS.accent,
  formula: COLORS.purple,
  example: COLORS.green,
  conclusion: COLORS.orange,
  process: COLORS.gray,
};

export const ConceptNode: React.FC<Props> = ({
  label,
  nodeType = "concept",
  startFrame,
  durationFrames,
  x = 960,
  y = 540,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const localFrame = frame - startFrame;

  const scale = spring({
    frame: localFrame,
    fps,
    config: { damping: 14, stiffness: 180 },
  });

  const opacity = interpolate(localFrame, [0, 10], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.out(Easing.ease),
  });

  if (localFrame < 0 || localFrame > durationFrames) return null;

  const color = TYPE_COLORS[nodeType] ?? COLORS.accent;

  return (
    <div
      style={{
        position: "absolute",
        left: x,
        top: y,
        transform: `translate(-50%, -50%) scale(${scale})`,
        opacity,
        background: "#fff",
        border: `3px solid ${color}`,
        borderRadius: 16,
        padding: "18px 32px",
        boxShadow: `0 8px 32px ${color}33`,
        minWidth: 200,
        textAlign: "center",
      }}
    >
      <div style={{ fontFamily: FONT.sans, fontSize: 36, color: COLORS.chalk, fontWeight: 600 }}>
        {label}
      </div>
      <div
        style={{
          marginTop: 6,
          fontFamily: FONT.sans,
          fontSize: 18,
          color,
          fontWeight: 500,
          textTransform: "uppercase",
          letterSpacing: "0.08em",
        }}
      >
        {nodeType}
      </div>
    </div>
  );
};
