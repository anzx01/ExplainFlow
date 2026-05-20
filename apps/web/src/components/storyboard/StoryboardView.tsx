"use client";

import { useEffect, useState } from "react";
import type { Scene, Storyboard, AnimationInstruction } from "@/lib/types";
import { penStyleLabel, videoStyleLabel } from "@/lib/constants";

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
            {scene.video_style || scene.videoStyle
              ? ` · ${videoStyleLabel(scene.video_style ?? scene.videoStyle)}`
              : ""}
            {scene.pen_style || scene.penStyle
              ? ` · ${penStyleLabel(scene.pen_style ?? scene.penStyle)}`
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
    <div className="h-full flex flex-col overflow-y-auto p-5 space-y-5">
      <div>
        <h3 className="text-xs font-semibold text-[--fg-muted] uppercase tracking-wider mb-2">
          场景标题
        </h3>
        <p className="text-sm font-medium text-[--fg-default]">{scene.title}</p>
        {(scene.board_mode || scene.hand_usage || scene.video_style || scene.videoStyle || scene.visual_style || scene.pen_style || scene.penStyle) && (
          <p className="mt-2 text-xs text-[--fg-muted] font-mono">
            {[
              scene.board_mode,
              scene.hand_usage,
              scene.video_style ?? scene.videoStyle,
              scene.visual_style,
              scene.pen_style ?? scene.penStyle,
            ]
              .filter(Boolean)
              .join(" · ")}
          </p>
        )}
      </div>

      <div>
        <h3 className="text-xs font-semibold text-[--fg-muted] uppercase tracking-wider mb-2">
          旁白文案
        </h3>
        <textarea
          value={scene.narration}
          rows={6}
          onChange={(e) => onUpdate?.({ narration: e.target.value })}
          className="w-full rounded-lg bg-[--bg-base] border border-[--border-default] text-[--fg-default] text-sm p-3 resize-none focus:outline-none focus:border-purple-500 transition-colors leading-relaxed"
        />
      </div>

      <div>
        <h3 className="text-xs font-semibold text-[--fg-muted] uppercase tracking-wider mb-2">
          动画指令
        </h3>
        <div className="space-y-2">
          {scene.animations.map((anim, i) => (
            <div
              key={i}
              className="p-3 rounded-lg bg-[--bg-base] border border-[--border-default] space-y-1"
            >
              <div className="flex items-center gap-2">
                <AnimationTag anim={anim} />
              </div>
              <p className="text-xs text-[--fg-default] font-mono">{anim.content}</p>
              {anim.latex && (
                <p className="text-xs text-cyan-400 font-mono">{anim.latex}</p>
              )}
            </div>
          ))}
        </div>
      </div>

      {(scene.image_url || scene.imageUrl) && (
        <div>
          <h3 className="text-xs font-semibold text-[--fg-muted] uppercase tracking-wider mb-2">
            图片预览
          </h3>
          <img
            src={scene.image_url ?? scene.imageUrl ?? ""}
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

      <div className="space-y-2">
        <button
          onClick={() => onRegenerateImage?.(scene)}
          disabled={Boolean(busyAction)}
          title="调用图像生成，替换本场参考图"
          className="w-full h-9 rounded-md border border-purple-500/50 hover:border-purple-500 disabled:opacity-50 text-sm text-purple-300 transition-colors"
        >
          {isBusy("image") ? "生成图片中..." : "重新生成本场图片"}
        </button>
        <button
          onClick={() => onRegenerateAudio?.(scene)}
          disabled={Boolean(busyAction)}
          title="合成本场旁白，供预听和微调文案"
          className="w-full h-9 rounded-md border border-[--border-default] hover:border-[--border-subtle] disabled:opacity-50 text-sm text-[--fg-muted] hover:text-[--fg-default] transition-colors"
        >
          {isBusy("audio") ? "配音生成中..." : "重新配音本场"}
        </button>
        <button
          onClick={() => onRepairCallouts?.(scene)}
          disabled={Boolean(busyAction)}
          title="收紧标签数量并改用短标注策略"
          className="w-full h-9 rounded-md border border-[--border-default] hover:border-[--border-subtle] disabled:opacity-50 text-sm text-[--fg-muted] hover:text-[--fg-default] transition-colors"
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
      <video
        key={url}
        src={url}
        controls
        autoPlay
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
      <div className="w-80 flex-shrink-0 bg-[--bg-elevated] border-l border-[--border-subtle] overflow-hidden">
        <div className="px-4 py-3 border-b border-[--border-subtle]">
          <p className="text-xs font-semibold text-[--fg-muted] uppercase tracking-wider">场景编辑</p>
        </div>
        {selectedScene && (
          <SceneEditor
            scene={selectedScene}
            onUpdate={(updates) => onSceneUpdate?.(selectedScene.id, updates)}
            onRegenerateImage={onRegenerateSceneImage}
            onRegenerateAudio={onRegenerateSceneAudio}
            onRepairCallouts={onRepairSceneCallouts}
            busyAction={busySceneAction}
          />
        )}
      </div>
    </div>
  );
}
