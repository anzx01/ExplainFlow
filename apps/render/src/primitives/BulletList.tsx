import React from "react";
import { useCurrentFrame, interpolate, spring, useVideoConfig, Easing } from "remotion";
import { COLORS, FONT } from "./types";

interface Props {
  items: string[];
  startFrame: number;
  durationFrames: number;
  x?: number;
  y?: number;
  fontSize?: number;
  color?: string;
  bulletColor?: string;
  title?: string;
  titleFontSize?: number;
}

export const BulletList: React.FC<Props> = ({
  items,
  startFrame,
  durationFrames,
  x = 100,
  y = 180,
  fontSize = 58,
  color = COLORS.ink,
  bulletColor = COLORS.blue,
  title,
  titleFontSize,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const localFrame = frame - startFrame;

  if (localFrame < 0 || localFrame > durationFrames) return null;

  const titleFs = titleFontSize ?? fontSize * 1.1;
  const itemCount = items.length;
  const titleDelay = title ? 14 : 0;
  const totalRevealFrames = Math.min(durationFrames * 0.85, titleDelay + itemCount * 36 + 12);
  const perItemFrames = (totalRevealFrames - titleDelay) / Math.max(itemCount, 1);

  const titleOpacity = interpolate(localFrame, [0, 12], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.out(Easing.ease),
  });

  return (
    <div style={{ position: "absolute", left: x, top: y, maxWidth: 1700 }}>
      {title && (
        <div
          style={{
            fontFamily: FONT.handwriting,
            fontSize: titleFs,
            fontWeight: 700,
            color: bulletColor,
            marginBottom: fontSize * 0.5,
            letterSpacing: "0.02em",
            opacity: titleOpacity,
          }}
        >
          {title}
        </div>
      )}

      {items.map((item, i) => {
        const itemStartLocal = titleDelay + i * perItemFrames;
        const itemLocal = localFrame - itemStartLocal;

        const enterSpring = spring({
          frame: itemLocal,
          fps,
          config: { damping: 20, stiffness: 220 },
        });
        const opacity = interpolate(itemLocal, [0, 10], [0, 1], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
          easing: Easing.out(Easing.ease),
        });
        const translateX = interpolate(enterSpring, [0, 1], [-50, 0]);

        return (
          <div
            key={i}
            style={{
              display: "flex",
              alignItems: "flex-start",
              gap: 22,
              marginBottom: fontSize * 0.65,
              opacity,
              transform: `translateX(${translateX}px)`,
            }}
          >
            {/* 手绘风格圆点 */}
            <svg width={fontSize * 0.55} height={fontSize * 0.55} style={{ flexShrink: 0, marginTop: fontSize * 0.28 }}>
              <ellipse
                cx={fontSize * 0.275}
                cy={fontSize * 0.275}
                rx={fontSize * 0.2}
                ry={fontSize * 0.18}
                fill={bulletColor}
                transform={`rotate(-10, ${fontSize * 0.275}, ${fontSize * 0.275})`}
              />
            </svg>
            <span
              style={{
                fontFamily: FONT.handwriting,
                fontSize,
                color,
                fontWeight: 400,
                lineHeight: 1.3,
                letterSpacing: "0.01em",
              }}
            >
              {item}
            </span>
          </div>
        );
      })}
    </div>
  );
};
