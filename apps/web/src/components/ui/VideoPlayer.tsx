"use client";

import { useRef, useState } from "react";

export function VideoPlayer({ src, className }: { src: string; className?: string }) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [error, setError] = useState("");
  async function playWithSound() {
    const video = videoRef.current;
    if (!video) return;
    video.defaultPlaybackRate = 1;
    video.playbackRate = 1;
    video.muted = false;
    video.volume = 1;
    try {
      await video.play();
      setError("");
    } catch {
      setError("播放失败，请下载视频或检查浏览器的声音权限。");
    }
  }
  return (
    <div className="space-y-2">
      <video key={src} ref={videoRef} src={src} controls playsInline preload="metadata"
        className={className}
        onLoadedMetadata={(event) => {
          event.currentTarget.defaultPlaybackRate = 1;
          event.currentTarget.playbackRate = 1;
          event.currentTarget.muted = false;
          event.currentTarget.volume = 1;
        }}
        onError={() => setError("视频加载失败，请刷新任务列表后重试。")}
      />
      <button type="button" onClick={playWithSound}
        className="rounded-md border border-[--border-default] px-3 py-2 text-xs text-[--fg-default]">
        正常速度 · 有声播放
      </button>
      {error && <p role="alert" className="text-xs text-red-400">{error}</p>}
    </div>
  );
}
