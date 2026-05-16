import React from "react";
import { useCurrentFrame, interpolate, spring, useVideoConfig, Easing } from "remotion";
import { COLORS, FONT } from "./types";

interface Props {
  steps: string[];
  startFrame: number;
  durationFrames: number;
  x?: number;
  y?: number;
  fontSize?: number;
  accentColor?: string;
}

export const StepReveal: React.FC<Props> = ({
  steps,
  startFrame,
  durationFrames,
  x = 100,
  y = 180,
  fontSize = 54,
  accentColor = COLORS.blue,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const localFrame = frame - startFrame;

  if (localFrame < 0 || localFrame > durationFrames) return null;

  const perStep = durationFrames / Math.max(steps.length, 1);
  const circleR = fontSize * 0.52;

  return (
    <div style={{ position: "absolute", left: x, top: y, maxWidth: 1600 }}>
      {steps.map((step, i) => {
        const stepStart = i * perStep;
        const stepLocal = localFrame - stepStart;
        if (stepLocal < 0) return null;

        const isCurrent = stepLocal < perStep;

        const enterSpring = spring({ frame: stepLocal, fps, config: { damping: 18, stiffness: 180 } });
        const opacity = interpolate(stepLocal, [0, 12], [0, 1], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
          easing: Easing.out(Easing.ease),
        });
        const translateY = interpolate(enterSpring, [0, 1], [40, 0]);

        const circleColor = isCurrent ? accentColor : COLORS.lineGray;
        const textColor = isCurrent ? COLORS.ink : COLORS.inkLight;
        const numColor = isCurrent ? "#fff" : COLORS.lineGray;

        return (
          <div
            key={i}
            style={{
              display: "flex",
              alignItems: "flex-start",
              gap: 28,
              marginBottom: fontSize * 0.9,
              opacity,
              transform: `translateY(${translateY}px)`,
            }}
          >
            {/* 手绘风格编号圆 */}
            <div
              style={{
                width: circleR * 2,
                height: circleR * 2,
                borderRadius: "50%",
                background: circleColor,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                flexShrink: 0,
                // 轻微倾斜模拟手绘
                transform: `rotate(${(i % 3) - 1}deg)`,
                boxShadow: isCurrent ? `2px 3px 0 rgba(0,0,0,0.12)` : "none",
              }}
            >
              <span
                style={{
                  fontFamily: FONT.handwriting,
                  fontSize: fontSize * 0.7,
                  fontWeight: 700,
                  color: numColor,
                  lineHeight: 1,
                }}
              >
                {i + 1}
              </span>
            </div>

            <span
              style={{
                fontFamily: FONT.handwriting,
                fontSize,
                color: textColor,
                fontWeight: isCurrent ? 700 : 400,
                lineHeight: 1.35,
                letterSpacing: "0.01em",
                paddingTop: circleR * 0.25,
              }}
            >
              {step}
            </span>
          </div>
        );
      })}
    </div>
  );
};
