import React from "react";
import { useCurrentFrame, interpolate, Easing } from "remotion";
import { COLORS } from "./types";

/**
 * 确定性抖动：用坐标和 seed 的三角函数，保证每帧相同坐标输出相同偏移，不会闪烁。
 */
function jitterPt(x: number, y: number, seed: number, amp = 3): [number, number] {
  return [
    x + Math.sin(seed * 127.1 + x * 0.017) * amp,
    y + Math.sin(seed * 311.7 + y * 0.013) * amp,
  ];
}

/** SVG stroke-dashoffset 画路径 */
function AnimatedPath({
  d,
  length,
  color,
  strokeWidth,
  startFrame,
  drawFrames,
  fill,
}: {
  d: string;
  length: number;
  color: string;
  strokeWidth: number;
  startFrame: number;
  drawFrames: number;
  fill?: string;
}) {
  const frame = useCurrentFrame();
  const localFrame = frame - startFrame;
  const progress = interpolate(localFrame, [0, Math.max(drawFrames, 1)], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.inOut(Easing.ease),
  });
  return (
    <path
      d={d}
      stroke={color}
      strokeWidth={strokeWidth}
      fill={fill ?? "none"}
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeDasharray={length}
      strokeDashoffset={length * (1 - progress)}
    />
  );
}

// ───────────── 不规则手绘矩形 ─────────────
interface SketchRectProps {
  x: number;
  y: number;
  width: number;
  height: number;
  startFrame: number;
  durationFrames: number;
  color?: string;
  strokeWidth?: number;
  fill?: string;
  label?: string;
  labelFontSize?: number;
}

/**
 * 手绘风格矩形：四条边略带不规则偏移，模拟手绘效果。
 * 用 stroke-dashoffset 依次画出每条边。
 */
export const SketchRect: React.FC<SketchRectProps> = ({
  x,
  y,
  width,
  height,
  startFrame,
  durationFrames,
  color = COLORS.blue,
  strokeWidth = 3,
  fill,
  label,
  labelFontSize = 28,
}) => {
  const frame = useCurrentFrame();
  const localFrame = frame - startFrame;

  if (localFrame < 0 || localFrame > durationFrames) return null;

  const perimeter = 2 * (width + height);
  const drawFrames = durationFrames * 0.7;
  const amp = Math.max(strokeWidth * 1.2, 4);

  // 四个角用 jitterPt 做确定性抖动，让矩形边线不那么机械
  const [x0, y0] = jitterPt(x, y, 1, amp);
  const [x1, y1] = jitterPt(x + width, y, 2, amp);
  const [x2, y2] = jitterPt(x + width, y + height, 3, amp);
  const [x3, y3] = jitterPt(x, y + height, 4, amp);
  // 每条边中点也轻微抖动，让边线略带弧度
  const [mx0, my0] = jitterPt((x + x + width) / 2, y, 5, amp * 0.6);
  const [mx1, my1] = jitterPt(x + width, (y + y + height) / 2, 6, amp * 0.6);
  const [mx2, my2] = jitterPt((x + x + width) / 2, y + height, 7, amp * 0.6);
  const [mx3, my3] = jitterPt(x, (y + y + height) / 2, 8, amp * 0.6);

  const path = [
    `M ${x0} ${y0}`,
    `Q ${mx0} ${my0} ${x1} ${y1}`,
    `Q ${mx1} ${my1} ${x2} ${y2}`,
    `Q ${mx2} ${my2} ${x3} ${y3}`,
    `Q ${mx3} ${my3} ${x0} ${y0}`,
  ].join(" ");

  const labelOpacity = interpolate(localFrame, [drawFrames, drawFrames + 10], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <svg
      style={{ position: "absolute", left: 0, top: 0, width: "100%", height: "100%", overflow: "visible", pointerEvents: "none" }}
    >
      {fill && (
        <rect
          x={x}
          y={y}
          width={width}
          height={height}
          fill={fill}
          opacity={interpolate(localFrame, [drawFrames * 0.5, drawFrames], [0, 1], {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
          })}
          rx={4}
        />
      )}
      <AnimatedPath
        d={path}
        length={perimeter * 1.05}
        color={color}
        strokeWidth={strokeWidth}
        startFrame={0}
        drawFrames={drawFrames}
        fill="none"
      />
      {label && (
        <text
          x={x + width / 2}
          y={y - labelFontSize * 0.5}
          textAnchor="middle"
          fill={color}
          fontSize={labelFontSize}
          fontFamily="'Caveat', cursive"
          fontWeight={700}
          opacity={labelOpacity}
        >
          {label}
        </text>
      )}
    </svg>
  );
};

