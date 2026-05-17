"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import Link from "next/link";
import { listJobs, deleteJob, updateJobTopic } from "@/lib/api";
import { RENDER_URL } from "@/lib/constants";
import { elapsedSeconds, estimateRemainingSeconds, etaLabel } from "@/lib/renderEstimate";
import type { RenderJobSummary } from "@/lib/types";

function StatusBadge({ job, now }: { job: RenderJobSummary; now: number }) {
  const { status, progress } = job;
  if (status === "done") {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs bg-green-500/15 text-green-400 font-mono">
        ✓ 已完成
      </span>
    );
  }
  if (status === "failed") {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs bg-red-500/15 text-red-400 font-mono">
        ✗ 失败
      </span>
    );
  }
  const remaining = estimateRemainingSeconds({
    phase: job.phase ?? "queued",
    progress,
    elapsed: elapsedSeconds(job.createdAt, now),
  });
  return (
    <span className="inline-flex flex-col gap-0.5 px-2 py-1 rounded-md text-xs bg-purple-500/15 text-purple-400 font-mono">
      <span className="inline-flex items-center gap-1.5">
        <span className="w-2 h-2 border border-purple-400 border-t-transparent rounded-full animate-spin inline-block" />
        渲染中 {progress}%
      </span>
      <span className="text-[10px] text-[--fg-muted]">{etaLabel(remaining)}</span>
    </span>
  );
}

