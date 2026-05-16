import React from "react";
import { AbsoluteFill, Audio, useCurrentFrame, interpolate, Easing } from "remotion";
import { getLength, getPointAtLength } from "@remotion/paths";
import { SketchText, getTextTipPosition } from "../primitives/SketchText";
import { SketchArrow, SketchRect, SketchUnderline } from "../primitives/SketchShape";
import { BulletList } from "../primitives/BulletList";
import { StepReveal } from "../primitives/StepReveal";
import { NarrationSubtitle } from "../primitives/NarrationSubtitle";
import { HandPen } from "../primitives/HandPen";
import { COLORS, FPS, FONT, WIDTH, HEIGHT } from "../primitives/types";
import type { Scene, AnimationInstruction } from "../primitives/types";

interface Props {
  scene: Scene;
}

// 内容安全区
const PAD_LEFT = 110;
const PAD_RIGHT = 110;
const TITLE_H = 130;
const SUBTITLE_H = 130;
const CONTENT_TOP = TITLE_H;
const CONTENT_BOTTOM = HEIGHT - SUBTITLE_H;
const CONTENT_H = CONTENT_BOTTOM - CONTENT_TOP;
const CONTENT_W = WIDTH - PAD_LEFT - PAD_RIGHT;

// 右侧 AI 缩略图区域
const THUMB_W = 400;
const THUMB_H = 340;
const THUMB_RIGHT = 80;
const THUMB_TOP = TITLE_H + 30;

// 有缩略图时，文字内容区变窄
const TEXT_W_WITH_THUMB = WIDTH - PAD_LEFT - THUMB_W - THUMB_RIGHT - 60;

const STAGGER = Math.round(FPS * 0.6);

function computeSlots(n: number) {
  if (n === 0) return [];
  const slotH = CONTENT_H / n;
  return Array.from({ length: n }, (_, i) => ({
    top: CONTENT_TOP + i * slotH,
    mid: CONTENT_TOP + (i + 0.5) * slotH,
    h: slotH,
  }));
}

/** 计算各动画的起始帧 */
function computeCursors(animations: AnimationInstruction[]): number[] {
  const cursors: number[] = [];
  let cursor = 0;
  for (const anim of animations) {
    cursors.push(cursor);
    const animFrames = Math.round(anim.duration * FPS);
    cursor += Math.max(animFrames - STAGGER, Math.round(FPS * 0.4));
  }
  return cursors;
}

/**
 * 根据当前帧和正在播放的动画，估算手（笔尖）的位置。
 * 返回 null 表示此时不显示手。
 */
