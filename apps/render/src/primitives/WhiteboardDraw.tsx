import React from "react";
import { useCurrentFrame, useVideoConfig, interpolate, Easing } from "remotion";
import { COLORS, FONT } from "./types";

interface Props {
  content: string;
  startFrame: number;
  durationFrames: number;
  x?: number;
  y?: number;
  fontSize?: number;
  color?: string;
  bold?: boolean;
}

export const WhiteboardDraw: React.FC<Props> = ({
  content,
  startFrame,
  durationFrames,
  x = 960,
  y = 540,
  fontSize = 48,
  color = COLORS.chalk,
  bold = false,
}) => {
  const frame = useCurrentFrame();
  const localFrame = frame - startFrame;

  const opacity = interpolate(localFrame, [0, 12], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.out(Easing.ease),
  });

  // Handwriting reveal effect via clip-path width
  const revealProgress = interpolate(
    localFrame,
    [0, Math.max(durationFrames * 0.6, 1)],
    [0, 100],
    {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
      easing: Easing.inOut(Easing.ease),
    }
  );

  if (localFrame < 0 || localFrame > durationFrames) return null;

  return (
    <div
      style={{
        position: "absolute",
        left: x,
        top: y,
        transform: "translate(-50%, -50%)",
        opacity,
        overflow: "hidden",
        width: `${revealProgress}%`,
        whiteSpace: "nowrap",
      }}
    >
      <span
        style={{
          fontFamily: FONT.sans,
          fontSize,
          color,
          fontWeight: bold ? 700 : 400,
          letterSpacing: "0.02em",
          textShadow: "1px 1px 0 rgba(0,0,0,0.08)",
        }}
      >
        {content}
      </span>
    </div>
  );
};
