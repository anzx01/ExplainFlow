import json
import logging
import re

from src.core.llm import chat_json, check_llm_connection
from .models import (
    ConceptEdge,
    ConceptNode,
    EnhancedTeachingBrief,
    ExplainGraph,
    GenerateGraphRequest,
    NodeType,
    TeachingBriefSceneOutline,
)

logger = logging.getLogger(__name__)

DEFAULT_AUDIENCE = "有高中/大学基础理科知识的初学者"

ENHANCE_SYSTEM_PROMPT = """你是一个教学视频 production brief 设计师，任务是把用户很短、很口语化的主题，改写成结构化教学 brief。

核心原则：
1. 用户 prompt 只是意图，不是完整脚本；你要主动补全教学必需的因果链、对比、过程和可视化方案。
2. 内容 brief 与视觉风格分离：这里不写模板，不写组件，只写主题、受众、目标、结构、必须包含内容和可画的画面。
3. 每个关键点必须按“现象 -> 原因 -> 结果 -> 类比/总结”展开，避免只罗列名词定义。
4. 每个核心概念必须能被画出来：结构图、状态对比图、箭头、过程变化、局部放大、截面图优先；少用 bullet list。
5. 如果用户提供参考材料，优先依据参考材料；否则用通用领域知识生成准确、初学者友好的讲解方案。
6. 输出要像给视频团队的 production brief：具体、可画、可同步旁白，不要泛泛描述。

主题类型参考：
- 器件原理：结构 -> 状态对比 -> 物理机制 -> 电路作用 -> 局限/改进
- 工程结构：整体结构 -> 局部放大 -> 受力/电场/流动路径 -> 对比旧方案
- 算法流程：目标 -> 当前状态 -> 方向/更新规则 -> 迭代变化 -> 收敛
- 数学推导：问题 -> 变量 -> 公式含义 -> 推导步骤 -> 直觉解释
- 物理机制：现象 -> 微观原因 -> 宏观结果 -> 实验/类比

如果主题涉及 MOS、MOSFET、晶体管、FinFET，必须包含：
- MOS Off/On 双图对比：未加栅压无反型沟道、无源漏电流；V_G > V_th 后形成电子沟道。
- 栅极电压使 MOS 电容另一端的衬底表面感应电荷，最终形成反型电子通道。
- V_DS 加在源漏之间后，通道导通并产生电流，MOS 像电压控制的开关。
- 尺寸缩小时沟道长度变短，短沟道效应会削弱栅极控制并导致器件失效风险。
- FinFET 使用三维 fin，栅极从三面包住沟道，增强栅控。
- FinFET 截面中有效沟道宽度 W_eff = 2H_fin + W_fin，三面被栅极包裹的表面都能感应电荷。

如果主题涉及梯度下降，必须包含：
- 损失曲线或损失地形、当前位置、梯度方向、学习率步长、参数更新、迭代收敛。

只输出 JSON，不要 Markdown。结构：
{
  "original_prompt": "用户原始输入",
  "audience_level": "默认：有高中/大学基础理科知识的初学者",
  "topic_type": "器件原理|算法流程|数学推导|物理机制|工程结构|对比概念|technical_explanation",
  "learning_objectives": ["3-6 个学习目标"],
  "core_explanation_chain": ["按因果顺序展开的讲解链"],
  "must_include_points": ["必须讲到的关键事实"],
  "visual_metaphors": ["可视化类比或图形表达"],
  "recommended_scene_outline": [
    {
      "title": "场景标题",
      "learning_goal": "该场景要解决的理解问题",
      "diagram_plan": "具体画面：布局、图形、箭头、标签、局部放大",
      "must_draw": ["必须画出的元素"],
      "narration_focus": "旁白应跟随哪些绘制动作"
    }
  ],
  "common_misconceptions": ["容易误解的点"]
}"""

