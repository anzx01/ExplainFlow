import React from "react";
import { useCurrentFrame, interpolate, Easing } from "remotion";
import { COLORS, FONT } from "./types";

interface Props {
  formula: string;  // Display as plain text (LaTeX rendering requires katex)
  startFrame: number;
  durationFrames: number;
  x?: number;
  y?: number;
  fontSize?: number;
}

export const FormulaReveal: React.FC<Props> = ({
  formula,
  startFrame,
  durationFrames,
  x = 960,
  y = 540,
  fontSize = 52,
}) => {
  const frame = useCurrentFrame();
  const localFrame = frame - startFrame;

  const opacity = interpolate(localFrame, [0, 15], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.out(Easing.cubic),
  });

  const scale = interpolate(localFrame, [0, 20], [0.8, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.out(Easing.back(1.5)),
  });

  if (localFrame < 0 || localFrame > durationFrames) return null;

  return (
    <div
      style={{
        position: "absolute",
        left: x,
        top: y,
        transform: `translate(-50%, -50%) scale(${scale})`,
        opacity,
        background: "#EEF2FF",
        border: "2px solid #7C3AED",
        borderRadius: 12,
        padding: "20px 32px",
      }}
    >
      <span
        style={{
          fontFamily: FONT.mono,
          fontSize,
          color: "#7C3AED",
          fontWeight: 500,
          letterSpacing: "0.04em",
        }}
      >
        {formula}
      </span>
    </div>
  );
};
