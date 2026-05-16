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

function TitleCard({ topic }: { topic: string }) {
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

  return (
    <AbsoluteFill style={{ background: COLORS.bg }}>
      {/* 淡色网格线背景 */}
      <svg
        style={{ position: "absolute", left: 0, top: 0, width: "100%", height: "100%", opacity: gridOpacity * 0.2 }}
      >
        {/* 横线 */}
        {Array.from({ length: 14 }).map((_, i) => (
          <line key={`h${i}`} x1={0} y1={i * 80} x2={1920} y2={i * 80} stroke={COLORS.lineGray} strokeWidth={1} />
        ))}
      </svg>

      {/* 主标题（手写逐字） */}
      <SketchText
        text={topic}
        startFrame={8}
        durationFrames={TITLE_FRAMES - 8}
        x={140}
        y={380}
        fontSize={120}
        color={COLORS.ink}
        bold
        maxWidth={1640}
      />

      {/* 下划线（标题写完后画） */}
      <SketchUnderline
        x={140}
        y={530}
        width={Math.min(1640, topic.length * 68 + 60)}
        startFrame={40}
        durationFrames={TITLE_FRAMES - 40}
        color={COLORS.blue}
        strokeWidth={5}
      />

      {/* 副标题 */}
      <div
        style={{
          position: "absolute",
          left: 140,
          top: 600,
          opacity: subtitleOpacity,
          fontFamily: FONT.handwriting,
          fontSize: 46,
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
  return (
    <Series>
      <Series.Sequence durationInFrames={TITLE_FRAMES}>
        <TitleCard topic={storyboard.topic} />
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
  );
};