SYSTEM_PROMPT = """你是通用技术教学视频的 Explain Graph 规划专家。你会收到用户原始 prompt、参考材料和已经增强过的教学 brief。

你的任务：
1. 不要只提取关键词，要把 enhanced brief 中的学习目标、因果链、必须包含内容转成教学图谱。
2. 节点要服务于“可讲、可画、可同步动画”的视频结构：状态对比、过程变化、结构局部、公式含义、结论。
3. 对复杂概念，优先创建 process / example / formula 节点，而不是一堆抽象 concept。
4. 不得遗漏 enhanced brief 的 must_include_points；如果用户原 prompt 太短，也要按 brief 补齐教学必要内容。
5. teach_order 必须是观众理解的顺序，从直观现象到机制，再到结果和总结。

输出 JSON，严格遵守：
{
  "topic": "主题名称",
  "summary": "面向初学者的一句话总结",
  "nodes": [
    {
      "id": "node_0",
      "label": "简短显示名称",
      "node_type": "concept|formula|example|conclusion|process",
      "description": "一句话说明该节点，并体现它在讲解链中的作用",
      "latex": "公式节点可填 LaTeX，否则 null",
      "teach_order": 0
    }
  ],
  "edges": [
    {"source": "node_0", "target": "node_1", "relation": "中文关系描述"}
  ],
  "key_insights": ["3-8 条核心洞察，必须覆盖 brief 的关键事实"]
}"""

SEMICONDUCTOR_TERMS = [
    "mos",
    "mosfet",
    "finfet",
    "晶体管",
    "场效应管",
    "栅极",
    "源极",
    "漏极",
    "沟道",
]

GRADIENT_TERMS = ["gradient", "descent", "梯度下降", "学习率", "损失函数", "loss"]

SEMICONDUCTOR_OBJECTIVES = [
    "看懂 MOS 晶体管的栅极、源极、漏极、衬底和沟道分别起什么作用。",
    "理解 MOS 的 Off/On 状态差异：无栅压时没有反型沟道，V_G > V_th 后形成电子通道。",
    "理解 V_DS 如何在已经形成的沟道中驱动源漏电流，把 MOS 看成电压控制的开关。",
    "理解尺寸缩小时短沟道效应为什么会削弱平面 MOS 的栅控能力。",
    "理解 FinFET 为什么把沟道做成立体 fin，并让栅极从三面包住沟道。",
    "通过截面图理解 W_eff = 2H_fin + W_fin 以及三面感应电荷的来源。",
]

SEMICONDUCTOR_CHAIN = [
    "先画平面 MOS 的基本结构：源极、漏极、栅极、氧化层、衬底和原本未导通的沟道区域。",
    "对比 Off 状态：栅压不足时，衬底表面没有形成连续电子通道，源极和漏极被隔开。",
    "逐步增加栅压：当 V_G > V_th，栅极电场通过氧化层吸引/感应衬底表面电荷，形成反型电子通道。",
    "再加 V_DS：源漏之间的电压沿通道推动载流子移动，出现漏电流，器件表现为电压控制开关。",
    "缩短沟道长度：源漏电场更容易影响沟道，短沟道效应削弱栅极控制，平面结构开始吃力。",
    "引入 FinFET：把沟道做成三维鳍片，栅极从三面包住它，增强对沟道电荷的控制。",
    "用截面图总结：三面都可形成受控表面，等效宽度 W_eff = 2H_fin + W_fin。",
]

SEMICONDUCTOR_POINTS = [
    "MOS Off 状态：V_G 未超过阈值电压，源漏之间没有连续反型沟道。",
    "MOS On 状态：V_G > V_th 后，衬底表面感应出电子并形成反型沟道。",
    "只有在通道形成后，V_DS 才能驱动源漏电流流过沟道。",
    "MOS 晶体管可以类比为一个由栅极电压控制的开关。",
    "沟道长度缩短会带来短沟道效应，使栅极对沟道的控制变弱。",
    "FinFET 的 gate 从三面包住 fin/channel，比平面栅极更强地控制沟道。",
    "FinFET 截面中有效沟道宽度为 W_eff = 2H_fin + W_fin。",
]

