import type { Storyboard } from "./types";

export type RenderPhase = "queued" | "tts" | "imagegen" | "codegen" | "bundling" | "rendering" | "done" | null;

const clamp = (value: number, min: number, max: number) => Math.max(min, Math.min(max, value));

export function formatDuration(seconds: number): string {
  const safe = Math.max(0, Math.round(seconds));
  if (safe < 60) return `${safe}s`;
  const minutes = Math.floor(safe / 60);
  const rest = safe % 60;
  return rest > 0 ? `${minutes}m ${rest}s` : `${minutes}m`;
}

export function elapsedSeconds(startedAt?: string | number | null, now = Date.now()): number {
  if (!startedAt) return 0;
  const start = typeof startedAt === "number" ? startedAt : new Date(startedAt).getTime();
  if (!Number.isFinite(start)) return 0;
  return Math.max(0, (now - start) / 1000);
}

function phaseWeights(storyboard?: Storyboard | null): Record<Exclude<RenderPhase, null>, number> {
  const sceneCount = storyboard?.scenes.length ?? 4;
  const duration = storyboard?.total_duration_estimate ?? 90;
  return {
    queued: 2,
    tts: clamp(sceneCount * 2.8, 5, 18),
    imagegen: clamp(sceneCount * 4, 6, 28),
    codegen: 2,
    bundling: 7,
    rendering: clamp(duration * 0.18, 14, 42),
    done: 0,
  };
}

export function estimateRemainingSeconds({
  phase,
  progress,
  elapsed,
  storyboard,
}: {
  phase: RenderPhase;
  progress: number;
  elapsed: number;
  storyboard?: Storyboard | null;
}): number | null {
  if (phase === "done") return 0;
  const weights = phaseWeights(storyboard);
  const order: Exclude<RenderPhase, null>[] = ["queued", "tts", "imagegen", "codegen", "bundling", "rendering", "done"];
  const active = phase ?? "queued";
  const activeIndex = Math.max(0, order.indexOf(active));
  const total = order.reduce((sum, item) => sum + weights[item], 0);
  const completedBefore = order.slice(0, activeIndex).reduce((sum, item) => sum + weights[item], 0);
  const phaseProgress =
    active === "bundling" || active === "rendering"
      ? clamp(Number(progress) || 0, 0, 99) / 100
      : 0;
  const estimatedDone = completedBefore + weights[active] * phaseProgress;
  const estimatedOverall = clamp(estimatedDone / Math.max(1, total), 0.03, 0.98);

  if (elapsed < 3 && estimatedDone <= weights.queued) return null;

  const byRate = elapsed > 2 ? (elapsed * (1 - estimatedOverall)) / estimatedOverall : total * (1 - estimatedOverall);
  const byPlan = total * (1 - estimatedOverall);
  return clamp(byRate * 0.65 + byPlan * 0.35, 3, 600);
}

export function etaLabel(remaining: number | null): string {
  return remaining == null ? "预计剩余：正在估算" : `预计剩余：${formatDuration(remaining)}`;
}
