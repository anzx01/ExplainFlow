# Golpo 风格视频生成开发计划

日期：2026-05-20

## 背景

用户希望 ExplainFlow 学习 Golpo Canvas 风格体系，并把这次修复沉淀为稳定默认能力：

- 生成前让用户选择视频风格。
- 默认不展示 explain 图谱，直接生成 Storyboard。
- 旁白贴题，不描述绘图动作。
- 中文自然转译，避免英文硬翻。
- 音频可靠。
- 白板图形更丰富，必须调用火山方舟文生图生成彩色主体图。
- 图形由文生图模型生成，文字、标签、动态标注由渲染端模拟手写叠加。
- 生成后自动检查问题并修复。

参考资料：

- Golpo Canvas Styles Guide: https://video.golpoai.com/guide/golpo-canvas-styles-guide
- 8 个风格视频样本已下载并制作 contact sheet，详见 `docs/golpo-canvas-style-notes.md`。

## 产品目标

1. 用户输入主题后，系统直接产出可编辑 Storyboard，不展示内部 explain 图谱。
2. 生成前提供 8 种 Canvas Visual Style 选择：
   - Chalkboard Black & White
   - Chalkboard Color
   - Modern Minimal
   - Technical
   - Editorial
   - Whiteboard
   - Playful
   - Sharpie
3. Pen-in-hand Animation 作为独立动画层，可与视觉风格组合：
   - Marker
   - Pen Style
   - Stylus
   - No Hand
4. 默认风格为 `whiteboard + marker`，优先图文并茂、彩色主体、手写标注。
5. 复杂主体用文生图直接生成，渲染端只负责标题、短标签、箭头、圈选、下划线和局部标注。
6. 自动 QA 要覆盖：画面丰富度、文字大小、标注位置、音频存在、视频是否空白、中文自然度。

## 架构方案

### 1. 前端

涉及文件：

- `apps/web/src/components/studio/LeftPanel.tsx`
- `apps/web/src/app/studio/page.tsx`
- `apps/web/src/lib/constants.ts`
- `apps/web/src/lib/types.ts`
- `apps/web/src/lib/api.ts`

任务：

- 在生成设置中展示 8 个 Canvas Visual Style。
- 展示 Pen-in-hand Animation 选择器。
- 默认选择 `whiteboard` 和 `marker`。
- 调用 `/planner/storyboard` 时传入 `video_style` 和 `pen_style`。
- 文案从“概念 Prompt”调整为更通用的“视频主题”。
- 不再在 Studio 主流程展示 ExplainGraphView。

验收：

- UI 中主风格正好是 8 个，不混入“智能推荐”作为第 9 个按钮。
- 选择风格后重新生成 Storyboard。
- Storyboard 页能显示 `video_style` 和 `pen_style`。

### 2. Planner

涉及文件：

- `services/api/src/planner/models.py`
- `services/api/src/planner/service.py`

任务：

- `GenerateStoryboardRequest` 支持 `video_style`、`pen_style`。
- `Scene` 和 `Storyboard` 保留 `video_style`、`pen_style`。
- 建立 8 种 Golpo 风格 preset。
- 保留旧 style id 的 alias 兼容：
  - `colorful_story`、`teacher_whiteboard`、`howto_demo` -> `whiteboard`
  - `math_chalkboard` -> `chalkboard_color`
  - `technical_reference` -> `technical_blueprint`
- `visual_style` 继续作为内部渲染语法，不能再代替 8 种 Canvas style。
- storyboard prompt 明确：
  - `image_description` 必须 text-free。
  - 可读文字由渲染端叠加。
  - 旁白禁止描述绘图动作。
  - 英文概念必须自然转译成中文。

验收：

- 每个 scene 都有 `video_style` 和 `pen_style`。
- `chalkboard_bw` 和 `chalkboard_color` 不会在 image prompt 中混淆。
- Whiteboard 风格下抽象/烹饪主题不会退化为黑白线稿。
- “interdependence”等英文概念不会生成“互赖”。

### 3. Image Generation

涉及文件：

- `services/api/src/imagegen/router.py`
- `services/api/src/imagegen/service.py`
- `apps/render/server.mjs`

任务：

- `/imagegen/scenes` 接收 `video_style`、`pen_style`。
- image prompt 按 8 种风格分别生成：
  - `chalkboard_bw`：纯黑板 + 白粉笔，无彩色。
  - `chalkboard_color`：黑板 + 白/青粉笔 + 少量黄/青强调。
  - `modern_minimal`：浅灰画布 + 细线 + 单一冷色强调。
  - `technical_blueprint`：深蓝图纸 + 浅蓝精密线稿。
  - `editorial`：米白画布 + 粗黑线 + 红橙强调 + collage。
  - `whiteboard`：白板 + 黑 marker + 蓝色标签 + 小面积彩色填充。
  - `playful`：奶油色背景 + 蜡笔质感 + 多彩柔和对象。
  - `sharpie`：亮白背景 + 粗黑 Sharpie + 少量荧光笔强调。
- 对烹饪主题追加领域约束：
  - 麻婆豆腐必须有红油、白豆腐、肉末、绿色葱蒜苗、蒸汽。
  - 炒/烧/勾芡默认宽口黑炒锅或平底锅。
  - 禁止蓝色汤锅、空锅、灰白无色菜品。

