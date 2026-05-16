"use client";

import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { StoryboardView } from "@/components/storyboard/StoryboardView";
import type { Storyboard } from "@/lib/types";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const RENDER = process.env.NEXT_PUBLIC_RENDER_URL ?? "http://localhost:3001";

type RenderState = "idle" | "submitting" | "polling" | "done" | "failed";

function RenderButton({
  storyboard,
  onVideoReady,
}: {
  storyboard: Storyboard;
  onVideoReady: (url: string) => void;
}) {
  const [state, setState] = useState<RenderState>("idle");
  const [jobId, setJobId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const poll = useCallback(
    async (id: string) => {
      const res = await fetch(`${API}/render/job/${id}`);
      const data = await res.json();
      if (data.status === "done") {
        setState("done");
        // Direct to render server (3001) for Range request support + no FastAPI proxy overhead
        onVideoReady(`${RENDER}/download/${id}`);
      } else if (data.status === "failed") {
        setState("failed");
        setError(data.error ?? "渲染失败");
      } else {
        setTimeout(() => poll(id), 3000);
      }
    },
    [onVideoReady]
  );

  const handleRender = async () => {
    setState("submitting");
    setError(null);
    try {
      const res = await fetch(`${API}/render/job`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ storyboard, voice: "xiaoxiao", resolution: "1080p" }),
      });
      if (!res.ok) {
        const d = await res.json();
        throw new Error(d.detail ?? "提交失败");
      }
      const { job_id } = await res.json();
      setJobId(job_id);
      setState("polling");
      poll(job_id);
    } catch (e) {
      setState("failed");
      setError(e instanceof Error ? e.message : "未知错误");
    }
  };

  if (state === "idle" || state === "failed") {
    return (
      <div className="flex items-center gap-2">
        {error && (
          <span className="text-xs text-red-400 max-w-48 truncate" title={error}>
            {error}
          </span>
        )}
        <button
          onClick={handleRender}
          className="h-9 px-4 rounded-md border border-[--border-default] hover:border-purple-500 text-sm text-[--fg-muted] hover:text-[--fg-default] transition-colors flex items-center gap-2"
        >
          ▶ 生成视频
        </button>
      </div>
    );
  }

  if (state === "submitting" || state === "polling") {
    return (
      <button
        disabled
        className="h-9 px-4 rounded-md border border-purple-500/40 text-sm text-purple-400 flex items-center gap-2"
      >
        <span className="inline-block w-3 h-3 border-2 border-purple-400 border-t-transparent rounded-full animate-spin" />
        {state === "submitting" ? "提交中..." : "渲染中..."}
      </button>
    );
  }

  // done — show download button alongside the watch indicator
  return (
    <div className="flex items-center gap-2">
      <span className="text-xs text-green-400 font-mono">✓ 已生成</span>
      <a
        href={`${RENDER}/download/${jobId}`}
        download
        className="h-9 px-4 rounded-md bg-purple-500/20 hover:bg-purple-500/30 border border-purple-500/50 text-purple-300 text-sm font-medium flex items-center gap-2 transition-colors"
      >
        ↓ 下载 MP4
      </a>
    </div>
  );
}

const DEMO_STORYBOARD: Storyboard = {
  topic: "梯度下降",
  total_duration_estimate: 120,
  scenes: [
    {
      id: "scene_0",
      order: 0,
      title: "开场：今天讲什么",
      narration: "今天我们来讲解机器学习中最核心的优化算法——梯度下降。它是深度学习一切的基础。",
      duration_estimate: 15,
      node_ids: [],
      animations: [
        { type: "whiteboard_draw", duration: 2, content: "梯度下降" },
        { type: "whiteboard_draw", duration: 1.5, content: "Gradient Descent" },
      ],
    },
    {
      id: "scene_1",
      order: 1,
      title: "损失函数",
      narration: "首先，我们需要理解损失函数。它衡量的是模型预测值和真实值之间的差距。损失越小，模型越准确。",
      duration_estimate: 28,
      node_ids: ["node_0"],
      animations: [
        { type: "concept_node", duration: 2, content: "损失函数 L(θ)" },
        { type: "formula_reveal", duration: 3, content: "MSE 公式", latex: "L(θ) = (1/n)·Σ(y - ŷ)²" },
      ],
    },
    {
      id: "scene_2",
      order: 2,
      title: "梯度是什么",
      narration: "梯度是损失函数对参数的偏导数。它告诉我们，在当前点沿哪个方向走，损失增大最快。",
      duration_estimate: 25,
      node_ids: ["node_1"],
      animations: [
        { type: "concept_node", duration: 2, content: "梯度 ∇L(θ)" },
        { type: "arrow_connect", duration: 2, content: "指向损失增大方向" },
      ],
    },
    {
      id: "scene_3",
      order: 3,
      title: "参数更新规则",
      narration: "参数更新公式是：参数减去学习率乘以梯度。我们沿梯度反方向走，每步减少损失。",
      duration_estimate: 30,
      node_ids: ["node_2"],
      animations: [
        { type: "formula_reveal", duration: 4, content: "θ := θ - α·∇L(θ)", latex: "θ := θ − α · ∇L(θ)" },
        { type: "whiteboard_draw", duration: 2, content: "α = 学习率（控制步长）" },
      ],
    },
    {
      id: "scene_4",
      order: 4,
      title: "收敛与总结",
      narration: "经过多次迭代，参数逐渐收敛到损失最小的位置。这就是梯度下降的核心思想：用导数信息，一步步找到最优解。",
      duration_estimate: 22,
      node_ids: ["node_3"],
      animations: [
        { type: "concept_node", duration: 2, content: "参数收敛" },
        { type: "text_narration", duration: 2, content: "多次迭代 → 趋近最优解 ✓" },
      ],
    },
  ],
};

export default function StoryboardPage() {
  const [storyboard, setStoryboard] = useState<Storyboard>(DEMO_STORYBOARD);
  const [videoUrl, setVideoUrl] = useState<string | null>(null);

  useEffect(() => {
    const saved = sessionStorage.getItem("explainflow_storyboard");
    if (saved) {
      try {
        const sb = JSON.parse(saved) as Storyboard;
        sb.topic = sb.topic.replace(/\x1b\[[0-9;]*m/g, "").trim();
        setStoryboard(sb);
      } catch {
        // ignore parse errors, keep demo
      }
    }
  }, []);

  return (
    <div className="flex flex-col h-screen bg-[--bg-base] text-[--fg-default] overflow-hidden">
      {/* Nav */}
      <header className="flex items-center justify-between px-6 h-14 bg-[--bg-surface] border-b border-[--border-subtle] flex-shrink-0">
        <div className="flex items-center gap-4">
          <Link
            href="/studio"
            className="flex items-center gap-1.5 text-sm text-[--fg-muted] hover:text-[--fg-default] transition-colors"
          >
            ← Studio
          </Link>
          <div className="w-px h-5 bg-[--border-default]" />
          <div className="flex items-center gap-2">
            <div className="w-5 h-5 rounded bg-gradient-to-br from-purple-500 to-pink-500" />
            <span className="text-sm font-medium">{storyboard.topic} — Storyboard</span>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <span className="text-xs font-mono text-[--fg-muted]">
            共 {storyboard.scenes.length} 场 · {Math.round(storyboard.total_duration_estimate)}s
          </span>
          <RenderButton storyboard={storyboard} onVideoReady={setVideoUrl} />
        </div>
      </header>

      {/* Content */}
      <div className="flex-1 overflow-hidden">
        <StoryboardView
          storyboard={storyboard}
          videoUrl={videoUrl}
        />
      </div>
    </div>
  );
}
