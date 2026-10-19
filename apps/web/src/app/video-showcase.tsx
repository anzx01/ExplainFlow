"use client";

import { useEffect, useRef, useState } from "react";
import { fetchRenderJobsDirect, RENDER_BASE_URL } from "@/lib/api";
import type { RenderJobSummary } from "@/lib/types";

export default function VideoShowcase() {
  const [videos, setVideos] = useState<RenderJobSummary[]>([]);
  const [playingId, setPlayingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const playingRef = useRef<HTMLVideoElement | null>(null);

  useEffect(() => {
    fetchRenderJobsDirect()
      .then((jobs) => {
        const done = jobs.filter((j) => j.status === "done" && j.videoUrl);
        setVideos(done);
        if (!done.length) setError("还没有已完成的视频,去创作第一个吧");
      })
      .catch((err) => setError(err.message));
  }, []);

  const handlePlay = (id: string) => {
    setPlayingId(id);
    // 其它卡片暂停;被点卡片在用户手势内直接 play() 并取消静音
    window.setTimeout(() => {
      document.querySelectorAll<HTMLVideoElement>("video[data-showcase]").forEach((v) => {
        if (v.dataset.jobId !== id) {
          v.pause();
          // 其它卡片回到预览帧
          if (v.duration) v.currentTime = Math.max(1, v.duration * 0.6);
        }
      });
      if (playingRef.current) {
        playingRef.current.muted = false;
        playingRef.current.play().catch(() => {});
      }
    }, 50);
  };

  // 预览帧:加载元数据后跳到视频 60% 处(开场是空白板,中段才是完整画面)
  const handleMeta = (e: React.SyntheticEvent<HTMLVideoElement>) => {
    const el = e.currentTarget;
    if (!el.dataset.jobId || el.dataset.jobId === playingId) return;
    if (el.duration) el.currentTime = Math.max(1, el.duration * 0.6);
  };

  const handleError = (id: string) => {
    setVideos((prev) => prev.filter((v) => v.id !== id));
    setPlayingId((cur) => (cur === id ? null : cur));
  };

  if (error && !videos.length) {
    return (
      <section id="showcase" className="px-20 py-16 border-t border-[--border-subtle]">
        <h2 className="text-2xl font-bold mb-6 text-center">作品展示</h2>
        <p className="text-center text-sm text-[--fg-muted]">{error}</p>
      </section>
    );
  }
  if (!videos.length) return null;

  return (
    <section id="showcase" className="px-20 py-16 border-t border-[--border-subtle]">
      <div className="flex items-end justify-between mb-8">
        <div>
          <h2 className="text-4xl font-bold tracking-tight">作品展示</h2>
          <p className="text-sm text-[--fg-muted] mt-2">全部由 ExplainFlow 本地生成,点击任意视频即可播放</p>
        </div>
        <span className="text-xs font-mono text-[--fg-muted]">{videos.length} 个视频</span>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5">
        {videos.map((v) => {
          const isPlaying = playingId === v.id;
          return (
            <div
              key={v.id}
              role="button"
              tabIndex={0}
              onClick={() => handlePlay(v.id)}
              onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") handlePlay(v.id); }}
              className={`group text-left rounded-xl overflow-hidden border transition-colors cursor-pointer ${
                isPlaying
                  ? "border-purple-500 ring-1 ring-purple-500/40"
                  : "border-[--border-default] hover:border-purple-500/60"
              } bg-[--bg-surface]`}
            >
              <div className="relative aspect-video bg-black">
                <video
                  data-showcase
                  data-job-id={v.id}
                  ref={isPlaying ? playingRef : undefined}
                  src={`${RENDER_BASE_URL}${v.videoUrl}`}
                  preload="metadata"
                  muted={!isPlaying}
                  controls={isPlaying}
                  autoPlay={isPlaying}
                  playsInline
                  onLoadedMetadata={handleMeta}
                  onError={() => handleError(v.id)}
                  className="w-full h-full object-contain"
                />
                {!isPlaying && (
                  <span className="absolute inset-0 flex items-center justify-center bg-black/30 opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none">
                    <span className="w-12 h-12 rounded-full bg-purple-500/90 text-white flex items-center justify-center text-xl">▶</span>
                  </span>
                )}
              </div>
              <div className="px-3 py-2.5">
                <span className="block text-sm font-medium truncate">{v.topic || v.id}</span>
                <span className="block text-xs font-mono text-[--fg-muted] mt-0.5">
                  {v.actualDurationSeconds ? `${Math.round(v.actualDurationSeconds)}s` : "--"} · {v.id.slice(0, 8)}
                </span>
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}
