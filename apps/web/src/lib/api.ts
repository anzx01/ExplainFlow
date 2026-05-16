import type { ExplainGraph, Storyboard, RenderJobSummary } from "./types";

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
  targetDuration = 120
): Promise<Storyboard> {
  const data = await post<{ storyboard: Storyboard }>("/planner/storyboard", {
    graph,
    target_duration: targetDuration,
  });
  return data.storyboard;
}

export async function listJobs(): Promise<RenderJobSummary[]> {
  return request<RenderJobSummary[]>("/render/jobs");
}

export async function deleteJob(jobId: string): Promise<void> {
  await request<{ ok: boolean }>(`/render/job/${jobId}`, { method: "DELETE" });
}

export async function updateJobTopic(jobId: string, topic: string): Promise<void> {
  await request<{ ok: boolean }>(`/render/job/${jobId}`, {
    method: "PATCH",
    body: JSON.stringify({ topic }),
  });
}
