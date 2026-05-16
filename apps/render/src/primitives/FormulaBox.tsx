import React from "react";
import { useCurrentFrame, interpolate, Easing } from "remotion";
import { COLORS, FONT } from "./types";

interface Props {
  formula: string;
  label?: string;
  startFrame: number;
  durationFrames: number;
  x?: number;
  y?: number;
  fontSize?: number;
  color?: string;
}

/**
 * 公式框：从左到右逐字符显现（clip-path reveal），带紫色边框。
 * 支持一行标注 label。
 */
export const FormulaBox: React.FC<Props> = ({
  formula,
  label,
  startFrame,
  durationFrames,
  x = 960,
  y = 400,
  fontSize = 54,
  color = COLORS.purple,
}) => {
  const frame = useCurrentFrame();
  const localFrame = frame - startFrame;

  // 边框 draw-in：用透明度+scale模拟
  const borderProgress = interpolate(localFrame, [0, Math.max(durationFrames * 0.3, 1)], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.out(Easing.ease),
  });

  // 文字逐字出现
  const textProgress = interpolate(
    localFrame,
    [durationFrames * 0.2, Math.max(durationFrames * 0.75, durationFrames * 0.21)],
    [0, 100],
    {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
      easing: Easing.inOut(Easing.ease),
    }
  );

  if (localFrame < 0 || localFrame > durationFrames) return null;

  const chars = Array.from(formula);

  return (
    <div
      style={{
        position: "absolute",
        left: x,
        top: y,
        transform: "translate(-50%, -50%)",
        background: "rgba(206,147,216,0.08)",
        border: `2px solid ${color}`,
        borderRadius: 14,
        padding: "20px 40px",
        opacity: borderProgress,
        textAlign: "center",
        boxShadow: `0 0 40px ${color}30`,
      }}
    >
      {label && (
        <div
          style={{
            fontFamily: FONT.sans,
            fontSize: fontSize * 0.45,
            color: COLORS.chalkDim,
            marginBottom: 8,
            letterSpacing: "0.06em",
            opacity: borderProgress,
          }}
        >
          {label}
        </div>
      )}
      <div style={{ display: "flex", flexWrap: "wrap", justifyContent: "center" }}>
        {chars.map((char, i) => {
          const threshold = (i / Math.max(chars.length, 1)) * 100;
          const charOpacity = interpolate(textProgress, [threshold, threshold + 8], [0, 1], {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
          });
          return (
            <span
              key={i}
              style={{
                fontFamily: FONT.mono,
                fontSize,
                color,
                fontWeight: 500,
                letterSpacing: "0.06em",
                opacity: charOpacity,
                display: "inline-block",
                whiteSpace: char === " " ? "pre" : undefined,
              }}
            >
              {char}
            </span>
          );
        })}
      </div>
    </div>
  );
};
