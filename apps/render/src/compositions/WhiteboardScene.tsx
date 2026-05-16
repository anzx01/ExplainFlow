import React from "react";
import { AbsoluteFill, Audio } from "remotion";
import { WhiteboardDraw } from "../primitives/WhiteboardDraw";
import { FormulaReveal } from "../primitives/FormulaReveal";
import { ConceptNode } from "../primitives/ConceptNode";
import { ArrowConnect } from "../primitives/ArrowConnect";
import { NarrationSubtitle } from "../primitives/NarrationSubtitle";
import { COLORS, FPS } from "../primitives/types";
import type { Scene, AnimationInstruction } from "../primitives/types";

interface Props {
  scene: Scene;
}

function renderAnimation(anim: AnimationInstruction, startFrame: number, durationFrames: number) {
  switch (anim.type) {
    case "whiteboard_draw":
      return (
        <WhiteboardDraw
          key={`${anim.type}-${startFrame}`}
          content={anim.content}
          startFrame={startFrame}
          durationFrames={durationFrames}
          y={360}
        />
      );
    case "formula_reveal":
      return (
        <FormulaReveal
          key={`${anim.type}-${startFrame}`}
          formula={anim.latex ?? anim.content}
          startFrame={startFrame}
          durationFrames={durationFrames}
        />
      );
    case "concept_node":
      return (
        <ConceptNode
          key={`${anim.type}-${startFrame}`}
          label={anim.content}
          startFrame={startFrame}
          durationFrames={durationFrames}
        />
      );
    case "arrow_connect":
      return (
        <ArrowConnect
          key={`${anim.type}-${startFrame}`}
          startFrame={startFrame}
          durationFrames={durationFrames}
          label={anim.content}
          from={{ x: 400, y: 400 }}
          to={{ x: 880, y: 400 }}
        />
      );
    case "text_narration":
      return (
        <WhiteboardDraw
          key={`${anim.type}-${startFrame}`}
          content={anim.content}
          startFrame={startFrame}
          durationFrames={durationFrames}
          y={600}
          fontSize={36}
          color={COLORS.gray}
        />
      );
    default:
      return null;
  }
}

export const WhiteboardScene: React.FC<Props> = ({ scene }) => {
  const sceneDurationFrames = Math.round(scene.duration_estimate * FPS);

  let cursor = 0;
  const animElements: React.ReactNode[] = [];
  for (const anim of scene.animations) {
    const animFrames = Math.round(anim.duration * FPS);
    animElements.push(renderAnimation(anim, cursor, sceneDurationFrames - cursor));
    cursor += Math.round(animFrames * 0.8);
  }

  return (
    <AbsoluteFill style={{ background: COLORS.bg }}>
      {scene.audioUrl && (
        <Audio src={scene.audioUrl} startFrom={0} />
      )}

      <div
        style={{
          position: "absolute",
          top: 60,
          left: 0,
          right: 0,
          textAlign: "center",
          fontSize: 28,
          color: COLORS.gray,
          fontFamily: "'Noto Sans SC', sans-serif",
          fontWeight: 400,
          letterSpacing: "0.06em",
        }}
      >
        {scene.title}
      </div>

      {animElements}

      <NarrationSubtitle
        text={scene.narration}
        startFrame={0}
        durationFrames={sceneDurationFrames}
      />
    </AbsoluteFill>
  );
};