function getHandPos(
  frame: number,
  animations: AnimationInstruction[],
  cursors: number[],
  slots: ReturnType<typeof computeSlots>,
  hasThumb: boolean,
): { x: number; y: number } | null {
  const maxW = hasThumb ? TEXT_W_WITH_THUMB : CONTENT_W;

  for (let i = 0; i < animations.length; i++) {
    const start = cursors[i];
    const anim = animations[i];
    const animFrames = Math.round(anim.duration * FPS);
    const writeFrames = animFrames * 0.7;
    const localF = frame - start;

    if (localF < 0 || localF > animFrames + FPS * 0.4) continue;

    const progress = Math.min(1, localF / Math.max(writeFrames, 1));
    const slot = slots[i];

    // ── 有 SVG path：精确跟随字形轮廓上的笔尖位置 ──
    const svgPath = anim.svgPath ?? anim.latexSvgPath;
    if (svgPath?.d) {
      const pt = getTextTipPosition(progress, svgPath);
      return { x: PAD_LEFT + pt.x - svgPath.bbox.x1, y: slot.top + slot.h * 0.1 + pt.y - svgPath.bbox.y1 };
    }

    const type = (() => {
      switch (anim.type) {
        case "whiteboard_draw": return "write_text";
        case "formula_reveal":  return "write_formula";
        case "concept_node":    return "concept_bubble";
        case "arrow_connect":   return "draw_arrow";
        case "text_narration":  return "write_text";
        default: return anim.type;
      }
    })();

    if (type === "write_title") {
      const fs = Math.min(120, Math.max(52, slot.h * 0.55) * 1.2);
      const chars = Array.from(anim.content);
      const estimatedW = Math.min(maxW * 0.9, chars.length * fs * 0.52);
      return { x: PAD_LEFT + progress * estimatedW, y: slot.top + fs * 0.55 };
    }

    if (type === "write_text") {
      const fs = Math.max(52, Math.min(96, slot.h * 0.55));
      const chars = Array.from(anim.content);
      const estimatedW = Math.min(maxW * 0.9, chars.length * fs * 0.52);
      return { x: PAD_LEFT + progress * estimatedW, y: slot.top + slot.h * 0.25 };
    }

    if (type === "write_formula") {
      const text = anim.latex ?? anim.content;
      const fs = Math.max(56, Math.min(90, slot.h * 0.45));
      const chars = Array.from(text);
      const estimatedW = Math.min(maxW * 0.75, chars.length * fs * 0.48);
      return { x: PAD_LEFT + progress * estimatedW, y: slot.top + slot.h * 0.45 };
    }

    if (type === "bullet_list" || type === "step_reveal") {
      const items = anim.items?.length
        ? anim.items
        : anim.content.split(/[·•\n|;；]/).map((s) => s.trim()).filter(Boolean);
      const fs = Math.max(42, Math.min(68, slot.h / (items.length + 1.5) * 0.85));
      const totalItems = Math.max(items.length, 1);
      // 当前正在写第几个 item
      const itemIdx = Math.min(totalItems - 1, Math.floor(progress * totalItems));
      const itemProgress = (progress * totalItems) % 1;
      const itemH = slot.h / totalItems;
      const estimatedItemW = Math.min(maxW * 0.8, Array.from(items[itemIdx] ?? "").length * fs * 0.52);
      return {
        x: PAD_LEFT + 60 + itemProgress * estimatedItemW,
        y: slot.top + itemIdx * itemH + fs * 0.5,
      };
    }

    if (type === "draw_arrow") {
      const fromX = PAD_LEFT * 2;
      const toX = WIDTH - PAD_RIGHT * 2 - (hasThumb ? THUMB_W + THUMB_RIGHT : 0);
      return { x: fromX + progress * (toX - fromX), y: slot.mid };
    }

    if (type === "concept_bubble" || type === "draw_box" || type === "highlight_region") {
      const cx = WIDTH / 2 - (hasThumb ? (THUMB_W + THUMB_RIGHT) / 2 : 0);
      const bw = Math.min(600, anim.content.length * 50 + 80);
      // 沿矩形边框顺时针运动模拟画框
      const perimeter = (bw + slot.h * 0.65) * 2;
      const dist = progress * perimeter;
      const bx = cx - bw / 2;
      const by = slot.mid - slot.h * 0.325;
      let hx: number, hy: number;
      if (dist < bw) {
        hx = bx + dist; hy = by;
      } else if (dist < bw + slot.h * 0.65) {
        hx = bx + bw; hy = by + (dist - bw);
      } else if (dist < bw * 2 + slot.h * 0.65) {
        hx = bx + bw - (dist - bw - slot.h * 0.65); hy = by + slot.h * 0.65;
      } else {
        hx = bx; hy = by + slot.h * 0.65 - (dist - bw * 2 - slot.h * 0.65);
      }
      return { x: hx, y: hy };
    }

    // fallback
    return { x: PAD_LEFT + progress * maxW * 0.5, y: slot.mid };
  }
  return null;
}

