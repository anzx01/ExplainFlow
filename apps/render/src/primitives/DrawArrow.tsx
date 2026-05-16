import React from "react";
import { useCurrentFrame, interpolate, Easing } from "remotion";
import { COLORS, FONT } from "./types";

interface Props {
  from: { x: number; y: number };
  to: { x: number; y: number };
  startFrame: number;
  durationFrames: number;
  label?: string;
  color?: string;
  strokeWidth?: number;
  curved?: boolean;
}

/**
 * SVG 路径动画箭头：用 stroke-dashoffset 模拟手绘逐步画出效果。
 */
export const DrawArrow: React.FC<Props> = ({
  from,
  to,
  startFrame,
  durationFrames,
  label,
  color = COLORS.accent,
  strokeWidth = 3,
  curved = false,
}) => {
  const frame = useCurrentFrame();
  const localFrame = frame - startFrame;

  const progress = interpolate(
    localFrame,
    [0, Math.max(durationFrames * 0.7, 1)],
    [0, 1],
    {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
      easing: Easing.inOut(Easing.ease),
    }
  );

  const labelOpacity = interpolate(localFrame, [durationFrames * 0.6, durationFrames * 0.9], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  if (localFrame < 0 || localFrame > durationFrames) return null;

  const dx = to.x - from.x;
  const dy = to.y - from.y;
  const totalLen = Math.sqrt(dx * dx + dy * dy);

  // 控制点（弯曲箭头）
  const cpX = (from.x + to.x) / 2 - dy * 0.2;
  const cpY = (from.y + to.y) / 2 + dx * 0.2;

  const pathD = curved
    ? `M ${from.x} ${from.y} Q ${cpX} ${cpY} ${to.x} ${to.y}`
    : `M ${from.x} ${from.y} L ${to.x} ${to.y}`;

  const dashLen = totalLen * 1.05;
  const dashOffset = dashLen * (1 - progress);

  const midX = curved ? cpX : (from.x + to.x) / 2;
  const midY = curved ? cpY - 20 : (from.y + to.y) / 2 - 20;

  const arrowId = `arrow-${from.x}-${from.y}-${to.x}`;

  return (
    <svg
      style={{ position: "absolute", left: 0, top: 0, width: "100%", height: "100%", overflow: "visible", pointerEvents: "none" }}
    >
      <defs>
        <marker id={arrowId} markerWidth="10" markerHeight="7" refX="8" refY="3.5" orient="auto">
          <polygon points="0 0, 10 3.5, 0 7" fill={color} opacity={progress > 0.85 ? 1 : 0} />
        </marker>
      </defs>
      <path
        d={pathD}
        stroke={color}
        strokeWidth={strokeWidth}
        fill="none"
        strokeDasharray={dashLen}
        strokeDashoffset={dashOffset}
        strokeLinecap="round"
        markerEnd={`url(#${arrowId})`}
      />
      {label && (
        <text
          x={midX}
          y={midY}
          textAnchor="middle"
          fill={color}
          fontSize={26}
          fontFamily="'Noto Sans SC', sans-serif"
          opacity={labelOpacity}
        >
          {label}
        </text>
      )}
    </svg>
  );
};
