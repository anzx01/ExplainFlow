import type { ExplainGraph, Storyboard, Scene, RenderJobSummary, PenStyleId, VideoStyleId } from "./types";

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API ${path} failed (${res.status}): ${text}`);
  }
  return res.json() as Promise<T>;
}

function post<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, { method: "POST", body: JSON.stringify(body) });
}

export async function generateGraph(
  prompt: string,
  markdown?: string
): Promise<ExplainGraph> {
  const data = await post<{ graph: ExplainGraph }>("/explain/graph", {
    prompt,
    markdown: markdown || null,
  });
  return data.graph;
}

export async function generateStoryboard(
  graph: ExplainGraph,
  targetDuration = 120,
  videoStyle: VideoStyleId = "whiteboard",
  penStyle: PenStyleId = "marker"
): Promise<Storyboard> {
  const data = await post<{ storyboard: Storyboard }>("/planner/storyboard", {
    graph,
    target_duration: targetDuration,
    video_style: videoStyle,
    pen_style: penStyle,
  });
  return data.storyboard;
}

export async function listJobs(): Promise<RenderJobSummary[]> {
  return request<RenderJobSummary[]>("/render/jobs");
}

export async function deleteJob(jobId: string): Promise<void> {
  await request<{ ok: boolean }>(`/render/job/${jobId}`, { method: "DELETE" });
}

export async function deleteJobs(jobIds: string[]): Promise<{ deleted: string[]; missing: string[] }> {
  return request<{ ok: boolean; deleted: string[]; missing: string[] }>("/render/jobs/delete", {
    method: "POST",
    body: JSON.stringify({ job_ids: jobIds }),
  });
}

export async function updateJobTopic(jobId: string, topic: string): Promise<void> {
  await request<{ ok: boolean }>(`/render/job/${jobId}`, {
    method: "PATCH",
    body: JSON.stringify({ topic }),
  });
}

export async function generateSceneImage(storyboard: Storyboard, scene: Scene): Promise<string> {
  const sceneId = scene.id;
  const data = await post<{ images: Record<string, string | null> }>("/imagegen/scenes", {
    scenes: [
      {
        scene_id: sceneId,
        topic: storyboard.topic,
        title: scene.title,
        image_description: scene.image_description || scene.learning_goal || scene.title,
        board_mode: scene.board_mode || "clean_canvas",
        hand_usage: scene.hand_usage || "annotate",
        video_style: scene.video_style || storyboard.video_style || "whiteboard",
        visual_style: scene.visual_style || "teacher_whiteboard",
        pen_style: scene.pen_style || storyboard.pen_style || "marker",
      },
    ],
  });
  const image = data.images?.[sceneId];
  if (!image) throw new Error("Scene image generation returned empty result");
  return image.startsWith("data:image/") ? image : `data:image/png;base64,${image}`;
}

export async function synthesizeSceneAudio(text: string, voice = "xiaoxiao"): Promise<string> {
  const res = await fetch(`${BASE_URL}/narration/synthesize`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, voice }),
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`API /narration/synthesize failed (${res.status}): ${body}`);
  }
  const blob = await res.blob();
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(reader.error ?? new Error("Failed to read synthesized audio"));
    reader.readAsDataURL(blob);
  });
}
