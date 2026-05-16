import React from "react";
import { AbsoluteFill, Series, useVideoConfig } from "remotion";
import { WhiteboardScene } from "./WhiteboardScene";
import { COLORS, FPS, FONT } from "../primitives/types";
import type { Storyboard } from "../primitives/types";

interface Props {
  storyboard: Storyboard;
}

const TITLE_FRAMES = 60; // 2s title card

function TitleCard({ topic }: { topic: string }) {
  return (
    <AbsoluteFill
      style={{
        background: COLORS.bg,
        alignItems: "center",
        justifyContent: "center",
        flexDirection: "column",
        gap: 24,
      }}
    >
      <div style={{ fontSize: 80, fontFamily: FONT.sans, fontWeight: 700, color: COLORS.chalk }}>
        {topic}
      </div>
      <div
        style={{
          width: 80,
          height: 4,
          background: COLORS.accent,
          borderRadius: 2,
        }}
      />
      <div style={{ fontSize: 28, fontFamily: FONT.sans, color: COLORS.gray }}>
        ExplainFlow · AI 白板动画
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
          <Series.Sequence key={scene.id} durationInFrames={Math.max(frames, 30)}>
            <WhiteboardScene scene={scene} />
          </Series.Sequence>
        );
      })}
    </Series>
  );
};
