# ExplainFlow

ExplainFlow 是一个面向教学讲解视频的本地化生成工具。当前目标是把用户输入的主题或参考图，生成带旁白、手部画笔、逐笔书写/绘制过程的白板讲解视频。

## 当前状态

- MVP 主链路已打通：主题输入 -> 知识图谱/故事板 -> 旁白 -> Remotion 动画 -> MP4。
- 渲染路线已改造为 Remotion + LLM，不依赖模板库或组件库。
- 白板动画已从“重画 SVG 线条”升级为“保留原图像素质量 + 路径遮罩逐笔揭示 + 手部跟随中心线”，并支持复杂图直接呈现后手写标注。
- Storyboard 已加入 `board_mode`、`hand_usage`、`visual_style`，可在白板手写、彩色 doodle 标注、黑板无手推导、复杂参考图讲解之间切换。
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

### 5. 参考样片抽象规则

已从 `whiteboard-style-1.mp4`、`ads-marketing-demo.mp4`、`iit-math-q5-solution.mp4` 抽象出通用课堂视频规则，并写入 prompt、Seedream 图像提示和 Remotion 本地编译器：

- 一屏一个核心想法，顶部短蓝色手写标题，主体图居中或略偏右。
- 主体图占画面约 45%-65%，四周保留大面积空白给手和后续标注。
- 黑色主体线为主，蓝色用于标题/控制关系，红色用于电流/风险/错误，绿色用于有效路径/正确结果，黄色只做短下划线或局部强调。
- 不使用固定左侧说明栏、长段落、海报式信息图、卡片、图例框或彩色背景块。
- 简单图逐笔 trace；复杂图直接呈现清晰主体，再用 2-4 个老师式 callout 讲重点。
- 营销/产品类视频允许彩色成品 doodle 或界面主体直接出现，手部只补标题、勾选、箭头、下划线和少量短标注。
- 数学/公式推导类视频允许无手黑板模式：深色背景、白色主式、cyan/green 变量、yellow 结论、pink/red 条件，按行推进并保留上下文。

### 6. 编码与质量

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

## 2026-05-18 多风格课堂语法

- 参考三支样片后，新增场景级 `board_mode`、`hand_usage`、`visual_style`。
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
