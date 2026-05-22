"use client";

import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { StoryboardView } from "@/components/storyboard/StoryboardView";
import { generateSceneImage, synthesizeSceneAudio } from "@/lib/api";
import type { BackgroundMusicTrack, RenderJobStatus, Storyboard } from "@/lib/types";
import { elapsedSeconds, estimateRemainingSeconds, etaLabel } from "@/lib/renderEstimate";

import { RENDER_URL, penStyleLabel, videoStyleLabel } from "@/lib/constants";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type RenderState = "idle" | "submitting" | "polling" | "done" | "failed";

type RenderPhase = "queued" | "tts" | "imagegen" | "codegen" | "bundling" | "rendering" | "qa" | "done" | "failed" | null;

const PHASE_LABEL: Record<NonNullable<RenderPhase>, string> = {
  queued: "排队中",
  tts: "合成语音",
  imagegen: "生成线稿",
  codegen: "生成动画代码",
  bundling: "编译 Remotion",
  rendering: "渲染视频",
  qa: "自动验收",
  failed: "失败",
  done: "已完成",
};

function RenderButton({
  storyboard,
  subtitlesEnabled,
  backgroundMusicEnabled,
  backgroundMusicId,
  backgroundMusicVolume,
  onVideoReady,
}: {
  storyboard: Storyboard;
  subtitlesEnabled: boolean;
  backgroundMusicEnabled: boolean;
  backgroundMusicId: string | null;
  backgroundMusicVolume: number;
  onVideoReady: (url: string) => void;
}) {
  const [state, setState] = useState<RenderState>("idle");
  const [jobId, setJobId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [progress, setProgress] = useState(0);
  const [phase, setPhase] = useState<RenderPhase>(null);
  const [startedAt, setStartedAt] = useState<string | number | null>(null);
  const [actualDurationSeconds, setActualDurationSeconds] = useState<number | null>(null);

  const poll = useCallback(
    async (id: string) => {
      const res = await fetch(`${API}/render/job/${id}`);
      const data = (await res.json()) as RenderJobStatus;
      if (typeof data.actualDurationSeconds === "number") {
        setActualDurationSeconds(data.actualDurationSeconds);
      }
      if (data.status === "done") {
        setState("done");
        setProgress(100);
        if (data.createdAt) setStartedAt(data.createdAt);
        // Direct to render server (3001) for Range request support + no FastAPI proxy overhead
        onVideoReady(`${RENDER_URL}/download/${id}`);
      } else if (data.status === "failed") {
        setState("failed");
        setError(data.error ?? "渲染失败");
      } else {
        setProgress(data.progress ?? 0);
        setPhase(data.phase ?? null);
        if (data.createdAt) setStartedAt(data.createdAt);
        setTimeout(() => poll(id), 2000);
      }
    },
    [onVideoReady]
  );

  const handleRender = async () => {
    setState("submitting");
    setError(null);
    setProgress(0);
    setPhase(null);
    setActualDurationSeconds(null);
    setStartedAt(Date.now());
    try {
      const res = await fetch(`${API}/render/job`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          storyboard,
          voice: "xiaoxiao",
          resolution: "1080p",
          subtitles_enabled: subtitlesEnabled,
          background_music_enabled: backgroundMusicEnabled,
          background_music_id: backgroundMusicId,
          background_music_volume: backgroundMusicVolume,
        }),
      });
      if (!res.ok) {
        const d = await res.json();
        throw new Error(d.detail ?? "提交失败");
      }
      const { job_id, createdAt } = (await res.json()) as { job_id: string; createdAt?: string | null };
      setJobId(job_id);
      if (createdAt) setStartedAt(createdAt);
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
    const phaseLabel = phase ? PHASE_LABEL[phase] : (state === "submitting" ? "提交中" : "准备中");
    const showProgress =
      state === "polling" &&
      (phase === "bundling" || phase === "rendering") &&
      progress > 0;
    const elapsed = elapsedSeconds(startedAt);
    const remaining = estimateRemainingSeconds({
      phase: phase ?? "queued",
      progress,
      elapsed,
      storyboard,
    });
    const etaText = etaLabel(remaining);
    return (
      <div className="flex items-center gap-3">
        <div className="flex flex-col items-end gap-1">
          <div className="flex items-center gap-2 text-sm text-purple-400">
            <span className="inline-block w-3 h-3 border-2 border-purple-400 border-t-transparent rounded-full animate-spin" />
            <span>{phaseLabel}...</span>
            {showProgress && (
              <span className="font-mono text-xs text-purple-300">{progress}%</span>
            )}
          </div>
          {showProgress && (
            <div className="w-40 h-1 bg-purple-900/40 rounded-full overflow-hidden">
              <div
                className="h-full bg-purple-500 rounded-full transition-all duration-500"
                style={{ width: `${progress}%` }}
              />
            </div>
          )}
          <span className="text-[11px] text-[--fg-muted] font-mono">
            {etaText}
            {actualDurationSeconds ? ` · 视频约 ${Math.round(actualDurationSeconds)}s` : ""}
          </span>
        </div>
      </div>
    );
  }

  // done — show download button alongside the watch indicator
  return (
    <div className="flex items-center gap-2">
      <span className="text-xs text-green-400 font-mono">✓ 已生成</span>
      <a
        href={`${RENDER_URL}/download/${jobId}`}
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
  total_duration_estimate: 130,
  video_style: "whiteboard",
  pen_style: "marker",
  scenes: [
    {
      id: "scene_0",
      order: 0,
      title: "开场：今天讲什么",
      narration: "今天我们来讲解机器学习中最核心的优化算法——梯度下降。它是深度学习一切的基础，无论是 GPT 还是 Stable Diffusion，背后都在用它。",
      duration_estimate: 18,
      node_ids: [],
      animations: [
        { type: "write_text", duration: 3, content: "梯度下降" },
        { type: "bullet_list", duration: 8, content: "今天你会学到", items: ["什么是损失函数", "梯度的含义", "参数如何更新", "收敛的过程"] },
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
        { type: "concept_bubble", duration: 3, content: "损失函数 L(θ)" },
        { type: "write_formula", duration: 6, content: "均方误差（MSE）", latex: "L(θ) = (1/n)·Σ(y - ŷ)²" },
        { type: "write_text", duration: 4, content: "损失 = 预测误差的度量" },
      ],
    },
    {
      id: "scene_2",
      order: 2,
      title: "梯度是什么",
      narration: "梯度是损失函数对参数的偏导数。它告诉我们，在当前点沿哪个方向走，损失增大最快。我们要反着走，所以叫梯度下降。",
      duration_estimate: 30,
      node_ids: ["node_1"],
      animations: [
        { type: "write_text", duration: 3, content: "∇L(θ)  =  损失函数的梯度" },
        { type: "draw_arrow", duration: 4, content: "梯度方向 = 损失增大最快" },
        { type: "write_text", duration: 4, content: "我们沿 梯度反方向 走 → 损失减小" },
      ],
    },
    {
      id: "scene_3",
      order: 3,
      title: "参数更新公式",
      narration: "参数更新公式是：新参数等于旧参数减去学习率乘以梯度。学习率控制每步的步长，太大会震荡，太小会很慢。",
      duration_estimate: 32,
      node_ids: ["node_2"],
      animations: [
        { type: "write_formula", duration: 6, content: "参数更新规则", latex: "θ := θ − α · ∇L(θ)" },
        { type: "step_reveal", duration: 12, content: "三个关键量", items: ["θ — 模型参数（需要学习的权重）", "α — 学习率（控制步长大小）", "∇L(θ) — 梯度（告诉你往哪走）"] },
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
        { type: "concept_bubble", duration: 3, content: "不断迭代 → 参数收敛" },
        { type: "bullet_list", duration: 8, content: "核心要点", items: ["损失函数定义目标", "梯度告诉方向", "学习率控制步长", "迭代直到收敛"] },
      ],
    },
  ],
};

