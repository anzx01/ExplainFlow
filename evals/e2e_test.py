#!/usr/bin/env python3
"""
ExplainFlow E2E 测试
覆盖完整链路：ExplainGraph → Storyboard（含 image_description）→ Imagegen（Seedream API）

运行方式：
  bash scripts/e2e.sh
  bash scripts/e2e.sh --topic 梯度下降   # 只跑单题
  bash scripts/e2e.sh --skip-imagegen    # 跳过真实 API 调用
"""

import asyncio
import json
import os
import re
import sys
import time
from pathlib import Path
from dataclasses import dataclass, field

import httpx

sys.path.insert(0, str(Path(__file__).parent.parent / "services" / "api"))

from src.explain.models import GenerateGraphRequest
from src.explain.service import generate_explain_graph
from src.planner.models import GenerateRemotionCodeRequest, GenerateStoryboardRequest, Storyboard
from src.planner.service import generate_remotion_code, generate_storyboard
from src.imagegen.service import SceneImageRequest, generate_all_scene_images


RESULTS_FILE = Path(__file__).parent / "e2e_results.json"
API_BASE_URL = os.getenv("E2E_API_BASE_URL", "http://localhost:8000")
RENDER_TIMEOUT_S = int(os.getenv("E2E_RENDER_TIMEOUT_S", "600"))

# 用于 e2e 的精简题目集（3 题，覆盖不同类型）
E2E_TOPICS = [
    {
        "id": "e2e_001",
        "topic": "梯度下降",
        "prompt": "讲解梯度下降算法的原理，包括损失函数、梯度、学习率的概念，以及参数如何逐步收敛到最优解。",
        "expected_concepts": ["损失", "梯度", "学习率"],
        "golden_formula": "θ := θ − α · ∇L(θ)",
    },
    {
        "id": "e2e_002",
        "topic": "Attention 机制",
        "prompt": "讲解 Transformer 中的 Self-Attention 机制，包括 Query、Key、Value 的概念和计算过程。",
        "expected_concepts": ["Query", "Key", "Value", "Softmax"],
        "golden_formula": "Attention(Q,K,V) = softmax(QK^T / √d_k) · V",
    },
    {
        "id": "e2e_003",
        "topic": "LoRA 低秩适配",
        "prompt": "讲解 LoRA 微调方法的原理：为什么用低秩矩阵分解、参数量对比、以及如何实现高效微调。",
        "expected_concepts": ["低秩", "参数", "微调"],
        "golden_formula": "W' = W + B·A",
    },
]


@dataclass
class StageResult:
    name: str
    passed: bool
    duration_s: float
    details: dict = field(default_factory=dict)
    error: str = ""


@dataclass
class TopicResult:
    id: str
    topic: str
    stages: list[StageResult] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(s.passed for s in self.stages)

    @property
    def total_duration_s(self) -> float:
        return sum(s.duration_s for s in self.stages)


# ── Stage 1: ExplainGraph ────────────────────────────────────────────────────

async def stage_explain_graph(spec: dict) -> tuple[StageResult, object]:
    t0 = time.perf_counter()
    try:
        req = GenerateGraphRequest(prompt=spec["prompt"])
        graph = await generate_explain_graph(req)
        dur = time.perf_counter() - t0

        checks = {}

        # 节点数量 5-10
        checks["node_count_ok"] = 5 <= len(graph.nodes) <= 10
        checks["node_count"] = len(graph.nodes)

        # 概念覆盖
        all_text = " ".join(n.label + " " + n.description for n in graph.nodes).lower()
        hits = [c for c in spec["expected_concepts"] if c.lower() in all_text]
        checks["concept_hits"] = hits
        checks["concept_coverage"] = len(hits) / len(spec["expected_concepts"])
        checks["concept_coverage_ok"] = checks["concept_coverage"] >= 0.6

        # teach_order 连续且从 0 开始
        orders = sorted(n.teach_order for n in graph.nodes)
        checks["teach_order_ok"] = orders[0] == 0

        # 有 edges
        checks["has_edges"] = len(graph.edges) > 0

        # topic 字段非空
        checks["topic_ok"] = bool(graph.topic)

        passed = all([
            checks["node_count_ok"],
            checks["concept_coverage_ok"],
            checks["teach_order_ok"],
            checks["has_edges"],
            checks["topic_ok"],
        ])

        return StageResult("explain_graph", passed, dur, checks), graph

    except Exception as e:
        return StageResult("explain_graph", False, time.perf_counter() - t0, error=str(e)), None


