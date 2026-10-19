"""Narration quality audit + one LLM deepen pass.

The reference projects (anything2explainer / storyboard-ai) converge on the
same lesson: narration density and structure decide whether a topic feels
"讲透" — the measured failure was 444 narration chars stretched over 124
seconds with three wrap-up scenes at the end. The audit below turns the
讲稿质量契约 into programmable checks; failing storyboards get one targeted
rewrite pass instead of shipping thin narration.
"""
from __future__ import annotations

import logging
import re

from src.core.llm import LLMResponseParseError, chat_json
from src.planner.models import Scene, Storyboard

logger = logging.getLogger(__name__)

# 中文旁白 TTS 实测可用密度约 4.5-5.5 字/秒;低于下限说明内容注水或缺失
GLOBAL_DENSITY_MIN = 3.6  # 字/秒(全片)
SCENE_DENSITY_MIN = 3.0  # 字/秒(单场,开场/收尾允许略松)
SCENE_MIN_CHARS = 30

_ANNOUNCER_RE = re.compile(
    r"^(接下来|下面我们|本[节章]|这一节|现在我们来看|首先我们|然后我们|接着我们|让我们来看)"
)
_DESCRIBES_IMAGE_RE = re.compile(r"(看图中|图中|画面上|屏幕上|图里|图中的|左边画|右边画|这里画|这幅图|这张图|图上)")
_WRAPUP_RE = re.compile(r"(总览|回顾|总结|小结|概览|归纳|收尾|overview|recap)")


def _sentence_split(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"[。！？!?；\n]", text) if s.strip()]


def _char_bigrams(text: str) -> set[str]:
    cleaned = re.sub(r"[，。、\s]", "", text)
    return {cleaned[i : i + 2] for i in range(max(0, len(cleaned) - 1))}


def audit_narration(storyboard: Storyboard, target_duration: int) -> dict:
    """Return {ok, issues:[{scene_id?, code, detail}]} for the contract checks."""
    issues: list[dict] = []
    scenes = storyboard.scenes
    total_chars = sum(len(s.narration or "") for s in scenes)
    total_seconds = sum(max(1.0, s.duration_estimate or 0) for s in scenes) or max(1, target_duration)
    density = total_chars / total_seconds
    if density < GLOBAL_DENSITY_MIN:
        issues.append({
            "code": "narration_too_thin",
            "detail": f"全片旁白 {total_chars} 字 / {round(total_seconds)}s = {density:.1f} 字/秒,低于 {GLOBAL_DENSITY_MIN}。需要补机制、数字、对比等实内容。",
        })

    for index, scene in enumerate(scenes):
        narration = (scene.narration or "").strip()
        sid = scene.id
        dur = max(1.0, scene.duration_estimate or 0)
        if len(narration) < SCENE_MIN_CHARS or len(narration) < dur * SCENE_DENSITY_MIN:
            issues.append({
                "scene_id": sid,
                "code": "scene_narration_thin",
                "detail": f"该场 {len(narration)} 字 / {round(dur)}s,低于 {SCENE_DENSITY_MIN} 字/秒下限。",
            })
        sentences = _sentence_split(narration)
        if sentences and _ANNOUNCER_RE.match(sentences[0]):
            issues.append({"scene_id": sid, "code": "announcer_opening", "detail": f"开场是报幕句:{sentences[0][:24]}…"})
        if _DESCRIBES_IMAGE_RE.search(narration):
            issues.append({"scene_id": sid, "code": "describes_image", "detail": "旁白在复述画面(看图中/这里画…)。"})
        if not scene.key_points:
            issues.append({"scene_id": sid, "code": "missing_key_points", "detail": "缺少 key_points 硬承诺。"})
        if 0 < index < len(scenes) - 1:
            blob = f"{scene.title} {scene.learning_goal or ''}"
            if _WRAPUP_RE.search(blob):
                issues.append({"scene_id": sid, "code": "mid_wrapup_scene", "detail": f"中间出现收束类场景「{scene.title}」,只允许开场钩子/最后总结。"})

    for prev, curr in zip(scenes, scenes[1:]):
        a, b = _char_bigrams(prev.narration or ""), _char_bigrams(curr.narration or "")
        if a and b:
            overlap = len(a & b) / max(1, min(len(a), len(b)))
            if overlap > 0.6:
                issues.append({
                    "scene_id": curr.id,
                    "code": "near_duplicate_narration",
                    "detail": f"与上一场旁白重复度 {overlap:.0%},两场在讲同一件事。",
                })
    return {"ok": not issues, "issues": issues, "density": round(density, 2), "totalChars": total_chars}


