import React from "react";

interface Props {
  /** 笔尖所在的像素坐标（场景内绝对坐标） */
  tipX: number;
  tipY: number;
  /** 整体缩放，默认 1 */
  scale?: number;
}

/**
 * 内联 SVG 手持马克笔图形。
 * 笔尖始终对准 (tipX, tipY)，无需外部图片资源。
 *
 * 坐标系：笔尖在 SVG 内的位置是 (30, 220)，图片尺寸 160×240。
 * 所以 left = tipX - 30, top = tipY - 220。
 */
export const HandPen: React.FC<Props> = ({ tipX, tipY, scale = 1 }) => {
  const W = 160 * scale;
  const H = 240 * scale;

  // 笔尖在图形内的偏移（用于定位）
  const TIP_X_OFFSET = 30 * scale;
  const TIP_Y_OFFSET = 220 * scale;

  return (
    <svg
      viewBox="0 0 160 240"
      width={W}
      height={H}
      style={{
        position: "absolute",
        left: tipX - TIP_X_OFFSET,
        top: tipY - TIP_Y_OFFSET,
        pointerEvents: "none",
        overflow: "visible",
      }}
    >
      {/* ── 马克笔主体（深色笔杆，倾斜约 30°） ── */}
      {/* 笔杆：从笔尖 (30,220) 向右上延伸 */}
      <g transform="rotate(-30, 30, 220)">
        {/* 笔尖（圆锥形） */}
        <polygon
          points="30,220 22,190 38,190"
          fill="#1a1a1a"
        />
        {/* 笔身下段（深灰） */}
        <rect x={20} y={130} width={20} height={60} rx={3} fill="#2d2d2d" />
        {/* 笔身中段（黑色笔帽颜色区） */}
        <rect x={20} y={80} width={20} height={52} rx={2} fill="#111" />
        {/* 笔帽夹（金属感细条） */}
        <rect x={36} y={85} width={4} height={45} rx={1} fill="#888" />
        {/* 笔帽顶部 */}
        <rect x={18} y={68} width={24} height={14} rx={4} fill="#222" />
      </g>

      {/* ── 手（简化轮廓，自然握笔姿势） ── */}
      {/* 手掌主体 */}
      <ellipse cx={72} cy={165} rx={34} ry={28} fill="#f0c9a0" />

      {/* 大拇指 */}
      <ellipse
        cx={48} cy={152} rx={12} ry={20}
        fill="#f0c9a0"
        transform="rotate(-30, 48, 152)"
      />

      {/* 食指（握住笔） */}
      <ellipse
        cx={52} cy={130} rx={10} ry={24}
        fill="#f0c9a0"
        transform="rotate(-15, 52, 130)"
      />

      {/* 中指 */}
      <ellipse
        cx={68} cy={125} rx={10} ry={26}
        fill="#f2cba8"
        transform="rotate(-5, 68, 125)"
      />

      {/* 无名指 */}
      <ellipse
        cx={84} cy={128} rx={9} ry={24}
        fill="#f2cba8"
        transform="rotate(8, 84, 128)"
      />

      {/* 小指 */}
      <ellipse
        cx={98} cy={135} rx={8} ry={20}
        fill="#f2cba8"
        transform="rotate(18, 98, 135)"
      />

      {/* 手掌轮廓线（柔和） */}
      <ellipse cx={72} cy={165} rx={34} ry={28} fill="none" stroke="#d4a574" strokeWidth={1.5} />

      {/* 指节线（轻描） */}
      <path d="M 52 140 Q 54 135 56 140" stroke="#c9946a" strokeWidth={1} fill="none" />
      <path d="M 68 136 Q 70 131 72 136" stroke="#c9946a" strokeWidth={1} fill="none" />
      <path d="M 84 138 Q 86 133 88 138" stroke="#c9946a" strokeWidth={1} fill="none" />

      {/* ── 笔杆再叠一层在手指前面（让笔看起来被握住） ── */}
      <g transform="rotate(-30, 30, 220)">
        <rect x={23} y={150} width={14} height={30} rx={2} fill="#2d2d2d" opacity={0.85} />
      </g>
    </svg>
  );
};