// ───────────── 手绘箭头 ─────────────
interface SketchArrowProps {
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
 * 手绘风格箭头：路径略带弧度，箭头头部用短线（不是三角形填充）。
 */
export const SketchArrow: React.FC<SketchArrowProps> = ({
  from,
  to,
  startFrame,
  durationFrames,
  label,
  color = COLORS.ink,
  strokeWidth = 3,
  curved = true,
}) => {
  const frame = useCurrentFrame();
  const localFrame = frame - startFrame;

  if (localFrame < 0 || localFrame > durationFrames) return null;

  const drawFrames = durationFrames * 0.75;
  const dx = to.x - from.x;
  const dy = to.y - from.y;
  const len = Math.sqrt(dx * dx + dy * dy);

  // 控制点（弯曲）+ 确定性抖动让箭头线条不那么机械
  const baseCpX = (from.x + to.x) / 2 + dy * 0.15;
  const baseCpY = (from.y + to.y) / 2 - dx * 0.15;
  const [cpX, cpY] = jitterPt(baseCpX, baseCpY, 9, Math.max(len * 0.02, 4));
  const [fx, fy] = jitterPt(from.x, from.y, 10, 3);
  const [tx, ty] = jitterPt(to.x, to.y, 11, 3);

  const mainPath = curved
    ? `M ${fx} ${fy} Q ${cpX} ${cpY} ${tx} ${ty}`
    : `M ${fx} ${fy} L ${tx} ${ty}`;

  // 手绘箭头头部：两条短线
  const angle = Math.atan2(dy, dx);
  const hw = Math.min(20, len * 0.12);
  const ah1 = `M ${to.x} ${to.y} L ${to.x - hw * Math.cos(angle - 0.45)} ${to.y - hw * Math.sin(angle - 0.45)}`;
  const ah2 = `M ${to.x} ${to.y} L ${to.x - hw * Math.cos(angle + 0.45)} ${to.y - hw * Math.sin(angle + 0.45)}`;

  const labelOpacity = interpolate(localFrame, [drawFrames * 0.7, drawFrames], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const midX = curved ? cpX : (from.x + to.x) / 2;
  const midY = (curved ? cpY : (from.y + to.y) / 2) - 22;

  return (
    <svg
      style={{ position: "absolute", left: 0, top: 0, width: "100%", height: "100%", overflow: "visible", pointerEvents: "none" }}
    >
      <AnimatedPath d={mainPath} length={len * 1.15} color={color} strokeWidth={strokeWidth} startFrame={0} drawFrames={drawFrames} />
      <AnimatedPath d={ah1} length={hw * 1.2} color={color} strokeWidth={strokeWidth} startFrame={drawFrames * 0.7} drawFrames={drawFrames * 0.3} />
      <AnimatedPath d={ah2} length={hw * 1.2} color={color} strokeWidth={strokeWidth} startFrame={drawFrames * 0.7} drawFrames={drawFrames * 0.3} />
      {label && (
        <text x={midX} y={midY} textAnchor="middle" fill={color} fontSize={28} fontFamily="'Caveat', cursive" opacity={labelOpacity}>
          {label}
        </text>
      )}
    </svg>
  );
};

// ───────────── 手绘下划线/高亮线 ─────────────
interface SketchUnderlineProps {
  x: number;
  y: number;
  width: number;
  startFrame: number;
  durationFrames: number;
  color?: string;
  strokeWidth?: number;
  double?: boolean;
}

export const SketchUnderline: React.FC<SketchUnderlineProps> = ({
  x,
  y,
  width,
  startFrame,
  durationFrames,
  color = COLORS.red,
  strokeWidth = 4,
  double: isDouble = false,
}) => {
  const frame = useCurrentFrame();
  const localFrame = frame - startFrame;

  if (localFrame < 0 || localFrame > durationFrames) return null;

  const drawFrames = durationFrames * 0.8;
  // 略带波浪的路径
  const path1 = `M ${x} ${y + 2} Q ${x + width * 0.4} ${y - 3} ${x + width} ${y + 1}`;
  const path2 = `M ${x} ${y + 9} Q ${x + width * 0.5} ${y + 6} ${x + width} ${y + 10}`;

  return (
    <svg
      style={{ position: "absolute", left: 0, top: 0, width: "100%", height: "100%", overflow: "visible", pointerEvents: "none" }}
    >
      <AnimatedPath d={path1} length={width * 1.05} color={color} strokeWidth={strokeWidth} startFrame={0} drawFrames={drawFrames} />
      {isDouble && (
        <AnimatedPath d={path2} length={width * 1.05} color={color} strokeWidth={strokeWidth} startFrame={drawFrames * 0.3} drawFrames={drawFrames * 0.7} />
      )}
    </svg>
  );
};

// ───────────── 手绘圆圈高亮 ─────────────
interface SketchCircleProps {
  cx: number;
  cy: number;
  rx: number;
  ry?: number;
  startFrame: number;
  durationFrames: number;
  color?: string;
  strokeWidth?: number;
}

export const SketchCircle: React.FC<SketchCircleProps> = ({
  cx,
  cy,
  rx,
  ry,
  startFrame,
  durationFrames,
  color = COLORS.red,
  strokeWidth = 3,
}) => {
  const frame = useCurrentFrame();
  const localFrame = frame - startFrame;

  if (localFrame < 0 || localFrame > durationFrames) return null;

  const _ry = ry ?? rx * 0.6;
  const perimeter = Math.PI * (3 * (rx + _ry) - Math.sqrt((3 * rx + _ry) * (rx + 3 * _ry)));
  const drawFrames = durationFrames * 0.7;

  const progress = interpolate(localFrame, [0, drawFrames], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.inOut(Easing.ease),
  });

  return (
    <svg
      style={{ position: "absolute", left: 0, top: 0, width: "100%", height: "100%", overflow: "visible", pointerEvents: "none" }}
    >
      <ellipse
        cx={cx}
        cy={cy}
        rx={rx}
        ry={_ry}
        stroke={color}
        strokeWidth={strokeWidth}
        fill="none"
        strokeLinecap="round"
        strokeDasharray={perimeter}
        strokeDashoffset={perimeter * (1 - progress)}
        transform={`rotate(-8, ${cx}, ${cy})`}
      />
    </svg>
  );
};
