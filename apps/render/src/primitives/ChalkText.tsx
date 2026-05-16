import React from "react";
import { useCurrentFrame, interpolate, Easing } from "remotion";
import { COLORS, FONT } from "./types";

interface Props {
  text: string;
  startFrame: number;
  durationFrames: number;
  x?: number;
  y?: number;
  fontSize?: number;
  color?: string;
  fontFamily?: string;
  bold?: boolean;
  align?: "left" | "center" | "right";
  maxWidth?: number;
}

/**
 * 文字逐字"写出"效果：每个字符依次淡入+轻微向上位移，模拟手写节奏。
 * 配合 stroke-dashoffset 的纯字符版本（无需 SVG 字体）。
 */
export const ChalkText: React.FC<Props> = ({
  text,
  startFrame,
  durationFrames,
  x = 960,
  y = 200,
  fontSize = 56,
  color = COLORS.chalk,
  fontFamily = FONT.sans,
  bold = false,
  align = "left",
  maxWidth = 1600,
}) => {
  const frame = useCurrentFrame();
  const localFrame = frame - startFrame;

  if (localFrame < 0 || localFrame > durationFrames) return null;

  const chars = Array.from(text);
  // 字符逐一出现，整体用 60% 的时间写完
  const writeFrames = Math.max(durationFrames * 0.65, 1);

  return (
    <div
      style={{
        position: "absolute",
        left: align === "center" ? "50%" : x,
        top: y,
        transform: align === "center" ? "translateX(-50%)" : undefined,
        maxWidth,
        fontFamily,
        fontSize,
        fontWeight: bold ? 700 : 500,
        color,
        lineHeight: 1.4,
        letterSpacing: "0.04em",
        display: "flex",
        flexWrap: "wrap",
        gap: 0,
      }}
    >
      {chars.map((char, i) => {
        const charStart = (i / chars.length) * writeFrames;
        const charProgress = interpolate(localFrame, [charStart, charStart + 6], [0, 1], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
          easing: Easing.out(Easing.ease),
        });
        const translateY = interpolate(charProgress, [0, 1], [8, 0]);
        return (
          <span
            key={i}
            style={{
              opacity: charProgress,
              transform: `translateY(${translateY}px)`,
              display: "inline-block",
              whiteSpace: char === " " ? "pre" : undefined,
            }}
          >
            {char}
          </span>
        );
      })}
    </div>
  );
};