function renderAnimation(
  anim: AnimationInstruction,
  startFrame: number,
  remainFrames: number,
  slot: { top: number; mid: number; h: number },
  idx: number,
  maxW: number,
): React.ReactNode {
  const key = `${anim.type}-${idx}`;
  const durationFrames = remainFrames;

  const type = (() => {
    switch (anim.type) {
      case "whiteboard_draw": return "write_text";
      case "formula_reveal":  return "write_formula";
      case "concept_node":    return "concept_bubble";
      case "arrow_connect":   return "draw_arrow";
      case "text_narration":  return "write_text";
      default: return anim.type;
    }
  })();

  const leftX = PAD_LEFT;
  const cx = WIDTH / 2;
  const autoFontSize = Math.max(52, Math.min(96, slot.h * 0.55));

  switch (type) {
    case "write_title":
      return (
        <SketchText
          key={key}
          text={anim.content}
          svgPath={anim.svgPath}
          startFrame={startFrame}
          durationFrames={durationFrames}
          x={leftX}
          y={anim.y ?? slot.top}
          fontSize={Math.min(120, autoFontSize * 1.2)}
          color={anim.color ?? COLORS.ink}
          bold
          underline
          underlineColor={anim.color ?? COLORS.blue}
          maxWidth={maxW}
        />
      );

    case "write_text":
      return (
        <SketchText
          key={key}
          text={anim.content}
          svgPath={anim.svgPath}
          startFrame={startFrame}
          durationFrames={durationFrames}
          x={leftX}
          y={anim.y ?? slot.top + slot.h * 0.1}
          fontSize={autoFontSize}
          color={anim.color ?? COLORS.ink}
          bold={idx === 0}
          maxWidth={maxW}
        />
      );

    case "write_formula": {
      const formula = anim.latex ?? anim.content;
      const hasLabel = anim.latex && anim.content && anim.content !== formula;
      const fs = Math.max(56, Math.min(90, slot.h * 0.45));
      return (
        <div key={key}>
          {hasLabel && (
            <SketchText
              text={anim.content}
              svgPath={anim.svgPath}
              startFrame={startFrame}
              durationFrames={Math.round(durationFrames * 0.35)}
              x={leftX}
              y={anim.y ?? slot.top + slot.h * 0.05}
              fontSize={fs * 0.6}
              color={COLORS.inkLight}
              maxWidth={maxW}
            />
          )}
          <SketchText
            text={formula}
            svgPath={anim.latexSvgPath ?? anim.svgPath}
            startFrame={startFrame + (hasLabel ? Math.round(durationFrames * 0.25) : 0)}
            durationFrames={durationFrames}
            x={leftX}
            y={anim.y ?? slot.top + (hasLabel ? slot.h * 0.35 : slot.h * 0.1)}
            fontSize={fs}
            color={anim.color ?? COLORS.purple}
            bold
            maxWidth={maxW}
          />
          <SketchRect
            x={leftX - 18}
            y={(anim.y ?? slot.top + (hasLabel ? slot.h * 0.35 : slot.h * 0.05)) - 16}
            width={maxW * 0.7}
            height={fs * 1.6}
            startFrame={startFrame}
            durationFrames={Math.round(durationFrames * 0.6)}
            color={anim.color ?? COLORS.purple}
            strokeWidth={3}
          />
        </div>
      );
    }

    case "concept_bubble": {
      const fs = Math.max(56, Math.min(100, slot.h * 0.5));
      const bw = Math.min(600, fs * anim.content.length * 0.7 + 80);
      const bh = fs * 1.8;
      const bx = (anim.x ?? cx) - bw / 2;
      const by = (anim.y ?? slot.mid) - bh / 2;
      const col = anim.color ?? COLORS.blue;
      return (
        <div key={key}>
          <SketchRect
            x={bx} y={by} width={bw} height={bh}
            startFrame={startFrame}
            durationFrames={Math.round(durationFrames * 0.5)}
            color={col} strokeWidth={4} fill={`${col}15`}
          />
          <SketchText
            text={anim.content}
            svgPath={anim.svgPath}
            startFrame={startFrame + Math.round(durationFrames * 0.3)}
            durationFrames={durationFrames}
            x={bx + 24} y={by + bh * 0.18}
            fontSize={fs} color={col} bold maxWidth={bw - 48}
          />
        </div>
      );
    }

    case "bullet_list": {
      const items = anim.items?.length
        ? anim.items
        : anim.content.split(/[·•\n|;；]/).map((s) => s.trim()).filter(Boolean);
      const fs = Math.max(42, Math.min(68, slot.h / (items.length + 1.5) * 0.85));
      return (
        <BulletList
          key={key} items={items}
          startFrame={startFrame} durationFrames={durationFrames}
          x={leftX} y={anim.y ?? slot.top}
          fontSize={fs} bulletColor={anim.color ?? COLORS.blue}
        />
      );
    }

    case "step_reveal": {
      const steps = anim.items?.length
        ? anim.items
        : anim.content.split(/\n|；|;/).map((s) => s.replace(/^\d+[.、\s]+/, "").trim()).filter(Boolean);
      const fs = Math.max(38, Math.min(62, slot.h / (steps.length + 1) * 0.85));
      return (
        <StepReveal
          key={key} steps={steps}
          startFrame={startFrame} durationFrames={durationFrames}
          x={leftX} y={anim.y ?? slot.top}
          fontSize={fs} accentColor={anim.color ?? COLORS.blue}
        />
      );
    }

    case "draw_arrow": {
      const arrowY = anim.y ?? slot.mid;
      return (
        <SketchArrow
          key={key}
          from={{ x: PAD_LEFT * 2, y: arrowY }}
          to={{ x: maxW + PAD_LEFT - PAD_LEFT, y: arrowY }}
          startFrame={startFrame} durationFrames={durationFrames}
          label={anim.content || undefined}
          color={anim.color ?? COLORS.ink} strokeWidth={4} curved
        />
      );
    }

    case "draw_box":
    case "highlight_region": {
      const bw = maxW * 0.55;
      const bh = slot.h * 0.65;
      return (
        <SketchRect
          key={key}
          x={(anim.x ?? cx) - bw / 2} y={(anim.y ?? slot.mid) - bh / 2}
          width={bw} height={bh}
          startFrame={startFrame} durationFrames={durationFrames}
          color={anim.color ?? COLORS.orange} strokeWidth={4}
          label={anim.content || undefined}
        />
      );
    }

    case "draw_underline":
      return (
        <SketchUnderline
          key={key}
          x={anim.x ?? leftX} y={anim.y ?? slot.mid}
          width={anim.x ? maxW * 0.4 : maxW * 0.6}
          startFrame={startFrame} durationFrames={durationFrames}
          color={anim.color ?? COLORS.red} strokeWidth={5}
        />
      );

    default:
      return (
        <SketchText
          key={key} text={anim.content}
          svgPath={anim.svgPath}
          startFrame={startFrame} durationFrames={durationFrames}
          x={leftX} y={anim.y ?? slot.top + slot.h * 0.1}
          fontSize={autoFontSize} color={COLORS.inkLight} maxWidth={maxW}
        />
      );
  }
}

