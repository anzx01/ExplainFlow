from src.explain.models import ExplainGraph
from .corpus import _graph_source_corpus, _contains_terms
from .analyzer import _brief_coverage_units
from ..storyboard_gen.normalizer import _short_text, _clean_narration_text
from ..storyboard_gen.timing import _max_scene_count_for_target

def _generic_relation_story_specs(graph: ExplainGraph, target_duration: int) -> list[dict]:
    topic = _short_text(graph.topic or "主题", 20)
    desired = _max_scene_count_for_target(target_duration)
    source_corpus = _graph_source_corpus(graph)
    framework_terms = [
        "通用问题解决框架",
        "问题解决框架",
        "全局地图",
        "取舍矩阵",
        "目标路径",
        "反馈闭环",
        "閫氱敤闂瑙ｅ喅妗嗘灦",
        "闂瑙ｅ喅妗嗘灦",
        "鍏ㄥ眬鍦板浘",
        "鍙栬垗鐭╅樀",
        "鐩爣璺緞",
        "鍙嶉闂幆",
    ]
    is_problem_framework = _contains_terms(source_corpus, framework_terms)
    if _contains_terms(source_corpus, ["通用问题解决框架", "问题解决框架", "取舍矩阵", "目标路径", "反馈闭环"]):
        desired = min(5, desired)
    if is_problem_framework:
        desired = min(5, desired)
    base_specs = [
        {
            "title": "全局地图",
            "learning_goal": f"先建立 {topic} 的整体认知，知道接下来会讲哪些部分。",
            "render_strategy": "trace",
            "visual_complexity": "medium",
            "board_mode": "whiteboard",
            "hand_usage": "trace",
            "visual_style": "teacher_whiteboard",
            "diagram_plan": {"kind": "overview_map", "layout": "central topic with surrounding units and route arrows", "required_labels": ["主题", "现象", "结构", "过程", "结果"]},
            "visual_beats": [
                {
                    "draw_intent": "在中心写主题，周围展开几个核心单元。",
                    "narration": f"解决问题先别急着撸袖子，得先摊开一张全局地图；不然很可能跑得满头汗，却在错误楼层找门牌。",
                    "required_labels": ["主题", "全局地图"],
                    "duration_estimate": 7,
                },
                {
                    "draw_intent": "用箭头串起后续讲解路线。",
                    "narration": "地图上至少要有目标、约束、关键对象和顺序，后面的每一步才知道自己是在给谁打工。",
                    "required_labels": ["对象", "边界", "顺序"],
                    "duration_estimate": 8,
                },
            ],
            "image_description": f"clean light grey-white whiteboard, rich colorful playful hand-drawn map for {topic}: central messy knot labeled 问题, compass icon, 4 route signs for 全局/结构/取舍/目标, red warning mark, green route arrow, blue route lines, yellow emphasis marks, generous white space, no poster no card no paper panel",
            "duration_estimate": 24,
        },
        {
            "title": "结构拆解",
            "learning_goal": "把复杂对象拆成组成部分，说明整体和局部如何连接。",
            "render_strategy": "trace",
            "visual_complexity": "medium",
            "board_mode": "whiteboard",
            "hand_usage": "trace",
            "visual_style": "teacher_whiteboard",
            "diagram_plan": {"kind": "structure", "layout": "main object broken into parts with nearby labels and a zoom callout", "required_labels": ["整体", "局部", "关键部分"]},
            "visual_beats": [
                {
                    "draw_intent": "画一个主体框架，并拆出 3 个局部。",
                    "narration": "结构拆解像把一台卡住的机器拆开看，别对着整机许愿，先找到哪个齿轮真在咬住结果。",
                    "required_labels": ["整体", "局部"],
                    "duration_estimate": 7,
                },
                {
                    "draw_intent": "圈出关键局部，并补一个放大框。",
                    "narration": "真正要紧的不是零件数量，而是谁连着谁、谁一动会带着一串人跟着动。",
                    "required_labels": ["关键部分", "连接"],
                    "duration_estimate": 8,
                },
            ],
            "image_description": "clean teacher whiteboard colorful playful structure diagram, big tangled ball split into 3 gears/blocks, magnifying glass callout, tiny question mark marks, blue/red/green arrows and nearby short labels, generous white space, no poster layout no paper panel",
            "duration_estimate": 24,
        },
        {
            "title": "状态对比",
            "learning_goal": "用对比让观众看见变化前后或方案 A/B 的差异。",
            "render_strategy": "trace",
            "visual_complexity": "medium",
            "board_mode": "whiteboard",
            "hand_usage": "trace",
            "visual_style": "teacher_whiteboard",
            "diagram_plan": {"kind": "comparison", "layout": "two-panel comparison with difference circles and an arrow between panels", "required_labels": ["A", "B", "差异", "结果"]},
            "visual_beats": [
                {
                    "draw_intent": "画左右两个面板，分别标出 A 和 B。",
                    "narration": "方案一多，大家都会举手说自己很香。对比图先把它们放到同一张桌上，别让嗓门替代判断。",
                    "required_labels": ["A", "B"],
                    "duration_estimate": 7,
                },
                {
                    "draw_intent": "圈出差异，并用箭头指向结果。",
                    "narration": "差异必须连到结果，才知道这是关键区别，还是包装纸上印得比较热闹。",
                    "required_labels": ["差异", "结果"],
                    "duration_estimate": 8,
                },
            ],
            "image_description": "two-panel whiteboard comparison with lively voting marks, option A and B as simple objects on a scale, circled differences, arrow to outcome, sparse handwritten labels, no poster no card",
            "duration_estimate": 24,
        },
        {
            "title": "优先取舍",
            "learning_goal": "用二维矩阵说明优先级和取舍规则。",
            "render_strategy": "trace",
            "visual_complexity": "medium",
            "board_mode": "whiteboard",
            "hand_usage": "trace",
            "visual_style": "teacher_whiteboard",
            "diagram_plan": {"kind": "tradeoff_matrix", "layout": "2x2 matrix with two axes and a highlighted preferred quadrant", "required_labels": ["重要", "紧急", "优先", "取舍"]},
            "visual_beats": [
                {
                    "draw_intent": "画 2x2 矩阵和两个判断轴。",
                    "narration": "取舍矩阵像给方案排队验票：一个维度看收益，一个维度看代价，谁插队一眼就露馅。",
                    "required_labels": ["重要", "紧急"],
                    "duration_estimate": 7,
                },
                {
                    "draw_intent": "圈出优先象限，并用箭头说明移动方向。",
                    "narration": "优先级不是把清单全吃完，而是先夹那块最能顶饱的菜；资源有限，就别假装自己有八只手。",
                    "required_labels": ["优先", "取舍"],
                    "duration_estimate": 8,
                },
            ],
            "image_description": "2x2 whiteboard priority matrix with four funny方案 tokens, one green winner badge, one red avoid zone, tiny crowd speech marks saying 选我, yellow underline on priority, large negative space no panel",
            "duration_estimate": 24,
        },
        {
            "title": "目标路径",
            "learning_goal": "把目标和行动路线连起来，避免只停留在愿望。",
            "render_strategy": "trace",
            "visual_complexity": "medium",
            "board_mode": "whiteboard",
            "hand_usage": "trace",
            "visual_style": "teacher_whiteboard",
            "diagram_plan": {"kind": "goal_path", "layout": "start point, milestones, target point, and a backcasting arrow", "required_labels": ["现在", "里程碑", "目标", "倒推"]},
            "visual_beats": [
                {
                    "draw_intent": "画从现在到目标的路径，并加入里程碑。",
                    "narration": "目标路径把愿望变成路线图。只喊我要到终点，听起来很燃，但出租车司机会问：到底往哪拐？",
                    "required_labels": ["现在", "目标"],
                    "duration_estimate": 7,
                },
                {
                    "draw_intent": "从目标反向画倒推箭头，标出下一步。",
                    "narration": "从终点倒推，会逼我们把里程碑说清楚；下一步不再是玄学，而是导航上的第一段路。",
                    "required_labels": ["倒推", "下一步"],
                    "duration_estimate": 8,
                },
            ],
            "image_description": "clean whiteboard colorful goal path as a winding road, current point as small confused dot, milestones as colored flags, target as star, backcasting arrow, tiny taxi/navigation icon, short nearby labels, generous white space, no card",
            "duration_estimate": 24,
        },
        {
            "title": "反馈闭环",
            "learning_goal": "说明结果会回到下一轮行动中，形成持续改进。",
            "render_strategy": "trace",
            "visual_complexity": "medium",
            "board_mode": "whiteboard",
            "hand_usage": "trace",
            "visual_style": "teacher_whiteboard",
            "diagram_plan": {"kind": "cycle", "layout": "circular feedback loop with plan, act, check, adjust nodes", "required_labels": ["计划", "执行", "检查", "调整"]},
            "visual_beats": [
                {
                    "draw_intent": "画一个四节点闭环。",
                    "narration": "反馈闭环的意思是，做完别马上散会。结果像小票，别揉了扔，它能告诉你下一轮哪里该调。",
                    "required_labels": ["计划", "执行", "检查", "调整"],
                    "duration_estimate": 8,
                },
                {
                    "draw_intent": "给闭环加循环箭头和改进下划线。",
                    "narration": "厉害的框架不靠一次神操作，而是每轮都校准一点点；像调收音机，噪声少一点，信号就清楚一点。",
                    "required_labels": ["反馈", "改进"],
                    "duration_estimate": 7,
                },
            ],
            "image_description": "whiteboard circular feedback loop with receipt/check ticket metaphor, plan act check adjust nodes, loop arrows, small tuning dial icon, yellow underline on improvement, no paper panel",
            "duration_estimate": 24,
        },
        {
            "title": "总结框架",
            "learning_goal": "把全片内容收束成可复述的框架。",
            "render_strategy": "trace",
            "visual_complexity": "simple",
            "board_mode": "whiteboard",
            "hand_usage": "trace",
            "visual_style": "teacher_whiteboard",
            "diagram_plan": {"kind": "summary", "layout": "short teacher checklist connected back to the overview map", "required_labels": ["看全局", "拆结构", "做对比", "定优先", "走闭环"]},
            "visual_beats": [
                {
                    "draw_intent": "写一列短清单，并用勾选符号逐项出现。",
                    "narration": "最后把工具装回工具箱：看全局，拆结构和过程，做取舍，按目标倒推，再用反馈修正。下次遇到乱麻，就不用徒手薅了。",
                    "required_labels": ["看全局", "拆结构", "做对比", "定优先", "走闭环"],
                    "duration_estimate": 9,
                }
            ],
            "image_description": "clean teacher whiteboard colorful summary map with green ticks, a small loop arrow, 3-5 tiny visual anchors, yellow emphasis underline, short labels only, no long paragraphs",
            "duration_estimate": 20,
        },
    ]
    if _contains_terms(source_corpus, ["通用问题解决框架", "问题解决框架", "取舍矩阵", "目标路径", "反馈闭环"]):
        priority_titles = {"全局地图", "结构拆解", "优先取舍", "目标路径", "反馈闭环"}
        selected = [spec for spec in base_specs if spec["title"] in priority_titles][:desired]
        if is_problem_framework and len(selected) < desired:
            return [base_specs[index] for index in [0, 1, 3, 4, 5]][:desired]
        return selected
    return base_specs[:desired]

