"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { LeftPanel } from "@/components/studio/LeftPanel";
import { generateGraph, generateStoryboard } from "@/lib/api";
import { ACTIVE_PEN_STYLE_ID, ACTIVE_VIDEO_STYLE_ID, penStyleLabel, videoStyleLabel } from "@/lib/constants";
import type { PenStyleId, Storyboard, VideoStyleId } from "@/lib/types";

type GenerationStage = "idle" | "graph" | "storyboard";

export default function StudioPage() {
  const router = useRouter();
  const [storyboard, setStoryboard] = useState<Storyboard | null>(null);
  const [generationStage, setGenerationStage] = useState<GenerationStage>("idle");
  const [error, setError] = useState<string | null>(null);
  const [projectName, setProjectName] = useState("未命名项目");
  const [targetDuration, setTargetDuration] = useState(120);
  const [videoStyle, setVideoStyle] = useState<VideoStyleId>(ACTIVE_VIDEO_STYLE_ID);
  const [penStyle, setPenStyle] = useState<PenStyleId>(ACTIVE_PEN_STYLE_ID);

  const handleDurationChange = (duration: number) => {
    setTargetDuration(duration);
    if (storyboard) {
      setStoryboard(null);
      sessionStorage.removeItem("explainflow_storyboard");
    }
  };

  const handleStyleChange = (style: VideoStyleId) => {
    if (style !== ACTIVE_VIDEO_STYLE_ID) return;
    setVideoStyle(style);
    if (storyboard) {
      setStoryboard(null);
      sessionStorage.removeItem("explainflow_storyboard");
    }
  };

  const handlePenStyleChange = (style: PenStyleId) => {
    if (style !== ACTIVE_PEN_STYLE_ID) return;
    setPenStyle(style);
    if (storyboard) {
      setStoryboard(null);
      sessionStorage.removeItem("explainflow_storyboard");
    }
  };

  const handleGenerate = async (
    prompt: string,
    markdown: string,
    style: VideoStyleId,
    pen: PenStyleId
  ) => {
    setError(null);
    setGenerationStage("graph");
    setStoryboard(null);
    sessionStorage.removeItem("explainflow_storyboard");

    try {
      const g = await generateGraph(prompt, markdown);
      setProjectName(g.topic);
      setGenerationStage("storyboard");
      const requestedStyle = style === ACTIVE_VIDEO_STYLE_ID ? style : ACTIVE_VIDEO_STYLE_ID;
      const requestedPen = pen === ACTIVE_PEN_STYLE_ID ? pen : ACTIVE_PEN_STYLE_ID;
      const sb = await generateStoryboard(g, targetDuration, requestedStyle, requestedPen);
      setStoryboard(sb);
      sessionStorage.setItem("explainflow_storyboard", JSON.stringify(sb));
      router.push("/storyboard");
    } catch (e) {
      setError(e instanceof Error ? e.message : "生成 Storyboard 失败，请检查 API 配置");
    } finally {
      setGenerationStage("idle");
    }
  };

  const isGenerating = generationStage !== "idle";

  return (
    <div className="flex flex-col h-screen bg-[--bg-base] text-[--fg-default] overflow-hidden">
      {/* NavBar */}
      <header className="flex items-center justify-between px-6 h-14 bg-[--bg-surface] border-b border-[--border-subtle] flex-shrink-0">
        <div className="flex items-center gap-4">
          <Link href="/" className="flex items-center gap-2 text-[--fg-muted] hover:text-[--fg-default] transition-colors">
            <span className="text-sm">←</span>
          </Link>
          <div className="w-px h-5 bg-[--border-default]" />
          <div className="flex items-center gap-2">
            <div className="w-5 h-5 rounded bg-gradient-to-br from-purple-500 to-pink-500" />
            <input
              value={projectName}
              onChange={(e) => setProjectName(e.target.value)}
              className="bg-transparent text-sm font-medium text-[--fg-default] focus:outline-none border-b border-transparent focus:border-[--border-default] transition-colors min-w-0 w-48"
            />
          </div>
          {storyboard && (
            <span className="flex items-center gap-1.5 text-xs text-green-500 font-mono">
              <span className="inline-block w-1.5 h-1.5 rounded-full bg-green-500" />
              已保存
            </span>
          )}
        </div>

        <div className="flex items-center gap-3">
          <Link
            href="/jobs"
            className="h-8 px-3 rounded-md border border-[--border-default] hover:border-[--border-subtle] text-xs text-[--fg-muted] hover:text-[--fg-default] inline-flex items-center transition-colors"
          >
            视频库
          </Link>
          {storyboard && (
            <Link
              href="/storyboard"
              className="h-8 px-4 rounded-md bg-purple-500 hover:bg-purple-400 text-white text-xs font-medium inline-flex items-center transition-colors"
            >
              前往 Storyboard →
            </Link>
          )}
        </div>
      </header>

      {/* Error */}
      {error && (
        <div className="px-6 py-2 bg-red-900/20 border-b border-red-800/30 text-sm text-red-400 flex items-center gap-2">
          <span>⚠</span> {error}
          <button onClick={() => setError(null)} className="ml-auto text-red-500 hover:text-red-400">×</button>
        </div>
      )}

      {/* Body */}
      <div className="flex flex-1 overflow-hidden">
        {/* Left panel */}
        <div className="w-96 flex-shrink-0 bg-[--bg-surface] border-r border-[--border-subtle] flex flex-col overflow-hidden">
          <LeftPanel
            onGenerate={handleGenerate}
            loading={isGenerating}
            duration={targetDuration}
            onDurationChange={handleDurationChange}
            videoStyle={videoStyle}
            onVideoStyleChange={handleStyleChange}
            penStyle={penStyle}
            onPenStyleChange={handlePenStyleChange}
          />
        </div>

        {/* Right panel */}
        <div className="flex-1 flex flex-col overflow-hidden">
          <div className="flex-1 overflow-hidden flex items-center justify-center">
            <div className="w-full max-w-lg px-8 text-center space-y-5">
              <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-2xl border border-purple-500/40 bg-purple-500/10 text-2xl text-purple-300">
                {isGenerating ? (
                  <span className="inline-block h-7 w-7 rounded-full border-2 border-current border-t-transparent animate-spin" />
                ) : (
                  "▶"
                )}
              </div>
              <div className="space-y-2">
                <h2 className="text-lg font-semibold text-[--fg-default]">
                  {generationStage === "graph"
                    ? "正在梳理讲解结构"
                    : generationStage === "storyboard"
                      ? "正在生成分镜与旁白"
                      : "准备生成 Storyboard"}
                </h2>
                <p className="text-sm leading-relaxed text-[--fg-muted]">
                  {isGenerating
                    ? "生成完成后会自动进入分镜编辑页。"
                    : "填写左侧内容后，系统会直接产出可编辑的分镜脚本。"}
                </p>
              </div>
              <div className="grid grid-cols-2 gap-3 text-left">
                <div className="rounded-lg border border-[--border-default] bg-[--bg-surface] p-3">
                  <p className="text-xs font-semibold text-[--fg-muted]">目标时长</p>
                  <p className="mt-1 text-sm text-purple-300">{targetDuration}s</p>
                </div>
                <div className="rounded-lg border border-[--border-default] bg-[--bg-surface] p-3">
                  <p className="text-xs font-semibold text-[--fg-muted]">视频风格</p>
                  <p className="mt-1 text-sm text-purple-300">
                    {videoStyleLabel(videoStyle)} · {penStyleLabel(penStyle)}
                  </p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
