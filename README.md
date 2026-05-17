# ExplainFlow

ExplainFlow 是一个面向教学讲解视频的本地化生成工具。当前目标是把用户输入的主题或参考图，生成带旁白、手部画笔、逐笔书写/绘制过程的白板讲解视频。

## 当前状态

- MVP 主链路已打通：主题输入 -> 知识图谱/故事板 -> 旁白 -> Remotion 动画 -> MP4。
- 渲染路线已改造为 Remotion + LLM，不依赖模板库或组件库。
- 白板动画已从“重画 SVG 线条”升级为“保留原图像素质量 + 路径遮罩逐笔揭示 + 手部跟随中心线”。
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

### 4. 编码与质量

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

## 2026-05-17 提示词增强与课堂板书感

- 在 Explain Graph 前新增 `EnhancedTeachingBrief`：短提示词会先被扩写成受众、学习目标、因果链、必讲点、视觉类比和推荐场景。
- Storyboard 增加 `learning_goal`、`diagram_plan`、`visual_beats`，让“正在画什么”和“此时说什么”绑定，减少图没画完旁白先结束的问题。
- 目标时长改为硬约束：最终 storyboard 会按用户设置的 60-180 秒缩放到目标时长，例如 120 秒会输出约 120 秒。
- 本地 Remotion 编译器会把每个场景的 `drawOps` 重新排布到接近场景末尾，减少场景间静态等待。
- 教学色彩从黑白线稿升级为有限彩色板书：红色表示电流/流动，蓝色表示电压/控制，绿色表示导通沟道，紫色表示栅极/结构，黄色表示重点下划线和 callout。
- MOS/FinFET 有确定性教学兜底：Off/On 对比、`V_G > V_th`、反型沟道、`V_DS` 电流、短沟道效应、三面栅控、`W_eff = 2H_fin + W_fin`。
- 视频库支持多选批量删除。
