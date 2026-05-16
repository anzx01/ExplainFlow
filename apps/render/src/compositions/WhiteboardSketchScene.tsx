import React from "react";
import { AbsoluteFill, Audio, Img, useCurrentFrame, interpolate, Easing, staticFile } from "remotion";
import { NarrationSubtitle } from "../primitives/NarrationSubtitle";
import { SketchText } from "../primitives/SketchText";
import { SketchUnderline } from "../primitives/SketchShape";
import { COLORS, FPS, FONT, WIDTH, HEIGHT } from "../primitives/types";
import type { Scene } from "../primitives/types";

interface Props {
  scene: Scene;
}

// 布局常量
const TITLE_H = 130;
const SUBTITLE_H = 120;
const PAD_H = 80;
const IMG_LEFT = 80;
const IMG_TOP = TITLE_H + 20;
const IMG_WIDTH = WIDTH * 0.62;
const IMG_HEIGHT = HEIGHT - TITLE_H - SUBTITLE_H - 40;

// 手持笔图片尺寸
const HAND_W = 320;
const HAND_H = 320;

export const WhiteboardSketchScene: React.FC<Props> = ({ scene }) => {
  const frame = useCurrentFrame();
  const totalFrames = Math.round(scene.duration_estimate * FPS);

  // 场景入场淡入
  const opacity = interpolate(frame, [0, 12], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.out(Easing.ease),
  });

  // mask reveal：图片从左到右逐渐显现（占总时长 70%）
  const revealEnd = Math.round(totalFrames * 0.7);
  const revealProgress = interpolate(frame, [8, revealEnd], [0, 100], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.inOut(Easing.ease),
  });

  // 手持笔位置：跟随 reveal 右边缘
  const handX = IMG_LEFT + (revealProgress / 100) * IMG_WIDTH - HAND_W * 0.55;
  const handY = IMG_TOP + IMG_HEIGHT - HAND_H * 0.6;

  // 手的透明度：reveal 完成后淡出
  const handOpacity = interpolate(frame, [revealEnd, revealEnd + 15], [1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <AbsoluteFill style={{ background: COLORS.bg, opacity }}>
      {scene.audioUrl && <Audio src={scene.audioUrl} startFrom={0} />}

      {/* 顶部标题栏 */}
      <div
        style={{
          position: "absolute",
          top: 0,
          left: 0,
          right: 0,
          height: TITLE_H,
          display: "flex",
          alignItems: "center",
          paddingLeft: PAD_H,
          paddingRight: PAD_H,
          borderBottom: `2px solid ${COLORS.lineGray}`,
        }}
      >
        <SketchText
          text={scene.title}
          startFrame={0}
          durationFrames={Math.round(FPS * 1.2)}
          x={PAD_H}
          y={28}
          fontSize={54}
          color={COLORS.blue}
          bold
          maxWidth={WIDTH - PAD_H * 2 - 120}
        />
        <div style={{ flex: 1 }} />
        <span
          style={{
            fontFamily: FONT.handwriting,
            fontSize: 38,
            color: COLORS.lineGray,
            fontWeight: 400,
          }}
        >
          {String(scene.order + 1).padStart(2, "0")}
        </span>
      </div>

      {/* 标题下划线 */}
      <SketchUnderline
        x={PAD_H}
        y={TITLE_H - 8}
        width={Math.min(scene.title.length * 36 + 40, WIDTH * 0.5)}
        startFrame={Math.round(FPS * 0.8)}
        durationFrames={Math.round(FPS * 0.6)}
        color={COLORS.blue}
        strokeWidth={4}
      />

      {/* AI 生成插图 + mask reveal */}
      <div
        style={{
          position: "absolute",
          left: IMG_LEFT,
          top: IMG_TOP,
          width: IMG_WIDTH,
          height: IMG_HEIGHT,
          clipPath: `inset(0 ${100 - revealProgress}% 0 0)`,
          borderRadius: 8,
          overflow: "hidden",
        }}
      >
        <Img
          src={scene.imageUrl!}
          style={{
            width: IMG_WIDTH,
            height: IMG_HEIGHT,
            objectFit: "contain",
            objectPosition: "left center",
            background: "#fff",
          }}
        />
      </div>

      {/* 手持笔 PNG，跟随 reveal 右边缘 */}
      <div
        style={{
          position: "absolute",
          left: handX,
          top: handY,
          width: HAND_W,
          height: HAND_H,
          opacity: handOpacity,
          pointerEvents: "none",
        }}
      >
        <Img
          src={staticFile("hand-with-pen.png")}
          style={{ width: HAND_W, height: HAND_H, objectFit: "contain" }}
        />
      </div>

      {/* 旁白字幕 */}
      <NarrationSubtitle
        text={scene.narration}
        startFrame={0}
        durationFrames={totalFrames}
      />
    </AbsoluteFill>
  );
};
