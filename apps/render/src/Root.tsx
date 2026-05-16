import React from "react";
import { Composition } from "remotion";
import { WhiteboardVideo } from "./compositions/WhiteboardVideo";
import { FPS, WIDTH, HEIGHT } from "./primitives/types";
import type { Storyboard } from "./primitives/types";

const DEMO_STORYBOARD: Storyboard = {
  topic: "梯度下降",
  total_duration_estimate: 120,
  scenes: [
    {
      id: "scene_0",
      order: 0,
      title: "开场",
      narration: "今天我们来讲解机器学习中最核心的优化算法——梯度下降。",
      duration_estimate: 15,
      node_ids: [],
      animations: [
        { type: "whiteboard_draw", duration: 2, content: "梯度下降", bold: true } as any,
        { type: "whiteboard_draw", duration: 1.5, content: "Gradient Descent", bold: false } as any,
      ],
    },
    {
      id: "scene_1",
      order: 1,
      title: "损失函数",
      narration: "首先，我们需要理解损失函数。它衡量的是模型预测值和真实值之间的差距。",
      duration_estimate: 25,
      node_ids: ["node_0"],
      animations: [
        { type: "concept_node", duration: 2, content: "损失函数 L(θ)" } as any,
        { type: "formula_reveal", duration: 3, content: "MSE", latex: "L(θ) = (1/n) Σ(y - ŷ)²" } as any,
      ],
    },
    {
      id: "scene_2",
      order: 2,
      title: "梯度",
      narration: "梯度是损失函数对参数的偏导数，它指向损失增大最快的方向。",
      duration_estimate: 25,
      node_ids: ["node_1"],
      animations: [
        { type: "concept_node", duration: 2, content: "梯度 ∇L(θ)" } as any,
        { type: "arrow_connect", duration: 2, content: "指向损失增大方向" } as any,
      ],
    },
    {
      id: "scene_3",
      order: 3,
      title: "更新规则",
      narration: "参数更新公式是：参数减去学习率乘以梯度。我们沿着梯度反方向走，损失就会减小。",
      duration_estimate: 30,
      node_ids: ["node_2", "node_3"],
      animations: [
        { type: "formula_reveal", duration: 4, content: "θ := θ - α · ∇L(θ)", latex: "θ := θ − α · ∇L(θ)" } as any,
        { type: "whiteboard_draw", duration: 2, content: "α = 学习率（步长）" } as any,
      ],
    },
    {
      id: "scene_4",
      order: 4,
      title: "收敛",
      narration: "经过多次迭代，参数会逐渐收敛到损失函数的最小值附近，这就是梯度下降的原理。",
      duration_estimate: 25,
      node_ids: ["node_4"],
      animations: [
        { type: "concept_node", duration: 2, content: "参数收敛" } as any,
        { type: "text_narration", duration: 2, content: "多次迭代 → 趋近最优解" } as any,
      ],
    },
  ],
};

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition
        id="WhiteboardVideo"
        component={WhiteboardVideo}
        durationInFrames={Math.round(DEMO_STORYBOARD.total_duration_estimate * FPS) + 60}
        fps={FPS}
        width={WIDTH}
        height={HEIGHT}
        defaultProps={{ storyboard: DEMO_STORYBOARD }}
      />
    </>
  );
};
