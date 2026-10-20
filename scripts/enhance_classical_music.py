"""古典音乐片增强:动效注入 + 旁白深化重写。

诊断结论(2026-10-20,用户反馈"效果不好"):
- 该片没有动画层——motion-inject 只注入带 scene.motion 规格的场景,
  之前的发动机/EV 片动效都来自手术时手工写的 motion 规格,新片没有;
- 旁白密度 3.4-3.9 字/秒,低于 4.2 目标线(REUSE_SB 跳过了 planner 的深化重写)。

本脚本:①给 8 场按画面内容手写 motion 规格(flow_arrows/pulse/cycle_ring);
②调用 planner 的 deepen_storyboard_narration 做一次 LLM 密度深化。
"""
import asyncio
import json
import sys

sys.path.insert(0, "services/api")

from src.planner.models import Storyboard
from src.planner.storyboard_gen.narration_quality import deepen_storyboard_narration

PATH = "outputs/gen-storyboard-cache.json"

# 动效词汇(flow_arrows=沿线流动箭头, pulse=扩散波纹, cycle_ring=四段循环环)
# 坐标为 0-1 归一化;默认 40% 场景进度后出场,避开手绘阶段。
MOTIONS = {
    "scene_1": {  # 右侧听众:音符小路流动入耳
        "elements": [{"type": "flow_arrows", "from": [0.70, 0.30], "to": [0.60, 0.36], "size": 0.05, "speed": 0.35, "color": "#2E86C1"}],
    },
    "scene_2": {  # 蛋糕顶层(最难的语言境层)心跳波纹
        "elements": [{"type": "pulse", "x": 0.5, "y": 0.26, "size": 0.06, "cycleSeconds": 2.6, "color": "#E67E22"}],
    },
    "scene_3": {  # 敲门:红色强拍波纹,短周期模拟"短短短长"
        "elements": [{"type": "pulse", "x": 0.5, "y": 0.40, "size": 0.09, "cycleSeconds": 1.4, "color": "#C0392B"}],
    },
    "scene_5": {  # 弹簧蓄力:重球脉动 + 回弹方向流动箭头
        "elements": [
            {"type": "pulse", "x": 0.63, "y": 0.38, "size": 0.10, "cycleSeconds": 2.0, "color": "#E67E22"},
            {"type": "flow_arrows", "from": [0.56, 0.58], "to": [0.40, 0.58], "size": 0.05, "speed": 0.8, "color": "#2E9E4F"},
        ],
    },
    "scene_4": {  # 三幕故事:主线方向的推进箭头
        "elements": [{"type": "flow_arrows", "from": [0.30, 0.70], "to": [0.70, 0.70], "size": 0.05, "speed": 0.5, "color": "#2E86C1"}],
    },
    "scene_6": {  # 主题三现:旋律在三次出现之间旅行
        "elements": [{"type": "flow_arrows", "from": [0.30, 0.52], "to": [0.68, 0.52], "size": 0.05, "speed": 0.4, "color": "#E67E22"}],
    },
    "scene_7": {  # 听-问-查循环:循环环正好叠在画面圆路上
        "elements": [{"type": "cycle_ring", "x": 0.5, "y": 0.40, "size": 0.26, "cycleSeconds": 5.0}],
    },
    "scene_0": {  # 收尾:留声机音符飘向听众
        "elements": [{"type": "flow_arrows", "from": [0.63, 0.40], "to": [0.47, 0.36], "size": 0.05, "speed": 0.3, "color": "#8E44AD"}],
    },
}


def main() -> None:
    sb = json.load(open(PATH, encoding="utf-8"))
    for s in sb["scenes"]:
        motion = MOTIONS.get(s["id"])
        if motion:
            s["motion"] = motion
    json.dump(sb, open(PATH, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"motion injected into {len(MOTIONS)} scenes")

    storyboard = Storyboard.model_validate(sb)
    target = int(round(sb.get("total_duration_estimate") or 114))
    before = {s.id: len(s.narration or "") for s in storyboard.scenes}
    storyboard = asyncio.run(deepen_storyboard_narration(storyboard, target))
    after = {s.id: len(s.narration or "") for s in storyboard.scenes}
    for sid in before:
        print(f"  {sid}: {before[sid]} -> {after[sid]} chars")
    out = json.loads(storyboard.model_dump_json())
    json.dump(out, open(PATH, "w", encoding="utf-8"), ensure_ascii=False)
    print("narration deepened and saved")


if __name__ == "__main__":
    main()
