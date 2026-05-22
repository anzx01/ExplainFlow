import logging

from src.core.visual_prompts import BOLD_EDITORIAL_BOARD_RULES, BOLD_EDITORIAL_LAYOUT_RULES

logger = logging.getLogger(__name__)

DEFAULT_AUDIENCE = "有高中/大学基础理科知识的初学者"

ENHANCE_SYSTEM_PROMPT = """你是一个教学视频 production brief 设计师，任务是把用户很短、很口语化的主题，改写成结构化教学 brief。

核心原则：
1. 用户 prompt 只是意图，不是完整脚本；你要主动补全教学必需的因果链、对比、过程和可视化方案。
2. 内容 brief 与视觉风格分离：这里不写模板，不写组件，只写主题、受众、目标、结构、必须包含内容和可画的画面。
3. 每个关键点必须按"现象 -> 原因 -> 结果 -> 类比/总结"展开，避免只罗列名词定义。
4. 每个核心概念必须能被画出来：结构图、状态对比图、箭头、过程变化、局部放大、截面图优先；少用 bullet list。
5. 如果用户提供参考材料，优先依据参考材料；否则用通用领域知识生成准确、初学者友好的讲解方案。
6. 输出要像给视频团队的 production brief：具体、可画、可同步旁白，不要泛泛描述。
7. 如果用户给的是英文术语、英文书名、英文框架或英文缩写，不要逐词硬翻。先判断中文语境中自然、常用、观众能听懂的说法；没有固定译名时，用"自然中文短语 + 必要英文原词括注"的方式转译。
8. 所有标题、节点、板书标签和旁白都要像中文老师会说的话：宁可解释成自然短语，也不要制造生硬中文词。例：interdependence 不写"互赖"，可写"互相依赖/成熟协作/协作共赢"，按上下文选择。
9. 参考真实老师白板讲解：一屏一个核心想法；顶部蓝色手写标题；主体图居中，占画面 45%-65%；保留大面积空白；文字只写短标签和关键结论。
10. 画面不是信息图海报：不要密集段落、图例框、装饰面板、彩色背景块、卡片式布局或复杂 UI；所有内容都像老师在白板上逐步补出来。
11. 色彩有教学含义：黑色主体线，蓝色标题/控制关系，红色风险/电流/错误，绿色有效路径/正确结果，黄色只做小下划线或局部强调。
12. 复杂图不要强行逐笔画完：如果一张图过密、标签多、像参考图/成品图/多层结构，应建议直接呈现主体，再用少量手写箭头、圈、下划线和局部 callout 讲重点。
13. 不要把所有视频都做成同一种"手一直画完整图"。这里的 visual_style 是内部课堂表达语法；最终 8 种 Golpo Canvas 视觉风格会在 storyboard 阶段由用户选择并覆盖画布、色彩和质感。根据内容选择呈现策略：
    - teacher_whiteboard：像真实白板老师，简单结构、流程、对比、机制图由手逐步写画。
    - marketing_doodle：像产品/营销白板，彩色 doodle 或复杂成品图可以直接出现，手只补标题、箭头、勾选、下划线和少量标注。
    - math_chalkboard：像黑板解题，深色黑板、无可见手，公式和推导按行/按步骤显现，保留上下文，颜色承载变量和结论。
    - technical_reference：复杂实物、参考图、三维结构、医学/机械/电路等，先清楚呈现主体，再逐步强调局部。
14. 对每个场景明确推荐 `board_mode`、`hand_usage`、`visual_style`。这不是模板库，而是课堂表达语法。
15. 不要围绕某个题材词做特殊处理；先抽象出教学关系，再选择画面语法：
    - overview_map：一个主题包含多个对象、单元、阶段或知识点时，先给全局地图。
    - comparison：讲前后、开关、A/B、好坏、旧新、状态变化时，用双图对比。
    - process：讲因果链、机制、流程、变化过程时，用"原因 -> 过程 -> 结果"。
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
2. 节点要服务于"可讲、可画、可同步动画"的视频结构：状态对比、过程变化、结构局部、公式含义、结论。
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

WHITEBOARD_BOARD_RULES: list[str] = [
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

WHITEBOARD_LAYOUT_PRINCIPLES: list[str] = [
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

STYLE_STRATEGY_RULES: list[str] = [
    "board_mode=whiteboard：浅灰白板，适合机制图、状态对比、流程、结构示意；hand_usage 通常为 trace 或 annotate。",
    "board_mode=chalkboard：深色黑板，适合数学推导、公式证明、解题过程；hand_usage=none，文字/公式按行显现。",
    "board_mode=clean_canvas：浅色干净画布，适合营销、产品、概念介绍；hand_usage=annotate，主体可以直接出现。",
    "board_mode=reference：用于复杂参考图、实物图、多层结构；主体 direct/hybrid 呈现，手只做局部标注。",
    "hand_usage=trace：简单图逐笔写画；hand_usage=annotate：主体已在场，只写少量 callout；hand_usage=none：无手逐步显现。",
    "visual_style 是内部课堂表达语法，不是最终画布风格；最终 Golpo Canvas 风格由 storyboard 的 video_style 控制。",
    "visual_style=teacher_whiteboard：稀疏白板课堂；marketing_doodle：彩色成品 doodle + 手部强调；math_chalkboard：黑板粉笔推导；technical_reference：复杂主体 + 精准局部讲解。",
]
