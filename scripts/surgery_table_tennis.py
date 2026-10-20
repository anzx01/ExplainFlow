"""乒乓球分镜手术:删 coverage 垃圾重复场 + 全场动效注入。

病灶(2026-10-20 LLM 初稿):scene_6「乒乓球入门:站位与握拍」是 coverage 兜底场
——描述/渲染元素是指令模板原文,内容与 scene_0 完全撞车,且插在收尾场之前。
其余 7 场 how-to 结构和描述质量合格,不动。

动效按画面内容手写(motion-inject 词汇:flow_arrows/pulse/cycle_ring)。
"""
import json

PATH = "outputs/gen-storyboard-cache.json"
DELETE = {"scene_6"}

MOTIONS = {
    "scene_0": {  # 站位:膝盖弹簧脉动
        "elements": [{"type": "pulse", "x": 0.26, "y": 0.60, "size": 0.07, "cycleSeconds": 2.0, "color": "#E67E22"}],
    },
    "scene_1": {  # 发力链:力量从脚沿箭头链流向手
        "elements": [{"type": "flow_arrows", "from": [0.28, 0.72], "to": [0.56, 0.38], "size": 0.06, "speed": 0.6, "color": "#C0392B"}],
    },
    "scene_2": {  # 击球时机:球沿抛物线飞行
        "elements": [
            {"type": "flow_arrows", "from": [0.34, 0.56], "to": [0.70, 0.28], "size": 0.05, "speed": 0.5, "color": "#2E86C1"},
            {"type": "pulse", "x": 0.52, "y": 0.30, "size": 0.05, "cycleSeconds": 1.8, "color": "#E67E22"},
        ],
    },
    "scene_3": {  # 平击发球:过网弧线方向
        "elements": [{"type": "flow_arrows", "from": [0.42, 0.34], "to": [0.68, 0.44], "size": 0.05, "speed": 0.5, "color": "#2E9E4F"}],
    },
    "scene_4": {  # 下旋发球:向前下方摩擦
        "elements": [{"type": "flow_arrows", "from": [0.56, 0.30], "to": [0.46, 0.48], "size": 0.05, "speed": 0.7, "color": "#8E44AD"}],
    },
    "scene_5": {  # 连续对攻:循环环叠在四节点环路上
        "elements": [{"type": "cycle_ring", "x": 0.42, "y": 0.44, "size": 0.24, "cycleSeconds": 4.0}],
    },
    "scene_7": {  # 收尾:中央正确人形呼吸脉动
        "elements": [{"type": "pulse", "x": 0.5, "y": 0.38, "size": 0.08, "cycleSeconds": 3.0, "color": "#2E9E4F"}],
    },
}


def main() -> None:
    sb = json.load(open(PATH, encoding="utf-8"))
    kept = [s for s in sb["scenes"] if s["id"] not in DELETE]
    assert len(kept) == len(sb["scenes"]) - len(DELETE), "unexpected scene ids"
    for order, s in enumerate(kept):
        s["order"] = order
        motion = MOTIONS.get(s["id"])
        assert motion, f"no motion designed for {s['id']}"
        s["motion"] = motion
    sb["scenes"] = kept
    sb["total_duration_estimate"] = round(sum(float(s.get("duration_estimate") or 0) for s in kept), 1)
    json.dump(sb, open(PATH, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"surgery+motion done: {len(kept)} scenes, est {sb['total_duration_estimate']}s")
    for s in kept:
        kinds = [e["type"] for e in s["motion"]["elements"]]
        print(f"  {s['order']}. {s['id']} [{s['title']}] motion={kinds}")


if __name__ == "__main__":
    main()