function TopicCell({
  job,
  onSaved,
}: {
  job: RenderJobSummary;
  onSaved: (id: string, topic: string) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(job.topic ?? "");
  const [saving, setSaving] = useState(false);

  const save = async () => {
    if (value.trim() === (job.topic ?? "")) { setEditing(false); return; }
    setSaving(true);
    try {
      await updateJobTopic(job.id, value.trim());
      onSaved(job.id, value.trim());
      setEditing(false);
    } catch {
      setValue(job.topic ?? "");
      setEditing(false);
    } finally {
      setSaving(false);
    }
  };

  if (editing) {
    return (
      <input
        autoFocus
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onBlur={save}
        onKeyDown={(e) => { if (e.key === "Enter") save(); if (e.key === "Escape") { setValue(job.topic ?? ""); setEditing(false); } }}
        disabled={saving}
        className="bg-[--bg-base] border border-purple-500 rounded px-2 py-0.5 text-sm text-[--fg-default] focus:outline-none w-48"
      />
    );
  }

  return (
    <button
      onClick={() => setEditing(true)}
      className="group flex items-center gap-1.5 text-sm text-[--fg-default] hover:text-purple-400 transition-colors text-left"
      title="点击编辑标题"
    >
      <span className="truncate max-w-48">{job.topic || <span className="text-[--fg-muted]">未命名</span>}</span>
      <span className="opacity-0 group-hover:opacity-60 text-xs text-[--fg-muted]">✎</span>
    </button>
  );
}

function DeleteButton({ jobId, onDeleted }: { jobId: string; onDeleted: (id: string) => void }) {
  const [confirm, setConfirm] = useState(false);
  const [loading, setLoading] = useState(false);

  if (confirm) {
    return (
      <div className="flex items-center gap-1">
        <button
          onClick={async () => {
            setLoading(true);
            try { await deleteJob(jobId); onDeleted(jobId); } catch { setConfirm(false); }
            setLoading(false);
          }}
          disabled={loading}
          className="px-2 py-0.5 rounded text-xs bg-red-500/20 hover:bg-red-500/30 text-red-400 border border-red-500/40 transition-colors"
        >
          {loading ? "..." : "确认删除"}
        </button>
        <button
          onClick={() => setConfirm(false)}
          className="px-2 py-0.5 rounded text-xs text-[--fg-muted] hover:text-[--fg-default] transition-colors"
        >
          取消
        </button>
      </div>
    );
  }

  return (
    <button
      onClick={() => setConfirm(true)}
      className="px-2 py-0.5 rounded text-xs text-[--fg-muted] hover:text-red-400 border border-transparent hover:border-red-500/40 transition-colors"
    >
      删除
    </button>
  );
}

export default function JobsPage() {
  const [jobs, setJobs] = useState<RenderJobSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<"all" | "done" | "processing" | "failed">("all");
  const [previewId, setPreviewId] = useState<string | null>(null);
  const [now, setNow] = useState(Date.now());
  const hasProcessingRef = useRef(false);

  const fetchJobs = useCallback(async () => {
    try {
      const data = await listJobs();
      hasProcessingRef.current = data.some((j) => j.status === "processing");
      setJobs(data);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchJobs();
    const id = setInterval(() => {
      if (hasProcessingRef.current) fetchJobs();
    }, 5000);
    return () => clearInterval(id);
  }, [fetchJobs]);

  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);

  const handleDeleted = (id: string) => setJobs((prev) => prev.filter((j) => j.id !== id));
  const handleTopicSaved = (id: string, topic: string) =>
    setJobs((prev) => prev.map((j) => (j.id === id ? { ...j, topic } : j)));

  const filtered = jobs.filter((j) => {
    if (filter !== "all" && j.status !== filter) return false;
    if (search && !(j.topic ?? "").toLowerCase().includes(search.toLowerCase()) && !j.id.includes(search)) return false;
    return true;
  });

  const previewJob = previewId ? jobs.find((j) => j.id === previewId) : null;

  return (
    <div className="flex flex-col h-screen bg-[--bg-base] text-[--fg-default] overflow-hidden">
      <header className="flex items-center justify-between px-6 h-14 bg-[--bg-surface] border-b border-[--border-subtle] flex-shrink-0">
        <div className="flex items-center gap-4">
          <Link
            href="/"
            className="text-sm text-[--fg-muted] hover:text-[--fg-default] transition-colors"
          >
            ← 首页
          </Link>
          <div className="w-px h-5 bg-[--border-default]" />
          <div className="flex items-center gap-2">
            <div className="w-5 h-5 rounded bg-gradient-to-br from-purple-500 to-pink-500" />
            <span className="text-sm font-medium">视频库</span>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-xs font-mono text-[--fg-muted]">
            {jobs.length} 个视频
          </span>
          <Link
            href="/studio"
            className="h-8 px-4 rounded-md bg-purple-500 hover:bg-purple-400 text-white text-xs font-medium inline-flex items-center transition-colors"
          >
            + 新建
          </Link>
        </div>
      </header>

      <div className="flex flex-1 overflow-hidden">
        <div className="flex flex-col flex-1 overflow-hidden">
          <div className="flex items-center gap-3 px-6 py-3 border-b border-[--border-subtle] bg-[--bg-surface] flex-shrink-0">
            <input
              type="text"
              placeholder="搜索标题或 ID..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="h-8 px-3 rounded-md bg-[--bg-elevated] border border-[--border-default] text-sm text-[--fg-default] placeholder:text-[--fg-muted] focus:outline-none focus:border-purple-500 transition-colors w-56"
            />
            <div className="flex items-center gap-1">
              {(["all", "done", "processing", "failed"] as const).map((f) => (
                <button
                  key={f}
                  onClick={() => setFilter(f)}
                  className={`h-7 px-3 rounded text-xs font-mono transition-colors ${
                    filter === f
                      ? "bg-purple-500/20 text-purple-400 border border-purple-500/40"
                      : "text-[--fg-muted] hover:text-[--fg-default] border border-transparent"
                  }`}
                >
                  {{ all: "全部", done: "已完成", processing: "渲染中", failed: "失败" }[f]}
                </button>
              ))}
            </div>
            <button
              onClick={fetchJobs}
              className="ml-auto h-7 px-3 rounded text-xs text-[--fg-muted] hover:text-[--fg-default] border border-[--border-default] hover:border-[--border-subtle] transition-colors"
            >
              ↻ 刷新
            </button>
          </div>

          <div className="flex-1 overflow-y-auto">
            {loading && (
              <div className="flex items-center justify-center h-40 text-[--fg-muted] text-sm">
                加载中...
              </div>
            )}
            {error && (
              <div className="flex items-center justify-center h-40 text-red-400 text-sm gap-2">
                <span>⚠</span> {error}
              </div>
            )}
            {!loading && !error && filtered.length === 0 && (
              <div className="flex flex-col items-center justify-center h-40 text-[--fg-muted] text-sm gap-2">
                <span className="text-3xl opacity-20">🎬</span>
                <span>{search || filter !== "all" ? "没有匹配的视频" : "还没有生成过视频"}</span>
              </div>
            )}
            {!loading && !error && filtered.length > 0 && (
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-[--border-subtle] text-xs text-[--fg-muted] uppercase tracking-wider">
                    <th className="text-left px-6 py-2 font-medium">标题</th>
                    <th className="text-left px-4 py-2 font-medium">状态</th>
                    <th className="text-left px-4 py-2 font-medium">创建时间</th>
                    <th className="text-left px-4 py-2 font-medium">ID</th>
                    <th className="px-4 py-2" />
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((job) => (
                    <tr
                      key={job.id}
                      className={`border-b border-[--border-subtle] hover:bg-[--bg-elevated] transition-colors ${
                        previewId === job.id ? "bg-purple-500/5" : ""
                      }`}
                    >
                      <td className="px-6 py-3">
                        <TopicCell job={job} onSaved={handleTopicSaved} />
                      </td>
                      <td className="px-4 py-3">
                        <StatusBadge job={job} now={now} />
                        {job.error && (
                          <p className="text-xs text-red-400 mt-0.5 max-w-48 truncate" title={job.error}>
                            {job.error}
                          </p>
                        )}
                      </td>
                      <td className="px-4 py-3 text-xs text-[--fg-muted] font-mono whitespace-nowrap">
                        {job.createdAt
                          ? new Date(job.createdAt).toLocaleString("zh-CN", { hour12: false })
                          : "—"}
                      </td>
                      <td className="px-4 py-3 text-xs text-[--fg-muted] font-mono">
                        {job.id.slice(0, 8)}
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2 justify-end">
                          {job.status === "done" && (
                            <>
                              <button
                                onClick={() => setPreviewId(previewId === job.id ? null : job.id)}
                                className={`px-2 py-0.5 rounded text-xs border transition-colors ${
                                  previewId === job.id
                                    ? "bg-purple-500/20 text-purple-400 border-purple-500/40"
                                    : "text-[--fg-muted] hover:text-[--fg-default] border-transparent hover:border-[--border-default]"
                                }`}
                              >
                                {previewId === job.id ? "收起" : "预览"}
                              </button>
                              <a
                                href={`${RENDER_URL}/download/${job.id}`}
                                download
                                className="px-2 py-0.5 rounded text-xs text-[--fg-muted] hover:text-purple-400 border border-transparent hover:border-purple-500/40 transition-colors"
                              >
                                下载
                              </a>
                            </>
                          )}
                          <DeleteButton jobId={job.id} onDeleted={handleDeleted} />
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>

        {previewJob && previewJob.status === "done" && (
          <div className="w-96 flex-shrink-0 bg-[--bg-elevated] border-l border-[--border-subtle] flex flex-col overflow-hidden">
            <div className="flex items-center justify-between px-4 py-3 border-b border-[--border-subtle]">
              <p className="text-xs font-semibold text-[--fg-muted] uppercase tracking-wider">预览</p>
              <button
                onClick={() => setPreviewId(null)}
                className="text-[--fg-muted] hover:text-[--fg-default] transition-colors text-lg leading-none"
              >
                ×
              </button>
            </div>
            <div className="flex-1 overflow-y-auto p-4 space-y-4">
              <video
                key={previewJob.id}
                src={`${RENDER_URL}/download/${previewJob.id}`}
                controls
                autoPlay
                className="w-full aspect-video rounded-lg bg-black border border-[--border-default]"
              />
              <div className="space-y-2 text-xs font-mono text-[--fg-muted]">
                <div className="flex justify-between">
                  <span>标题</span>
                  <span className="text-[--fg-default]">{previewJob.topic ?? "未命名"}</span>
                </div>
                <div className="flex justify-between">
                  <span>状态</span>
                  <span className="text-green-400">已完成</span>
                </div>
                <div className="flex justify-between">
                  <span>创建时间</span>
                  <span>
                    {previewJob.createdAt
                      ? new Date(previewJob.createdAt).toLocaleString("zh-CN", { hour12: false })
                      : "—"}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span>Job ID</span>
                  <span>{previewJob.id.slice(0, 12)}...</span>
                </div>
              </div>
              <a
                href={`${RENDER_URL}/download/${previewJob.id}`}
                download
                className="flex items-center justify-center gap-2 h-9 rounded-lg bg-purple-500/20 hover:bg-purple-500/30 border border-purple-500/50 text-purple-300 text-sm font-medium transition-colors"
              >
                ↓ 下载 MP4
              </a>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
