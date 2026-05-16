# ExplainFlow 项目评审与优化方案（v1.0）

> 本文档是对 `../mdd.md`（产品 PRD）和 `../教学视频制作软件.txt`（市场对标功能清单）的评审与修订建议。
> 评审日期：2026-05-16

## Context（为什么做这次评审）

ExplainFlow 当前只有一份 PRD（mdd.md）和一份对标功能清单（教学视频制作软件.txt），尚未进入实现阶段。PRD 提出了一个野心很大的定位 —— "AI Explain Engine"（不是视频生成器，是知识解释引擎）。这个差异化叙事在 pitch 层面足够性感，但落到工程和市场上有几个必须先回答的问题：

1. **定位 vs 用户认知**：用户搜的是"AI 白板讲解视频生成器"，不是"Explain Engine"，叙事太抽象会让用户找不到入口
2. **技术栈选型**：PRD 提了"Explain DSL""Visual Reasoning""Animation Engine"，到底自研还是基于成熟引擎二次封装，决定能不能 6 个月内出第一版
3. **MVP 范围**：PRD 第 13 章说"第一阶段做 STEM 白板讲解"，但 STEM 仍涵盖数学/物理/AI/半导体/编程，太宽
4. **对标差异化**：参考清单里的白板讲解类工具已有 5+ 家在做，ExplainFlow 的护城河"AI Explain Capability"在用户视角能否感知，需要有效性验证

**已与用户对齐的关键决策**：
- ✅ MVP 收窄到 **AI/ML 概念讲解** 单垂直
- ✅ 动画引擎采用 **Remotion + LLM 生成 TSX**（放弃自创 Explain DSL）
- ✅ 首发市场：**国内中文**

---

## 一、市场匹配度分析

### 1.1 对标产品对照（参考清单还原）

参考文档的 29 条功能描述，基本能拼出 4 类竞品：

| 类别 | 代表 | ExplainFlow 的差异化 |
|---|---|---|
| 白板手绘（人工模板）| VideoScribe / Doodly | 它们要手工拖拽，ExplainFlow 主打 LLM 自动规划 |
| 文档转视频（图文拼接）| Pictory / Visla / Lumen5 | 它们做"图片+字幕"拼图，ExplainFlow 做"动态图解" |
| AI 数字人讲解 | Synthesia / HeyGen | 它们做"人脸+语音"，ExplainFlow 做"白板+概念图" |
| 教学动画 / STEM | Manim（开源）/ 3Blue1Brown | Manim 要 Python 编程，ExplainFlow 把编程门槛消除 |

**结论**：差异化定位清晰 —— "LLM 规划的 AI/ML 概念白板动画"。真正对手是 **InVideo AI 的白板模式 + Synthesia 的 STEM 模板 + 国内即梦/智谱的视频能力**，而不是泛 AI 视频工具。

### 1.2 目标用户（MVP 期只盯一类）

✅ **首选：国内 AI/ML 方向的技术博主与培训师**（B 站知识区 UP 主、知乎大 V、AI 课程讲师）
- 内容输出频率高（一周 1-2 条），LTV 高
- 自带传播渠道，视频本身就是广告
- 容忍度高，AI 生成的"草稿"他们会二次剪辑
- **付费路径**：先靠免费版获客，再向培训机构/教育公司销售团队版（B 端付费率更高）

推迟：高校教师（付费意愿低）、企业培训（销售周期长）、教育平台（B2B 决策链长）

### 1.3 国内市场特殊风险与对策

| 风险 | 对策 |
|---|---|
| C 端创作者付费率低 | 免费版获客，**B 端培训机构/MCN 团队版** 为主要变现 |
| 视频平台审核（B 站/抖音）| 仅生成"教学动画"内容风险低，但需准备字体/水印合规 |
| 国内 AI 视频工具同质化（即梦/通义万相等）| 强调"理解深度"和"STEM 准确性"，避开它们擅长的"通用 AI 视频" |
| LLM 出口合规 | 全栈用国内模型，不依赖 OpenAI/Claude（详见 2.3）|
| 中文字体渲染 | 需要内置思源黑体/思源宋体并通过商业授权 |

---

## 二、技术可行性分析

### 2.1 PRD 关键模块的实现难度

