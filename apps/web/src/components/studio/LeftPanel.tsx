"use client";

import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { ACTIVE_PEN_STYLE_ID, ACTIVE_VIDEO_STYLE_ID, PEN_STYLE_OPTIONS, VIDEO_STYLE_OPTIONS } from "@/lib/constants";
import type { PenStyleId, VideoStyleId } from "@/lib/types";

interface Props {
  onGenerate: (prompt: string, markdown: string, videoStyle: VideoStyleId, penStyle: PenStyleId) => void;
  loading: boolean;
  duration: number;
  onDurationChange: (duration: number) => void;
  videoStyle: VideoStyleId;
  onVideoStyleChange: (style: VideoStyleId) => void;
  penStyle: PenStyleId;
  onPenStyleChange: (style: PenStyleId) => void;
}

function durationLabel(seconds: number) {
  const minutes = Math.floor(seconds / 60);
  const rest = seconds % 60;
  if (rest === 0) return `${minutes} 分钟`;
  return `${minutes}分${rest.toString().padStart(2, "0")}秒`;
}

export function LeftPanel({
  onGenerate,
  loading,
  duration,
  onDurationChange,
  videoStyle,
  onVideoStyleChange,
  penStyle,
  onPenStyleChange,
}: Props) {
  const [prompt, setPrompt] = useState("");
  const [markdown, setMarkdown] = useState("");

  const handleSubmit = () => {
    if (!prompt.trim()) return;
    onGenerate(prompt.trim(), markdown.trim(), ACTIVE_VIDEO_STYLE_ID, ACTIVE_PEN_STYLE_ID);
  };

  return (
    <div className="flex flex-col h-full">
      <div className="flex-1 overflow-y-auto p-5 space-y-5">
        {/* Prompt */}
        <section className="space-y-2">
          <label className="block text-xs font-semibold text-[--fg-muted] uppercase tracking-wider">
            视频主题
          </label>
          <textarea
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            placeholder="如何制作好吃的麻婆豆腐，要求图文并茂..."
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
              <span className="font-mono text-purple-400">{durationLabel(duration)}</span>
            </div>
            <input
              type="range"
              min={60}
              max={180}
              step={10}
              value={duration}
              onChange={(e) => onDurationChange(Number(e.target.value))}
              className="w-full accent-purple-500"
            />
            <div className="flex justify-between text-xs text-[--fg-subtle]">
              <span>1 分钟</span>
              <span>3 分钟</span>
            </div>
          </div>

          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-xs text-[--fg-default]">Canvas Visual Style</span>
              <span className="text-xs px-2 py-1 rounded border border-[--border-default] text-[--fg-muted]">
                1 available
              </span>
            </div>
            <div className="grid grid-cols-2 gap-2">
              {VIDEO_STYLE_OPTIONS.map((option) => {
                const selected = option.id === videoStyle;
                const unavailable = !option.available;
                return (
                  <button
                    key={option.id}
                    type="button"
                    onClick={() => {
                      if (!unavailable) onVideoStyleChange(option.id);
                    }}
                    disabled={loading || unavailable}
                    aria-disabled={loading || unavailable}
                    title={unavailable ? option.unavailableReason : option.tone}
                    className={`min-h-16 rounded-lg border p-2 text-left transition-colors disabled:cursor-not-allowed ${
                      unavailable
                        ? "border-[--border-default] bg-[--bg-elevated]/45 text-[--fg-subtle] opacity-45 grayscale"
                        : selected
                        ? "border-purple-500 bg-purple-500/10 text-[--fg-default]"
                        : "border-[--border-default] bg-[--bg-elevated] text-[--fg-muted] hover:border-[--border-subtle] hover:text-[--fg-default]"
                    }`}
                  >
                    <span className="flex items-center gap-1.5 min-w-0">
                      <span className={`h-2 w-2 rounded-full ${option.swatch} ${unavailable ? "opacity-40" : ""}`} />
                      <span className="text-xs font-medium">{option.label}</span>
                      {unavailable && (
                        <span className="ml-auto rounded border border-[--border-default] px-1 py-0.5 text-[10px] text-[--fg-subtle]">
                          暂不可用
                        </span>
                      )}
                    </span>
                    <span className="mt-1 block text-[11px] text-[--fg-subtle] leading-snug">
                      {option.fit}
                    </span>
                  </button>
                );
              })}
            </div>
          </div>

          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-xs text-[--fg-default]">Pen-in-hand Animation</span>
              <span className="text-xs px-2 py-1 rounded border border-[--border-default] text-[--fg-muted]">
                Marker only
              </span>
            </div>
            <div className="grid grid-cols-2 gap-2">
              {PEN_STYLE_OPTIONS.map((option) => {
                const selected = option.id === penStyle;
                const unavailable = !option.available;
                return (
                  <button
                    key={option.id}
                    type="button"
                    onClick={() => {
                      if (!unavailable) onPenStyleChange(option.id);
                    }}
                    disabled={loading || unavailable}
                    aria-disabled={loading || unavailable}
                    title={unavailable ? option.unavailableReason : option.label}
                    className={`min-h-12 rounded-lg border px-2.5 py-2 text-left transition-colors disabled:cursor-not-allowed ${
                      unavailable
                        ? "border-[--border-default] bg-[--bg-elevated]/45 text-[--fg-subtle] opacity-45 grayscale"
                        : selected
                        ? "border-purple-500 bg-purple-500/10 text-[--fg-default]"
                        : "border-[--border-default] bg-[--bg-elevated] text-[--fg-muted] hover:border-[--border-subtle] hover:text-[--fg-default]"
                    }`}
                  >
                    <span className="flex items-center justify-between gap-2 text-xs font-medium">
                      <span>{option.label}</span>
                      {unavailable && <span className="text-[10px] text-[--fg-subtle]">暂不可用</span>}
                    </span>
                    <span className="mt-0.5 block text-[11px] text-[--fg-subtle] leading-snug">
                      {option.fit}
                    </span>
                  </button>
                );
              })}
            </div>
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
          {loading ? "正在生成 Storyboard" : "生成 Storyboard"}
        </Button>
      </div>
    </div>
  );
}
