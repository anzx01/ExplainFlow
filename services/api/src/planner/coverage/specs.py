import re

from src.explain.models import ExplainGraph
from ..models import (
    Scene,
    Storyboard,
    VisualBeat,
    AnimationInstruction,
    AnimationType,
    DiagramPlan,
)
from .analyzer import _diagram_kind_for_coverage_unit
from ..storyboard_gen.normalizer import (
    _clean_text,
    _clean_narration_text,
    _normalize_image_description_text,
    _planner_str_list,
    _parse_annotation_plan,
    _short_text,
)
from ..storyboard_gen.timing import (
    _estimate_scene_duration,
    _narration_from_beats,
)

def _coverage_scene_spec(unit: dict, index: int, topic: str) -> dict:
    label = _coverage_unit_label(unit) or f"关键单元 {index + 1}"
    kind = _diagram_kind_for_coverage_unit(unit)
    must_show = _planner_str_list(unit.get("must_show") or unit.get("required_labels") or unit.get("must_draw"), limit=5)
    if not must_show:
        must_show = [label]
    teaching_goal = _clean_text(unit.get("teaching_goal")) or f"讲清楚 {label} 的含义、原因和结果。"
    narration_focus = _clean_text(unit.get("narration_focus")) or teaching_goal
    short_label = _short_text(label, 22)

    if kind == "comparison":
        diagram_kind = "comparison"
        layout = "two whiteboard panels contrasting the state before and after the key change"
        beat_one_draw = f"用双栏对比呈现 {short_label} 的前后状态，并放上最短标签。"
        beat_two_draw = f"在两栏之间补箭头、差异圈选和结论下划线，让变化原因可见。"
        beat_one_narration = f"{short_label} 不能单独拎着看，不然就像只看菜单不看菜，味道全靠猜。"
        beat_two_narration = _clean_narration_text(narration_focus)
    elif kind == "tradeoff_matrix":
        diagram_kind = "tradeoff_matrix"
        layout = "2x2 whiteboard matrix showing two decision axes, four zones, and the preferred zone underlined"
        beat_one_draw = f"把 {short_label} 放进二维判断矩阵，横轴和纵轴各表达一个关键标准。"
        beat_two_draw = "圈出最值得关注的区域，并用箭头说明取舍方向。"
        beat_one_narration = f"{short_label} 需要两个维度来降噪，不然所有方案都在喊“选我”，会议很快变成菜市场。"
        beat_two_narration = _clean_narration_text(narration_focus)
    elif kind == "interaction":
        diagram_kind = "interaction"
        layout = "two or three actors/nodes with bidirectional arrows, exchanged signals, and a shared outcome callout"
        beat_one_draw = f"把 {short_label} 拆成参与对象和它们之间的相互影响。"
        beat_two_draw = "补双向箭头、信息交换标签和共同结果，让关系不是孤立节点。"
        beat_one_narration = f"{short_label} 的重点不在单个角色，而在它们怎么互相递球；球传歪了，结果也会跟着跑偏。"
        beat_two_narration = _clean_narration_text(narration_focus)
    elif kind == "goal_path":
        diagram_kind = "goal_path"
        layout = "start point, milestones, target point, and a backcasting arrow on a sparse whiteboard"
        beat_one_draw = f"把 {short_label} 画成从当前位置到目标的路径。"
        beat_two_draw = "加入里程碑和倒推箭头，说明每一步为什么服务于终点。"
        beat_one_narration = f"{short_label} 要先把终点钉住，否则行动会很勤奋，但方向可能像没开导航的出租车。"
        beat_two_narration = _clean_narration_text(narration_focus)
    elif kind == "cycle":
        diagram_kind = "cycle"
        layout = "3 to 5 node circular loop with arrows and one highlighted improvement point"
        beat_one_draw = f"把 {short_label} 做成一个闭环，而不是一次性动作。"
        beat_two_draw = "用环形箭头连接各节点，并强调下一轮会带来什么改进。"
        beat_one_narration = f"{short_label} 不是交卷就散场，而是看一眼结果，再把下一轮动作调准一点。"
        beat_two_narration = _clean_narration_text(narration_focus)
    elif kind == "formula":
        diagram_kind = "formula"
        layout = "one formula line with variable callouts and a small meaning diagram"
        beat_one_draw = f"写出 {short_label} 的核心表达，并把变量拆成短标签。"
        beat_two_draw = "用箭头把公式中的变量连接到旁边的小示意图。"
        beat_one_narration = f"{short_label} 的关键不只是记住符号，而是知道每个量对应现实中的哪一部分。"
        beat_two_narration = _clean_narration_text(narration_focus)
    elif kind == "process":
        diagram_kind = "process"
        layout = "left-to-right cause-process-result flow with arrows and a small conclusion underline"
        beat_one_draw = f"把 {short_label} 拆成原因、过程、结果三个节点。"
        beat_two_draw = "用箭头表示变化方向，并圈出最关键的转折点。"
        beat_one_narration = f"理解 {short_label} 要抓住因果链，别只盯着结论；那就像只看终点照片，不知道车是怎么开到那里的。"
        beat_two_narration = _clean_narration_text(narration_focus)
    elif kind == "summary":
        diagram_kind = "summary"
        layout = "teacher checklist or loop map summarizing the key units"
        beat_one_draw = f"把 {short_label} 做成一张总结清单或闭环图。"
        beat_two_draw = "给核心结论加下划线，并把它连回主题。"
        beat_one_narration = f"{short_label} 是收口动作，把刚才散落的零件装回工具箱，下次要用时才找得到。"
        beat_two_narration = _clean_narration_text(narration_focus)
    elif kind == "overview_map":
        diagram_kind = "overview_map"
        layout = "central topic with 3 to 5 surrounding units, arrows showing the lesson route, and one highlighted current unit"
        beat_one_draw = f"先把 {short_label} 放在中心，并展开本主题的几个核心单元。"
        beat_two_draw = "用路线箭头串起这些单元，让观众知道后面会怎样推进。"
        beat_one_narration = f"{short_label} 要先有全局地图，不然观众会像进了陌生商场，走得很努力但不知道电梯在哪。"
        beat_two_narration = _clean_narration_text(narration_focus)
    else:
        diagram_kind = "structure"
        layout = "central concept sketch with nearby short labels, arrows and a concrete example"
        beat_one_draw = f"在白板中央呈现 {short_label} 的核心对象，并贴近写短标签。"
        beat_two_draw = "补一个具体例子或局部放大，再用下划线强调结论。"
        beat_one_narration = f"{short_label} 要先放回整体里看，否则它就像桌上的一颗螺丝，重要但不知道拧在哪。"
        beat_two_narration = _clean_narration_text(narration_focus)

    return {
        "title": short_label,
        "learning_goal": teaching_goal,
        "render_strategy": "trace",
        "visual_complexity": "medium",
        "board_mode": "whiteboard",
        "hand_usage": "trace",
        "visual_style": "teacher_whiteboard",
        "diagram_plan": {
            "kind": diagram_kind,
            "layout": layout,
            "required_labels": must_show[:6],
        },
        "visual_beats": [
            {
                "draw_intent": beat_one_draw,
                "narration": beat_one_narration,
                "required_labels": must_show[:3],
                "duration_estimate": 8,
            },
            {
                "draw_intent": beat_two_draw,
                "narration": beat_two_narration,
                "required_labels": must_show[:5],
                "duration_estimate": 9,
            },
        ],
        "image_description": (
            "clean light grey-white whiteboard, rich colorful educational doodle illustration, strong readable marker outlines, short blue handwritten title, "
            f"{layout}, topic {topic}, labels {', '.join(must_show[:6])}, yellow underline for the key term, "
            "3-6 meaningful visual parts, purposeful semantic color accents, generous white space, no poster, no card, no legend box, no colored background"
        ),
        "duration_estimate": 30,
    }