SEMICONDUCTOR_SCENES = [
    {
        "title": "MOS 结构先搭起来",
        "learning_goal": "让观众知道源、漏、栅、氧化层、衬底和沟道的位置关系。",
        "diagram_plan": "Left-to-right labeled planar MOS cross-section, source and drain blocks on substrate, thin oxide, gate above channel, empty channel region highlighted.",
        "must_draw": ["Source", "Drain", "Gate", "Oxide", "Substrate", "Channel region"],
        "narration_focus": "先画器件剖面，再指出栅极隔着氧化层控制衬底表面。",
    },
    {
        "title": "Off/On 两种状态",
        "learning_goal": "用双图对比解释为什么阈值电压是导通分界线。",
        "diagram_plan": "Two-panel comparison: OFF panel with no channel and crossed current arrow; ON panel with V_G > V_th, electron channel drawn between source and drain.",
        "must_draw": ["OFF: V_G < V_th", "ON: V_G > V_th", "No channel", "Electron channel"],
        "narration_focus": "边画边讲无沟道到形成连续电子沟道的变化。",
    },
    {
        "title": "电流像水流一样被打开",
        "learning_goal": "说明 V_DS 只有在沟道形成后才能推动源漏电流。",
        "diagram_plan": "MOS ON diagram with V_DS battery between drain and source, arrows moving through channel, switch analogy icon.",
        "must_draw": ["V_DS", "I_D arrows", "Voltage-controlled switch"],
        "narration_focus": "先画通道，再画源漏电压和电流箭头，最后总结成开关。",
    },
    {
        "title": "尺寸缩小后的短沟道效应",
        "learning_goal": "解释为什么平面 MOS 缩小后栅极控制会变差。",
        "diagram_plan": "Long-channel versus short-channel comparison, source/drain fields intrude into channel, leakage/failed control warning arrow.",
        "must_draw": ["Long channel", "Short channel", "Source/drain field intrusion", "Short-channel effect"],
        "narration_focus": "对比长沟道和短沟道，强调源漏电场抢走控制权。",
    },
    {
        "title": "FinFET 的三面包围",
        "learning_goal": "看懂 FinFET 为什么把沟道竖起来并用栅极包住。",
        "diagram_plan": "Simple 3D whiteboard sketch of a fin channel standing up, source and drain at two ends, gate wrapping over top and two sidewalls, control arrows on three sides.",
        "must_draw": ["Fin channel", "Source", "Drain", "Gate wraps three sides", "Three-side control arrows"],
        "narration_focus": "逐笔画出 fin，再画栅极像夹子一样从三面包住沟道。",
    },
    {
        "title": "截面里的有效宽度",
        "learning_goal": "用截面图解释 W_eff = 2H_fin + W_fin 和三面感应电荷。",
        "diagram_plan": "FinFET cross-section: U-shaped gate around fin, labels H_fin on two sidewalls and W_fin on top, electrons induced on three surfaces, formula W_eff = 2H_fin + W_fin.",
        "must_draw": ["U-shaped gate", "H_fin", "W_fin", "Induced charges on three surfaces", "W_eff = 2H_fin + W_fin"],
        "narration_focus": "边画三条受控表面边写公式，说明有效宽度来自三部分相加。",
    },
]

GRADIENT_OBJECTIVES = [
    "把损失函数理解成一条曲线或地形，高低表示模型错误大小。",
    "看懂当前位置、梯度方向和负梯度更新方向的关系。",
    "理解学习率决定每一步走多远，过大或过小都会影响收敛。",
    "理解参数经过多次迭代逐步接近较低损失区域。",
]

GRADIENT_CHAIN = [
    "先画损失曲线，说明纵轴是 loss，横轴是参数 theta。",
    "标出当前位置，画出斜率/梯度方向，解释梯度指向 loss 增大的方向。",
    "沿负梯度方向走一步，步长由学习率控制。",
    "重复更新，点沿曲线逐渐接近最低点。",
    "总结学习率太大可能震荡，太小则收敛很慢。",
]

GRADIENT_POINTS = [
    "梯度下降的目标是让损失函数变小。",
    "梯度方向指向损失增大的方向，更新时沿负梯度方向移动。",
    "学习率控制每次参数更新的步长。",
    "多次迭代后，参数通常会逐步接近低损失区域。",
]


