# ExplainFlow

ExplainFlow 是一个面向教学讲解视频的本地化生成工具。当前目标是把用户输入的主题或参考图，生成带旁白、手部画笔、逐笔书写/绘制过程的白板讲解视频。

## 当前状态

- MVP 主链路已打通：主题输入 -> 知识图谱/故事板 -> 旁白 -> Remotion 动画 -> MP4。
- 渲染路线已改造为 Remotion + LLM，不依赖模板库或组件库。
- 白板动画已从“重画 SVG 线条”升级为“保留原图像素质量 + 路径遮罩逐笔揭示 + 手部跟随中心线”，并支持复杂图直接呈现后手写标注。
- Storyboard 已加入 `board_mode`、`hand_usage`、`visual_style`，可在白板手写、彩色 doodle 标注、黑板无手推导、复杂参考图讲解之间切换。
- 当前重点已从“修某个具体主题”转向“通用教学视频质量规则”：按教学关系、信息密度、讲画同步和呈现策略做统一判断，避免继续为单个题材词打补丁。
- 前端已显示渲染阶段与预计剩余生成时间。
- 最近一次 `outputs/images` 全量 raster reveal e2e：36 张图片全部通过；测试产物已清理。

## 技术路线

### 1. 内容规划

- `services/api` 使用 FastAPI 提供规划、旁白、渲染任务和健康检查接口。
- LLM 负责生成讲解内容、场景结构、讲解文字和 Remotion 动画代码。
- `/health/llm?force=true` 用于强制检查大模型连通性；渲染前会先做 LLM 健康检查，失败则停止后续 TTS/codegen/render。

### 2. Remotion 渲染

- `apps/render/server.mjs` 使用 `@remotion/bundler` 和 `@remotion/renderer` Node API 渲染，不走 Remotion CLI。
- 每个任务生成独立 `apps/render/generated/<jobId>` 项目，再 bundle 并输出 MP4。
- 生成代码必须导出 `GeneratedVideo`，只允许受控导入和受控 `staticFile()` 资产。
- 禁止模板库、组件库、CSS animation、SVG animate、任意文件读写、网络 fetch 等不稳定行为。

### 3. 原图逐笔揭示

当前白板图像方案不是把原图边缘重画成 SVG，而是：

1. 用 `sharp` 从本地参考图提取深色线稿，并去掉黄色/纸张背景，生成透明 PNG 线稿资产。
2. 对线稿 mask 做清理和骨架化，得到笔画中心线。
3. 将中心线按端点、交叉点、闭环和空间顺序切成约 120-150 条 stroke。
4. Remotion 中用 SVG `<mask>` 逐条打开原图透明线稿 `<image>`。
5. `HandPen` 使用同一批中心线 `drawOps`，通过 `pointOnPolyline()` 让笔尖沿当前笔画移动。
6. 绘制完成后淡出 masked SVG 图层，淡入 HTML `<Img>` 最终图层，保证末帧接近原始清晰线稿。

这样可以避免旧方案中的空心字、缺笔画、圆圈锯齿和末帧覆盖不完整问题。

### 4. 绘制策略抽象

系统不按具体学科名词决定画法，而按“老师能否舒服地逐笔画完”选择策略：

- `trace`：结构简单、元素少、可分解为少量板书步骤的图，逐笔揭示原图线稿。
- `direct`：特别复杂、密集、多层、实物/参考图/成品图，直接呈现主体，再手写重点标注。
- `hybrid`：主体复杂但仍需要教学强调，直接呈现主体，后续用画笔写箭头、圈、下划线和局部 callout。

渲染端会综合 `render_strategy`、`visual_complexity`、标签数量、visual beat 数量、线稿骨架像素数、mask 覆盖率和路径数量做决策。目标是让简单图像参考视频一样实时写画，复杂图避免成百上千笔乱跳。

同时每个场景会携带课堂表达字段：

- `board_mode=whiteboard`：浅灰白板，适合老师逐步讲结构、机制、流程、对比。
- `board_mode=clean_canvas`：干净浅色画布，适合彩色 doodle、产品/营销说明，主体可直接出现。
- `board_mode=reference`：复杂参考图、三维结构、医学/机械/电路等，主体直接或混合呈现，手只标注重点。
- `board_mode=chalkboard`：深色黑板，适合数学推导/解题，`hand_usage=none`，公式按行显现。
- `hand_usage=trace|annotate|none`：分别表示逐笔写画、只做局部标注、无手逐步显现。
- `visual_style=teacher_whiteboard|marketing_doodle|math_chalkboard|technical_reference`：表达视觉语法，不引入模板库。

