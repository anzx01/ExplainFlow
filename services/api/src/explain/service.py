import json
import logging
import re

from src.core.visual_prompts import BOLD_EDITORIAL_BOARD_RULES, BOLD_EDITORIAL_LAYOUT_RULES
from src.core.llm import chat_json, check_llm_connection
from .models import (
    ConceptEdge,
    ConceptNode,
    EnhancedTeachingBrief,
    ExplainGraph,
    GenerateGraphRequest,
    NodeType,
    TeachingCoverageUnit,
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
7. 如果用户给的是英文术语、英文书名、英文框架或英文缩写，不要逐词硬翻。先判断中文语境中自然、常用、观众能听懂的说法；没有固定译名时，用“自然中文短语 + 必要英文原词括注”的方式转译。
8. 所有标题、节点、板书标签和旁白都要像中文老师会说的话：宁可解释成自然短语，也不要制造生硬中文词。例：interdependence 不写“互赖”，可写“互相依赖/成熟协作/协作共赢”，按上下文选择。
9. 参考真实老师白板讲解：一屏一个核心想法；顶部蓝色手写标题；主体图居中，占画面 45%-65%；保留大面积空白；文字只写短标签和关键结论。
10. 画面不是信息图海报：不要密集段落、图例框、装饰面板、彩色背景块、卡片式布局或复杂 UI；所有内容都像老师在白板上逐步补出来。
11. 色彩有教学含义：黑色主体线，蓝色标题/控制关系，红色风险/电流/错误，绿色有效路径/正确结果，黄色只做小下划线或局部强调。
12. 复杂图不要强行逐笔画完：如果一张图过密、标签多、像参考图/成品图/多层结构，应建议直接呈现主体，再用少量手写箭头、圈、下划线和局部 callout 讲重点。
13. 不要把所有视频都做成同一种“手一直画完整图”。这里的 visual_style 是内部课堂表达语法；最终 8 种 Golpo Canvas 视觉风格会在 storyboard 阶段由用户选择并覆盖画布、色彩和质感。根据内容选择呈现策略：
    - teacher_whiteboard：像真实白板老师，简单结构、流程、对比、机制图由手逐步写画。
    - marketing_doodle：像产品/营销白板，彩色 doodle 或复杂成品图可以直接出现，手只补标题、箭头、勾选、下划线和少量标注。
    - math_chalkboard：像黑板解题，深色黑板、无可见手，公式和推导按行/按步骤显现，保留上下文，颜色承载变量和结论。
    - technical_reference：复杂实物、参考图、三维结构、医学/机械/电路等，先清楚呈现主体，再逐步强调局部。
14. 对每个场景明确推荐 `board_mode`、`hand_usage`、`visual_style`。这不是模板库，而是课堂表达语法。
15. 不要围绕某个题材词做特殊处理；先抽象出教学关系，再选择画面语法：
    - overview_map：一个主题包含多个对象、单元、阶段或知识点时，先给全局地图。
    - comparison：讲前后、开关、A/B、好坏、旧新、状态变化时，用双图对比。
    - process：讲因果链、机制、流程、变化过程时，用“原因 -> 过程 -> 结果”。
    - structure：讲组成、层级、整体和局部时，用主体结构图、贴近标签和局部放大。
    - interaction：讲对象之间互相影响、沟通、协作、交换、反馈关系时，用节点和双向箭头。
    - tradeoff_matrix：讲优先级、取舍、二维判断或分类时，用坐标/四象限/2x2 矩阵。
    - goal_path：讲目标、路线、里程碑、倒推或成长路径时，用起点到终点路径图。
    - cycle：讲迭代、复盘、更新、闭环时，用环形箭头和 3-5 个节点。
    - formula：讲公式时，用公式、变量 callout 和一个小示意图解释含义。
    - reference_callout：复杂主体必须清楚保真时，直接呈现主体，再用局部 callout 讲重点。
    - summary：收束时用少量清单、闭环或框架图，不写长段落。

主题类型参考：
- 器件原理：结构 -> 状态对比 -> 物理机制 -> 电路作用 -> 局限/改进
- 工程结构：整体结构 -> 局部放大 -> 受力/电场/流动路径 -> 对比旧方案
- 算法流程：目标 -> 当前状态 -> 方向/更新规则 -> 迭代变化 -> 收敛
- 数学推导：问题 -> 变量 -> 公式含义 -> 推导步骤 -> 直觉解释
- 物理机制：现象 -> 微观原因 -> 宏观结果 -> 实验/类比

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
  "board_style_rules": ["通用白板老师讲课规则"],
  "layout_principles": ["构图布局规则"],
  "recommended_scene_outline": [
    {
      "title": "场景标题",
      "learning_goal": "该场景要解决的理解问题",
      "diagram_plan": "具体画面：布局、图形、箭头、标签、局部放大",
      "must_draw": ["必须画出的元素"],
      "narration_focus": "旁白应跟随哪些绘制动作",
      "board_mode": "whiteboard|chalkboard|clean_canvas|reference",
      "hand_usage": "trace|annotate|none",
      "visual_style": "teacher_whiteboard|marketing_doodle|math_chalkboard|technical_reference"
    }
  ],
  "teaching_coverage_units": [
    {
      "id": "unit_0",
      "label": "必须覆盖的概念、对象、状态、步骤或结论",
      "unit_type": "concept|process|comparison|state|formula|example|conclusion",
      "teaching_goal": "这一单元要让观众真正理解什么",
      "visual_role": "overview_map|structure|process|comparison|interaction|tradeoff_matrix|goal_path|cycle|simulation|formula|reference_callout|summary",
      "must_show": ["图上必须出现的短标签、箭头、状态或对象"],
      "narration_focus": "旁白必须解释的因果、变化或结论",
      "priority": 5
    }
  ],
  "recommended_board_mode": "whiteboard|chalkboard|clean_canvas|reference",
  "recommended_hand_usage": "trace|annotate|none",
  "recommended_visual_style": "teacher_whiteboard|marketing_doodle|math_chalkboard|technical_reference",
  "common_misconceptions": ["容易误解的点"]
}"""

SYSTEM_PROMPT = """你是通用技术教学视频的 Explain Graph 规划专家。你会收到用户原始 prompt、参考材料和已经增强过的教学 brief。