# ── Stage 2: Storyboard ──────────────────────────────────────────────────────

async def stage_storyboard(graph, target_duration: int = 90) -> tuple[StageResult, Storyboard | None]:
    t0 = time.perf_counter()
    try:
        req = GenerateStoryboardRequest(graph=graph, target_duration=target_duration)
        sb = await generate_storyboard(req)
        dur = time.perf_counter() - t0

        checks = {}

        # 场景数量 3-6
        checks["scene_count"] = len(sb.scenes)
        checks["scene_count_ok"] = 3 <= len(sb.scenes) <= 6

        # 每个场景有 narration
        checks["all_have_narration"] = all(bool(s.narration) for s in sb.scenes)

        # 每个场景有 animations
        checks["all_have_animations"] = all(len(s.animations) >= 1 for s in sb.scenes)

        # 每个场景有 image_description（新字段）
        with_img_desc = [s for s in sb.scenes if s.image_description]
        checks["image_description_count"] = len(with_img_desc)
        checks["image_description_ok"] = len(with_img_desc) >= len(sb.scenes) * 0.8

        # image_description 是英文（简单检测：包含英文字母）
        import re
        checks["image_description_english"] = all(
            bool(re.search(r"[a-zA-Z]{3,}", s.image_description or ""))
            for s in with_img_desc
        )

        # 总时长在目标 ±30s 内
        checks["total_duration"] = sb.total_duration_estimate
        checks["duration_ok"] = abs(sb.total_duration_estimate - target_duration) <= 30

        # 场景 id 唯一
        ids = [s.id for s in sb.scenes]
        checks["ids_unique"] = len(ids) == len(set(ids))

        passed = all([
            checks["scene_count_ok"],
            checks["all_have_narration"],
            checks["all_have_animations"],
            checks["image_description_ok"],
            checks["image_description_english"],
            checks["ids_unique"],
        ])

        return StageResult("storyboard", passed, dur, checks), sb

    except Exception as e:
        return StageResult("storyboard", False, time.perf_counter() - t0, error=str(e)), None


# ── Stage 3: Imagegen ────────────────────────────────────────────────────────

async def stage_imagegen(storyboard: Storyboard, topic: str) -> StageResult:
    t0 = time.perf_counter()
    try:
        scenes_with_desc = [s for s in storyboard.scenes if s.image_description]
        if not scenes_with_desc:
            return StageResult(
                "imagegen", False, 0.0,
                {"error": "no scenes with image_description"},
                error="no image_description in any scene",
            )

        requests = [
            SceneImageRequest(
                scene_id=s.id,
                topic=topic,
                title=s.title,
                image_description=s.image_description or "",
            )
            for s in scenes_with_desc
        ]

        results = await generate_all_scene_images(requests)
        dur = time.perf_counter() - t0

        checks = {}
        checks["requested"] = len(requests)
        checks["succeeded"] = sum(1 for v in results.values() if v)
        checks["failed"] = sum(1 for v in results.values() if not v)
        checks["success_rate"] = checks["succeeded"] / checks["requested"]

        # 成功率 >= 80%
        checks["success_rate_ok"] = checks["success_rate"] >= 0.8

        # 返回的 URL 格式正确
        urls = [v for v in results.values() if v]
        checks["urls_valid"] = all(v.startswith("http") for v in urls)

        # 每个 URL 不同（没有重复）
        checks["urls_unique"] = len(urls) == len(set(urls))

        passed = checks["success_rate_ok"] and checks["urls_valid"]

        return StageResult("imagegen", passed, dur, checks)

    except Exception as e:
        return StageResult("imagegen", False, time.perf_counter() - t0, error=str(e))