def _scene_from_spec(index: int, spec: dict) -> Scene:
    beats = [
        VisualBeat(
            id=f"beat_{beat_index}",
            draw_intent=beat["draw_intent"],
            narration=beat["narration"],
            required_labels=beat.get("required_labels", []),
            duration_estimate=beat.get("duration_estimate", 6.0),
        )
        for beat_index, beat in enumerate(spec["visual_beats"])
    ]
    animations = [
        AnimationInstruction(
            type=AnimationType.WHITEBOARD_DRAW,
            duration=min(15.0, max(4.0, float(beat.duration_estimate))),
            content=beat.draw_intent,
            items=beat.required_labels or None,
        )
        for beat in beats
    ]
    if spec.get("formula"):
        animations.append(
            AnimationInstruction(
                type=AnimationType.WRITE_FORMULA,
                duration=5.0,
                content=spec["formula"],
                latex=spec["formula"],
            )
        )
    narration = _narration_from_beats(spec.get("narration", ""), beats)
    duration = _estimate_scene_duration(float(spec.get("duration_estimate", 28)), narration, beats, animations)
    diagram = spec.get("diagram_plan") or {}
    return Scene(
        id=f"scene_{index}",
        order=index,
        title=spec["title"],
        learning_goal=spec["learning_goal"],
        diagram_plan=DiagramPlan(
            kind=diagram.get("kind", "process"),
            layout=diagram.get("layout", ""),
            required_labels=diagram.get("required_labels", []),
        ),
        visual_beats=beats,
        narration=narration,
        duration_estimate=duration,
        animations=animations,
        node_ids=spec.get("node_ids", []),
        image_description=_normalize_image_description_text(spec["image_description"]),
        visual_mode=spec.get("visual_mode"),
        teaching_density=spec.get("teaching_density"),
        visual_anchor=spec.get("visual_anchor"),
        annotation_plan=_parse_annotation_plan(spec.get("annotation_plan")),
        render_strategy=spec.get("render_strategy", ""),
        visual_complexity=spec.get("visual_complexity", ""),
        board_mode=spec.get("board_mode", ""),
        hand_usage=spec.get("hand_usage", ""),
        video_style=spec.get("video_style"),
        visual_style=spec.get("visual_style", ""),
        pen_style=spec.get("pen_style"),
    )


def _replace_with_specs(storyboard: Storyboard, specs: list[dict]) -> Storyboard:
    scenes = [_scene_from_spec(index, spec) for index, spec in enumerate(specs)]
    for scene in scenes:
        if scene.image_description:
            scene.image_description = _normalize_image_description_text(scene.image_description)
    return Storyboard(
        topic=storyboard.topic,
        total_duration_estimate=round(sum(scene.duration_estimate for scene in scenes), 1),
        scenes=scenes,
        video_style=storyboard.video_style,
        pen_style=storyboard.pen_style,
    )

