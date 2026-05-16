import React from "react";
import { useCurrentFrame, interpolate, Easing } from "remotion";
import { FONT } from "./types";

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
    [0, 8, durationFrames - 8, durationFrames],
    [0, 1, 1, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
  );

  if (localFrame < 0 || localFrame > durationFrames) return null;

  return (
    <div
      style={{
        position: "absolute",
        bottom: 60,
        left: "50%",
        transform: "translateX(-50%)",
        opacity,
        background: "rgba(0,0,0,0.72)",
        borderRadius: 8,
        padding: "10px 28px",
        maxWidth: 1400,
        textAlign: "center",
      }}
    >
      <span
        style={{
          fontFamily: FONT.sans,
          fontSize: 30,
          color: "#FFFFFF",
          fontWeight: 400,
          lineHeight: 1.5,
          letterSpacing: "0.04em",
        }}
      >
        {text}
      </span>
    </div>
  );
};
