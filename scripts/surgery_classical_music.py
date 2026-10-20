"""分镜手术:如何欣赏古典音乐。

病灶(2026-10-20 LLM 初稿):
- scene_8/scene_9 是 coverage 兜底垃圾(重复主题+指令泄漏话术,renderElements 是模板原文);
- scene_0 是很好的收束场却被排在开头(标题不含"总结"关键词,审计正则漏判);
- 8/10 场的 image_description 是图表话术(漏斗/时间轴/等号/面板),Flux 会照字面画图表。

术式:删 scene_8/9;scene_0 移到末尾当收束;重排为
hook → 三层框架 → 感官层 → 张力 → 结构层 → 实操 → 心态 → 收尾;
全部 image_description 按物件清单公式重写(具体物件+颜色+粗箭头,禁图表词);
renderElements 字幕与标签同步改写(它们是画在视频里的可见文字)。
"""
import json

PATH = "outputs/gen-storyboard-cache.json"
STYLE = ("Bold editorial hand-drawn explainer illustration, thick imperfect black marker outlines, "
         "warm off-white surface, generous blank margins, text-free artwork.")

DESCS = {
    "scene_1": (
        "on the left a person wearing big over-ear headphones with a tangled scribbly knot of grey sound "
        "waves around their head and one big red question mark floating above; on the right the same person "
        "sitting relaxed with closed eyes and a smile, one clean bright blue path of round glowing musical "
        "notes flowing gently into their ear. " + STYLE
    ),
    "scene_2": (
        "one large three-layer layer cake in the center: the bottom layer wide and warm yellow, the middle "
        "layer coral pink and narrower, the top layer small and sky blue, one big red cherry on top; the "
        "three layers clearly stacked with thick black outlines, a few small yellow stars sprinkled around "
        "the top layer. " + STYLE
    ),
    "scene_3": (
        "a heavy dark brown wooden door in the center shaking, four bold round impact dents on its surface: "
        "three short dents in a row and one much bigger long dent beside them, curved grey sound-wave ripples "
        "spreading from the door to both sides. " + STYLE
    ),
    "scene_5": (
        "a big coiled grey metal spring stretched tight between a solid dark wall on the left and a heavy "
        "dark blue ball on the right, the ball pulled far from the wall so the spring is long and thin, the "
        "ball just about to snap back toward the wall. " + STYLE
    ),
    "scene_4": (
        "three small story moments in a row connected by two chunky black arrows: first a bold red race car "
        "bursting forward with speed lines and next to it a gentle blue swan singing with a few round notes; "
        "then the two caught in a playful grey scribble tangle cloud with small yellow star bursts; finally "
        "the red car and the blue swan traveling together along a quiet road toward a cozy little house with "
        "warm yellow windows. " + STYLE
    ),
    "scene_6": (
        "the same little orange bird appearing three times from left to right connected by two chunky black "
        "arrows: first sitting big and clear on a bare branch in full view; second half hidden behind big "
        "green leaves with only its tail and one wing showing; third back on the branch in full view singing, "
        "a few round blue notes floating above its head. " + STYLE
    ),
    "scene_7": (
        "a circular sandy path in the center with three friendly stops along it: a big pink ear, a glowing "
        "yellow light bulb, and an open blue book, bold green curved arrows following the path from the ear "
        "to the bulb to the book and looping back to the ear. " + STYLE
    ),
    "scene_0": (
        "a cozy evening listening scene: a person relaxing in a big coral armchair under warm yellow "
        "lamplight, eyes closed with a smile, wearing headphones; beside the chair an old brown gramophone "
        "with a large horn, a winding path of colorful round musical notes floating from the horn across the "
        "room into the person's ears. " + STYLE
    ),
}

# renderElements 字幕是画进视频的手写小标题,必须跟着新比喻走(按场景内顺序)。
ELEMENT_SUBTITLES = {
    "scene_1": ["左侧人物与杂乱音团逐笔出现", "右侧同一位听众与清晰的音符小路出现"],
    "scene_2": ["三层蛋糕逐层画出,底层最宽", "中层与顶层依次出现,颜色不同"],
    "scene_3": ["一扇木门与四个敲门印出现", "声波涟漪向两侧扩散出现"],
    "scene_5": ["拉紧的弹簧与重球出现", "弹簧回弹与落地星星出现"],
    "scene_4": ["红色赛车与蓝色天鹅并排出现", "中间打架的乱线团与回家的小路出现"],
    "scene_6": ["枝头上的小鸟清晰出现", "半藏的小鸟与回归的小鸟出现"],
    "scene_7": ["耳朵、灯泡和书三样东西出现", "绿色循环小路把它们连成圈"],
    "scene_0": ["沙发听众与留声机出现", "彩色音符小路飘进耳朵出现"],
}

LABEL_OVERRIDES = {
    "scene_7": ["乐理是工具", "循环上升", "边听边学"],
}

KEEP_ORDER = ["scene_1", "scene_2", "scene_3", "scene_5", "scene_4", "scene_6", "scene_7", "scene_0"]
DELETE = {"scene_8", "scene_9"}


def main() -> None:
    sb = json.load(open(PATH, encoding="utf-8"))
    by_id = {s["id"]: s for s in sb["scenes"]}

    for sid in DELETE:
        by_id.pop(sid, None)
    missing = [sid for sid in KEEP_ORDER if sid not in by_id]
    assert not missing, f"missing scenes: {missing}"

    scenes = []
    for new_order, sid in enumerate(KEEP_ORDER):
        s = by_id[sid]
        s["order"] = new_order
        s["image_description"] = DESCS[sid]
        elements = s.get("renderElements") or []
        subs = ELEMENT_SUBTITLES[sid]
        assert len(elements) >= len(subs), f"{sid}: {len(elements)} elements < {len(subs)} subtitles"
        for el, sub in zip(elements, subs):
            el["subtitle"] = sub
        if sid in LABEL_OVERRIDES:
            plan = s.get("annotation_plan") or []
            labels = LABEL_OVERRIDES[sid]
            assert len(plan) >= len(labels), f"{sid}: {len(plan)} annotations < {len(labels)} labels"
            for item, label in zip(plan, labels):
                item["label"] = label
        scenes.append(s)

    sb["scenes"] = scenes
    sb["total_duration_estimate"] = round(sum(float(s.get("duration_estimate") or 0) for s in scenes), 1)
    json.dump(sb, open(PATH, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"surgery done: {len(scenes)} scenes, est {sb['total_duration_estimate']}s")
    for s in scenes:
        print(f"  {s['order']}. {s['id']} [{s['title']}]")


if __name__ == "__main__":
    main()