_DEEPEN_SYSTEM_PROMPT = """你是教学视频旁白深化编辑。你会收到一份分镜脚本(含每场时长、key_points 硬承诺、现有旁白)和审计诊断列表。
任务:重写不达标的旁白,让全片"讲透"。

改写规则(硬约束):
1. 覆盖:每场旁白必须逐条覆盖该场 key_points 的事实;不得编造 key_points 之外的具体数字。
2. 密度:每场字数 ≥ 时长秒数×4.2;全片接近目标时长。宁可多讲机制/对比/数字,不许注水。
3. 口语:像脑子清楚的老师在讲;一句 ≤35 字;每句都给观众新信息。禁止报幕句("接下来我们看")、禁止复述画面("看图中")。
4. 承接:上一场结尾留的问题,下一场第一句接住;最后一场回扣开场处境。
5. 稳定:不改场景顺序、标题、时长和视觉规划;只重写 narration(必要时补充 key_points)。

输出 JSON:
{"scenes": [{"id": "scene_0", "narration": "重写后的完整旁白", "key_points": ["..."]}]}
只输出被你改写的场景;未列出的场景保持原样。"""


def _deepen_payload(storyboard: Storyboard, audit: dict) -> str:
    lines = [
        f"主题:{storyboard.topic}",
        f"主线 spine:{storyboard.spine or '(未设定,由你提炼并贯彻)'}",
        f"贯穿示例:{storyboard.example_context or '(未设定,选一个具体到数字的例子全程使用)'}",
        "",
        "审计诊断:",
    ]
    for issue in audit["issues"][:40]:
        target = f"[{issue['scene_id']}] " if issue.get("scene_id") else ""
        lines.append(f"- {target}{issue['code']}: {issue['detail']}")
    lines.append("")
    lines.append("场景清单:")
    for scene in storyboard.scenes:
        lines.append(f"### {scene.id}《{scene.title}》 时长{round(scene.duration_estimate or 0)}秒")
        if scene.learning_goal:
            lines.append(f"学习目标:{scene.learning_goal}")
        lines.append("key_points:")
        for point in scene.key_points or []:
            lines.append(f"- {point}")
        lines.append(f"现有旁白({len(scene.narration or '')}字):{scene.narration or '(空)'}")
        lines.append("")
    return "\n".join(lines)


async def deepen_storyboard_narration(storyboard: Storyboard, target_duration: int) -> Storyboard:
    """One audit → rewrite → re-audit pass. Never raises; logs residual issues."""
    audit = audit_narration(storyboard, target_duration)
    if audit["ok"]:
        logger.info("narration audit passed: %s chars / %.1f chars-per-sec", audit["totalChars"], audit["density"])
        return storyboard

    logger.info("narration audit failed (%d issues, %.2f c/s): %s",
                len(audit["issues"]), audit["density"], [i["code"] for i in audit["issues"]])
    failing_ids = {issue["scene_id"] for issue in audit["issues"] if issue.get("scene_id")}
    try:
        raw = await chat_json(messages=[
            {"role": "system", "content": _DEEPEN_SYSTEM_PROMPT},
            {"role": "user", "content": _deepen_payload(storyboard, audit)},
        ])
    except (LLMResponseParseError, Exception) as exc:  # noqa: BLE001 - 深化失败不阻塞渲染
        logger.warning("narration deepen pass failed, keeping original: %s", exc)
        return storyboard

    by_id = {item.get("id"): item for item in raw.get("scenes", []) if isinstance(item, dict) and item.get("id")}
    changed = 0
    for scene in storyboard.scenes:
        rewrite = by_id.get(scene.id)
        if not rewrite:
            continue
        new_narration = str(rewrite.get("narration") or "").strip()
        if new_narration and new_narration != (scene.narration or "").strip():
            scene.narration = new_narration
            changed += 1
        new_points = rewrite.get("key_points")
        if isinstance(new_points, list) and new_points:
            scene.key_points = [str(p).strip() for p in new_points if str(p).strip()]
    logger.info("narration deepen rewrote %d scenes (targeted %d)", changed, len(failing_ids))

    recheck = audit_narration(storyboard, target_duration)
    if not recheck["ok"]:
        logger.info("narration residual issues after deepen: %s", [i["code"] for i in recheck["issues"]])
    else:
        logger.info("narration audit passed after deepen: %.1f chars-per-sec", recheck["density"])
    return storyboard