export default function StoryboardPage() {
  const [storyboard, setStoryboard] = useState<Storyboard>(DEMO_STORYBOARD);
  const [videoUrl, setVideoUrl] = useState<string | null>(null);
  const [subtitlesEnabled, setSubtitlesEnabled] = useState(false);
  const [backgroundMusicEnabled, setBackgroundMusicEnabled] = useState(false);
  const [musicTracks, setMusicTracks] = useState<BackgroundMusicTrack[]>([]);
  const [selectedMusicId, setSelectedMusicId] = useState("");
  const [musicError, setMusicError] = useState<string | null>(null);
  const [sceneActionError, setSceneActionError] = useState<string | null>(null);
  const [busySceneAction, setBusySceneAction] = useState<string | null>(null);
  const backgroundMusicVolume = 0.12;

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

  const handleSceneUpdate = (sceneId: string, updates: Partial<Storyboard["scenes"][number]>) => {
    persistStoryboard((current) => ({
      ...current,
      scenes: current.scenes.map((scene) =>
        scene.id === sceneId ? { ...scene, ...updates } : scene
      ),
    }));
  };

  const persistStoryboard = (updater: (current: Storyboard) => Storyboard) => {
    setStoryboard((current) => {
      const next = updater(current);
      sessionStorage.setItem("explainflow_storyboard", JSON.stringify(next));
      return next;
    });
  };

  const withSceneAction = async (sceneId: string, action: string, fn: () => Promise<void>) => {
    setBusySceneAction(`${sceneId}:${action}`);
    setSceneActionError(null);
    try {
      await fn();
    } catch (error) {
      setSceneActionError(error instanceof Error ? error.message : "场景修复失败");
    } finally {
      setBusySceneAction(null);
    }
  };

  const handleRegenerateSceneImage = async (scene: Storyboard["scenes"][number]) => {
    await withSceneAction(scene.id, "image", async () => {
      const imageUrl = await generateSceneImage(storyboard, scene);
      persistStoryboard((current) => ({
        ...current,
        scenes: current.scenes.map((item) =>
          item.id === scene.id
            ? {
                ...item,
                image_url: imageUrl,
                reference_image_base64: imageUrl,
                render_strategy: item.render_strategy || "hybrid",
                hand_usage: item.hand_usage || "annotate",
              }
            : item
        ),
      }));
    });
  };

  const handleRegenerateSceneAudio = async (scene: Storyboard["scenes"][number]) => {
    await withSceneAction(scene.id, "audio", async () => {
      const audioUrl = await synthesizeSceneAudio(scene.narration || scene.title);
      persistStoryboard((current) => ({
        ...current,
        scenes: current.scenes.map((item) =>
          item.id === scene.id ? { ...item, audioUrl } : item
        ),
      }));
    });
  };

  const handleRepairSceneCallouts = (scene: Storyboard["scenes"][number]) => {
    const trimLabels = (labels: string[] | undefined) => (labels ?? []).slice(0, 4);
    persistStoryboard((current) => ({
      ...current,
      scenes: current.scenes.map((item) => {
        if (item.id !== scene.id) return item;
        return {
          ...item,
          render_strategy: "hybrid",
          hand_usage: item.hand_usage === "none" ? "none" : "annotate",
          visual_complexity: item.visual_complexity === "dense" ? "medium" : item.visual_complexity,
          diagram_plan: item.diagram_plan
            ? {
                ...item.diagram_plan,
                required_labels: trimLabels(item.diagram_plan.required_labels),
              }
            : item.diagram_plan,
          visual_beats: (item.visual_beats ?? []).map((beat) => ({
            ...beat,
            required_labels: trimLabels(beat.required_labels),
          })),
          qa_fix_hint: "callouts_repaired_short_labels_near_subject",
        };
      }),
    }));
  };

  useEffect(() => {
    let active = true;
    fetch(`${API}/render/music`)
      .then(async (res) => {
        if (!res.ok) throw new Error("music unavailable");
        return (await res.json()) as { tracks?: BackgroundMusicTrack[] };
      })
      .then((data) => {
        if (!active) return;
        const tracks = data.tracks ?? [];
        setMusicTracks(tracks);
        setSelectedMusicId((current) => current || tracks[0]?.id || "");
        setMusicError(null);
      })
      .catch(() => {
        if (!active) return;
        setMusicTracks([]);
        setMusicError("音乐库不可用");
      });
    return () => {
      active = false;
    };
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
          <Link
            href="/jobs"
            className="h-8 px-3 rounded-md border border-[--border-default] hover:border-[--border-subtle] text-xs text-[--fg-muted] hover:text-[--fg-default] inline-flex items-center transition-colors"
          >
            视频库
          </Link>
          <span className="text-xs font-mono text-[--fg-muted]">
            {videoStyleLabel(storyboard.video_style)} · {penStyleLabel(storyboard.pen_style)} · 共 {storyboard.scenes.length} 场 · {Math.round(storyboard.total_duration_estimate)}s
          </span>
          <label className="h-8 px-2.5 rounded-md border border-[--border-default] text-xs text-[--fg-muted] inline-flex items-center gap-2 select-none cursor-pointer">
            <input
              type="checkbox"
              checked={subtitlesEnabled}
              onChange={(event) => setSubtitlesEnabled(event.target.checked)}
              className="sr-only"
            />
            <span
              className={`relative h-4 w-7 rounded-full border transition-colors ${
                subtitlesEnabled
                  ? "bg-purple-500/30 border-purple-500"
                  : "bg-[--bg-elevated] border-[--border-default]"
              }`}
            >
              <span
                className={`absolute top-0.5 h-2.5 w-2.5 rounded-full transition-transform ${
                  subtitlesEnabled
                    ? "translate-x-3.5 bg-purple-300"
                    : "translate-x-0.5 bg-[--fg-subtle]"
                }`}
              />
            </span>
            <span className={subtitlesEnabled ? "text-purple-300" : ""}>字幕</span>
          </label>
          <label className="h-8 px-2.5 rounded-md border border-[--border-default] text-xs text-[--fg-muted] inline-flex items-center gap-2 select-none cursor-pointer">
            <input
              type="checkbox"
              checked={backgroundMusicEnabled}
              onChange={(event) => setBackgroundMusicEnabled(event.target.checked)}
              disabled={musicTracks.length === 0}
              className="sr-only"
            />
            <span
              className={`relative h-4 w-7 rounded-full border transition-colors ${
                backgroundMusicEnabled && musicTracks.length > 0
                  ? "bg-purple-500/30 border-purple-500"
                  : "bg-[--bg-elevated] border-[--border-default]"
              }`}
            >
              <span
                className={`absolute top-0.5 h-2.5 w-2.5 rounded-full transition-transform ${
                  backgroundMusicEnabled && musicTracks.length > 0
                    ? "translate-x-3.5 bg-purple-300"
                    : "translate-x-0.5 bg-[--fg-subtle]"
                }`}
              />
            </span>
            <span className={backgroundMusicEnabled ? "text-purple-300" : ""}>音乐</span>
          </label>
          {backgroundMusicEnabled && (
            <select
              value={selectedMusicId}
              onChange={(event) => setSelectedMusicId(event.target.value)}
              disabled={musicTracks.length === 0}
              className="h-8 max-w-44 rounded-md border border-[--border-default] bg-[--bg-elevated] px-2 text-xs text-[--fg-muted] outline-none hover:border-[--border-subtle] focus:border-purple-500"
              title={musicTracks.find((track) => track.id === selectedMusicId)?.name ?? "背景音乐"}
            >
              {musicTracks.map((track) => (
                <option key={track.id} value={track.id}>
                  {track.name}
                </option>
              ))}
            </select>
          )}
          {musicError && (
            <span className="max-w-24 truncate text-xs text-red-400" title={musicError}>
              {musicError}
            </span>
          )}
          {sceneActionError && (
            <span className="max-w-48 truncate text-xs text-red-400" title={sceneActionError}>
              {sceneActionError}
            </span>
          )}
          <RenderButton
            storyboard={storyboard}
            subtitlesEnabled={subtitlesEnabled}
            backgroundMusicEnabled={backgroundMusicEnabled && musicTracks.length > 0}
            backgroundMusicId={selectedMusicId || null}
            backgroundMusicVolume={backgroundMusicVolume}
            onVideoReady={setVideoUrl}
          />
        </div>
      </header>

      {/* Content */}
      <div className="flex-1 overflow-hidden">
        <StoryboardView
          storyboard={storyboard}
          videoUrl={videoUrl}
          onSceneUpdate={handleSceneUpdate}
          onRegenerateSceneImage={handleRegenerateSceneImage}
          onRegenerateSceneAudio={handleRegenerateSceneAudio}
          onRepairSceneCallouts={handleRepairSceneCallouts}
          busySceneAction={busySceneAction}
        />
      </div>
    </div>
  );
}
