"use client";
import { VideoPlayer } from "@/components/ui/VideoPlayer";

import { useEffect, useState } from "react";
import dynamic from "next/dynamic";
import type { Scene, Storyboard, AnimationInstruction } from "@/lib/types";
import { penStyleLabel, videoStyleLabel } from "@/lib/constants";

const StoryboardCanvasEditor = dynamic(() => import("./StoryboardCanvasEditor"), { ssr: false });

interface Props {
  storyboard: Storyboard;
  videoUrl?: string | null;
  onSceneUpdate?: (sceneId: string, updates: Partial<Scene>) => void;
  onRegenerateSceneImage?: (scene: Scene) => Promise<void> | void;
  onRegenerateSceneAudio?: (scene: Scene) => Promise<void> | void;
  onRepairSceneCallouts?: (scene: Scene) => Promise<void> | void;
  busySceneAction?: string | null;
}

const ANIM_LABELS: Record<string, string> = {
  whiteboard_draw: "✏ 白板书写",
  formula_reveal: "∑ 公式展示",
  concept_node: "⬡ 概念节点",
  arrow_connect: "→ 箭头连接",
  highlight: "★ 高亮",
  particle_flow: "⋯ 粒子流",
  network_layer: "⊞ 网络层",
  text_narration: "T 文字旁白",
};

const STYLE_LABELS: Record<string, string> = {
  teacher_whiteboard: "经典白板",
  marketing_doodle: "彩色手绘",
  math_chalkboard: "数学黑板",
  technical_reference: "参考标注",
  modern_minimal: "极简",
  editorial: "编辑",
  playful: "趣味",
  sharpie: "Sharpie",
};

function AnimationTag({ anim }: { anim: AnimationInstruction }) {
  return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs bg-[--bg-base] border border-[--border-default] text-[--fg-muted] font-mono">
      {ANIM_LABELS[anim.type] ?? anim.type}
      <span className="text-[--fg-subtle]">{anim.duration}s</span>
    </span>
  );
}