# ── Runner ───────────────────────────────────────────────────────────────────

def make_render_smoke_storyboard(storyboard: Storyboard, duration_s: int = 18) -> Storyboard:
    scene_count = max(1, min(2, len(storyboard.scenes)))
    scene_duration = duration_s / scene_count
    scenes = []
    for index, scene in enumerate(storyboard.scenes[:scene_count]):
        narration = scene.narration.strip()
        if len(narration) > 90:
            narration = narration[:90].rstrip("，。,. ") + "。"
        scenes.append(
            scene.model_copy(
                update={
                    "order": index,
                    "duration_estimate": scene_duration,
                    "narration": narration,
                }
            )
        )
    return storyboard.model_copy(
        update={
            "total_duration_estimate": duration_s,
            "scenes": scenes,
        }
    )


async def stage_remotion_code(storyboard: Storyboard) -> StageResult:
    t0 = time.perf_counter()
    try:
        req = GenerateRemotionCodeRequest(
            storyboard=storyboard,
            fps=30,
            width=1280,
            height=720,
            style_prompt=(
                "E2E smoke: hand-drawn YouTube whiteboard animation, black ink outlines, "
                "loose watercolor fills, live handwriting, and live SVG stroke drawing."
            ),
        )
        code = await generate_remotion_code(req)
        dur = time.perf_counter() - t0
        tsx = code.tsx
        checks = {
            "tsx_length": len(tsx),
            "duration_in_frames": code.duration_in_frames,
            "has_generated_video": "GeneratedVideo" in tsx,
            "uses_frame_api": "useCurrentFrame" in tsx,
            "uses_sequence": "Sequence" in tsx,
            "uses_dash_draw": "strokeDasharray" in tsx and "strokeDashoffset" in tsx,
            "reveals_text": (
                "glyphPaths" in tsx
                or re.search(r"\bspec\.text\.(?:slice|substring)\s*\(", tsx) is not None
                or "clipPath" in tsx
            ),
            "uses_glyph_outline_text": (
                "glyphPaths" in tsx
                and re.search(r"\b(DrawGlyphPath|GlyphText)\b", tsx) is not None
                and "fontOutline" in tsx
            ),
            "no_handtext_slice_renderer": "HandText" not in tsx and "spec.text.slice" not in tsx,
            "uses_hand_asset": "hand-real-pen.png" in tsx,
            "uses_hand_img": "staticFile(" in tsx and "Img" in tsx,
            "has_hand_pen": "HandPen" in tsx,
            "has_pen_tip_coordinates": any(token in tsx for token in ["tipX", "tipY", "penX", "penY"]),
            "has_hand_size_constants": "HAND_WIDTH" in tsx and "PEN_TIP_X" in tsx and "PEN_TIP_Y" in tsx,
            "has_draw_ops": "drawOps" in tsx,
            "has_draw_op_points": len(
                re.findall(
                    r"\{\s*['\"]?x['\"]?\s*:\s*-?\d+(?:\.\d+)?\s*,\s*['\"]?y['\"]?\s*:\s*-?\d+(?:\.\d+)?\s*\}",
                    tsx,
                )
            )
            >= 16,
            "has_text_draw_ops": re.search(r"\b['\"]?kind['\"]?\s*:\s*['\"]text['\"]", tsx) is not None,
            "has_shape_draw_ops": re.search(r"\b['\"]?kind['\"]?\s*:\s*['\"](?:path|stroke|shape|arrow|box)['\"]", tsx) is not None,
            "samples_polyline": "pointOnPolyline" in tsx,
            "uses_active_draw_op": "getActiveDrawOp" in tsx,
            "hand_from_draw_ops": re.search(r"\bgetPenPosition\s*\(\s*frame\s*\)", tsx) is not None,
            "no_coarse_tip_interpolate": re.search(
                r"\bconst\s+(?:tipX|tipY|penX|penY)\s*=\s*interpolate\s*\(\s*frame\s*,\s*\[[^\]]+\]\s*,\s*\[[^\]]+\]",
                tsx,
            )
            is None,
            "has_hand_visible_flag": "visible" in tsx,
            "uses_handwriting_font": re.search(
                r"\b(STXingkai|Xingkai|KaiTi|STKaiti|Kaiti|楷体|华文行楷|华文楷体)\b",
                tsx,
                flags=re.IGNORECASE,
            )
            is not None,
            "no_bold_sans_text": re.search(r"\bfontWeight\s*:\s*['\"]?(?:700|800|900|bold)\b", tsx, flags=re.IGNORECASE) is None,
            "has_anime_doodle": re.search(
                r"\b(AnimeDoodle|CartoonDiagram|CartoonMascot|DoodleCharacter|anime|cartoon|doodle)\b",
                tsx,
                flags=re.IGNORECASE,
            )
            is not None,
            "uses_per_stroke_dash_length": "dashLength" in tsx and "const length = spec.dashLength" in tsx,
            "no_static_doodle_face": "faceOpacity" not in tsx and "cx=\"78%\"" not in tsx,
            "has_multiple_doodle_strokes": len(re.findall(r"['\"]?role['\"]?\s*:\s*['\"]doodle['\"]", tsx)) >= 5,
            "has_content_aware_diagram_kind": bool(
                set(re.findall(r"['\"]diagramKind['\"]\s*:\s*['\"]([^'\"]+)['\"]", tsx))
                & {
                    "process_flow",
                    "comparison_transform",
                    "formula_derivation",
                    "optimization_curve",
                    "attention_network",
                    "matrix_transform",
                    "feedback_loop",
                }
            ),
            "has_contextual_stroke_roles": re.search(
                r"['\"]?role['\"]?\s*:\s*['\"](?:axis|loss_curve|node|matrix|matrix_grid|loop|formula|change|arrow|arrowhead)['\"]",
                tsx,
            )
            is not None,
            "has_arrowheads": len(re.findall(r"['\"]?role['\"]?\s*:\s*['\"]arrowhead['\"]", tsx)) >= 2,
            "rejects_fixed_sun_box_curve": all(
                token not in tsx
                for token in [
                    "sun_cx",
                    "sun_rx",
                    "small sun",
                    "\"role\":\"diagram\",\"d\":\"M 665.6 403.2",
                    "\"color\":\"#E15D4F\"",
                ]
            ),
            "hand_outside_svg": re.search(
                r"<svg(?:(?!</svg>).)*<HandPen(?:(?!</svg>).)*</svg>",
                tsx,
                flags=re.IGNORECASE | re.DOTALL,
            )
            is None,
            "hand_img_wrapped": re.search(r"HandPen[\s\S]*?<div[\s\S]*?<Img", tsx, flags=re.IGNORECASE) is not None,
            "no_local_imports": "from \"./" not in tsx and "from './" not in tsx,
        }
        passed = all(
            [
                checks["tsx_length"] > 500,
                checks["duration_in_frames"] >= 300,
                checks["has_generated_video"],
                checks["uses_frame_api"],
                checks["uses_sequence"],
                checks["uses_dash_draw"],
                checks["reveals_text"],
                checks["uses_glyph_outline_text"],
                checks["no_handtext_slice_renderer"],
                checks["uses_hand_asset"],
                checks["uses_hand_img"],
                checks["has_hand_pen"],
                checks["has_pen_tip_coordinates"],
                checks["has_hand_size_constants"],
                checks["has_draw_ops"],
                checks["has_draw_op_points"],
                checks["has_text_draw_ops"],
                checks["has_shape_draw_ops"],
                checks["samples_polyline"],
                checks["uses_active_draw_op"],
                checks["hand_from_draw_ops"],
                checks["no_coarse_tip_interpolate"],
                checks["has_hand_visible_flag"],
                checks["uses_handwriting_font"],
                checks["no_bold_sans_text"],
                checks["has_anime_doodle"],
                checks["uses_per_stroke_dash_length"],
                checks["no_static_doodle_face"],
                checks["has_multiple_doodle_strokes"],
                checks["has_content_aware_diagram_kind"],
                checks["has_contextual_stroke_roles"],
                checks["has_arrowheads"],
                checks["rejects_fixed_sun_box_curve"],
                checks["hand_outside_svg"],
                checks["hand_img_wrapped"],
                checks["no_local_imports"],
            ]
        )
        return StageResult("remotion_code", passed, dur, checks)
    except Exception as e:
        return StageResult("remotion_code", False, time.perf_counter() - t0, error=str(e))