| 模块 | 难度 | 方案 |
|---|---|---|
| 内容输入（PDF/PPT/DOCX）| ★★ | PyMuPDF + python-pptx + python-docx，成熟 |
| 内容理解（提取概念/关系）| ★★★ | DeepSeek/Qwen + 结构化 JSON output |
| Explain Graph | ★★★ | 带类型的概念图，存为 JSON，不需要图数据库 |
| Teaching Planner | ★★★★ | LLM prompt 工程 + 评测集；**产品壁垒所在** |
| Visual Reasoning | ★★★★★ | **真正的难点** —— "什么视觉最合适"难稳定 |
| Explain DSL | — | **已放弃**，改用 Remotion 组件库 |
| 动画引擎 | ★★★★ | 用 Remotion，不自研 |
| 旁白引擎 | ★★ | 火山引擎 TTS / Edge-TTS，成熟 |
| 音画同步 | ★★★★ | 旁白先生成 → 测出每段时长 → 反推动画时长 |
| 视频渲染导出 | ★★ | Remotion `@remotion/renderer`（本机或 Lambda）|

### 2.2 动画引擎决策（已对齐）

**采用 Remotion + LLM 生成 TSX 方案**。落地细节：

1. **封装一套受控的组件原语**（在 `apps/render/primitives/`），LLM 只在组件集上组合：
   ```tsx
   <WhiteboardDraw path="..." duration={1.2} />
   <HighlightArrow from="A" to="B" />
   <ParticleFlow source="..." target="..." count={20} />
   <FormulaReveal latex="\nabla L = ..." />
   <ConceptNode id="A" label="梯度" position={[100, 200]} />
   ```
   等价于 DSL，但语法是 LLM 极熟悉的 TSX，调试可直接 hot reload。

2. **LLM 输出格式约束**：用 function calling / JSON Schema 限定输出，再模板化拼成 TSX，避免 LLM 直接产出 broken JSX。

3. **组件库分两层**：
   - 底层原语（绘制/动效/相机）—— 工程团队维护
   - 上层场景模板（"神经网络层"、"梯度下降小球"、"Attention 高亮"）—— 随领域知识沉淀

### 2.3 技术栈（适配国内市场调整）

遵循全局 CLAUDE.md 的硬性要求：

| 层 | 选型 | 国内适配说明 |
|---|---|---|
| 前端 | Next.js 15.4 + React 19 + Tailwind v4 + TS | 部署在国内 CDN（七牛/阿里）|
| 动画引擎 | **Remotion**（React 化的视频引擎）| 需自带中文字体（思源黑体/Noto Sans SC）|
| 后端 | Python 3.11+ + FastAPI + uv | 按 CLAUDE.md 要求 |
| LLM（规划层）| **DeepSeek-V3 / Qwen-Max** | 中文理解强、成本低、合规；保留 Claude 接口做对比评测 |
| LLM（代码生成）| **DeepSeek-Coder / Qwen-Coder** | TSX 生成质量好，比通用模型更稳 |
| TTS | **火山引擎 TTS / 微软 Azure 中文 / Edge-TTS（兜底）** | 中文质量优于 ElevenLabs |
| PDF/PPT 解析 | PyMuPDF + python-pptx | — |
| 视频渲染 | Remotion `@remotion/renderer` | 国内服务器跑，避免出网延迟 |
| 存储 | 阿里 OSS / 腾讯 COS（视频）+ Postgres（元数据）| — |
| 部署 | Docker，国内云（阿里/腾讯/火山）| — |

---

## 三、关键优化建议（按优先级）

### P0 必须改

1. **MVP 收窄到"AI/ML 概念讲解"单一垂直** ✅
   - 第一批支持的题目：梯度下降、反向传播、Attention、Transformer 结构、Embedding、激活函数、Loss 函数、CNN、RNN、Diffusion 原理
   - 这 10 个题目作为"标杆 demo"，每个都打磨到能直接发 B 站

2. **放弃自创 Explain DSL，改 Remotion + LLM 生成 TSX** ✅
   - 节省至少 2 个月研发

3. **第一版只支持 1 种风格（Khan Academy 中文白板）**
   - 三种风格全做会把 prompt 调优时间放大 3 倍

### P1 建议改

4. **强调"AI 草稿 + 人工微调"而不是"一键黑盒"**
   - Storyboard 阶段必须能编辑文案、单场景重生成、调节奏
   - 这是与"那种生成出来就废"的工具的核心差异

5. **Explain Graph 必须暴露给用户**
   - 视频生成前让用户看到"AI 是如何理解这份资料的"
   - 把 PRD 里的"护城河"叙事变成用户可感知价值