### 5. 教学关系视觉语法

当前规则不再围绕某个具体题材打补丁，而是先把用户提示词和增强 brief 抽象成“这一场要讲清的关系”，再决定画面：

- `overview_map`：主题下有多个对象、单元或阶段，先给全局地图。
- `comparison`：讲前后、开关、A/B、旧新、好坏或状态变化，用双图对比。
- `process`：讲因果链、机制、流程、变化过程，用原因 -> 过程 -> 结果。
- `structure`：讲组成、层级、整体和局部，用主体图、贴近标签和局部放大。
- `interaction`：讲对象之间互相影响、沟通、协作、交换或反馈，用节点和双向箭头。
- `tradeoff_matrix`：讲优先级、取舍、二维判断或分类，用坐标/四象限/2x2 矩阵。
- `goal_path`：讲目标、路线、里程碑、倒推或成长路径，用起点到终点路径图。
- `cycle`：讲迭代、复盘、更新、闭环，用环形箭头和 3-5 个节点。
- `formula`：讲公式含义，用公式、变量 callout 和小示意图。
- `reference_callout`：复杂主体需要保真时直接呈现，再用 2-4 个局部 callout 讲重点。
- `summary`：收束时用少量清单、闭环或框架图，不写长段落。

### 6. 参考样片抽象规则

已从 `whiteboard-style-1.mp4`、`ads-marketing-demo.mp4`、`iit-math-q5-solution.mp4` 抽象出通用课堂视频规则，并写入 prompt、Seedream 图像提示和 Remotion 本地编译器：

- 一屏一个核心想法，顶部短蓝色手写标题，主体图居中或略偏右。
- 主体图占画面约 45%-65%，四周保留大面积空白给手和后续标注。
- 黑色主体线为主，蓝色用于标题/控制关系，红色用于电流/风险/错误，绿色用于有效路径/正确结果，黄色只做短下划线或局部强调。
- 不使用固定左侧说明栏、长段落、海报式信息图、卡片、图例框或彩色背景块。
- 简单图逐笔 trace；复杂图直接呈现清晰主体，再用 2-4 个老师式 callout 讲重点。
- 营销/产品类视频允许彩色成品 doodle 或界面主体直接出现，手部只补标题、勾选、箭头、下划线和少量短标注。
- 数学/公式推导类视频允许无手黑板模式：深色背景、白色主式、cyan/green 变量、yellow 结论、pink/red 条件，按行推进并保留上下文。
- 所有题材共用上面的视觉语法：视频质量问题优先归因到“关系没有抽对、beat 没对齐、图像策略不合适”，而不是继续为单个主题写专门规则。

### 7. 通用质量审查规则

最新质量目标不是把某类内容写成专门分支，而是把失败现象抽象成可复用规则：

- **关系覆盖**：用户提示词或增强 brief 中出现的核心教学关系必须被实际场景覆盖，例如全局地图、结构拆解、对比、过程、取舍矩阵、目标路径、反馈循环和总结。压缩场景数量时不能因为保留 summary 而丢掉关键关系。
- **一屏一事**：每个 scene 只推进一个核心理解任务；复杂内容拆成多个 visual beat，不把整页报告、长段落或密集信息图塞到一屏。
- **讲画同窗**：每个 visual beat 的旁白、字幕、TTS 和 drawOps 应落在同一个时间窗；如果图没画完或旁白没讲完，不应该切到下一场。
- **呈现策略匹配**：简单结构、流程、对比和公式适合逐笔 trace；复杂主体、密集参考图、多层结构、成品插图适合 direct/hybrid，先清楚呈现主体，再做少量老师式标注。
- **字幕完整**：字幕来自解说词，但必须按完整句或完整短句显示，不能被机械截断成半句话。
- **中文编码健康**：所有进入 TTS、字幕、文件名、任务列表和 Remotion 的中文必须保持 UTF-8；一旦出现 mojibake，应先修复编码链路，再评估画面质量。
- **画面有趣但克制**：用结构图、过程图、对比图、箭头、圈选、下划线、局部放大和少量颜色表达意义，避免单调方框，也避免装饰性堆砌。
- **连续播放**：场景之间像连续板书推进，不留明显空白停顿；上一场完整收尾后再进入下一场。

### 8. 编码与质量

- Remotion 帧格式使用 PNG，减少线稿边缘中间态损失。
- H.264 默认使用 `yuv444p`，对密集黑白线稿比 `yuv420p` 更稳定。
- 默认 CRF 为 8，可通过 `REMOTION_CRF` 调整。
- 参考图资产默认按最终展示尺寸附近生成，减少浏览器二次缩放造成的边缘偏差。
- `sharp` 使用宽容读取处理截断 JPEG，避免个别损坏图片导致本地图链路失败。

