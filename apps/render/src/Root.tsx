import React, { useEffect } from "react";
import { Composition } from "remotion";
import { WhiteboardVideo } from "./compositions/WhiteboardVideo";
import { FPS, WIDTH, HEIGHT } from "./primitives/types";
import { CAVEAT_400_DATA_URL, CAVEAT_700_DATA_URL } from "./primitives/caveatFont";
import type { Storyboard } from "./primitives/types";

// 字体注入：直接写入 <style> 标签，不用 FontFace API，不阻塞渲染
if (typeof document !== "undefined") {
  const style = document.createElement("style");
  style.textContent = `
    @font-face {
      font-family: 'Caveat';
      font-weight: 400;
      font-style: normal;
      src: url('${CAVEAT_400_DATA_URL}') format('woff2');
    }
    @font-face {
      font-family: 'Caveat';
      font-weight: 700;
      font-style: normal;
      src: url('${CAVEAT_700_DATA_URL}') format('woff2');
    }
  `;
  document.head.appendChild(style);
}

const DEMO_STORYBOARD: Storyboard = {
  topic: "梯度下降",
  total_duration_estimate: 130,
  scenes: [
    {
      id: "scene_0",
      order: 0,
      title: "开场：今天讲什么",
      narration: "今天我们来讲解机器学习中最核心的优化算法——梯度下降，它是深度学习一切的基础。",
      duration_estimate: 18,
      node_ids: [],
      animations: [
        { type: "write_title", duration: 4, content: "梯度下降" },
        { type: "bullet_list", duration: 10, content: "今天你会学到", items: ["损失函数是什么", "梯度的含义", "参数如何更新", "收敛的过程"] },
      ],
    },
    {
      id: "scene_1",
      order: 1,
      title: "损失函数",
      narration: "损失函数衡量的是模型预测值和真实值之间的差距，损失越小，模型越准确。",
      duration_estimate: 28,
      node_ids: ["node_0"],
      animations: [
        { type: "write_text", duration: 3, content: "损失函数 L(θ)" },
        { type: "write_formula", duration: 7, content: "均方误差（MSE）", latex: "L(θ) = (1/n) · Σ(y - ŷ)²" },
        { type: "write_text", duration: 4, content: "损失越小 → 模型越准" },
      ],
    },
    {
      id: "scene_2",
      order: 2,
      title: "梯度是什么",
      narration: "梯度是损失函数对参数的偏导数，指向损失增大最快的方向。我们要反着走，所以叫梯度下降。",
      duration_estimate: 30,
      node_ids: ["node_1"],
      animations: [
        { type: "write_text", duration: 3, content: "∇L(θ) = 损失函数的梯度" },
        { type: "draw_arrow", duration: 5, content: "梯度方向 = 损失增大最快" },
        { type: "write_text", duration: 5, content: "反方向走 → 损失减小 ✓" },
      ],
    },
    {
      id: "scene_3",
      order: 3,
      title: "参数更新公式",
      narration: "参数更新公式：新参数等于旧参数减去学习率乘以梯度。学习率控制步长，太大震荡，太小则慢。",
      duration_estimate: 32,
      node_ids: ["node_2"],
      animations: [
        { type: "write_formula", duration: 7, content: "参数更新规则", latex: "θ := θ − α · ∇L(θ)" },
        { type: "step_reveal", duration: 14, content: "三个关键量", items: ["θ — 模型参数", "α — 学习率（步长）", "∇L(θ) — 梯度（方向）"] },
      ],
    },
    {
      id: "scene_4",
      order: 4,
      title: "收敛与总结",
      narration: "经过多次迭代，参数逐渐收敛到损失最小的位置，这就是梯度下降的核心思想。",
      duration_estimate: 22,
      node_ids: ["node_3"],
      animations: [
        { type: "concept_bubble", duration: 4, content: "不断迭代 → 参数收敛" },
        { type: "bullet_list", duration: 10, content: "核心三要素", items: ["损失函数 — 定义目标", "梯度 — 告诉方向", "学习率 — 控制步长"] },
      ],
    },
  ],
};

export const RemotionRoot: React.FC = () => {
  const totalFrames = Math.round(DEMO_STORYBOARD.total_duration_estimate * FPS) + 80;
  return (
    <>
      <Composition
        id="WhiteboardVideo"
        component={WhiteboardVideo}
        durationInFrames={totalFrames}
        fps={FPS}
        width={WIDTH}
        height={HEIGHT}
        defaultProps={{ storyboard: DEMO_STORYBOARD }}
      />
    </>
  );
};