def _clean(value: object) -> str:
    text = "" if value is None else str(value)
    text = re.sub(r"\x1b\[[0-9;]*m", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _as_str_list(value: object, limit: int | None = None) -> list[str]:
    if isinstance(value, list):
        items = [_clean(item) for item in value]
    elif isinstance(value, str):
        items = [_clean(part) for part in re.split(r"[\n；;]+", value)]
    else:
        items = []
    items = [item for item in items if item]
    return items[:limit] if limit else items


def _norm(value: str) -> str:
    return re.sub(r"\s+", "", value).lower()


def _append_unique(items: list[str], additions: list[str], limit: int | None = None) -> list[str]:
    result = list(items)
    seen = {_norm(item) for item in result}
    for addition in additions:
        text = _clean(addition)
        key = _norm(text)
        if text and key not in seen:
            result.append(text)
            seen.add(key)
        if limit and len(result) >= limit:
            break
    return result


def _contains_any_text(text: str, terms: list[str]) -> bool:
    lowered = text.lower()
    return any(term.lower() in lowered for term in terms)


def _request_blob(req: GenerateGraphRequest) -> str:
    return f"{req.prompt}\n{req.markdown or ''}"


def _is_semiconductor_topic(text: str) -> bool:
    return _contains_any_text(text, SEMICONDUCTOR_TERMS)


def _is_gradient_topic(text: str) -> bool:
    return _contains_any_text(text, GRADIENT_TERMS)


def _outline_from_raw(value: object) -> list[TeachingBriefSceneOutline]:
    outlines: list[TeachingBriefSceneOutline] = []
    if not isinstance(value, list):
        return outlines
    for index, item in enumerate(value):
        if isinstance(item, dict):
            try:
                outlines.append(
                    TeachingBriefSceneOutline(
                        title=_clean(item.get("title")) or f"场景 {index + 1}",
                        learning_goal=_clean(item.get("learning_goal")) or _clean(item.get("goal")) or "解释该步骤的核心概念",
                        diagram_plan=_clean(item.get("diagram_plan")) or _clean(item.get("visual_plan")) or "whiteboard process diagram",
                        must_draw=_as_str_list(item.get("must_draw") or item.get("required_visuals")),
                        narration_focus=_clean(item.get("narration_focus")) or None,
                    )
                )
            except Exception:
                logger.debug("Skipping invalid teaching brief scene outline: %r", item)
        elif isinstance(item, str) and item.strip():
            outlines.append(
                TeachingBriefSceneOutline(
                    title=f"场景 {index + 1}",
                    learning_goal=_clean(item),
                    diagram_plan=_clean(item),
                    must_draw=[],
                )
            )
    return outlines


def _brief_from_raw(raw: dict, req: GenerateGraphRequest) -> EnhancedTeachingBrief:
    return EnhancedTeachingBrief(
        original_prompt=_clean(raw.get("original_prompt")) or req.prompt,
        audience_level=_clean(raw.get("audience_level")) or DEFAULT_AUDIENCE,
        topic_type=_clean(raw.get("topic_type")) or "technical_explanation",
        learning_objectives=_as_str_list(raw.get("learning_objectives"), limit=8),
        core_explanation_chain=_as_str_list(raw.get("core_explanation_chain"), limit=12),
        must_include_points=_as_str_list(raw.get("must_include_points"), limit=16),
        visual_metaphors=_as_str_list(raw.get("visual_metaphors"), limit=10),
        recommended_scene_outline=_outline_from_raw(raw.get("recommended_scene_outline")),
        common_misconceptions=_as_str_list(raw.get("common_misconceptions"), limit=8),
    )


def _fallback_brief(req: GenerateGraphRequest) -> EnhancedTeachingBrief:
    topic = _clean(req.prompt)
    return EnhancedTeachingBrief(
        original_prompt=topic,
        audience_level=DEFAULT_AUDIENCE,
        topic_type="technical_explanation",
        learning_objectives=[
            f"理解 {topic} 的核心结构和关键变量。",
            f"理解 {topic} 的因果过程，而不只是记住名词。",
            f"能用一张过程图或对比图复述 {topic} 的工作原理。",
        ],
        core_explanation_chain=[
            "先给出直观现象或问题背景。",
            "再拆开结构、变量或步骤。",
            "用箭头说明原因如何导致结果。",
            "最后用类比或结论收束。",
        ],
        must_include_points=[topic],
        visual_metaphors=["用结构图、过程箭头和局部放大图代替纯文字列表。"],
        recommended_scene_outline=[
            TeachingBriefSceneOutline(
                title="核心结构",
                learning_goal="建立观众对主题的第一张图像。",
                diagram_plan="A clear whiteboard structure diagram with labels and arrows.",
                must_draw=["核心对象", "关键关系", "方向箭头"],
                narration_focus="边画结构边解释每个部分的作用。",
            )
        ],
        common_misconceptions=["把定义当成原理，忽略中间变化过程。"],
    )


def _scene_outline_from_dicts(items: list[dict]) -> list[TeachingBriefSceneOutline]:
    return [
        TeachingBriefSceneOutline(
            title=item["title"],
            learning_goal=item["learning_goal"],
            diagram_plan=item["diagram_plan"],
            must_draw=list(item["must_draw"]),
            narration_focus=item.get("narration_focus"),
        )
        for item in items
    ]


def _ensure_semiconductor_brief(brief: EnhancedTeachingBrief) -> EnhancedTeachingBrief:
    brief.learning_objectives = _append_unique(brief.learning_objectives, SEMICONDUCTOR_OBJECTIVES, limit=8)
    brief.core_explanation_chain = _append_unique(brief.core_explanation_chain, SEMICONDUCTOR_CHAIN, limit=14)
    brief.must_include_points = _append_unique(brief.must_include_points, SEMICONDUCTOR_POINTS, limit=18)
    brief.visual_metaphors = _append_unique(
        brief.visual_metaphors,
        [
            "MOS 像一个由栅极电压控制的水龙头/开关，通道形成后电流才被放行。",
            "FinFET 的栅极像三面夹住鳍片的夹子，比只从上方压住更容易控制沟道。",
            "用 Off/On 双图、长短沟道对比、三维包围图、截面公式图串起讲解。",
        ],
        limit=12,
    )
    existing_titles = {_norm(scene.title) for scene in brief.recommended_scene_outline}
    for scene in _scene_outline_from_dicts(SEMICONDUCTOR_SCENES):
        if _norm(scene.title) not in existing_titles:
            brief.recommended_scene_outline.append(scene)
            existing_titles.add(_norm(scene.title))
    brief.common_misconceptions = _append_unique(
        brief.common_misconceptions,
        [
            "误以为加了源漏电压就一定有电流；实际上必须先由栅压形成沟道。",
            "误以为 FinFET 只是把器件画成立体；关键是三面栅控增强了对沟道的电场控制。",
            "误以为 W_eff 只等于鳍片顶部宽度；两侧壁也贡献受控沟道宽度。",
        ],
        limit=10,
    )
    brief.topic_type = "工程结构 + 物理机制 + 状态对比"
    return brief


def _ensure_gradient_brief(brief: EnhancedTeachingBrief) -> EnhancedTeachingBrief:
    brief.learning_objectives = _append_unique(brief.learning_objectives, GRADIENT_OBJECTIVES, limit=6)
    brief.core_explanation_chain = _append_unique(brief.core_explanation_chain, GRADIENT_CHAIN, limit=10)
    brief.must_include_points = _append_unique(brief.must_include_points, GRADIENT_POINTS, limit=10)
    brief.visual_metaphors = _append_unique(
        brief.visual_metaphors,
        [
            "把损失函数画成山谷曲线，参数点像小球沿负梯度方向下坡。",
            "用箭头表示梯度方向，用短线段表示学习率步长。",
        ],
        limit=8,
    )
    if not brief.recommended_scene_outline:
        brief.recommended_scene_outline = _scene_outline_from_dicts(
            [
                {
                    "title": "损失曲线",
                    "learning_goal": "建立 loss 和参数位置的图像。",
                    "diagram_plan": "Loss curve with current parameter point on a whiteboard.",
                    "must_draw": ["Loss axis", "theta axis", "current point"],
                    "narration_focus": "先画地形，再解释高低代表错误大小。",
                },
                {
                    "title": "负梯度更新",
                    "learning_goal": "解释方向和步长。",
                    "diagram_plan": "Gradient arrow, negative-gradient arrow, learning-rate step on the curve.",
                    "must_draw": ["gradient", "negative gradient", "learning rate"],
                    "narration_focus": "边画箭头边说明为什么反方向走。",
                },
                {
                    "title": "迭代收敛",
                    "learning_goal": "展示重复更新的过程。",
                    "diagram_plan": "Multiple dots moving toward a valley minimum.",
                    "must_draw": ["iteration dots", "convergence", "minimum"],
                    "narration_focus": "每一步都把参数推向更低损失。",
                },
            ]
        )
    return brief


def _ensure_brief_minimums(brief: EnhancedTeachingBrief, req: GenerateGraphRequest) -> EnhancedTeachingBrief:
    topic = _clean(req.prompt)
    if not brief.original_prompt:
        brief.original_prompt = topic
    if not brief.audience_level:
        brief.audience_level = DEFAULT_AUDIENCE
    if len(brief.learning_objectives) < 3:
        brief.learning_objectives = _append_unique(
            brief.learning_objectives,
            [
                f"理解 {topic} 的核心对象和关键变量。",
                f"能按因果顺序解释 {topic} 的工作过程。",
                f"能通过图形、箭头和对比复述 {topic} 的主要结论。",
            ],
            limit=6,
        )
    if not brief.core_explanation_chain:
        brief.core_explanation_chain = [
            "先画直观结构或现象。",
            "再解释关键原因如何发生。",
            "接着画出变化过程和结果。",
            "最后用对比或类比总结。",
        ]
    if not brief.must_include_points:
        brief.must_include_points = [topic]
    if not brief.visual_metaphors:
        brief.visual_metaphors = ["结构图 + 过程箭头 + 局部放大 + 状态对比。"]
    if not brief.recommended_scene_outline:
        brief.recommended_scene_outline = _fallback_brief(req).recommended_scene_outline

    blob = _request_blob(req)
    if _is_semiconductor_topic(blob):
        brief = _ensure_semiconductor_brief(brief)
    if _is_gradient_topic(blob):
        brief = _ensure_gradient_brief(brief)
    return brief


async def enhance_prompt(req: GenerateGraphRequest) -> EnhancedTeachingBrief:
    user_content = {
        "original_prompt": req.prompt,
        "reference_material": req.markdown or "",
        "default_audience": DEFAULT_AUDIENCE,
    }
    logger.info("Enhancing teaching prompt for: %s", req.prompt[:50])
    raw = await chat_json(
        messages=[
            {"role": "system", "content": ENHANCE_SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(user_content, ensure_ascii=False)},
        ]
    )
    try:
        brief = _brief_from_raw(raw, req)
    except Exception as exc:
        logger.warning("Prompt enhancement JSON was incomplete; using deterministic brief: %s", exc)
        brief = _fallback_brief(req)
    return _ensure_brief_minimums(brief, req)


def _safe_node_type(value: object) -> NodeType:
    try:
        return NodeType(str(value or "concept"))
    except ValueError:
        return NodeType.CONCEPT


def _brief_context(req: GenerateGraphRequest, brief: EnhancedTeachingBrief) -> str:
    payload = {
        "original_prompt": req.prompt,
        "reference_material": req.markdown or "",
        "enhanced_teaching_brief": brief.model_dump(mode="json"),
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _graph_blob(graph: ExplainGraph) -> str:
    parts: list[str] = [graph.topic, graph.summary, *graph.key_insights]
    for node in graph.nodes:
        parts.extend([node.label, node.description, node.latex or ""])
    return "\n".join(parts)


def _next_node_id(graph: ExplainGraph) -> str:
    used = {node.id for node in graph.nodes}
    index = len(graph.nodes)
    while f"node_{index}" in used:
        index += 1
    return f"node_{index}"


def _ensure_node(
    graph: ExplainGraph,
    label: str,
    description: str,
    node_type: NodeType = NodeType.CONCEPT,
    latex: str | None = None,
) -> None:
    blob = _graph_blob(graph)
    if _contains_any_text(blob, [label, description]):
        return
    graph.nodes.append(
        ConceptNode(
            id=_next_node_id(graph),
            label=label,
            node_type=node_type,
            description=description,
            latex=latex,
            teach_order=len(graph.nodes),
        )
    )


def _ensure_chain_edges(graph: ExplainGraph) -> None:
    ordered = sorted(graph.nodes, key=lambda item: item.teach_order)
    existing = {(edge.source, edge.target) for edge in graph.edges}
    for source, target in zip(ordered, ordered[1:]):
        key = (source.id, target.id)
        if key not in existing:
            graph.edges.append(ConceptEdge(source=source.id, target=target.id, relation="顺序铺垫"))
            existing.add(key)


def _ensure_semiconductor_graph(graph: ExplainGraph) -> None:
    required = [
        (
            "MOS Off 状态",
            "栅压未超过阈值时，衬底表面没有连续反型沟道，源漏之间不能形成正常电流。",
            NodeType.EXAMPLE,
            None,
        ),
        (
            "阈值电压 Vth",
            "当 V_G > V_th，栅极电场足以在衬底表面感应电子并形成反型沟道。",
            NodeType.PROCESS,
            "V_G > V_{th}",
        ),
        (
            "源漏电流",
            "通道形成后，V_DS 才能推动载流子从源极到漏极运动，产生漏电流。",
            NodeType.PROCESS,
            "I_D",
        ),
        (
            "电压控制开关",
            "MOS 可以被理解成由栅极电压打开或关闭的电子开关。",
            NodeType.CONCLUSION,
            None,
        ),
        (
            "短沟道效应",
            "沟道长度缩短后，源漏电场会更明显地影响沟道，削弱栅极控制。",
            NodeType.CONCEPT,
            None,
        ),
        (
            "FinFET 三面栅控",
            "FinFET 把沟道做成立体鳍片，让栅极从顶部和两个侧壁包住沟道。",
            NodeType.CONCEPT,
            None,
        ),
        (
            "有效沟道宽度",
            "FinFET 截面中，顶部和两侧壁都贡献受控沟道宽度。",
            NodeType.FORMULA,
            "W_{eff}=2H_{fin}+W_{fin}",
        ),
    ]
    for label, description, node_type, latex in required:
        _ensure_node(graph, label, description, node_type, latex)
    graph.key_insights = _append_unique(graph.key_insights, SEMICONDUCTOR_POINTS, limit=12)


def _ensure_gradient_graph(graph: ExplainGraph) -> None:
    required = [
        ("损失曲线", "用曲线或地形表示模型错误大小，越低代表损失越小。", NodeType.CONCEPT, None),
        ("当前位置", "当前参数对应损失曲线上的一个点。", NodeType.EXAMPLE, None),
        ("负梯度方向", "梯度指向损失增大的方向，更新时沿负梯度方向移动。", NodeType.PROCESS, "-\\nabla L"),
        ("学习率步长", "学习率决定每次参数更新走多远。", NodeType.FORMULA, "\\theta_{t+1}=\\theta_t-\\eta\\nabla L"),
        ("迭代收敛", "重复多次更新后，参数逐步接近较低损失区域。", NodeType.CONCLUSION, None),
    ]
    for label, description, node_type, latex in required:
        _ensure_node(graph, label, description, node_type, latex)
    graph.key_insights = _append_unique(graph.key_insights, GRADIENT_POINTS, limit=10)


def _ensure_graph_quality(graph: ExplainGraph, req: GenerateGraphRequest, brief: EnhancedTeachingBrief) -> ExplainGraph:
    if len(graph.nodes) < 3:
        for index, item in enumerate(brief.core_explanation_chain[:5]):
            _ensure_node(graph, f"步骤 {index + 1}", item, NodeType.PROCESS)

    blob = _request_blob(req) + "\n" + _graph_blob(graph)
    if _is_semiconductor_topic(blob):
        _ensure_semiconductor_graph(graph)
    if _is_gradient_topic(blob):
        _ensure_gradient_graph(graph)

    graph.key_insights = _append_unique(graph.key_insights, brief.must_include_points, limit=12)
    _ensure_chain_edges(graph)
    graph.nodes = sorted(graph.nodes, key=lambda item: item.teach_order)
    return graph


async def generate_explain_graph(req: GenerateGraphRequest) -> ExplainGraph:
    await check_llm_connection()
    brief = await enhance_prompt(req)

    logger.info("Generating explain graph for: %s", req.prompt[:50])
    raw = await chat_json(
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": _brief_context(req, brief)},
        ]
    )

    nodes: list[ConceptNode] = []
    for i, node in enumerate(raw.get("nodes", [])):
        if not isinstance(node, dict):
            continue
        nodes.append(
            ConceptNode(
                id=_clean(node.get("id")) or f"node_{i}",
                label=_clean(node.get("label")) or f"概念 {i + 1}",
                node_type=_safe_node_type(node.get("node_type")),
                description=_clean(node.get("description")),
                latex=_clean(node.get("latex")) or None,
                teach_order=int(node.get("teach_order", i) or i),
            )
        )

    edges = [
        ConceptEdge(
            source=_clean(edge.get("source")),
            target=_clean(edge.get("target")),
            relation=_clean(edge.get("relation")) or "关联",
        )
        for edge in raw.get("edges", [])
        if isinstance(edge, dict) and edge.get("source") and edge.get("target")
    ]

    graph = ExplainGraph(
        topic=_clean(raw.get("topic")) or req.prompt,
        summary=_clean(raw.get("summary")),
        nodes=nodes,
        edges=edges,
        key_insights=_as_str_list(raw.get("key_insights"), limit=12),
        enhanced_brief=brief,
    )

    graph = _ensure_graph_quality(graph, req, brief)
    logger.info("Graph generated: %d nodes, %d edges", len(graph.nodes), len(graph.edges))
    return graph