async def stage_render_smoke(storyboard: Storyboard) -> StageResult:
    t0 = time.perf_counter()
    try:
        payload = {
            "storyboard": storyboard.model_dump(mode="json"),
            "voice": "xiaoxiao",
            "resolution": "1080p",
        }
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(f"{API_BASE_URL}/render/job", json=payload)
            response.raise_for_status()
            job_id = response.json()["job_id"]

        deadline = time.perf_counter() + RENDER_TIMEOUT_S
        last_status = {}
        async with httpx.AsyncClient(timeout=30) as client:
            while time.perf_counter() < deadline:
                status_response = await client.get(f"{API_BASE_URL}/render/job/{job_id}")
                status_response.raise_for_status()
                last_status = status_response.json()
                if last_status.get("status") in {"done", "failed"}:
                    break
                await asyncio.sleep(5)

            if last_status.get("status") != "done":
                return StageResult(
                    "render_smoke",
                    False,
                    time.perf_counter() - t0,
                    {"job_id": job_id, "last_status": last_status},
                    error=last_status.get("error") or "render timed out",
                )

            download = await client.get(f"{API_BASE_URL}/render/download/{job_id}")
            download.raise_for_status()
            content = download.content

        details = {
            "job_id": job_id,
            "bytes": len(content),
            "content_type": download.headers.get("content-type"),
            "phase": last_status.get("phase"),
            "progress": last_status.get("progress"),
            "has_mp4_ftyp": b"ftyp" in content[:32],
        }
        passed = details["bytes"] > 100_000 and details["has_mp4_ftyp"]
        return StageResult("render_smoke", passed, time.perf_counter() - t0, details)
    except Exception as e:
        return StageResult("render_smoke", False, time.perf_counter() - t0, error=str(e))