你的任务：
1. 不要只提取关键词，要把 enhanced brief 中的学习目标、因果链、必须包含内容转成教学图谱。
2. 节点要服务于“可讲、可画、可同步动画”的视频结构：状态对比、过程变化、结构局部、公式含义、结论。
3. 对复杂概念，优先创建 process / example / formula 节点，而不是一堆抽象 concept。
4. 不得遗漏 enhanced brief 的 must_include_points；如果用户原 prompt 太短，也要按 brief 补齐教学必要内容。
5. teach_order 必须是观众理解的顺序，从直观现象到机制，再到结果和总结。
6. 图谱中的 topic、summary、label、description、relation 必须是自然中文。遇到英文概念时，先转译成中文语境里通顺的表达；只有行业固定术语、缩写或搜索名词才保留英文或括注英文，禁止逐词硬翻。

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

COOKING_TERMS = [
    "cook",
    "cooking",
    "recipe",
    "food",
    "dish",
    "wok",
    "skillet",
    "stir-fry",
    "stir fry",
    "sauce",
    "tofu",
    "mapo",
    "麻婆",
    "豆腐",
    "烹饪",
    "做法",
    "好吃",
    "食材",
    "炒",
    "煸",
    "爆香",
    "锅",
    "菜",
    "勾芡",
    "出锅",
    "装盘",
]

COOKING_GRAPH_TERMS = [
    "食材",
    "豆腐",
    "肉末",
    "豆瓣酱",
    "花椒",
    "蒜苗",
    "红油",
    "炒锅",
    "炒",
    "煸",
    "烧",
    "勾芡",
    "装盘",
    "wok",
    "tofu",
    "sauce",
    "recipe",
    "cook",
]