## 启动方式

Windows 一键启动：

```bat
scripts\start.bat
```

或分别启动：

```bash
bash scripts/dev-api.sh     # http://localhost:8000
bash scripts/dev-web.sh     # http://localhost:3000
bash scripts/dev-render.sh  # http://localhost:3001
```

## 主要目录

| 路径 | 说明 |
|------|------|
| `services/api` | FastAPI 服务，负责规划、旁白、Remotion codegen、LLM 健康检查 |
| `apps/web` | Next.js 前端，含故事板页、任务页、渲染进度和预计剩余时间 |
| `apps/render` | Remotion 渲染服务、图像 tracing、任务 bundle/render |
| `outputs/images` | Seedream 或测试生成的参考图片 |
| `discuss/开发进度.md` | 开发进度和技术方案记录 |
| `evals` | 评测脚本与数据 |

## 最近验证

- `node --check apps/render/server.mjs`
- `python -m compileall services/api/main.py services/api/src`
- `outputs/images` 全量 raster reveal e2e：36/36 pass
- 2026-05-19 通用问题解决框架隔离 e2e 生成成功，MP4 时长 141.6 秒，音视频流可被 `ffprobe` 正常读取；抽帧审查发现仍存在中文乱码、目标路径关系被压缩掉、字幕/标题质量不稳定等共性问题，已记录为下一轮优先修复项。

## 2026-05-19 通用质量规则沉淀

- 不再围绕“行为/原则/习惯类”等具体词做特殊处理；这些问题统一抽象为“多概念框架型教学视频”的共性要求：先给全局地图，再按关系拆分为结构、过程、对比、取舍、目标路径、反馈循环和总结。
- 场景裁剪和压缩不能只按数量截断，必须优先保留用户提示中明确要求的核心教学关系；summary 不能替代目标路径、过程模拟或反馈循环。
- 旁白压缩必须保持完整句，字幕也必须跟随完整句；短视频可以减少例子数量，但不能生成半句字幕或半句旁白。
- 当前生成链路已能产出多种视觉语法，但质量审查显示还需要补“关系覆盖优先级”和“中文编码健康检查”两类保护规则。
- 最新测试文件：`outputs/*_b8a338c2.mp4`。结论：渲染链路可用，视频还未达到目标样片质量，下一步应优先修复编码、关系覆盖和 beat 同步。

## 2026-05-18 多风格课堂语法

- 参考三支样片后，新增场景级 `board_mode`、`hand_usage`、`visual_style`。
- 新增通用 `diagram_plan.kind` 视觉语法：`overview_map`、`comparison`、`process`、`structure`、`interaction`、`tradeoff_matrix`、`goal_path`、`cycle`、`formula`、`reference_callout`、`summary`。
- Prompt enhancement 会自动识别数学推导、营销 doodle、复杂参考图和普通白板机制讲解，并输出对应 visual strategy。
- Storyboard schema 和 Remotion codegen prompt 已要求每场选择呈现方式，避免所有场景都强行“手逐笔画完整图”。
- 本地 Remotion 编译器支持黑板无手逐行推导，并在白板/参考图场景继续保留 `HandPen` 跟随路径能力。
- Seedream 图像提示按场景风格切换：白板线稿、营销彩色 doodle、复杂技术参考图、黑板推导分别有不同 prompt suffix。

## 2026-05-17 提示词增强与课堂板书感

- 在 Explain Graph 前新增 `EnhancedTeachingBrief`：短提示词会先被扩写成受众、学习目标、因果链、必讲点、视觉类比和推荐场景。
- Storyboard 增加 `learning_goal`、`diagram_plan`、`visual_beats`，让“正在画什么”和“此时说什么”绑定，减少图没画完旁白先结束的问题。
- 目标时长改为硬约束：最终 storyboard 会按用户设置的 60-180 秒缩放到目标时长，例如 120 秒会输出约 120 秒。
- 本地 Remotion 编译器会把每个场景的 `drawOps` 重新排布到接近场景末尾，减少场景间静态等待。
- 教学色彩从黑白线稿升级为有限彩色板书：红色表示电流/流动，蓝色表示电压/控制，绿色表示导通沟道，紫色表示栅极/结构，黄色表示重点下划线和 callout。
- MOS/FinFET 有确定性教学兜底：Off/On 对比、`V_G > V_th`、反型沟道、`V_DS` 电流、短沟道效应、三面栅控、`W_eff = 2H_fin + W_fin`。
- 视频库支持多选批量删除。