async def run_topic(
    spec: dict,
    skip_imagegen: bool = False,
    render_smoke: bool = False,
) -> TopicResult:
    result = TopicResult(id=spec["id"], topic=spec["topic"])

    # Stage 1
    s1, graph = await stage_explain_graph(spec)
    result.stages.append(s1)
    if not s1.passed or graph is None:
        return result

    # Stage 2
    s2, storyboard = await stage_storyboard(graph)
    result.stages.append(s2)
    if not s2.passed or storyboard is None:
        return result

    # Stage 3
    compact_storyboard = make_render_smoke_storyboard(storyboard)
    s3 = await stage_remotion_code(compact_storyboard)
    result.stages.append(s3)
    if not s3.passed:
        return result

    # Stage 4
    if render_smoke:
        s4 = await stage_render_smoke(compact_storyboard)
        result.stages.append(s4)

    # Legacy optional stage
    if skip_imagegen:
        result.stages.append(StageResult("imagegen", True, 0.0, {"skipped": True}))
    else:
        s5 = await stage_imagegen(storyboard, spec["topic"])
        result.stages.append(s5)

    return result


def print_result(r: TopicResult) -> None:
    status = "PASS" if r.passed else "FAIL"
    print(f"\n  [{status}]  [{r.id}] {r.topic}  ({r.total_duration_s:.1f}s)")
    for s in r.stages:
        icon = "  [ok]" if s.passed else "  [!!]"
        skipped = s.details.get("skipped")
        if skipped:
            print(f"    {icon} {s.name:<20} (skipped)")
            continue
        print(f"    {icon} {s.name:<20} {s.duration_s:.1f}s", end="")
        if s.error:
            print(f"  ERROR: {s.error}", end="")
        elif s.name == "explain_graph":
            cov = s.details.get("concept_coverage", 0)
            print(f"  nodes={s.details.get('node_count')}  concept_cov={cov:.0%}", end="")
        elif s.name == "storyboard":
            print(
                f"  scenes={s.details.get('scene_count')}  "
                f"img_desc={s.details.get('image_description_count')}  "
                f"dur={s.details.get('total_duration'):.0f}s",
                end="",
            )
        elif s.name == "imagegen":
            rate = s.details.get("success_rate", 0)
            print(
                f"  {s.details.get('succeeded')}/{s.details.get('requested')} images  "
                f"rate={rate:.0%}",
                end="",
            )
        elif s.name == "remotion_code":
            print(
                f"  tsx={s.details.get('tsx_length')} chars  "
                f"frames={s.details.get('duration_in_frames')}  "
                f"dash={s.details.get('uses_dash_draw')}  "
                f"hand={s.details.get('has_hand_pen')}  "
                f"stroke_ops={s.details.get('has_draw_ops')}  "
                f"pen_path={s.details.get('hand_from_draw_ops')}  "
                f"anime={s.details.get('has_anime_doodle')}  "
                f"doodle_strokes={s.details.get('has_multiple_doodle_strokes')}  "
                f"content_diagram={s.details.get('has_content_aware_diagram_kind')}  "
                f"arrowheads={s.details.get('has_arrowheads')}",
                end="",
            )
        elif s.name == "render_smoke":
            print(
                f"  job={s.details.get('job_id')}  "
                f"bytes={s.details.get('bytes')}  "
                f"ftyp={s.details.get('has_mp4_ftyp')}",
                end="",
            )
        print()


