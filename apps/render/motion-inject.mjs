/**
 * motion-inject.mjs — 确定性场景动画层注入
 *
 * LLM 生成的 TSX 会剥掉 scene.motion 字段,也不会主动实现动画层,
 * 所以在 codegen 后处理里:
 *   1. 把 storyboard 的 motion 规格按场景标题注入为 SCENE_MOTION 常量
 *   2. 把原 GeneratedVideo 改名为 GeneratedVideoBase
 *   3. 追加一个包装版 GeneratedVideo,叠加按场景窗口循环播放的动画层
 * 动画只允许 useCurrentFrame() 数学驱动(曲柄滑块公式/模数推进),
 * 与 validate-tsx.mjs 的全部禁令兼容(无 <animate>/CSS 动画/阴影/渐变)。
 */

const MARKER = "SCENE_MOTION_BY_TITLE";

export function injectSceneMotion(tsx, storyboard, dims = {}) {
  if (!tsx || tsx.includes(MARKER)) return tsx;
  // LLM 自己实现了动画(引用 scene.motion)时不再重复注入
  if (/scene\.motion\b|\.motion\.elements/.test(tsx.replace(/"motion":\{[^}]*\}/g, ""))) return tsx;

  const fps = Number(dims.fps ?? 24);
  const width = Math.round(Number(dims.width ?? 960));
  const height = Math.round(Number(dims.height ?? 540));

  const entries = (storyboard?.scenes ?? [])
    .filter((scene) => scene?.motion && Array.isArray(scene.motion.elements) && scene.motion.elements.length > 0)
    .map((scene) => ({ title: scene.title, motion: scene.motion }));
  if (entries.length === 0) return tsx;

  const renamed = renameGeneratedVideoExport(tsx);
  if (!renamed) return tsx;

  const data = JSON.stringify(entries).replace(/</g, "\\u003c");
  const layer = `\n// --- scene motion layer (deterministic injection) ---\n` +
    `const ${MARKER} = ${data};\n` +
    `const MOTION_FPS = ${fps};\n` +
    `const MOTION_W = ${width};\n` +
    `const MOTION_H = ${height};\n` +
    `const MOTION_INK = "#2f2f2f";\n` +
    `const MOTION_STROKE = Math.max(3, Math.round(MOTION_H / 135));\n` +
    motionLayerSource() +
    `\nexport function GeneratedVideo() {\n` +
    `  return (\n    <>\n      <GeneratedVideoBase />\n      <SceneMotionOverlay sceneList={scenes} />\n    </>\n  );\n}\n`;
  return renamed + layer;
}

