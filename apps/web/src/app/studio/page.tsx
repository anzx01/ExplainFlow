"use client";

import { useState } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/Button";
import { LeftPanel } from "@/components/studio/LeftPanel";
import { ExplainGraphView } from "@/components/studio/ExplainGraphView";
import { generateGraph, generateStoryboard } from "@/lib/api";
import type { ExplainGraph, Storyboard } from "@/lib/types";

type Tab = "graph" | "preview";

export default function StudioPage() {
  const [graph, setGraph] = useState<ExplainGraph | null>(null);
  const [storyboard, setStoryboard] = useState<Storyboard | null>(null);
  const [loadingGraph, setLoadingGraph] = useState(false);
  const [loadingStoryboard, setLoadingStoryboard] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("graph");
  const [projectName, setProjectName] = useState("未命名项目");

  const handleGenerate = async (prompt: string, markdown: string, duration: number) => {
    setError(null);
    setLoadingGraph(true);
    setGraph(null);
    setStoryboard(null);

    try {
      const g = await generateGraph(prompt, markdown);
      setGraph(g);
      setProjectName(g.topic);
      setTab("graph");
    } catch (e) {
      setError(e instanceof Error ? e.message : "生成失败，请检查 API 配置");
    } finally {
      setLoadingGraph(false);
    }
  };

  const handleGenerateStoryboard = async () => {
    if (!graph) return;
    setLoadingStoryboard(true);
    try {
      const sb = await generateStoryboard(graph, 120);
      setStoryboard(sb);
      sessionStorage.setItem("explainflow_storyboard", JSON.stringify(sb));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Storyboard 生成失败");
    } finally {
      setLoadingStoryboard(false);
    }
  };

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
          {(graph || storyboard) && (
            <span className="flex items-center gap-1.5 text-xs text-green-500 font-mono">
              <span className="inline-block w-1.5 h-1.5 rounded-full bg-green-500" />
              已保存
            </span>
          )}
        </div>

        <div className="flex items-center gap-3">
          {graph && !storyboard && (
            <Button
              variant="secondary"
              size="sm"
              onClick={handleGenerateStoryboard}
              loading={loadingStoryboard}
            >
              生成 Storyboard
            </Button>
          )}
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
          <LeftPanel onGenerate={handleGenerate} loading={loadingGraph} />
        </div>

        {/* Right panel */}
        <div className="flex-1 flex flex-col overflow-hidden">
          {/* Tab bar */}
          <div className="flex items-end gap-1 px-6 bg-[--bg-surface] border-b border-[--border-subtle] flex-shrink-0 h-11">
            {(["graph", "preview"] as Tab[]).map((t) => (
              <button
                key={t}
                onClick={() => setTab(t)}
                className={`flex items-center gap-2 h-full px-4 text-sm border-b-2 transition-colors ${
                  tab === t
                    ? "border-purple-500 text-[--fg-default]"
                    : "border-transparent text-[--fg-muted] hover:text-[--fg-default]"
                }`}
              >
                {t === "graph" ? "⬡ Explain 图谱" : "▶ 预览"}
              </button>
            ))}
          </div>

          {/* Tab content */}
          <div className="flex-1 overflow-hidden flex flex-col">
            {tab === "graph" && (
              <ExplainGraphView graph={graph} loading={loadingGraph} />
            )}
            {tab === "preview" && (
              <div className="flex-1 flex items-center justify-center text-[--fg-muted] text-sm">
                <div className="text-center space-y-3">
                  <div className="text-4xl opacity-20">▶</div>
                  <p>请先生成 Storyboard，再预览视频效果</p>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
