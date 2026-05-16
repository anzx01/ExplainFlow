#!/usr/bin/env python3
"""ExplainFlow 评测脚本 — 对 20 个 AI/ML 标杆题目跑 Explain Graph 生成并评分"""

import asyncio
import json
import sys
from pathlib import Path

# 确保能 import services/api 的模块
sys.path.insert(0, str(Path(__file__).parent.parent / "services" / "api"))

from src.explain.models import ExplainGraph, GenerateGraphRequest
from src.explain.service import generate_explain_graph


TOPICS_FILE = Path(__file__).parent / "topics.json"
RESULTS_FILE = Path(__file__).parent / "results.json"


def score_graph(graph: ExplainGraph, topic_spec: dict) -> dict:
    """对单个 Explain Graph 评分（满分 40 分）"""
    score = 0
    details: dict = {}

    # 1. 节点数量（10 分）
    expected = topic_spec.get("expected_node_count", 5)
    actual = len(graph.nodes)
    node_score = min(10, round(10 * min(actual, expected) / expected))
    score += node_score
    details["node_count"] = {"expected": expected, "actual": actual, "score": node_score}

    # 2. 概念覆盖（20 分）
    expected_concepts: list[str] = topic_spec.get("expected_concepts", [])
    all_labels = " ".join(n.label + " " + n.description for n in graph.nodes).lower()
    hit = sum(1 for c in expected_concepts if c.lower() in all_labels)
    concept_score = round(20 * hit / len(expected_concepts)) if expected_concepts else 20
    score += concept_score
    details["concept_coverage"] = {
        "expected": expected_concepts,
        "hit": hit,
        "score": concept_score,
    }

    # 3. 公式存在（10 分）
    golden = topic_spec.get("golden_formula", "")
    has_formula = any(n.latex for n in graph.nodes)
    formula_score = 10 if has_formula else 0
    score += formula_score
    details["formula"] = {"golden": golden, "has_formula": has_formula, "score": formula_score}

    return {"total": score, "max": 40, "details": details}


async def run_eval(topic_spec: dict) -> dict:
    req = GenerateGraphRequest(prompt=topic_spec["prompt"])
    try:
        graph = await generate_explain_graph(req)
        scores = score_graph(graph, topic_spec)
        return {
            "id": topic_spec["id"],
            "topic": topic_spec["topic"],
            "status": "ok",
            "node_count": len(graph.nodes),
            "scores": scores,
        }
    except Exception as e:
        return {
            "id": topic_spec["id"],
            "topic": topic_spec["topic"],
            "status": "error",
            "error": str(e),
            "scores": {"total": 0, "max": 40},
        }


async def main() -> None:
    topics = json.loads(TOPICS_FILE.read_text(encoding="utf-8"))

    # 支持 --topic 参数只跑单题
    filter_id = None
    if "--topic" in sys.argv:
        idx = sys.argv.index("--topic")
        filter_id = sys.argv[idx + 1]
        topics = [t for t in topics if t["id"] == filter_id or t["topic"] == filter_id]

    print(f"[eval] 开始评测 {len(topics)} 个题目...")
    results = []
    for i, topic in enumerate(topics, 1):
        print(f"  [{i}/{len(topics)}] {topic['topic']} ...", end=" ", flush=True)
        result = await run_eval(topic)
        results.append(result)
        status = result["status"]
        if status == "ok":
            print(f"✓ {result['scores']['total']}/40")
        else:
            print(f"✗ {result.get('error', 'unknown error')}")

    # 汇总
    ok_results = [r for r in results if r["status"] == "ok"]
    avg_score = sum(r["scores"]["total"] for r in ok_results) / len(ok_results) if ok_results else 0
    summary = {
        "total_topics": len(topics),
        "success": len(ok_results),
        "failed": len(topics) - len(ok_results),
        "avg_graph_score": round(avg_score, 1),
        "results": results,
    }

    RESULTS_FILE.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[eval] 完成。平均 Graph 分数: {avg_score:.1f}/40")
    print(f"[eval] 结果已写入: {RESULTS_FILE}")


if __name__ == "__main__":
    asyncio.run(main())
