"use client";

import { useState } from "react";
import { Button } from "@/components/ui/Button";

interface Props {
  onGenerate: (prompt: string, markdown: string, duration: number) => void;
  loading: boolean;
}

export function LeftPanel({ onGenerate, loading }: Props) {
  const [prompt, setPrompt] = useState("");
  const [markdown, setMarkdown] = useState("");
  const [duration, setDuration] = useState(120);

  const handleSubmit = () => {
    if (!prompt.trim()) return;
    onGenerate(prompt.trim(), markdown.trim(), duration);
  };

  return (
    <div className="flex flex-col h-full">
      <div className="flex-1 overflow-y-auto p-5 space-y-5">
        {/* Prompt */}
        <section className="space-y-2">
          <label className="block text-xs font-semibold text-[--fg-muted] uppercase tracking-wider">
            概念 Prompt
          </label>
          <textarea
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            placeholder="讲解梯度下降算法的原理，包括损失函数、偏导数、学习率的作用..."
            rows={6}
            className="w-full rounded-lg bg-[--bg-elevated] border border-[--border-default] text-[--fg-default] placeholder:text-[--fg-subtle] text-sm p-3 resize-none focus:outline-none focus:border-purple-500 transition-colors font-sans leading-relaxed"
          />
        </section>

        {/* Markdown */}
        <section className="space-y-2">
          <div className="flex items-center justify-between">
            <label className="block text-xs font-semibold text-[--fg-muted] uppercase tracking-wider">
              Markdown 补充
            </label>
            <span className="text-xs text-[--fg-subtle]">可选</span>
          </div>
          <textarea
            value={markdown}
            onChange={(e) => setMarkdown(e.target.value)}
            placeholder={"## 梯度下降\n\n更新规则：θ := θ − α · ∇L(θ)\n\n- θ 是参数\n- α 是学习率\n- ∇L 是梯度"}
            rows={8}
            className="w-full rounded-lg bg-[--bg-elevated] border border-[--border-default] text-[--fg-muted] placeholder:text-[--fg-subtle] text-xs p-3 resize-none focus:outline-none focus:border-purple-500 transition-colors font-mono leading-relaxed"
          />
        </section>

        {/* Settings */}
        <section className="space-y-3">
          <label className="block text-xs font-semibold text-[--fg-muted] uppercase tracking-wider">
            生成设置
          </label>

          <div className="space-y-1">
            <div className="flex justify-between text-xs">
              <span className="text-[--fg-default]">视频时长</span>
              <span className="font-mono text-purple-400">{Math.round(duration / 60)} 分钟</span>
            </div>
            <input
              type="range"
              min={60}
              max={180}
              step={10}
              value={duration}
              onChange={(e) => setDuration(Number(e.target.value))}
              className="w-full accent-purple-500"
            />
            <div className="flex justify-between text-xs text-[--fg-subtle]">
              <span>1 分钟</span>
              <span>3 分钟</span>
            </div>
          </div>

          <div className="flex items-center justify-between">
            <span className="text-xs text-[--fg-default]">动画风格</span>
            <span className="text-xs px-2 py-1 rounded border border-[--border-default] text-[--fg-muted] font-mono">
              Khan Academy 白板
            </span>
          </div>

          <div className="flex items-center justify-between">
            <span className="text-xs text-[--fg-default]">语音</span>
            <span className="text-xs px-2 py-1 rounded border border-[--border-default] text-[--fg-muted] font-mono">
              普通话 · 晓晓
            </span>
          </div>
        </section>
      </div>

      {/* Generate button */}
      <div className="p-4 border-t border-[--border-subtle]">
        <Button
          variant="primary"
          size="lg"
          className="w-full"
          onClick={handleSubmit}
          loading={loading}
          disabled={!prompt.trim()}
        >
          ✦ 生成 Explain 图谱
        </Button>
      </div>
    </div>
  );
}
