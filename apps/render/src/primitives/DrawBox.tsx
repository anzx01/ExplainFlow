import React from "react";
import { useCurrentFrame, interpolate, Easing } from "remotion";
import { COLORS } from "./types";

interface Props {
  x: number;
  y: number;
  width: number;
  height: number;
  startFrame: number;
  durationFrames: number;
  color?: string;
  strokeWidth?: number;
  label?: string;
  filled?: boolean;
}

/**
 * 画矩形边框：SVG stroke-dashoffset 沿矩形路径逐渐画出。
 */
export const DrawBox: React.FC<Props> = ({
  x,
  y,
  width,
  height,
  startFrame,
  durationFrames,
  color = COLORS.yellow,
  strokeWidth = 3,
  label,
  filled = false,
}) => {
  const frame = useCurrentFrame();
  const localFrame = frame - startFrame;

  const progress = interpolate(
    localFrame,
    [0, Math.max(durationFrames * 0.6, 1)],
    [0, 1],
    {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
      easing: Easing.inOut(Easing.ease),
    }
  );

  if (localFrame < 0 || localFrame > durationFrames) return null;

  const perimeter = 2 * (width + height);
  const dashOffset = perimeter * (1 - progress);

  return (
    <svg
      style={{ position: "absolute", left: 0, top: 0, width: "100%", height: "100%", overflow: "visible", pointerEvents: "none" }}
    >
      <rect
        x={x}
        y={y}
        width={width}
        height={height}
        stroke={color}
        strokeWidth={strokeWidth}
        fill={filled ? `${color}15` : "none"}
        strokeDasharray={perimeter}
        strokeDashoffset={dashOffset}
        strokeLinecap="round"
        rx={8}
      />
      {label && progress > 0.8 && (
        <text
          x={x + width / 2}
          y={y - 12}
          textAnchor="middle"
          fill={color}
          fontSize={24}
          fontFamily="'Noto Sans SC', sans-serif"
          opacity={interpolate(progress, [0.8, 1], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" })}
        >
          {label}
        </text>
      )}
    </svg>
  );
};
