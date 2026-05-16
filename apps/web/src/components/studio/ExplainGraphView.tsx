"use client";

import type { ExplainGraph, ConceptNode } from "@/lib/types";

const NODE_COLORS: Record<string, string> = {
  concept: "#a855f7",
  formula: "#7c3aed",
  example: "#22c55e",
  conclusion: "#f59e0b",
  process: "#71717a",
};

const GRID_POSITIONS = [
  { x: 80, y: 80 },
  { x: 340, y: 60 },
  { x: 580, y: 140 },
  { x: 200, y: 240 },
  { x: 440, y: 260 },
  { x: 720, y: 80 },
  { x: 700, y: 280 },
  { x: 80, y: 370 },
];

interface NodeCardProps {
  node: ConceptNode;
  position: { x: number; y: number };
}

function NodeCard({ node, position }: NodeCardProps) {
  const color = NODE_COLORS[node.node_type] ?? NODE_COLORS.concept;
  return (
    <div
      style={{ left: position.x, top: position.y, borderColor: color, boxShadow: `0 4px 20px ${color}25` }}
      className="absolute w-44 rounded-xl border bg-[--bg-elevated] p-3"
    >
      <div className="flex items-center gap-2 mb-1.5">
        <span
          className="inline-block w-2 h-2 rounded-full flex-shrink-0"
          style={{ background: color }}
        />
        <span className="text-xs font-mono" style={{ color }}>
          {node.node_type}
        </span>
      </div>
      <p className="text-sm font-semibold text-[--fg-default] leading-tight mb-1">{node.label}</p>
      <p className="text-xs text-[--fg-muted] leading-relaxed">{node.description}</p>
      {node.latex && (
        <code className="mt-1.5 block text-xs font-mono text-purple-400 bg-purple-950/30 rounded px-2 py-1">
          {node.latex}
        </code>
      )}
    </div>
  );
}

interface Props {
  graph: ExplainGraph | null;
  loading?: boolean;
}

export function ExplainGraphView({ graph, loading }: Props) {
  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <div className="text-center space-y-4">
          <div className="inline-block w-10 h-10 border-2 border-purple-500 border-t-transparent rounded-full animate-spin" />
          <p className="text-sm text-[--fg-muted]">AI 正在分析概念，生成 Explain 图谱...</p>
        </div>
      </div>
    );
  }

  if (!graph) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <div className="text-center space-y-3 max-w-sm">
          <div className="text-4xl opacity-20">⬡</div>
          <p className="text-sm text-[--fg-muted]">
            在左侧输入 AI/ML 概念 Prompt，点击「生成 Explain 图谱」后，这里会显示 AI 对概念的理解结构。
          </p>
        </div>
      </div>
    );
  }

  const sortedNodes = [...graph.nodes].sort((a, b) => a.teach_order - b.teach_order);

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      {/* Summary bar */}
      <div className="px-4 py-3 border-b border-[--border-subtle] bg-[--bg-surface]">
        <p className="text-sm text-[--fg-muted]">
          <span className="text-purple-400 font-medium">{graph.topic}</span>
          {" — "}{graph.summary}
        </p>
      </div>

      {/* Graph canvas */}
      <div className="flex-1 relative overflow-hidden">
        {/* Dot grid */}
        <svg className="absolute inset-0 w-full h-full opacity-10" aria-hidden>
          <defs>
            <pattern id="dots" x="0" y="0" width="32" height="32" patternUnits="userSpaceOnUse">
              <circle cx="1" cy="1" r="1" fill="#71717a" />
            </pattern>
          </defs>
          <rect width="100%" height="100%" fill="url(#dots)" />
        </svg>

        {sortedNodes.map((node, i) => (
          <NodeCard
            key={node.id}
            node={node}
            position={GRID_POSITIONS[i % GRID_POSITIONS.length]}
          />
        ))}
      </div>

      {/* Key insights */}
      {graph.key_insights.length > 0 && (
        <div className="px-4 py-3 border-t border-[--border-subtle] bg-[--bg-surface]">
          <p className="text-xs text-[--fg-muted] mb-1.5 font-medium">核心洞察</p>
          <div className="flex flex-wrap gap-2">
            {graph.key_insights.map((insight, i) => (
              <span
                key={i}
                className="text-xs px-2 py-0.5 rounded-full border border-[--border-default] text-[--fg-muted]"
              >
                {insight}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
