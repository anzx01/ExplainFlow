import React from "react";
import { useCurrentFrame, interpolate, Easing } from "remotion";
import { COLORS } from "./types";

interface Point { x: number; y: number; }

interface Props {
  from: Point;
  to: Point;
  label?: string;
  startFrame: number;
  durationFrames: number;
  color?: string;
}

export const ArrowConnect: React.FC<Props> = ({
  from,
  to,
  label,
  startFrame,
  durationFrames,
  color = COLORS.accent,
}) => {
  const frame = useCurrentFrame();
  const localFrame = frame - startFrame;

  const progress = interpolate(localFrame, [0, Math.max(durationFrames * 0.7, 1)], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.inOut(Easing.ease),
  });

  if (localFrame < 0 || localFrame > durationFrames) return null;

  const dx = to.x - from.x;
  const dy = to.y - from.y;
  const len = Math.sqrt(dx * dx + dy * dy);
  const midX = from.x + dx * 0.5;
  const midY = from.y + dy * 0.5;

  // SVG path: straight line with arrowhead
  const endX = from.x + dx * progress;
  const endY = from.y + dy * progress;

  return (
    <svg
      style={{ position: "absolute", left: 0, top: 0, width: "100%", height: "100%", overflow: "visible" }}
    >
      <defs>
        <marker id="arrowhead" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
          <polygon points="0 0, 10 3.5, 0 7" fill={color} />
        </marker>
      </defs>
      <line
        x1={from.x}
        y1={from.y}
        x2={endX}
        y2={endY}
        stroke={color}
        strokeWidth={2.5}
        strokeDasharray="none"
        markerEnd={progress > 0.9 ? "url(#arrowhead)" : undefined}
      />
      {label && progress > 0.5 && (
        <text
          x={midX}
          y={midY - 10}
          textAnchor="middle"
          fill={color}
          fontSize={16}
          fontFamily="'Noto Sans SC', sans-serif"
        >
          {label}
        </text>
      )}
    </svg>
  );
};