MAPO_TOFU_SCENES = [
    {
        "title": "食材先备齐",
        "learning_goal": "让观众知道一盘麻婆豆腐需要哪些关键食材。",
        "diagram_plan": "Whiteboard cooking prep layout: cutting board with tofu cubes, small bowls for minced meat, Pixian doubanjiang chili bean paste, Sichuan pepper, garlic/ginger, garlic sprouts/scallions, starch slurry.",
        "must_draw": ["豆腐", "肉末", "豆瓣酱", "花椒", "蒜苗", "水淀粉"],
        "narration_focus": "说明豆腐、豆瓣酱、花椒和蒜苗分别负责口感、辣香、麻香和收尾香气。",
        "board_mode": "whiteboard",
        "hand_usage": "trace",
        "visual_style": "teacher_whiteboard",
    },
    {
        "title": "炒香底料",
        "learning_goal": "理解红油和香味来自小火煸炒，而不是最后硬加辣味。",
        "diagram_plan": "Wide black Chinese wok on burner, minced meat turning brown, red doubanjiang chili oil blooming, garlic and ginger aromatics, red oil pooling around the spatula.",
        "must_draw": ["炒锅", "肉末", "豆瓣酱", "红油", "小火煸香"],
        "narration_focus": "强调肉末要煸到干香，豆瓣酱要炒出红油，火太大会糊。",
        "board_mode": "whiteboard",
        "hand_usage": "trace",
        "visual_style": "teacher_whiteboard",
    },
    {
        "title": "豆腐入锅烧透",
        "learning_goal": "展示豆腐怎样吸进汤汁并保持完整。",
        "diagram_plan": "Wide black wok or skillet, white tofu cubes in glossy red sauce with minced meat, stock or water being added, gentle simmer bubbles and steam, spatula pushing softly rather than smashing.",
        "must_draw": ["豆腐块", "红汤汁", "轻推", "烧透"],
        "narration_focus": "说明豆腐下锅后轻推不要翻碎，小火烧一会儿让味道进豆腐。",
        "board_mode": "whiteboard",
        "hand_usage": "trace",
        "visual_style": "teacher_whiteboard",
    },
    {
        "title": "勾芡锁住红油",
        "learning_goal": "理解水淀粉让汤汁挂在豆腐上，形成麻婆豆腐的浓亮口感。",
        "diagram_plan": "Close whiteboard zoom of red sauce thickening around tofu cubes in a black wok, starch slurry stream entering, sauce changing from watery to glossy, arrows showing sauce coating tofu.",
        "must_draw": ["水淀粉", "浓亮", "挂汁", "红油"],
        "narration_focus": "解释勾芡要分次加入，边推边观察浓度，让红油和汤汁包住豆腐。",
        "board_mode": "whiteboard",
        "hand_usage": "trace",
        "visual_style": "teacher_whiteboard",
    },
    {
        "title": "出锅撒花椒粉",
        "learning_goal": "收束成品状态：麻、辣、烫、香都要在最后一口里出现。",
        "diagram_plan": "Finished Sichuan mapo tofu in a shallow white bowl, white tofu cubes in glossy red chili oil sauce, brown minced meat, green garlic sprouts/scallions, Sichuan pepper powder sprinkled on top, steam.",
        "must_draw": ["红油", "豆腐", "肉末", "蒜苗", "花椒粉"],
        "narration_focus": "总结花椒粉和蒜苗最后放，保留麻香和清香，趁热吃最有风味。",
        "board_mode": "whiteboard",
        "hand_usage": "trace",
        "visual_style": "teacher_whiteboard",
    },
]

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
        "board_mode": "whiteboard",
        "hand_usage": "trace",
        "visual_style": "teacher_whiteboard",
    },
    {
        "title": "Off/On 两种状态",
        "learning_goal": "用双图对比解释为什么阈值电压是导通分界线。",
        "diagram_plan": "Two-panel comparison: OFF panel with no channel and crossed current arrow; ON panel with V_G > V_th, electron channel drawn between source and drain.",
        "must_draw": ["OFF: V_G < V_th", "ON: V_G > V_th", "No channel", "Electron channel"],
        "narration_focus": "边画边讲无沟道到形成连续电子沟道的变化。",
        "board_mode": "whiteboard",
        "hand_usage": "trace",
        "visual_style": "teacher_whiteboard",
    },
    {
        "title": "电流像水流一样被打开",
        "learning_goal": "说明 V_DS 只有在沟道形成后才能推动源漏电流。",
        "diagram_plan": "MOS ON diagram with V_DS battery between drain and source, arrows moving through channel, switch analogy icon.",
        "must_draw": ["V_DS", "I_D arrows", "Voltage-controlled switch"],
        "narration_focus": "先画通道，再画源漏电压和电流箭头，最后总结成开关。",
        "board_mode": "whiteboard",
        "hand_usage": "trace",
        "visual_style": "teacher_whiteboard",
    },
    {
        "title": "尺寸缩小后的短沟道效应",
        "learning_goal": "解释为什么平面 MOS 缩小后栅极控制会变差。",
        "diagram_plan": "Long-channel versus short-channel comparison, source/drain fields intrude into channel, leakage/failed control warning arrow.",
        "must_draw": ["Long channel", "Short channel", "Source/drain field intrusion", "Short-channel effect"],
        "narration_focus": "对比长沟道和短沟道，强调源漏电场抢走控制权。",
        "board_mode": "whiteboard",
        "hand_usage": "trace",
        "visual_style": "teacher_whiteboard",
    },
    {
        "title": "FinFET 的三面包围",
        "learning_goal": "看懂 FinFET 为什么把沟道竖起来并用栅极包住。",
        "diagram_plan": "Simple 3D whiteboard sketch of a fin channel standing up, source and drain at two ends, gate wrapping over top and two sidewalls, control arrows on three sides.",
        "must_draw": ["Fin channel", "Source", "Drain", "Gate wraps three sides", "Three-side control arrows"],
        "narration_focus": "逐笔画出 fin，再画栅极像夹子一样从三面包住沟道。",
        "board_mode": "reference",
        "hand_usage": "annotate",
        "visual_style": "technical_reference",
    },
    {
        "title": "截面里的有效宽度",
        "learning_goal": "用截面图解释 W_eff = 2H_fin + W_fin 和三面感应电荷。",
        "diagram_plan": "FinFET cross-section: U-shaped gate around fin, labels H_fin on two sidewalls and W_fin on top, electrons induced on three surfaces, formula W_eff = 2H_fin + W_fin.",
        "must_draw": ["U-shaped gate", "H_fin", "W_fin", "Induced charges on three surfaces", "W_eff = 2H_fin + W_fin"],
        "narration_focus": "边画三条受控表面边写公式，说明有效宽度来自三部分相加。",
        "board_mode": "reference",
        "hand_usage": "annotate",
        "visual_style": "technical_reference",
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

WHITEBOARD_BOARD_RULES = [
    "像真实老师白板讲课：手写标题、手绘主体图、边讲边补标签和箭头。",
    *BOLD_EDITORIAL_BOARD_RULES,
    "一屏只承载一个核心想法，最多一个主图或一个双图对比。",
    "旁白讲概念、因果、变化和结论，不说“先画、再画、这里写”。",
    "图形和旁白必须同 beat 对齐：讲到的对象就是当前正在出现或被强调的对象。",
    "复杂主体可以直接呈现，手部只负责补少量 callout、圈选、下划线和关键箭头。",
    "不是所有场景都需要手：数学推导、公式演算、代码/逻辑证明可用黑板无手逐行显现。",
    "营销或产品说明可直接呈现彩色 doodle/成品图，再用手补标题、勾选、箭头和短标注。",
    "特别复杂的参考图、三维结构、医学/机械/电路图优先清楚呈现主体，避免手部逐笔描完造成拖沓。",
]

WHITEBOARD_LAYOUT_PRINCIPLES = [
    "标题放顶部左侧或顶部居中，蓝色手写，可用短下划线强调。",
    *BOLD_EDITORIAL_LAYOUT_RULES,
    "主体图放画面中部或略偏右，占宽度约 45%-65%，四周留出空白给后续标注。",
    "每个标签尽量 1-4 个词，贴近对应结构，避免远距离长引线。",
    "每屏文字总量克制：短标题、少量标签、一个关键结论即可。",
    "流程和因果用粗黑箭头或蓝色箭头连接；风险/错误/限制用红色；有效路径/成功结果用绿色。",
    "不要彩色背景块、卡片、图例框、海报式密集排版或装饰性插画。",
    "黑板推导布局采用深色背景、左上题目/目标、主区域保留已写步骤，下一行只推进一个推导动作。",
    "彩色 doodle 布局采用大主体对象分组、少量标签和 checklist/箭头强调，不追求每条轮廓都由笔画完。",
]

STYLE_STRATEGY_RULES = [
    "board_mode=whiteboard：浅灰白板，适合机制图、状态对比、流程、结构示意；hand_usage 通常为 trace 或 annotate。",
    "board_mode=chalkboard：深色黑板，适合数学推导、公式证明、解题过程；hand_usage=none，文字/公式按行显现。",
    "board_mode=clean_canvas：浅色干净画布，适合营销、产品、概念介绍；hand_usage=annotate，主体可以直接出现。",
    "board_mode=reference：用于复杂参考图、实物图、多层结构；主体 direct/hybrid 呈现，手只做局部标注。",
    "hand_usage=trace：简单图逐笔写画；hand_usage=annotate：主体已在场，只写少量 callout；hand_usage=none：无手逐步显现。",
    "visual_style 是内部课堂表达语法，不是最终画布风格；最终 Golpo Canvas 风格由 storyboard 的 video_style 控制。",
    "visual_style=teacher_whiteboard：稀疏白板课堂；marketing_doodle：彩色成品 doodle + 手部强调；math_chalkboard：黑板粉笔推导；technical_reference：复杂主体 + 精准局部讲解。",
]


def _localize_chinese_terms(text: str) -> str:
    replacements = {
        "相互依赖": "互相依赖",
        "互赖": "互相依赖",
        "同理心倾听": "先理解别人",
        "协同增效": "统合综效",
        "削尖锯子": "不断更新",
    }
    for source, target in replacements.items():
        text = text.replace(source, target)
    return text


def _clean(value: object) -> str:
    text = "" if value is None else str(value)
    text = re.sub(r"\x1b\[[0-9;]*m", "", text)
    return _localize_chinese_terms(re.sub(r"\s+", " ", text).strip())


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


def _looks_corrupted_text(text: str) -> bool:
    if not text:
        return False
    question_runs = len(re.findall(r"\?{4,}", text))
    replacement_count = text.count("�")
    visible = max(1, len(re.sub(r"\s+", "", text)))
    return question_runs > 0 or replacement_count / visible > 0.01


def _request_blob(req: GenerateGraphRequest) -> str:
    return f"{req.prompt}\n{req.markdown or ''}"


def _is_semiconductor_topic(text: str) -> bool:
    lowered = text.lower()
    latin_patterns = [
        r"(?<![a-z0-9_])mos(?![a-z0-9_])",
        r"(?<![a-z0-9_])mosfet(?![a-z0-9_])",
        r"(?<![a-z0-9_])finfet(?![a-z0-9_])",
    ]
    if any(re.search(pattern, lowered) for pattern in latin_patterns):
        return True
    return any(term in text for term in ["晶体管", "场效应管", "栅极", "源极", "漏极", "沟道"])


def _is_gradient_topic(text: str) -> bool:
    return _contains_any_text(text, GRADIENT_TERMS)


def _is_cooking_topic(text: str) -> bool:
    return _contains_any_text(text, COOKING_TERMS)


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
                        board_mode=_clean(item.get("board_mode")) or None,
                        hand_usage=_clean(item.get("hand_usage")) or None,
                        visual_style=_clean(item.get("visual_style")) or None,
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


def _coverage_units_from_raw(value: object) -> list[TeachingCoverageUnit]:
    units: list[TeachingCoverageUnit] = []
    if not isinstance(value, list):
        return units
    for index, item in enumerate(value):
        try:
            if isinstance(item, dict):
                label = _clean(item.get("label") or item.get("title") or item.get("name"))
                goal = _clean(item.get("teaching_goal") or item.get("learning_goal") or item.get("goal"))
                if not label and not goal:
                    continue
                units.append(
                    TeachingCoverageUnit(
                        id=_clean(item.get("id")) or f"unit_{index}",
                        label=label or f"教学单元 {index + 1}",
                        unit_type=_clean(item.get("unit_type") or item.get("type")) or "concept",
                        teaching_goal=goal,
                        visual_role=_clean(item.get("visual_role") or item.get("diagram_kind") or item.get("role")) or "structure",
                        must_show=_as_str_list(item.get("must_show") or item.get("required_labels") or item.get("must_draw"), limit=8),
                        narration_focus=_clean(item.get("narration_focus")) or None,
                        priority=int(item.get("priority") or 3),
                    )
                )
            elif isinstance(item, str) and item.strip():
                units.append(
                    TeachingCoverageUnit(
                        id=f"unit_{index}",
                        label=_clean(item),
                        unit_type="concept",
                        teaching_goal=f"讲清楚 {_clean(item)} 的含义、作用和使用场景。",
                        visual_role="structure",
                        must_show=[_clean(item)],
                        priority=3,
                    )
                )
        except Exception:
            logger.debug("Skipping invalid teaching coverage unit: %r", item)
    return units


def _brief_from_raw(raw: dict, req: GenerateGraphRequest) -> EnhancedTeachingBrief:
    return EnhancedTeachingBrief(
        original_prompt=_clean(raw.get("original_prompt")) or req.prompt,
        audience_level=_clean(raw.get("audience_level")) or DEFAULT_AUDIENCE,
        topic_type=_clean(raw.get("topic_type")) or "technical_explanation",
        learning_objectives=_as_str_list(raw.get("learning_objectives"), limit=8),
        core_explanation_chain=_as_str_list(raw.get("core_explanation_chain"), limit=12),
        must_include_points=_as_str_list(raw.get("must_include_points"), limit=16),
        visual_metaphors=_as_str_list(raw.get("visual_metaphors"), limit=10),
        board_style_rules=_as_str_list(raw.get("board_style_rules"), limit=12),
        layout_principles=_as_str_list(raw.get("layout_principles"), limit=12),
        recommended_board_mode=_clean(raw.get("recommended_board_mode")) or "whiteboard",
        recommended_hand_usage=_clean(raw.get("recommended_hand_usage")) or "trace",
        recommended_visual_style=_clean(raw.get("recommended_visual_style")) or "teacher_whiteboard",
        recommended_scene_outline=_outline_from_raw(raw.get("recommended_scene_outline")),
        teaching_coverage_units=_coverage_units_from_raw(raw.get("teaching_coverage_units")),
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
        board_style_rules=list(WHITEBOARD_BOARD_RULES),
        layout_principles=list(WHITEBOARD_LAYOUT_PRINCIPLES),
        recommended_board_mode="whiteboard",
        recommended_hand_usage="trace",
        recommended_visual_style="teacher_whiteboard",
        recommended_scene_outline=[
            TeachingBriefSceneOutline(
                title="核心结构",
                learning_goal="建立观众对主题的第一张图像。",
                diagram_plan="A clear whiteboard structure diagram with labels and arrows.",
                must_draw=["核心对象", "关键关系", "方向箭头"],
                narration_focus="边画结构边解释每个部分的作用。",
                board_mode="whiteboard",
                hand_usage="trace",
                visual_style="teacher_whiteboard",
            )
        ],
        teaching_coverage_units=[
            TeachingCoverageUnit(
                id="unit_0",
                label=topic,
                unit_type="concept",
                teaching_goal=f"讲清楚 {topic} 的核心对象、关键关系和最终结论。",
                visual_role="structure",
                must_show=[topic, "关键关系", "结论"],
                narration_focus="按对象、关系、变化、结论的顺序讲清楚。",
                priority=5,
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
            board_mode=item.get("board_mode"),
            hand_usage=item.get("hand_usage"),
            visual_style=item.get("visual_style"),
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
    brief.recommended_board_mode = "whiteboard"
    brief.recommended_hand_usage = "trace"
    brief.recommended_visual_style = "teacher_whiteboard"
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
                    "board_mode": "whiteboard",
                    "hand_usage": "trace",
                    "visual_style": "teacher_whiteboard",
                },
                {
                    "title": "负梯度更新",
                    "learning_goal": "解释方向和步长。",
                    "diagram_plan": "Gradient arrow, negative-gradient arrow, learning-rate step on the curve.",
                    "must_draw": ["gradient", "negative gradient", "learning rate"],
                    "narration_focus": "边画箭头边说明为什么反方向走。",
                    "board_mode": "whiteboard",
                    "hand_usage": "trace",
                    "visual_style": "teacher_whiteboard",
                },
                {
                    "title": "迭代收敛",
                    "learning_goal": "展示重复更新的过程。",
                    "diagram_plan": "Multiple dots moving toward a valley minimum.",
                    "must_draw": ["iteration dots", "convergence", "minimum"],
                    "narration_focus": "每一步都把参数推向更低损失。",
                    "board_mode": "whiteboard",
                    "hand_usage": "trace",
                    "visual_style": "teacher_whiteboard",
                },
            ]
        )
    if brief.recommended_visual_style != "math_chalkboard":
        brief.recommended_board_mode = "whiteboard"
        brief.recommended_hand_usage = "trace"
        brief.recommended_visual_style = "teacher_whiteboard"
    return brief


def _ensure_cooking_brief(brief: EnhancedTeachingBrief, req: GenerateGraphRequest) -> EnhancedTeachingBrief:
    topic = _clean(req.prompt)
    is_mapo = _contains_any_text(topic, ["麻婆", "mapo", "豆腐", "tofu"])
    if is_mapo:
        objectives = [
            "看懂麻婆豆腐的关键食材：豆腐、肉末、豆瓣酱、花椒、蒜苗和水淀粉。",
            "理解炒香底料、烧透豆腐、勾芡挂汁、出锅撒花椒粉这几步分别解决什么问题。",
            "能通过颜色和状态判断一锅麻婆豆腐是否好吃：红油亮、豆腐完整、汤汁挂住、麻香最后上来。",
        ]
        chain = [
            "先备料：豆腐切块，肉末、豆瓣酱、花椒、蒜苗和水淀粉分开准备。",
            "用炒锅小火煸肉末和豆瓣酱，炒出红油和酱香。",
            "下豆腐和汤汁轻推烧透，让豆腐吸味但不被铲碎。",
            "分次加入水淀粉勾芡，让红亮汤汁挂在豆腐上。",
            "出锅前撒花椒粉和蒜苗，保留麻香、清香和热度。",
        ]
        points = [
            "豆瓣酱要炒出红油，麻婆豆腐才有底香和颜色。",
            "豆腐下锅后轻推，不要大力翻炒，否则容易碎。",
            "勾芡要分次少量加入，看到汤汁能挂住豆腐就停。",
            "花椒粉和蒜苗适合最后放，香气更明显。",
        ]
        outline = _scene_outline_from_dicts(MAPO_TOFU_SCENES)
    else:
        objectives = [
            f"看懂 {topic} 的关键食材、器具和火候。",
            f"理解 {topic} 每一步为什么这么做，而不是只记步骤。",
            f"能通过颜色、气味、质地和成品状态判断是否做到位。",
        ]
        chain = [
            "先备齐主要食材和调味料。",
            "再处理关键食材的形状、大小或预处理状态。",
            "进入加热步骤，说明火候、锅具和香味变化。",
            "最后收汁、调味或装盘，总结成品判断标准。",
        ]
        points = [topic, "食材准备", "火候控制", "调味与成品状态"]
        outline = [
            TeachingBriefSceneOutline(
                title="食材与器具",
                learning_goal="建立观众对主要食材和工具的第一张图像。",
                diagram_plan="Colorful whiteboard cooking prep layout with ingredients, cookware, and short labels.",
                must_draw=["食材", "锅具", "调味料"],
                narration_focus="说明每个食材和工具的作用。",
                board_mode="whiteboard",
                hand_usage="trace",
                visual_style="teacher_whiteboard",
            ),
            TeachingBriefSceneOutline(
                title="关键步骤",
                learning_goal="把做法拆成清楚的可操作流程。",
                diagram_plan="Whiteboard process diagram with cookware, heat, arrows, food color/state changes.",
                must_draw=["加热", "翻炒/炖煮", "调味", "成品"],
                narration_focus="按步骤解释颜色、气味和质地的变化。",
                board_mode="whiteboard",
                hand_usage="trace",
                visual_style="teacher_whiteboard",
            ),
        ]

    brief.topic_type = "cooking_recipe"
    brief.learning_objectives = _append_unique(objectives, brief.learning_objectives, limit=8)
    brief.core_explanation_chain = _append_unique(chain, brief.core_explanation_chain, limit=12)
    brief.must_include_points = _append_unique(points, brief.must_include_points, limit=18)
    brief.visual_metaphors = _append_unique(
        [
            "用食材小碗、炒锅、红油颜色变化、蒸汽、汤汁挂在豆腐上的局部放大来讲做法。",
            "不要画成抽象流程框；每一步都要有真实食材、锅具、颜色和状态变化。",
        ],
        brief.visual_metaphors,
        limit=12,
    )
    existing_titles = {_norm(scene.title) for scene in brief.recommended_scene_outline}
    for scene in outline:
        if _norm(scene.title) not in existing_titles:
            brief.recommended_scene_outline.append(scene)
            existing_titles.add(_norm(scene.title))
    brief.recommended_board_mode = "whiteboard"
    brief.recommended_hand_usage = "trace"
    brief.recommended_visual_style = "teacher_whiteboard"
    brief.common_misconceptions = _append_unique(
        [
            "把麻婆豆腐画成白水豆腐或普通汤锅，会让观众看不出红油和锅气。",
            "只列步骤不画食材状态，观众不知道什么叫炒香、烧透、挂汁。",
            "花椒粉过早下锅容易损失麻香，最后撒更清楚。",
        ],
        brief.common_misconceptions,
        limit=8,
    )
    return brief


def _coverage_unit(
    index: int,
    label: str,
    unit_type: str,
    teaching_goal: str,
    visual_role: str,
    must_show: list[str] | None = None,
    narration_focus: str | None = None,
    priority: int = 3,
) -> TeachingCoverageUnit:
    return TeachingCoverageUnit(
        id=f"unit_{index}",
        label=_clean(label) or f"教学单元 {index + 1}",
        unit_type=unit_type,
        teaching_goal=_clean(teaching_goal),
        visual_role=visual_role,
        must_show=[item for item in (must_show or []) if _clean(item)],
        narration_focus=_clean(narration_focus) or None,
        priority=max(1, min(5, int(priority))),
    )


def _split_teaching_items(value: str) -> list[str]:
    text = _clean(value)
    if not text:
        return []
    text = re.sub(r"^\s*[\-•*]\s*", "", text)
    parts = re.split(r"[；;。.!?\n]+", text)
    items: list[str] = []
    for part in parts:
        part = _clean(part)
        if not part:
            continue
        subparts = re.split(r"(?:\s*[、,，]\s*)", part)
        if 2 <= len(subparts) <= 10 and all(2 <= len(item) <= 18 for item in subparts):
            items.extend(subparts)
        else:
            items.append(part)
    return [_clean(item) for item in items if _clean(item)]


def _derive_teaching_coverage_units(brief: EnhancedTeachingBrief, req: GenerateGraphRequest) -> list[TeachingCoverageUnit]:
    units = list(brief.teaching_coverage_units or [])
    source_items: list[tuple[str, str, str, int]] = []

    for index, item in enumerate(brief.recommended_scene_outline):
        source_items.append(
            (
                item.title,
                item.learning_goal or f"讲清楚 {item.title}。",
                item.diagram_plan or "whiteboard structure/process diagram",
                5 if index < 6 else 4,
            )
        )

    for point in brief.must_include_points:
        source_items.append((point, f"讲清楚 {point} 的含义、原因和结果。", "callout/process", 5))

    for objective in brief.learning_objectives:
        for item in _split_teaching_items(objective):
            source_items.append((item, objective, "concept_map", 3))

    for chain_item in brief.core_explanation_chain:
        source_items.append((chain_item, chain_item, "process", 4))

    topic = _clean(req.prompt)
    if topic:
        source_items.append((topic, f"让观众建立对 {topic} 的完整认知框架。", "overview", 5))

    seen = {_norm(unit.label) for unit in units}
    for label, goal, visual_role, priority in source_items:
        label = _clean(label)
        if not label:
            continue
        label = re.sub(r"^(?:理解|看懂|掌握|知道|说明|解释|通过|用)\s*", "", label)
        label = _clean(label.strip("：:，,。 "))
        if not label:
            continue
        if len(label) > 46:
            label = label[:46].rstrip() + "..."
        key = _norm(label)
        if not key or key in seen:
            continue
        seen.add(key)
        visual_text = f"{visual_role} {label}".lower()
        unit_type = "process" if any(term in visual_text for term in ["process", "simulation", "cycle", "goal_path", "interaction"]) else "concept"
        if any(term in visual_text for term in ["vs", "对比", "比较", "off/on", "before", "after", "comparison", "state"]):
            unit_type = "comparison"
            visual_role = "comparison"
        elif any(term in visual_text for term in ["tradeoff", "priority", "quadrant", "matrix", "取舍", "优先", "象限", "矩阵"]):
            unit_type = "comparison"
            visual_role = "tradeoff_matrix"
        elif any(term in visual_text for term in ["interaction", "relationship", "mutual", "communication", "collaboration", "互相", "互动", "关系", "沟通", "协作"]):
            unit_type = "process"
            visual_role = "interaction"
        elif any(term in visual_text for term in ["goal", "target", "path", "roadmap", "目标", "路径", "路线", "里程碑"]):
            unit_type = "process"
            visual_role = "goal_path"
        elif any(term in visual_text for term in ["cycle", "loop", "feedback", "iterate", "renew", "循环", "闭环", "反馈", "迭代", "更新"]):
            unit_type = "process"
            visual_role = "cycle"
        elif any(term in visual_text for term in ["公式", "=", "w_eff", "theta", "loss", "formula", "equation"]):
            unit_type = "formula"
            visual_role = "formula"
        units.append(
            _coverage_unit(
                len(units),
                label,
                unit_type,
                goal,
                visual_role,
                must_show=[label],
                narration_focus="按现象、原因、过程、结果讲清楚，不只给定义。",
                priority=priority,
            )
        )
        if len(units) >= 18:
            break

    return units


def _ensure_teaching_coverage_brief(brief: EnhancedTeachingBrief, req: GenerateGraphRequest) -> EnhancedTeachingBrief:
    units = _derive_teaching_coverage_units(brief, req)
    brief.teaching_coverage_units = units
    if units:
        brief.must_include_points = _append_unique(
            brief.must_include_points,
            [unit.label for unit in units if unit.priority >= 4],
            limit=24,
        )
    brief.visual_metaphors = _append_unique(
        brief.visual_metaphors,
        [
            "通用课堂结构：全局地图、状态对比、因果流程、结构拆解、交互关系、优先级矩阵、目标路径、反馈闭环、公式 callout 和总结清单按教学关系选择。",
            "不要根据题材词套专门图形；同一种关系在技术、商业、管理、医学、数学等主题中都用同一套可迁移视觉语法。",
            "英文术语要先做中文本地化转译：优先使用中文语境中自然、常用、好懂的说法；没有固定译名时用自然短语解释，不要逐词硬翻。",
            "复杂主体直接呈现清晰图，老师只用手写箭头、圈选、下划线和短标签强调重点。",
            "如果主题包含多个单元、状态、对象或阶段，每个单元都必须有独立画面或明确视觉 beat 覆盖。",
        ],
        limit=14,
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
    brief.board_style_rules = _append_unique(brief.board_style_rules, WHITEBOARD_BOARD_RULES + STYLE_STRATEGY_RULES, limit=20)
    brief.layout_principles = _append_unique(brief.layout_principles, WHITEBOARD_LAYOUT_PRINCIPLES, limit=16)
    if brief.recommended_board_mode not in {"whiteboard", "chalkboard", "clean_canvas", "reference"}:
        brief.recommended_board_mode = "whiteboard"
    if brief.recommended_hand_usage not in {"trace", "annotate", "none"}:
        brief.recommended_hand_usage = "trace"
    if brief.recommended_visual_style not in {
        "teacher_whiteboard",
        "marketing_doodle",
        "math_chalkboard",
        "technical_reference",
    }:
        brief.recommended_visual_style = "teacher_whiteboard"
    if not brief.recommended_scene_outline:
        brief.recommended_scene_outline = _fallback_brief(req).recommended_scene_outline

    blob = _request_blob(req)
    blob_lower = blob.lower()
    chalkboard_math_signals = [
        "数学",
        "解题",
        "推导",
        "证明",
        "integral",
        "积分",
        "derivative",
        "导数证明",
        "geometry",
        "几何证明",
        "iit",
    ]
    marketing_signals = ["广告", "营销", "产品", "推广", "brand", "marketing", "ad ", "ads", "golpo", "landing"]
    if any(signal in blob_lower for signal in chalkboard_math_signals):
        brief.recommended_board_mode = "chalkboard"
        brief.recommended_hand_usage = "none"
        brief.recommended_visual_style = "math_chalkboard"
    elif any(signal in blob_lower for signal in marketing_signals):
        brief.recommended_board_mode = "clean_canvas"
        brief.recommended_hand_usage = "annotate"
        brief.recommended_visual_style = "marketing_doodle"
    if _is_gradient_topic(blob):
        brief = _ensure_gradient_brief(brief)
    if _is_cooking_topic(blob):
        brief = _ensure_cooking_brief(brief, req)
    brief = _ensure_teaching_coverage_brief(brief, req)
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


def _topic_tokens(text: str) -> list[str]:
    tokens = re.findall(r"[A-Za-z0-9_]+|[\u3400-\u9fff]{2,}", text)
    stop = {
        "讲解",
        "一个",
        "通用",
        "必须",
        "包含",
        "理解",
        "核心",
        "过程",
        "问题",
        "框架",
        "the",
        "and",
        "with",
        "for",
    }
    return [token.lower() for token in tokens if token.lower() not in stop and len(token) >= 2]


def _graph_looks_off_topic(graph: ExplainGraph, req: GenerateGraphRequest) -> bool:
    request_text = _request_blob(req)
    graph_text = _graph_blob(graph)
    if _looks_corrupted_text(graph_text):
        return True
    if _is_semiconductor_topic(graph_text) and not _is_semiconductor_topic(request_text):
        return True
    if _is_gradient_topic(graph_text) and not _is_gradient_topic(request_text):
        return True
    if _is_cooking_topic(request_text) and not _contains_any_text(graph_text, COOKING_GRAPH_TERMS):
        return True
    request_tokens = set(_topic_tokens(request_text))
    if not request_tokens:
        return False
    graph_tokens = set(_topic_tokens(graph_text))
    overlap = request_tokens & graph_tokens
    return len(overlap) == 0 and len(request_tokens) >= 3


def _fallback_graph_from_brief(req: GenerateGraphRequest, brief: EnhancedTeachingBrief) -> ExplainGraph:
    if _is_cooking_topic(_request_blob(req)):
        brief = _ensure_cooking_brief(brief, req)
    topic = _clean(req.prompt)
    units = list(brief.teaching_coverage_units or [])
    nodes: list[ConceptNode] = []
    for index, unit in enumerate(units[:8]):
        label = _clean(unit.label)
        if not label:
            continue
        nodes.append(
            ConceptNode(
                id=f"node_{index}",
                label=label[:36],
                node_type=_node_type_for_unit(unit),
                description=_clean(unit.teaching_goal or unit.narration_focus) or f"讲清楚 {label} 的含义、关系和结论。",
                teach_order=index,
            )
        )
    if not nodes:
        for index, item in enumerate((brief.core_explanation_chain or [topic])[:5]):
            nodes.append(
                ConceptNode(
                    id=f"node_{index}",
                    label=(item[:28] if item else f"步骤 {index + 1}"),
                    node_type=NodeType.PROCESS,
                    description=item or f"讲清楚 {topic} 的关键步骤。",
                    teach_order=index,
                )
            )
    graph = ExplainGraph(
        topic=topic,
        summary=_clean(brief.core_explanation_chain[0] if brief.core_explanation_chain else "") or f"围绕 {topic} 建立清晰的解释路径。",
        nodes=nodes,
        edges=[],
        key_insights=_append_unique([], brief.must_include_points or [topic], limit=12),
        enhanced_brief=brief,
    )
    _ensure_chain_edges(graph)
    return graph


def _is_problem_solving_framework_request(req: GenerateGraphRequest) -> bool:
    text = _request_blob(req)
    lowered = text.lower()
    if re.search(r"通用.{0,8}问题.{0,8}(解决|求解|处理).{0,8}框架", text):
        return True
    if "问题" in text and "框架" in text and any(term in text for term in ["解决", "求解", "处理"]):
        return True
    if "problem" in lowered and ("solving" in lowered or "solve" in lowered) and "framework" in lowered:
        return True
    groups = [
        ["通用问题解决框架", "问题解决框架", "解决问题框架", "问题处理框架", "framework"],
        ["问题", "解决", "求解", "处理"],
        ["全局地图", "建立全局", "全局", "地图"],
        ["取舍", "取舍矩阵", "矩阵", "方案"],
        ["目标路径", "里程碑", "倒推", "终点"],
        ["反馈闭环", "闭环", "反馈", "持续改进"],
        ["问题解决", "解决问题", "problem solving"],
        ["全局地图", "地图", "overview"],
        ["取舍", "矩阵", "tradeoff", "matrix"],
        ["目标路径", "里程碑", "倒推", "goal path"],
        ["反馈闭环", "闭环", "反馈", "feedback"],
    ]
    return sum(1 for group in groups if _contains_any_text(text, group)) >= 3


def _problem_solving_framework_graph(req: GenerateGraphRequest, brief: EnhancedTeachingBrief) -> ExplainGraph:
    topic = "通用问题解决框架"
    specs = [
        ("全局地图", "先把问题、目标、约束和相关对象放到同一张图里，避免一上来就钻进细节。", NodeType.CONCEPT),
        ("结构拆解", "把大问题拆成对象、关系、边界和关键变量，找到真正能动手处理的部位。", NodeType.PROCESS),
        ("过程拆解", "把变化拆成输入、动作、输出和关键转折，说明结果是怎么一步步发生的。", NodeType.PROCESS),
        ("取舍矩阵", "用二维标准比较方案，把资源放到最能改变结果的位置。", NodeType.EXAMPLE),
        ("目标路径", "从终点倒推里程碑和下一步行动，让努力不偏航。", NodeType.PROCESS),
        ("反馈闭环", "把每次结果变成下一轮调整依据，让框架越用越准。", NodeType.CONCLUSION),
    ]
    nodes = [
        ConceptNode(id=f"node_{index}", label=label, node_type=node_type, description=description, teach_order=index)
        for index, (label, description, node_type) in enumerate(specs)
    ]
    graph = ExplainGraph(
        topic=topic,
        summary="一个可复用的问题解决框架：先看全局，再拆结构和过程，用矩阵做取舍，从目标倒推行动，并靠反馈闭环持续修正。",
        nodes=nodes,
        edges=[],
        key_insights=[
            "先建立全局地图，避免局部忙乱。",
            "结构拆解负责看清组成和关系，过程拆解负责看清变化链条。",
            "取舍矩阵让方案比较从吵架变成定位。",
            "目标路径用终点倒推里程碑和下一步。",
            "反馈闭环把结果带回下一轮改进。",
        ],
        enhanced_brief=brief,
    )
    _ensure_chain_edges(graph)
    return graph


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


def _node_type_for_unit(unit: TeachingCoverageUnit) -> NodeType:
    value = (unit.unit_type or unit.visual_role or "").lower()
    if any(term in value for term in ["formula", "equation"]):
        return NodeType.FORMULA
    if any(term in value for term in ["process", "state", "change", "mechanism", "flow", "step", "interaction", "goal_path", "cycle", "feedback"]):
        return NodeType.PROCESS
    if any(term in value for term in ["example", "case", "analogy", "comparison", "tradeoff", "matrix"]):
        return NodeType.EXAMPLE
    if any(term in value for term in ["summary", "conclusion", "takeaway"]):
        return NodeType.CONCLUSION
    return NodeType.CONCEPT


def _ensure_teaching_coverage_graph(graph: ExplainGraph, brief: EnhancedTeachingBrief) -> None:
    units = list(brief.teaching_coverage_units or [])
    if not units:
        return
    for unit in sorted(units, key=lambda item: (-item.priority, item.id)):
        label = _clean(unit.label)
        if not label:
            continue
        description = _clean(unit.teaching_goal or unit.narration_focus) or f"讲清楚 {label} 的含义、过程和结论。"
        if unit.must_show:
            description = f"{description} 画面必须出现：{'、'.join(unit.must_show[:5])}。"
        _ensure_node(graph, label, description, _node_type_for_unit(unit))
    graph.key_insights = _append_unique(graph.key_insights, [unit.label for unit in units], limit=24)


def _ensure_graph_quality(graph: ExplainGraph, req: GenerateGraphRequest, brief: EnhancedTeachingBrief) -> ExplainGraph:
    if len(graph.nodes) < 3:
        for index, item in enumerate(brief.core_explanation_chain[:5]):
            _ensure_node(graph, f"步骤 {index + 1}", item, NodeType.PROCESS)

    request_blob = _request_blob(req)
    if _is_gradient_topic(request_blob):
        _ensure_gradient_graph(graph)
    _ensure_teaching_coverage_graph(graph, brief)

    graph.key_insights = _append_unique(graph.key_insights, brief.must_include_points, limit=24)
    _ensure_chain_edges(graph)
    graph.nodes = sorted(graph.nodes, key=lambda item: item.teach_order)
    return graph


async def generate_explain_graph(req: GenerateGraphRequest) -> ExplainGraph:
    await check_llm_connection()
    brief = await enhance_prompt(req)
    if _is_problem_solving_framework_request(req):
        graph = _problem_solving_framework_graph(req, brief)
        logger.info("Graph generated from problem-solving framework fallback: %d nodes, %d edges", len(graph.nodes), len(graph.edges))
        return graph

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
    if _graph_looks_off_topic(graph, req):
        logger.warning("LLM graph drifted off requested topic; rebuilding graph from teaching brief")
        graph = _fallback_graph_from_brief(req, brief)
        logger.info("Graph generated from brief fallback: %d nodes, %d edges", len(graph.nodes), len(graph.edges))
        return graph

    graph = _ensure_graph_quality(graph, req, brief)
    logger.info("Graph generated: %d nodes, %d edges", len(graph.nodes), len(graph.edges))
    return graph