function AssetContractPanel({ scene }: { scene: Scene }) {
  const contract = scene.assetContract;
  const elements = [...(scene.renderElements ?? [])].sort((a, b) => a.sequence - b.sequence);
  if (!contract && elements.length === 0) return null;
  return (
    <div className="space-y-3">
      {contract && (
        <div>
          <h3 className="text-xs font-semibold text-[--fg-muted] uppercase tracking-wider mb-2">
            资产契约
          </h3>
          <div className="rounded-lg bg-[--bg-base] border border-[--border-default] p-3 space-y-2 text-xs font-mono text-[--fg-muted]">
            <div className="flex flex-wrap gap-x-4 gap-y-1">
              <span>mode: <b className="text-cyan-300">{contract.mode}</b></span>
              <span>size: <b className="text-[--fg-default]">{contract.width ?? "?"}×{contract.height ?? "?"}</b></span>
              <span>quality: <b className="text-[--fg-default]">{contract.quality ?? "?"}</b></span>
            </div>
            <div>layers: <b className="text-[--fg-default]">{(contract.layers ?? []).join(" → ") || "未记录"}</b></div>
            {contract.provider && <div>provider: {contract.provider}</div>}
            {contract.sourceHash && <div className="truncate" title={contract.sourceHash}>source: {contract.sourceHash.slice(0, 16)}…</div>}
            {contract.promptHash && <div className="truncate" title={contract.promptHash}>prompt: {contract.promptHash.slice(0, 16)}…</div>}
            {contract.observedContentBounds && (
              <div>
                bounds: ({contract.observedContentBounds.x}, {contract.observedContentBounds.y}) {contract.observedContentBounds.width}×{contract.observedContentBounds.height}
                {typeof contract.cropConfidence === "number" ? ` · ${(contract.cropConfidence * 100).toFixed(0)}%` : ""}
              </div>
            )}
          </div>
        </div>
      )}
      {elements.length > 0 && (
        <div>
          <h3 className="text-xs font-semibold text-[--fg-muted] uppercase tracking-wider mb-2">
            元素时间轴
          </h3>
          <div className="rounded-lg bg-[--bg-base] border border-[--border-default] divide-y divide-[--border-default]">
            {elements.map((element) => (
              <div key={element.id} className="px-3 py-2 text-xs font-mono text-[--fg-muted] flex items-center justify-between gap-3">
                <span className="truncate text-[--fg-default]">{element.sequence}. {element.id}</span>
                <span className="shrink-0">{element.reveal.startMs}–{element.reveal.startMs + element.reveal.durationMs}ms</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function SceneCard({
  scene,
  selected,
  onClick,
}: {
  scene: Scene;
  selected: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={`w-full text-left p-3 rounded-lg border transition-all ${
        selected
          ? "border-purple-500 bg-purple-500/10"
          : "border-[--border-default] hover:border-[--border-subtle] bg-[--bg-elevated] hover:bg-[--bg-surface]"
      }`}
    >
      <div className="flex items-start gap-3">
        <span
          className={`flex-shrink-0 w-6 h-6 rounded text-xs font-mono flex items-center justify-center ${
            selected ? "bg-purple-500 text-white" : "bg-[--bg-base] text-[--fg-muted]"
          }`}
        >
          {scene.order + 1}
        </span>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-[--fg-default] truncate">{scene.title}</p>
          <p className="text-xs text-[--fg-muted] mt-0.5 font-mono">
            {scene.duration_estimate}s
            {scene.video_style
              ? ` · ${videoStyleLabel(scene.video_style)}`
              : ""}
            {scene.pen_style
              ? ` · ${penStyleLabel(scene.pen_style)}`
              : ""}
            {scene.visual_style ? ` · ${STYLE_LABELS[scene.visual_style] ?? scene.visual_style}` : ""}
          </p>
        </div>
      </div>
    </button>
  );
}

function SceneEditor({
  scene,
  onUpdate,
  onRegenerateImage,
  onRegenerateAudio,
  onRepairCallouts,
  busyAction,
}: {
  scene: Scene;
  onUpdate?: (updates: Partial<Scene>) => void;
  onRegenerateImage?: (scene: Scene) => Promise<void> | void;
  onRegenerateAudio?: (scene: Scene) => Promise<void> | void;
  onRepairCallouts?: (scene: Scene) => Promise<void> | void;
  busyAction?: string | null;
}) {
  const isBusy = (action: string) => busyAction === `${scene.id}:${action}`;
  return (
    <div className="relative h-full min-h-0 flex flex-col overflow-hidden p-2 space-y-1">
      <div className="min-h-0 flex-1 overflow-y-auto overflow-x-hidden scrollbar-none space-y-1">
        <StoryboardCanvasEditor scene={scene} onUpdate={(updates) => onUpdate?.(updates)} />
      <div>
        <h3 className="text-[11px] font-semibold text-[--fg-muted] uppercase tracking-wider mb-0.5">
          场景标题
        </h3>
        <p className="text-xs font-medium text-[--fg-default] truncate">{scene.title}</p>
        {(scene.board_mode || scene.hand_usage || scene.video_style || scene.visual_style || scene.pen_style) && (
          <p className="mt-0.5 text-[10px] text-[--fg-muted] font-mono truncate">
            {[
              scene.board_mode,
              scene.hand_usage,
              scene.video_style,
              scene.visual_style,
              scene.pen_style,
            ]
              .filter(Boolean)
              .join(" · ")}
          </p>
        )}
      </div>

      <div>
        <h3 className="text-[11px] font-semibold text-[--fg-muted] uppercase tracking-wider mb-0.5">
          旁白文案
        </h3>
        <textarea
          value={scene.narration}
          rows={2}
          onChange={(e) => onUpdate?.({ narration: e.target.value })}
          className="w-full h-14 rounded-md bg-[--bg-base] border border-[--border-default] text-xs p-2 resize-none focus:outline-none focus:border-purple-500 transition-colors leading-snug"
        />
      </div>

      <div>
        <h3 className="text-[11px] font-semibold text-[--fg-muted] uppercase tracking-wider mb-0.5">
          动画指令
        </h3>
        <div className="space-y-1">
          {scene.animations.map((anim, i) => (
            <div
              key={i}
              className="px-2 py-1 rounded-md bg-[--bg-base] border border-[--border-default] flex items-center gap-2 min-h-8"
            >
              <div className="flex items-center gap-2">
                <AnimationTag anim={anim} />
              </div>
              <p className="text-[11px] text-[--fg-default] font-mono truncate">{anim.content}</p>
            </div>
          ))}
        </div>
      </div>

      {scene.image_url && (
        <div>
          <h3 className="text-xs font-semibold text-[--fg-muted] uppercase tracking-wider mb-2">
            图片预览
          </h3>
          <img
            src={scene.image_url}
            alt=""
            className="w-full aspect-video object-contain rounded-lg bg-[--bg-base] border border-[--border-default]"
          />
        </div>
      )}

      {scene.audioUrl && (
        <div>
          <h3 className="text-xs font-semibold text-[--fg-muted] uppercase tracking-wider mb-2">
            配音预听
          </h3>
          <audio src={scene.audioUrl} controls className="w-full h-9" />
        </div>
      )}
      </div>

      <div className="z-20 flex flex-shrink-0 gap-1 border-t border-[--border-subtle] bg-[--bg-elevated] px-2 py-1.5">
        <button
          onClick={() => onRegenerateImage?.(scene)}
          disabled={Boolean(busyAction)}
          title="调用图像生成，替换本场参考图"
          className="flex-1 h-8 rounded-md border border-purple-500/50 hover:border-purple-500 disabled:opacity-50 text-xs text-purple-300 transition-colors truncate"
        >
          {isBusy("image") ? "生成图片中..." : "重新生成本场图片"}
        </button>
        <button
          onClick={() => onRegenerateAudio?.(scene)}
          disabled={Boolean(busyAction)}
          title="合成本场旁白，供预听和微调文案"
          className="flex-1 h-8 rounded-md border border-[--border-default] hover:border-[--border-subtle] disabled:opacity-50 text-xs text-[--fg-muted] hover:text-[--fg-default] transition-colors truncate"
        >
          {isBusy("audio") ? "配音生成中..." : "重新配音本场"}
        </button>
        <button
          onClick={() => onRepairCallouts?.(scene)}
          disabled={Boolean(busyAction)}
          title="收紧标签数量并改用短标注策略"
          className="flex-1 h-8 rounded-md border border-[--border-default] hover:border-[--border-subtle] disabled:opacity-50 text-xs text-[--fg-muted] hover:text-[--fg-default] transition-colors truncate"
        >
          修复标注位置
        </button>
      </div>
    </div>
  );
}

function VideoPreview({ url, scene }: { url: string; scene: Scene }) {
  return (
    <div className="w-full max-w-2xl px-8 space-y-4">
      <VideoPlayer
        key={url}
        src={url}
        className="w-full aspect-video rounded-xl bg-black border border-[--border-default] shadow-lg shadow-purple-500/10"
      />
      <div className="flex flex-wrap gap-2">
        {scene.animations.map((anim, i) => (
          <AnimationTag key={i} anim={anim} />
        ))}
      </div>
    </div>
  );
}

function ScenePlaceholder({ scene }: { scene: Scene }) {
  return (
    <div className="w-full max-w-2xl px-8 space-y-6">
      <div className="aspect-video rounded-xl bg-[--bg-elevated] border border-[--border-default] flex flex-col items-center justify-center gap-4 relative overflow-hidden">
        <div className="absolute inset-0 bg-gradient-to-br from-purple-500/5 to-cyan-500/5" />
        <div className="text-5xl opacity-20">▶</div>
        <div className="text-center space-y-1 z-10">
          <p className="text-sm font-medium text-[--fg-default]">
            场景 {scene.order + 1}：{scene.title}
          </p>
          <p className="text-xs text-[--fg-muted] font-mono">
            {scene.duration_estimate}s · {scene.animations.length} 个动画
          </p>
        </div>
      </div>

      <div className="space-y-2">
        <p className="text-xs font-semibold text-[--fg-muted] uppercase tracking-wider">旁白预览</p>
        <p className="text-sm text-[--fg-default] leading-relaxed bg-[--bg-elevated] rounded-lg p-4 border border-[--border-default]">
          {scene.narration}
        </p>
      </div>

      <div className="flex flex-wrap gap-2">
        {scene.animations.map((anim, i) => (
          <AnimationTag key={i} anim={anim} />
        ))}
      </div>
    </div>
  );
}

export function StoryboardView({
  storyboard,
  videoUrl,
  onSceneUpdate,
  onRegenerateSceneImage,
  onRegenerateSceneAudio,
  onRepairSceneCallouts,
  busySceneAction,
}: Props) {
  const [selectedId, setSelectedId] = useState<string>(storyboard.scenes[0]?.id ?? "");

  useEffect(() => {
    if (!storyboard.scenes.some((scene) => scene.id === selectedId)) {
      setSelectedId(storyboard.scenes[0]?.id ?? "");
    }
  }, [storyboard.scenes, selectedId]);

  const selectedScene = storyboard.scenes.find((s) => s.id === selectedId) ?? storyboard.scenes[0];

  return (
    <div className="flex h-full overflow-hidden">
      {/* Scene list */}
      <div className="w-72 flex-shrink-0 bg-[--bg-surface] border-r border-[--border-subtle] flex flex-col overflow-hidden">
        <div className="px-4 py-3 border-b border-[--border-subtle]">
          <p className="text-xs font-semibold text-[--fg-muted] uppercase tracking-wider">
            分镜列表 · {storyboard.scenes.length} 场
          </p>
        </div>
        <div className="flex-1 overflow-y-auto p-3 space-y-2">
          {storyboard.scenes.map((scene) => (
            <SceneCard
              key={scene.id}
              scene={scene}
              selected={scene.id === selectedId}
              onClick={() => setSelectedId(scene.id)}
            />
          ))}
        </div>
      </div>

      {/* Preview area */}
      <div className="flex-1 flex items-center justify-center bg-[--bg-base] overflow-hidden">
        {selectedScene ? (
          videoUrl ? (
            <VideoPreview url={videoUrl} scene={selectedScene} />
          ) : (
            <ScenePlaceholder scene={selectedScene} />
          )
        ) : (
          <p className="text-[--fg-muted] text-sm">请选择一个场景</p>
        )}
      </div>

      {/* Edit panel */}
      <div className="w-[820px] max-w-[58vw] min-h-0 flex-shrink-0 bg-[--bg-elevated] border-l border-[--border-subtle] flex flex-col overflow-hidden">
        <div className="flex-shrink-0 px-4 py-2 border-b border-[--border-subtle]">
          <p className="text-xs font-semibold text-[--fg-muted] uppercase tracking-wider">场景编辑</p>
        </div>
        {selectedScene && (
          <div className="flex-1 min-h-0 overflow-hidden">
          <SceneEditor
            scene={selectedScene}
            onUpdate={(updates) => onSceneUpdate?.(selectedScene.id, updates)}
            onRegenerateImage={onRegenerateSceneImage}
            onRegenerateAudio={onRegenerateSceneAudio}
            onRepairCallouts={onRepairSceneCallouts}
            busyAction={busySceneAction}
          />
          </div>
        )}
      </div>
    </div>
  );
}
