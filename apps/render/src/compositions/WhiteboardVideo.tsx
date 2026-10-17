import React from "react";
import { AbsoluteFill, Series, useCurrentFrame, interpolate, Easing } from "remotion";
import { WhiteboardScene } from "./WhiteboardScene";
import { SketchText } from "../primitives/SketchText";
import { SketchUnderline } from "../primitives/SketchShape";
import { COLORS, FPS, FONT, WIDTH } from "../primitives/types";
import type { Storyboard } from "../primitives/types";

interface Props {
  storyboard: Storyboard;
}

const TITLE_FRAMES = 80; // ~2.7s 标题卡

function TitleCard({ topic, imageUrl }: { topic: string; imageUrl?: string | null }) {
  const frame = useCurrentFrame();

  const subtitleOpacity = interpolate(frame, [45, 65], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.out(Easing.ease),
  });

  // 装饰线格
  const gridOpacity = interpolate(frame, [0, 20], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // 主题插图淡入
  const imageOpacity = interpolate(frame, [0, 25], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.out(Easing.ease),
  });

  return (
    <AbsoluteFill style={{ background: COLORS.bg }}>
      {/* 淡色网格线背景 */}
      <svg
        style={{ position: "absolute", left: 0, top: 0, width: "100%", height: "100%", opacity: gridOpacity * 0.2 }}
      >
        {/* 横线 */}
        {Array.from({ length: 14 }).map((_, i) => (
          <line key={`h${i}`} x1={0} y1={i * 40} x2={WIDTH} y2={i * 40} stroke={COLORS.lineGray} strokeWidth={1} />
        ))}
      </svg>

      {/* 主题插图（如果有） */}
      {imageUrl && (
        <div
          style={{
            position: "absolute",
            right: 70,
            top: 90,
            width: 260,
            height: 260,
            opacity: imageOpacity,
            borderRadius: 8,
            overflow: "hidden",
            border: `2px solid ${COLORS.lineGray}`,
            background: "#fff",
          }}
        >
          <div
            style={{
              width: "100%",
              height: "100%",
              backgroundImage: `url(${imageUrl})`,
              backgroundSize: "cover",
              backgroundRepeat: "no-repeat",
              backgroundPosition: "center",
            }}
          />
        </div>
      )}

      {/* 主标题（手写逐字） */}
      <SketchText
        text={topic}
        startFrame={8}
        durationFrames={TITLE_FRAMES - 8}
        x={70}
        y={190}
        fontSize={60}
        color={COLORS.ink}
        bold
        maxWidth={imageUrl ? 540 : 820}
      />

      {/* 下划线（标题写完后画） */}
      <SketchUnderline
      x={70}
      y={265}
      width={Math.min(imageUrl ? 540 : 820, topic.length * 34 + 30)}
        startFrame={40}
        durationFrames={TITLE_FRAMES - 40}
        color={COLORS.blue}
      strokeWidth={3}
      />

      {/* 副标题 */}
      <div
        style={{
          position: "absolute",
          left: 70,
          top: 300,
          opacity: subtitleOpacity,
          fontFamily: FONT.handwriting,
          fontSize: 23,
          color: COLORS.inkLight,
          fontWeight: 400,
          letterSpacing: "0.04em",
        }}
      >
        AI 白板动画 · ExplainFlow
      </div>
    </AbsoluteFill>
  );
}

export const WhiteboardVideo: React.FC<Props> = ({ storyboard }) => {
  const monochrome = String(storyboard.line_art_color_mode ?? "color").toLowerCase() === "monochrome";
  return (
    <div style={monochrome ? { filter: "grayscale(1) contrast(1.04)" } : undefined}>
    <Series>
      <Series.Sequence durationInFrames={TITLE_FRAMES}>
        <TitleCard topic={storyboard.topic} imageUrl={storyboard.titleImageUrl} />
      </Series.Sequence>

      {storyboard.scenes.map((scene) => {
        const frames = Math.round(scene.duration_estimate * FPS);
        return (
          <Series.Sequence key={scene.id} durationInFrames={Math.max(frames, 60)}>
            <WhiteboardScene scene={scene} />
          </Series.Sequence>
        );
      })}
    </Series>
    </div>
  );
};
