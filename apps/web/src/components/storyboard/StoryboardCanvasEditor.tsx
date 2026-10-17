"use client";
import { VideoPlayer } from "@/components/ui/VideoPlayer";

import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import Konva from "konva";
import { Image as KonvaImage, Layer, Rect, Stage, Text, Transformer } from "react-konva";
import type { RenderElement, Scene } from "@/lib/types";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8010";

interface Props {
  scene: Scene;
  onUpdate: (updates: Partial<Scene>) => void;
}

const colorFor = (index: number) => ["#7c3aed", "#0891b2", "#ea580c", "#16a34a", "#dc2626"][index % 5];

export default function StoryboardCanvasEditor({ scene, onUpdate }: Props) {
  const stageRef = useRef<Konva.Stage>(null);
  const transformerRef = useRef<Konva.Transformer>(null);
  const shapeRefs = useRef<Record<string, Konva.Rect | null>>({});
  const canvasWidth = scene.canvasWidth ?? 1920;
  const canvasHeight = scene.canvasHeight ?? 1080;
  // Keep the complete canvas inside the compact editor instead of clipping
  // the lower half of the interactive Konva stage.
  const displayWidth = 760;
  const scale = displayWidth / canvasWidth;
  const displayHeight = Math.round(canvasHeight * scale);
  const elements = useMemo(() => [...(scene.renderElements ?? [])].sort((a, b) => a.sequence - b.sequence), [scene.renderElements]);
  const [selectedId, setSelectedId] = useState<string | null>(elements[0]?.id ?? null);
  const [image, setImage] = useState<HTMLImageElement | null>(null);
  const [validation, setValidation] = useState<string>("");
  const [enginePreviewUrl, setEnginePreviewUrl] = useState<string | null>(null);
  const [engineBusy, setEngineBusy] = useState(false);

  useEffect(() => {
    if (!scene.image_url) {
      setImage(null);
      return;
    }
    const next = new window.Image();
    next.crossOrigin = "anonymous";
    next.onload = () => setImage(next);
    next.src = scene.image_url;
  }, [scene.image_url]);

  useEffect(() => {
    const node = selectedId ? shapeRefs.current[selectedId] : null;
    transformerRef.current?.nodes(node ? [node] : []);
    transformerRef.current?.getLayer()?.batchDraw();
  }, [selectedId, elements]);

  const commit = (next: RenderElement[]) => onUpdate({ renderElements: next.sort((a, b) => a.sequence - b.sequence) });
  const updateElement = (id: string, patch: Partial<RenderElement>) => {
    commit(elements.map((item) => (item.id === id ? { ...item, ...patch, source: "authored" } : item)));
  };
  const updateReveal = (id: string, patch: Partial<RenderElement["reveal"]>) => {
    commit(elements.map((item) => item.id === id ? { ...item, source: "authored", reveal: { ...item.reveal, ...patch } } : item));
  };
  const addElement = () => {
    const sequence = elements.length + 1;
    const id = `${scene.id}-region-${Date.now()}`;
    const next: RenderElement = {
      id,
      sequence,
      narrativeRole: "content",
      subtitle: "",
      region: { x: 100 + sequence * 30, y: 100 + sequence * 30, width: 480, height: 240 },
      reveal: { startMs: Math.max(0, (sequence - 1) * 1500), durationMs: 1300, protectedRegions: [] },
      source: "authored",
    };
    commit([...elements, next]);
    setSelectedId(id);
  };
  const removeSelected = () => {
    if (!selectedId) return;
    commit(elements.filter((item) => item.id !== selectedId).map((item, index) => ({ ...item, sequence: index + 1 })));
    setSelectedId(null);
  };
  const moveSelected = (delta: number) => {
    if (!selectedId) return;
    const index = elements.findIndex((item) => item.id === selectedId);
    const target = index + delta;
    if (index < 0 || target < 0 || target >= elements.length) return;
    const reordered = [...elements];
    [reordered[index], reordered[target]] = [reordered[target], reordered[index]];
    commit(reordered.map((item, itemIndex) => ({ ...item, sequence: itemIndex + 1, source: "authored" })));
  };
  const addProtectedRegion = () => {
    if (!selectedId) return;
    const element = elements.find((item) => item.id === selectedId);
    if (!element) return;
    const region = {
      x: element.region.x + Math.round(element.region.width * 0.25),
      y: element.region.y + Math.round(element.region.height * 0.25),
      width: Math.max(20, Math.round(element.region.width * 0.5)),
      height: Math.max(20, Math.round(element.region.height * 0.5)),
    };
    updateReveal(selectedId, { protectedRegions: [...(element.reveal.protectedRegions ?? []), region] });
  };
  const validate = async () => {
    setValidation("校验中…");
    const response = await fetch(`${API}/planner/validate-storyboard`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ storyboard: { topic: scene.title, total_duration_estimate: scene.duration_estimate, scenes: [scene] }, fps: 30 }),
    });
    const data = await response.json();
    if (!response.ok) {
      setValidation(data.detail ?? "校验失败");
      return;
    }
    const issues = data.issues ?? [];
    setValidation(issues.length ? issues.map((item: { code: string }) => item.code).join("、") : "契约有效");
  };
  const exportDiagnostic = () => {
    const url = stageRef.current?.toDataURL({ pixelRatio: 2 });
    if (!url) return;
    const link = document.createElement("a");
    link.href = url;
    link.download = `${scene.id}-regions.png`;
    link.click();
  };
  const generateEnginePreview = async () => {
    if (!scene.image_url) return;
    setEngineBusy(true);
    setValidation("使用本地逐笔渲染器生成预览…");
    try {
      const response = await fetch(`${API}/render/engine/preview`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          scene_id: scene.id,
          image_url: scene.image_url,
          duration: Math.min(12, Math.max(2, scene.duration_estimate)),
          fps: 24,
          width: 1280,
          height: 720,
          hand: "asian",
          stroke_detail: "rich",
          color_fill: "contour-wipe",
          color_fill_scope: scene.visual_complexity === "dense" ? "scene" : "block",
        }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail ?? "真实笔迹预览失败");
      setEnginePreviewUrl(`${API}${data.preview_url}`);
      setValidation("本地逐笔预览已生成");
    } catch (error) {
      setValidation(error instanceof Error ? error.message : "真实笔迹预览失败");
    } finally {
      setEngineBusy(false);
    }
  };

  return (
    <div className="space-y-1">
      <div className="flex flex-wrap items-center gap-1">
        <button onClick={addElement} className="px-2.5 py-1.5 rounded border border-[--border-default] text-xs">新增区域</button>
        <button onClick={removeSelected} disabled={!selectedId} className="px-2.5 py-1.5 rounded border border-red-500/40 text-red-300 text-xs disabled:opacity-40">删除区域</button>
        <button onClick={() => moveSelected(-1)} disabled={!selectedId} className="px-2.5 py-1.5 rounded border border-[--border-default] text-xs disabled:opacity-40">前移</button>
        <button onClick={() => moveSelected(1)} disabled={!selectedId} className="px-2.5 py-1.5 rounded border border-[--border-default] text-xs disabled:opacity-40">后移</button>
        <button onClick={addProtectedRegion} disabled={!selectedId} className="px-2.5 py-1.5 rounded border border-red-500/40 text-red-300 text-xs disabled:opacity-40">添加保护区</button>
        <button onClick={validate} className="px-2.5 py-1.5 rounded border border-purple-500/50 text-purple-300 text-xs">校验时间与遮罩</button>
        <button onClick={generateEnginePreview} disabled={!scene.image_url || engineBusy} className="px-2.5 py-1.5 rounded border border-cyan-500/50 text-cyan-300 text-xs disabled:opacity-40">{engineBusy ? "生成中…" : "本地逐笔预览"}</button>
        <button onClick={exportDiagnostic} className="px-2.5 py-1.5 rounded border border-[--border-default] text-xs">导出诊断图</button>
        {validation && <span className="text-xs text-[--fg-muted]">{validation}</span>}
      </div>
      {enginePreviewUrl && <VideoPlayer src={enginePreviewUrl} className="w-full max-w-[760px] rounded-lg border border-cyan-500/30 bg-black" />}
      <div className="h-[27rem] flex items-center justify-center overflow-hidden rounded-lg border border-[--border-default] bg-[#f5ebd7]">
        <Stage ref={stageRef} width={displayWidth} height={displayHeight} scaleX={scale} scaleY={scale} onMouseDown={(event) => { if (event.target === event.target.getStage()) setSelectedId(null); }}>
          <Layer>
            {image && <KonvaImage image={image} x={0} y={0} width={canvasWidth} height={canvasHeight} opacity={0.45} />}
            {elements.map((element, index) => {
              const color = colorFor(index);
              return (
                <Fragment key={element.id}>
                  <Rect
                    ref={(node) => { shapeRefs.current[element.id] = node; }}
                    {...element.region}
                    fill={`${color}24`}
                    stroke={color}
                    strokeWidth={selectedId === element.id ? 6 : 3}
                    draggable
                    onClick={() => setSelectedId(element.id)}
                    onTap={() => setSelectedId(element.id)}
                    onDragEnd={(event) => updateElement(element.id, { region: { ...element.region, x: Math.round(event.target.x()), y: Math.round(event.target.y()) } })}
                    onTransformEnd={() => {
                      const node = shapeRefs.current[element.id];
                      if (!node) return;
                      const width = Math.max(1, Math.round(node.width() * node.scaleX()));
                      const height = Math.max(1, Math.round(node.height() * node.scaleY()));
                      node.scaleX(1); node.scaleY(1);
                      updateElement(element.id, { region: { x: Math.round(node.x()), y: Math.round(node.y()), width, height } });
                    }}
                  />
                  <Text key={`${element.id}-label`} x={element.region.x + 10} y={element.region.y + 8} text={`${element.sequence}. ${element.narrativeRole ?? "content"}`} fill={color} fontSize={28} listening={false} />
                  {(element.reveal.protectedRegions ?? []).map((region, protectedIndex) => <Rect key={`${element.id}-protected-${protectedIndex}`} {...region} stroke="#dc2626" dash={[14, 8]} strokeWidth={3} fill="#dc262618" listening={false} />)}
                </Fragment>
              );
            })}
            <Transformer ref={transformerRef} rotateEnabled={false} boundBoxFunc={(oldBox, newBox) => newBox.width < 20 || newBox.height < 20 ? oldBox : newBox} />
          </Layer>
        </Stage>
      </div>
      <div className="space-y-2">
        {elements.map((element) => (
          <div key={`${element.id}-timing`} className={`grid grid-cols-[28px_1fr_70px_70px_82px] gap-1 items-center rounded border p-1 ${selectedId === element.id ? "border-purple-500" : "border-[--border-default]"}`}>
            <button onClick={() => setSelectedId(element.id)} className="text-xs font-mono">{element.sequence}</button>
            <input value={element.subtitle ?? ""} onChange={(event) => updateElement(element.id, { subtitle: event.target.value })} placeholder="对应字幕/旁白" className="min-w-0 bg-[--bg-base] border border-[--border-default] rounded px-2 py-1 text-xs" />
            <input type="number" value={element.reveal.startMs} onChange={(event) => updateReveal(element.id, { startMs: Math.max(0, Number(event.target.value)) })} title="开始毫秒" className="bg-[--bg-base] border border-[--border-default] rounded px-2 py-1 text-xs" />
            <input type="number" value={element.reveal.durationMs} onChange={(event) => updateReveal(element.id, { durationMs: Math.max(1, Number(event.target.value)) })} title="持续毫秒" className="bg-[--bg-base] border border-[--border-default] rounded px-2 py-1 text-xs" />
            <input value={element.parallelGroup ?? ""} onChange={(event) => updateElement(element.id, { parallelGroup: event.target.value || null })} placeholder="并行组" className="bg-[--bg-base] border border-[--border-default] rounded px-2 py-1 text-xs" />
          </div>
        ))}
      </div>
    </div>
  );
}
