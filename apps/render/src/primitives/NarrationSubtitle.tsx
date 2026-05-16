import React from "react";
import { useCurrentFrame, interpolate, Easing } from "remotion";
import { COLORS, FONT } from "./types";

interface Props {
  text: string;
  startFrame: number;
  durationFrames: number;
}

export const NarrationSubtitle: React.FC<Props> = ({ text, startFrame, durationFrames }) => {
  const frame = useCurrentFrame();
  const localFrame = frame - startFrame;

  const opacity = interpolate(
    localFrame,
    [0, 8, durationFrames - 6, durationFrames],
    [0, 1, 1, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
  );

  if (localFrame < 0 || localFrame > durationFrames) return null;

  return (
    <div
      style={{
        position: "absolute",
        bottom: 48,
        left: "50%",
        transform: "translateX(-50%)",
        opacity,
        // 白底风格字幕条：半透明白色背景 + 深色文字
        background: "rgba(255,255,255,0.88)",
        borderRadius: 10,
        padding: "12px 36px",
        maxWidth: 1440,
        textAlign: "center",
        boxShadow: "0 2px 12px rgba(0,0,0,0.10)",
        border: `1px solid ${COLORS.lineGray}`,
      }}
    >
      <span
        style={{
          fontFamily: FONT.sans,
          fontSize: 32,
          color: COLORS.ink,
          fontWeight: 400,
          lineHeight: 1.55,
          letterSpacing: "0.04em",
        }}
      >
        {text}
      </span>
    </div>
  );
};