验收：

- 生成“如何制作好吃的麻婆豆腐，要求图文并茂”时，至少大部分场景走火山方舟文生图。
- 图中主体足够大、有真实食物色彩，不是小图标流程图。
- 图片不含可读乱字；标题和标签由渲染端写。

### 4. Remotion Render

涉及文件：

- `apps/render/server.mjs`
- `services/api/src/planner/service.py` 中 fallback Remotion compiler

任务：

- 渲染端识别 `video_style`。
- 生成 Seedream 参考图时把 `video_style` 传给 Python API。
- `technical_blueprint`、`editorial`、`whiteboard`、`playful`、`sharpie` 默认优先 direct/hybrid 呈现复杂主体。
- 只有简单线稿才 trace。
- 动态标注必须使用大字号、短标签，位置靠近目标对象。
- 避免长箭头乱指、圈选覆盖主体、标签过小。

验收：

- `sharpie` 风格有粗黑 marker 和真实手写感。
- `technical_blueprint` 是深蓝背景，不被白板背景覆盖。
- `playful` 是奶油色和蜡笔色，不变成普通白板。
- 复杂文生图最终出现在视频里，不被简化 SVG 替换。

### 5. Audio Reliability

涉及文件：

- `apps/render/server.mjs`
- TTS/audio injection 相关模块

任务：

- 每个 scene 生成音频后校验文件存在、时长大于 0。
- `audioSegments` 与 visual beats 对齐。
- Remotion 生成代码必须包含所有 scene/audio segment 的 Audio。
- 若缺音频，进入 retry 或 fallback，不允许静默产出无声视频。

验收：

- 渲染前能列出缺失音轨并阻断。
- 渲染完成视频有可听旁白。
- Storyboard 的总时长与实际音频时长接近。

### 6. 自动检查与修复

新增建议：

- `scripts/qa_render_output.py`
- 或在 render job 后置阶段加入 QA。

检查项：

- 视频是否非空白。
- 是否有音轨。
- 每个 scene 是否有 reference image 或足够复杂图形。
- 文本大小是否低于阈值。
- 标注箭头终点是否落在主体附近。
- image prompt 是否包含 text-free。
- cooking topic 是否包含正确锅具和菜品颜色关键词。
- 中文是否包含硬翻黑名单：`互赖` 等。

修复策略：

- 缺图：重新调用 imagegen，并提高 direct/hybrid 权重。
- 缺音频：重试 TTS。
- 文本过小：提高字号，减少标签数量。
- 标注偏移：改为短 callout、边缘 tick、局部下划线。
- 图形单调：补充主体对象、颜色、材料、场景状态。

## 阶段计划

### P0：当前收口

- 完成 `video_style`、`pen_style` 全链路传递。
- 完成 8 风格 prompt 分支。
- 完成前端 8 风格选择器。
- 跑后端编译和前端 build。

### P1：提示词库稳定化

- 把 8 种 Golpo 风格抽象成共享 prompt preset。
- 避免 planner、imagegen、render 三处重复写散。
- 为每个风格准备正向 prompt、负向 prompt、布局规则、色彩规则。

### P2：样例回归

必须固定测试以下主题：

- `如何制作好吃的麻婆豆腐，要求图文并茂`
- `高效能人士的七个习惯`
- `梯度下降原理`
- `MOSFET 工作原理`
- `给投资人讲一个 SaaS 产品如何增长`

每个主题至少测试 `whiteboard`、`editorial`、`technical_blueprint`、`sharpie` 四种风格。

### P3：自动 QA

- 加入视频后验收脚本。
- 支持失败项自动重试或生成修复建议。
- 把 QA 结果写入 render job status。

### P4：用户可控修复

- Storyboard 页增加“重新生成本场图片”“重新配音本场”“修复标注位置”按钮。
- 保留用户编辑过的旁白和标签，不被自动修复覆盖。

## 验收清单

- 用户不再看到 explain 图谱。
- Storyboard 生成前必须能选风格。
- 默认 `whiteboard + marker`。
- 火山方舟文生图会被调用，并且生成的彩色主体图进入最终视频。
- 旁白不说“这里画/先画/再画/标出”等绘图动作。
- 中文自然，不出现“互赖”这类硬翻。
- 麻婆豆腐视频里的锅和菜有颜色、有食欲、主体足够大。
- 动态标注指向正确区域，文字足够大。
- 视频有声音。
- 生成后有自动检查，不合格能修复或阻断。

## 验证命令

```bash
python -m compileall services/api/src
npm run build --workspace apps/web
```

如果本地不是 npm workspace，则在 `apps/web` 下运行：

```bash
npm run build
```

## 风险

- 仅靠 prompt 不能完全保证图像模型不生成乱字，需要负向 prompt 和渲染端覆盖双保险。
- Direct image 的标注坐标不掌握内部物体精确位置，应该使用短 callout 和边缘标注，不做长距离精准箭头。
- 过度 trace 复杂图会导致画面碎、慢、单调，应优先 direct/hybrid。
- 音频和画面时长不一致会造成静音或截断，需要以后置 QA 阻断。
- 旧 storyboard 或旧接口仍可能只带 `visual_style`，需要 alias 兼容一段时间。
