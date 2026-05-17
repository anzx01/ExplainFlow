import React from "react";
import { AbsoluteFill, Composition } from "remotion";

const RuntimePlaceholder: React.FC = () => {
  return (
    <AbsoluteFill
      style={{
        background: "#f7f3ea",
        color: "#1d1d1d",
        fontFamily: "Arial, sans-serif",
        alignItems: "center",
        justifyContent: "center",
        padding: 96,
      }}
    >
      <div style={{ maxWidth: 980, lineHeight: 1.45 }}>
        <div style={{ fontSize: 58, fontWeight: 800, marginBottom: 28 }}>
          ExplainFlow LLM Remotion Runtime
        </div>
        <div style={{ fontSize: 30, color: "#4b5563" }}>
          Production renders are generated per job by the render server. Each job
          writes its own self-contained Remotion TSX entry under apps/render/generated.
        </div>
      </div>
    </AbsoluteFill>
  );
};

export const RemotionRoot: React.FC = () => {
  return (
    <Composition
      id="ExplainFlowRuntime"
      component={RuntimePlaceholder}
      durationInFrames={150}
      fps={30}
      width={1920}
      height={1080}
    />
  );
};
