import type { ExplainGraph, Storyboard } from "./types";

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API ${path} failed (${res.status}): ${text}`);
  }
  return res.json() as Promise<T>;
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