function renameGeneratedVideoExport(tsx) {
  if (/export\s+function\s+GeneratedVideo\s*\(/.test(tsx)) {
    return tsx.replace(/export\s+function\s+GeneratedVideo\s*\(/, "function GeneratedVideoBase(");
  }
  if (/export\s+default\s+function\s+GeneratedVideo\s*\(/.test(tsx)) {
    return tsx.replace(/export\s+default\s+function\s+GeneratedVideo\s*\(/, "function GeneratedVideoBase(");
  }
  if (/export\s+const\s+GeneratedVideo\s*=/.test(tsx)) {
    return tsx.replace(/export\s+const\s+GeneratedVideo\s*=/, "const GeneratedVideoBase =");
  }
  return null;
}

function motionLayerSource() {
  return `function motionTitleMap() {
  const map: Record<string, any> = {};
  ${MARKER}.forEach((entry: any) => { if (entry && entry.title && entry.motion) map[entry.title] = entry.motion; });
  return map;
}

const motionPolar = (cx: number, cy: number, radius: number, angle: number) => ({
  x: cx + radius * Math.sin(angle),
  y: cy + radius * Math.cos(angle),
});

function MotionPistonCrank({ el, frame, phase }: { el: any; frame: number; phase: number }) {
  const s = (el.size ?? 0.16) * MOTION_H;
  const cx = (el.x ?? 0.5) * MOTION_W;
  const cy = (el.y ?? 0.68) * MOTION_H;
  const r = s * 0.16;
  const rod = s * 0.38;
  const pw = s * 0.34;
  const ph = s * 0.20;
  const cps = el.cyclesPerSecond ?? 0.5;
  const a = (frame * 2 * Math.PI * cps) / MOTION_FPS + phase;
  const pin = motionPolar(cx, cy, r, a);
  const rodDx = pin.x - cx;
  const wristY = pin.y - Math.sqrt(Math.max(rod * rod - rodDx * rodDx, 0));
  const wallTop = cy - rod - r - ph - 12;
  const ink = el.color ?? MOTION_INK;
  return (
    <g stroke={ink} strokeWidth={MOTION_STROKE} strokeLinecap="round" fill="none">
      <line x1={cx - pw / 2 - 7} y1={wallTop} x2={cx - pw / 2 - 7} y2={cy + r + 8} strokeDasharray="18 7" />
      <line x1={cx + pw / 2 + 7} y1={wallTop} x2={cx + pw / 2 + 7} y2={cy + r + 8} strokeDasharray="18 7" />
      <rect x={cx - pw / 2} y={wristY - ph} width={pw} height={ph} rx={5} stroke={el.color ?? "#2E86C1"} />
      <circle cx={cx} cy={cy} r={r} />
      <line x1={cx} y1={cy} x2={pin.x} y2={pin.y} />
      <line x1={cx} y1={wristY} x2={pin.x} y2={pin.y} stroke={el.color ?? "#2E86C1"} />
      <circle cx={pin.x} cy={pin.y} r={5} fill={ink} stroke="none" />
    </g>
  );
}

function MotionPistonRow({ el, frame }: { el: any; frame: number }) {
  const count = Math.max(2, Math.min(6, el.count ?? 4));
  const s = (el.size ?? 0.18) * MOTION_H;
  const span = s * 2.6;
  const cx = (el.x ?? 0.5) * MOTION_W;
  const cy = (el.y ?? 0.6) * MOTION_H;
  const units = [];
  for (let i = 0; i < count; i += 1) {
    const unitX = cx - span / 2 + (span * i) / (count - 1);
    units.push(
      <MotionPistonCrank
        key={"unit-" + i}
        el={{ ...el, x: unitX / MOTION_W, y: cy / MOTION_H, size: s / MOTION_H }}
        frame={frame}
        phase={(i * Math.PI) / count}
      />
    );
  }
  return (
    <g>
      <line x1={cx - span / 2 - 10} y1={cy + s * 0.16 + 6} x2={cx + span / 2 + 10} y2={cy + s * 0.16 + 6}
        stroke={MOTION_INK} strokeWidth={MOTION_STROKE} strokeLinecap="round" />
      {units}
    </g>
  );
}

function MotionFlowArrows({ el, frame }: { el: any; frame: number }) {
  const from = { x: (el.from?.[0] ?? el.x ?? 0.4) * MOTION_W, y: (el.from?.[1] ?? el.y ?? 0.3) * MOTION_H };
  const to = { x: (el.to?.[0] ?? el.x ?? 0.6) * MOTION_W, y: (el.to?.[1] ?? el.y ?? 0.3) * MOTION_H };
  const dx = to.x - from.x;
  const dy = to.y - from.y;
  const len = Math.max(Math.sqrt(dx * dx + dy * dy), 1);
  const ux = dx / len;
  const uy = dy / len;
  const px = -uy;
  const py = ux;
  const head = (el.size ?? 0.1) * MOTION_H * 0.22;
  const speed = el.speed ?? 0.5;
  const chevrons = [];
  for (let i = 0; i < 3; i += 1) {
    const p = (frame * speed) / MOTION_FPS + i / 3;
    const t = p - Math.floor(p);
    const bx = from.x + dx * t;
    const by = from.y + dy * t;
    const opacity = Math.sin(Math.PI * t);
    chevrons.push(
      <path
        key={"ch-" + i}
        d={
          "M " + (bx - ux * head + px * head) + " " + (by - uy * head + py * head) +
          " L " + (bx + ux * head) + " " + (by + uy * head) +
          " L " + (bx - ux * head - px * head) + " " + (by - uy * head - py * head)
        }
        stroke={el.color ?? "#2E9E4F"}
        strokeWidth={MOTION_STROKE + 2}
        strokeLinecap="round"
        strokeLinejoin="round"
        fill="none"
        opacity={opacity}
      />
    );
  }
  return <g>{chevrons}</g>;
}

function MotionPulse({ el, frame }: { el: any; frame: number }) {
  const cycle = el.cycleSeconds ?? 2;
  const t = ((frame / MOTION_FPS) / cycle) % 1;
  const cx = (el.x ?? 0.5) * MOTION_W;
  const cy = (el.y ?? 0.3) * MOTION_H;
  const radius = (el.size ?? 0.1) * MOTION_H * (0.3 + 0.7 * t);
  return (
    <circle cx={cx} cy={cy} r={radius} stroke={el.color ?? "#E67E22"} strokeWidth={MOTION_STROKE + 1}
      fill="none" opacity={1 - t} />
  );
}

function MotionCycleRing({ el, frame }: { el: any; frame: number }) {
  const cycle = el.cycleSeconds ?? 4;
  const cx = (el.x ?? 0.5) * MOTION_W;
  const cy = (el.y ?? 0.45) * MOTION_H;
  const radius = (el.size ?? 0.2) * MOTION_H * 0.5;
  const arcs = [];
  const t = ((frame / MOTION_FPS) / cycle) % 1;
  const active = Math.floor(t * 4) % 4;
  for (let i = 0; i < 4; i += 1) {
    const a0 = -Math.PI / 2 + (i * 2 * Math.PI) / 4 + 0.14;
    const a1 = -Math.PI / 2 + ((i + 1) * 2 * Math.PI) / 4 - 0.14;
    const p0 = motionPolar(cx, cy, radius, a0);
    const p1 = motionPolar(cx, cy, radius, a1);
    arcs.push(
      <path key={"arc-" + i}
        d={"M " + p0.x + " " + p0.y + " A " + radius + " " + radius + " 0 0 1 " + p1.x + " " + p1.y}
        stroke={i === active ? "#E67E22" : MOTION_INK}
        strokeWidth={i === active ? 8 : 5}
        strokeLinecap="round"
        fill="none"
        opacity={i === active ? 1 : 0.35}
      />
    );
  }
  const dotAngle = t * 2 * Math.PI - Math.PI / 2;
  const dot = motionPolar(cx, cy, radius, dotAngle);
  return (
    <g>
      {arcs}
      <circle cx={dot.x} cy={dot.y} r={7} fill="#E67E22" stroke="none" />
    </g>
  );
}

function MotionElement({ el, frame }: { el: any; frame: number }) {
  if (!el || !el.type) return null;
  if (el.type === "piston_crank") return <MotionPistonCrank el={el} frame={frame} phase={0} />;
  if (el.type === "piston_row") return <MotionPistonRow el={el} frame={frame} />;
  if (el.type === "flow_arrows") return <MotionFlowArrows el={el} frame={frame} />;
  if (el.type === "pulse") return <MotionPulse el={el} frame={frame} />;
  if (el.type === "cycle_ring") return <MotionCycleRing el={el} frame={frame} />;
  return null;
}

function MotionScene({ motion, duration }: { motion: any; duration: number }) {
  const frame = useCurrentFrame();
  const startFraction = motion?.startFraction ?? 0.4;
  if (frame < startFraction * duration) return null;
  const elements = (motion && motion.elements) || [];
  return (
    <svg width={MOTION_W} height={MOTION_H} style={{ position: "absolute", top: 0, left: 0, pointerEvents: "none" }}>
      {elements.map((el: any, i: number) => (
        <MotionElement key={"mel-" + i} el={el} frame={frame} />
      ))}
    </svg>
  );
}

export function SceneMotionOverlay({ sceneList }: { sceneList: any[] }) {
  const titleMotion = motionTitleMap();
  let cursor = 0;
  const items: any[] = [];
  sceneList.forEach((scene: any) => {
    const start = cursor;
    cursor += scene.duration;
    const motion = titleMotion[scene.title];
    if (motion) items.push({ start, duration: scene.duration, motion });
  });
  if (items.length === 0) return null;
  return (
    <div style={{ position: "absolute", top: 0, left: 0, width: MOTION_W, height: MOTION_H, pointerEvents: "none" }}>
      {items.map((item, i: number) => (
        <Sequence key={"smo-" + i} from={item.start} durationInFrames={item.duration}>
          <MotionScene motion={item.motion} duration={item.duration} />
        </Sequence>
      ))}
    </div>
  );
}
`;
}