async def main() -> None:
    skip_imagegen = "--skip-imagegen" in sys.argv
    render_smoke = "--render-smoke" in sys.argv or "--render" in sys.argv

    topics = E2E_TOPICS
    if "--topic" in sys.argv:
        idx = sys.argv.index("--topic")
        name = sys.argv[idx + 1]
        topics = [t for t in topics if t["id"] == name or t["topic"] == name]
        if not topics:
            print(f"[e2e] Topic not found: {name}")
            sys.exit(1)

    mode_parts = [
        "skip imagegen" if skip_imagegen else "with Seedream API",
        "render smoke" if render_smoke else "codegen only",
    ]
    mode = "(" + ", ".join(mode_parts) + ")"
    print(f"[e2e] Starting E2E test: {len(topics)} topics {mode}")
    print("=" * 60)

    all_results = []
    for i, spec in enumerate(topics, 1):
        print(f"\n[{i}/{len(topics)}] {spec['topic']} ...", flush=True)
        r = await run_topic(spec, skip_imagegen=skip_imagegen, render_smoke=render_smoke)
        all_results.append(r)
        print_result(r)

    # 汇总
    passed = sum(1 for r in all_results if r.passed)
    failed = len(all_results) - passed
    total_time = sum(r.total_duration_s for r in all_results)

    print("\n" + "=" * 60)
    print(f"[e2e] Result: {passed}/{len(all_results)} passed  total: {total_time:.1f}s")

    # 写结果文件
    summary = {
        "passed": passed,
        "failed": failed,
        "total": len(all_results),
        "skip_imagegen": skip_imagegen,
        "render_smoke": render_smoke,
        "results": [
            {
                "id": r.id,
                "topic": r.topic,
                "passed": r.passed,
                "duration_s": round(r.total_duration_s, 2),
                "stages": [
                    {
                        "name": s.name,
                        "passed": s.passed,
                        "duration_s": round(s.duration_s, 2),
                        "details": s.details,
                        "error": s.error,
                    }
                    for s in r.stages
                ],
            }
            for r in all_results
        ],
    }
    RESULTS_FILE.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[e2e] Results written to: {RESULTS_FILE}")

    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    asyncio.run(main())