function SceneSlideIn({ children }: { children: React.ReactNode }) {
  const frame = useCurrentFrame();
  const tx = interpolate(frame, [0, 14], [50, 0], {
    extrapolateLeft: "clamp", extrapolateRight: "clamp",
    easing: Easing.out(Easing.ease),
  });
  const opacity = interpolate(frame, [0, 10], [0, 1], {
    extrapolateLeft: "clamp", extrapolateRight: "clamp",
  });
  return (
    <div style={{ transform: `translateX(${tx}px)`, opacity, width: "100%", height: "100%" }}>
      {children}
    </div>
  );
}

export const WhiteboardScene: React.FC<Props> = ({ scene }) => {
  const frame = useCurrentFrame();
  const sceneDurationFrames = Math.round(scene.duration_estimate * FPS);
  const hasThumb = Boolean(scene.imageUrl);
  const maxW = hasThumb ? TEXT_W_WITH_THUMB : CONTENT_W;

  const slots = computeSlots(scene.animations.length);
  const cursors = computeCursors(scene.animations);

  // 手的位置（笔尖坐标）
  const handPos = getHandPos(frame, scene.animations, cursors, slots, hasThumb);

  // 手 PNG 的偏移：让笔尖对准 handPos
  // 图片右下角握笔，笔尖在图片左下约 (45px, 220px) 处
        
  const animElements: React.ReactNode[] = [];
  for (let i = 0; i < scene.animations.length; i++) {
    const anim = scene.animations[i];
    animElements.push(
      renderAnimation(anim, cursors[i], sceneDurationFrames - cursors[i], slots[i], i, maxW)
    );
  }

  // AI 缩略图淡入：场景开始 0.5s 后出现
  const thumbOpacity = hasThumb
    ? interpolate(frame, [Math.round(FPS * 0.5), Math.round(FPS * 1.0)], [0, 1], {
        extrapolateLeft: "clamp", extrapolateRight: "clamp",
        easing: Easing.out(Easing.ease),
      })
    : 0;

  return (
    <AbsoluteFill style={{ background: COLORS.bg }}>
      {scene.audioUrl && <Audio src={scene.audioUrl} startFrom={0} />}

      <SceneSlideIn>
        {/* 顶部标题栏 */}
        <div
          style={{
            position: "absolute", top: 0, left: 0, right: 0, height: TITLE_H,
            display: "flex", alignItems: "center",
            paddingLeft: PAD_LEFT, paddingRight: PAD_RIGHT,
            borderBottom: `2px solid ${COLORS.lineGray}`,
          }}
        >
          {/* 标题：有 svgPath 时走手写描绘，否则静态显示 */}
          {scene.titlePath?.d ? (
            <SketchText
              text={scene.title}
              svgPath={scene.titlePath}
              startFrame={0}
              durationFrames={Math.round(FPS * 1.2)}
              x={0}
              y={TITLE_H * 0.15}
              fontSize={52}
              color={COLORS.ink}
              bold
            />
          ) : (
            <span style={{ fontFamily: FONT.handwriting, fontSize: 52, fontWeight: 700, color: COLORS.ink, letterSpacing: "0.02em" }}>
              {scene.title}
            </span>
          )}
          <div style={{ flex: 1 }} />
          <span style={{ fontFamily: FONT.handwriting, fontSize: 38, color: COLORS.lineGray, fontWeight: 400 }}>
            {String(scene.order + 1).padStart(2, "0")}
          </span>
        </div>

        {/* 右侧 AI 缩略图（如果有） */}
        {hasThumb && (
          <div
            style={{
              position: "absolute",
              right: THUMB_RIGHT,
              top: THUMB_TOP,
              width: THUMB_W,
              height: THUMB_H,
              opacity: thumbOpacity,
              borderRadius: 12,
              overflow: "hidden",
              border: `2px solid ${COLORS.lineGray}`,
              background: "#fff",
            }}
          >
            <div
              style={{
                width: "100%",
                height: "100%",
                backgroundImage: `url(${scene.imageUrl})`,
                backgroundSize: "contain",
                backgroundRepeat: "no-repeat",
                backgroundPosition: "center",
              }}
            />
          </div>
        )}

        {/* 内容动画层 */}
        {animElements}

        {/* 手持笔光标 */}
        {handPos && (
          <HandPen tipX={handPos.x} tipY={handPos.y} scale={1} />
        )}

        {/* 旁白字幕 */}
        <NarrationSubtitle
          text={scene.narration}
          startFrame={0}
          durationFrames={sceneDurationFrames}
        />
      </SceneSlideIn>
    </AbsoluteFill>
  );
};