6. **音画同步采用"先音后画"策略**
   - 先把旁白文本和节奏调好 → 测出每段时长 → 反推动画时长
   - 比反过来稳定 10 倍

7. **B 端商业模式优先于 C 端订阅**
   - 国内 C 端教育创作者付费率低
   - 直接做培训机构/MCN 团队版（按席位/视频数计费）
   - C 端免费做获客和品牌

### P2 可选

8. **建立 STEM 评测集**
   - 准备 20 个 AI/ML 标杆题目，每次模型/prompt 改动跑一遍人工打分
   - 没有评测集 = 没有质量护城河

9. **MVP 不做 PDF/PPT 输入，只做 Prompt + Markdown**
   - 文档解析是深坑，先把"文字 → 视频"打磨到 90 分，再做"文档 → 视频"

10. **中文字体合规**
    - 思源黑体（SIL OFL，免费可商用）
    - 提前确认其它字体（如阿里普惠/HarmonyOS Sans）授权

---

## 四、修订后的 MVP 范围

| 维度 | 原 PRD | 修订 MVP |
|---|---|---|
| 用户 | STEM 创作者 + 技术博主 + 企业 + 教育平台 | **国内 AI/ML 方向 B 站/知乎技术博主** |
| 输入 | Prompt + PDF + PPT + DOCX + MD + URL | **Prompt + Markdown** |
| 输出风格 | Khan Academy / Technical Minimal / Data Storytelling | **仅 Khan Academy 中文白板** |
| 动画类型 | 白板 + STEM + Data | 白板 + 简单 STEM（公式/箭头/粒子/网络结构）|
| 时长 | 不限 | 1-3 分钟 |
| 语言 | 多语言 | **仅中文** |
| 导出 | MP4 / Shorts / GIF | MP4 1080p（横屏 + 竖屏 Shorts）|
| 旁白 | AI 配音 + 多语言 + 克隆 | **火山引擎中文 2-3 个声音** |
| 商业 | 三档订阅 | **C 端免费 + B 端团队版** |

---

## 五、实施时的文件骨架（参考，本次不创建）

```
explainflow/
├── apps/web/                      # Next.js 15.4 前端
│   ├── app/                       # App Router 页面
│   ├── components/storyboard/     # 故事板编辑器
│   └── components/explain-graph/  # 概念图谱可视化
├── apps/render/                   # Remotion 视频组件库
│   ├── compositions/whiteboard/   # 白板组合场景
│   ├── primitives/                # <WhiteboardDraw> 等原语
│   └── templates/ml/              # AI/ML 领域模板（神经网络、梯度下降等）
├── services/api/                  # FastAPI 后端
│   ├── explain/                   # 内容理解 + Explain Graph
│   ├── planner/                   # Teaching Planner
│   ├── visual/                    # Visual Reasoning
│   ├── narration/                 # TTS（火山引擎）
│   └── render/                    # 调度 Remotion 渲染
├── scripts/                       # CLAUDE.md 要求的 .sh 启停脚本
├── docs/                          # 正式文档
├── discuss/                       # 评审文档（本文件归宿）
├── logs/                          # 统一日志输出
└── evals/                         # STEM 评测集（20 题）
```

---

## 六、验证计划

**评审阶段（本次）**：
- [x] MVP 收窄到 AI/ML 单垂直
- [x] 动画引擎采用 Remotion + LLM 生成 TSX
- [x] 首发国内中文市场

**实施阶段端到端验证**：
1. 用 5 个 AI/ML 题目跑 LLM prompt，人工评估"教学顺序"质量
2. 实现 1 个完整端到端：输入"梯度下降" → 1 分钟 1080p 中文 MP4
3. 准备 20 题评测集（梯度下降、反向传播、Attention、Transformer 等），模型/prompt 每次改动跑回归
4. 把首批 3 个 demo 发到内部群和 B 站，看真实创作者的反馈
5. 联系 2-3 家 AI 培训机构，看 B 端付费意愿

---

## 七、下一步建议

评审到此结束。建议的后续动作（按顺序）：

1. **PRD 修订**：基于本评审，更新 `mdd.md`，把 MVP 章节（第 13 章）改成上述 v1.0 范围
2. **搭工程骨架**：按第五节的目录结构初始化 monorepo，准备好 `scripts/` 启停脚本和 `logs/` 日志
3. **打磨第一个 demo**："梯度下降" 端到端跑通，作为后续所有 prompt/组件迭代的 golden case
4. **20 题评测集**：在 `evals/` 下沉淀题目和评分标准，作为质量回归基线
