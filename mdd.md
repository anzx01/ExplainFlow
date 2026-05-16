# 《ExplainFlow》AI Explain Engine 产品需求文档（PRD）

## 一、项目概述

| 项目         | 内容                                                |
| ------------ | --------------------------------------------------- |
| 产品名称     | ExplainFlow（暂定）                                 |
| 产品定位     | AI 驱动的动态讲解视频生成平台                       |
| 产品本质     | AI Explain Engine（AI 可解释内容引擎）              |
| 核心价值     | 自动把复杂知识转换为易理解的动态讲解视频            |
| 产品形态     | Web 应用（优先）                                    |
| 第一阶段方向 | STEM / 技术 / 教学白板讲解视频                      |
| 核心输出     | 白板动画、技术讲解、动态图解、培训视频              |
| 核心用户     | 教师、工程师、教育博主、AI 博主、培训部门、技术公司 |

---

# 二、产品愿景

未来大多数知识传播方式将从：

* 文档
* PPT
* PDF
* 静态图表

转变为：

# “动态解释”

ExplainFlow 的目标：

> 让任何复杂知识，都能被 AI 自动讲明白。

系统不是传统视频编辑器。

而是：

# “知识解释引擎”

---

# 三、产品核心理念

---

# 1️⃣ 不做 AI 视频生成器

ExplainFlow 不追求：

* AI 电影
* AI 短剧
* AI diffusion 视频

系统重点：

# “解释能力”

---

# 2️⃣ 视频不是核心

真正核心：

# AI Explain Graph（解释图谱）

系统会：

* 理解知识
* 建立逻辑关系
* 规划教学顺序
* 选择视觉表达
* 自动生成动画

---

# 3️⃣ 用结构化动画替代 AI 视频扩散

采用：

* 白板动画
* SVG 动画
* 动态图表
* 图层动画
* 流程动画
* 粒子动画

实现：

* 高可控
* 高稳定
* 低算力
* 高教学效率

---

# 四、目标用户

---

# A. STEM 教学创作者

## 包括：

* 数学
* AI
* 物理
* 半导体
* 编程
* 工程

## 典型需求：

* 自动生成讲解视频
* 自动生成白板动画
* 解释复杂原理

---

# B. 技术博主 / YouTube 创作者

## 场景：

* 无脸频道
* 科技解释
* AI 教程
* 商业分析

## 痛点：

* 动画制作耗时
* 视频更新困难
* 讲解成本高

---

# C. 企业培训

## 场景：

* onboarding
* SOP
* 合规培训
* 产品培训

## 痛点：

* 文档没人看
* PPT 太枯燥
* 培训成本高

---

# D. 教育平台

## 场景：

* 在线课程
* 微课
* AI Tutor

---

# 五、产品核心能力

---

# 1️⃣ 内容输入系统

支持：

| 类型        | 支持 |
| ----------- | ---- |
| 文本 Prompt | ✅   |
| PDF         | ✅   |
| PPT         | ✅   |
| DOCX        | ✅   |
| Markdown    | ✅   |
| URL         | ✅   |
| 音频转录    | 后期 |

---

# 2️⃣ 内容理解引擎（核心）

系统会自动：

## 提取：

* 核心概念
* 专业术语
* 因果关系
* 流程关系
* 数学结构
* 数据关系

---

## 自动识别：

| 内容     | 示例        |
| -------- | ----------- |
| 流程     | SOP         |
| 对比     | CPU vs GPU  |
| 网络结构 | Transformer |
| 数学过程 | 梯度下降    |
| 电路结构 | MOS 管      |
| 数据变化 | 股票趋势    |

---

# 3️⃣ Explain Graph（解释图谱）

这是系统核心。

系统不会直接生成视频。

而是：

# 先生成“解释结构”。

---

## Explain Graph 包括：

| 模块           | 功能           |
| -------------- | -------------- |
| Concept Nodes  | 核心概念       |
| Relations      | 因果/流程/依赖 |
| Teaching Order | 教学顺序       |
| Emphasis       | 重点           |
| Visual Mapping | 视觉表达       |
| Narration Flow | 旁白节奏       |

---

# 4️⃣ Teaching Planner（教学规划）

系统自动决定：

* 先讲什么
* 后讲什么
* 哪些需要拆解
* 哪些需要强调
* 哪些需要动画

---

## 示例：

输入：

> “MOS 管工作原理”

系统自动规划：

<pre class="overflow-visible! px-0!" data-start="1951" data-end="2029"><div class="relative w-full mt-4 mb-1"><div class=""><div class="relative"><div class="h-full min-h-0 min-w-0"><div class="h-full min-h-0 min-w-0"><div class="border border-token-border-light border-radius-3xl corner-superellipse/1.1 rounded-3xl"><div class="h-full w-full border-radius-3xl bg-token-bg-elevated-secondary corner-superellipse/1.1 overflow-clip rounded-3xl lxnfua_clipPathFallback"><div class="pointer-events-none absolute end-1.5 top-1 z-2 md:end-2 md:top-1"></div><div class="relative"><div class="pe-11 pt-3"><div class="relative z-0 flex max-w-full"><div id="code-block-viewer" dir="ltr" class="q9tKkq_viewer cm-editor z-10 light:cm-light dark:cm-light flex h-full w-full flex-col items-stretch ͼd ͼr"><div class="cm-scroller"><pre class="cm-content q9tKkq_readonly m-0"><code><span>1. MOS结构</span><br/><span>2. 栅极作用</span><br/><span>3. 电场形成</span><br/><span>4. 电子聚集</span><br/><span>5. 沟道形成</span><br/><span>6. 导通</span><br/><span>7. 电流流动</span></code></pre></div></div></div></div></div></div></div></div></div><div class=""><div class=""></div></div></div></div></div></pre>

---

# 5️⃣ Visual Reasoning Engine（视觉推理系统）

系统会自动判断：

# “什么视觉最适合解释这个知识”

---

## 示例：

| 概念      | 视觉表达 |
| --------- | -------- |
| 电流      | 粒子流   |
| 电场      | 箭头     |
| 网络      | 节点连接 |
| 优化      | 小球下坡 |
| Attention | 动态高亮 |
| 数据增长  | 动态图表 |

---

# 六、Explain DSL（动画语言）

系统内部会生成：

# “动画解释脚本”

而不是直接生成视频。

---

## 示例：

<pre class="overflow-visible! px-0!" data-start="2307" data-end="2403"><div class="relative w-full mt-4 mb-1"><div class=""><div class="relative"><div class="h-full min-h-0 min-w-0"><div class="h-full min-h-0 min-w-0"><div class="border border-token-border-light border-radius-3xl corner-superellipse/1.1 rounded-3xl"><div class="h-full w-full border-radius-3xl bg-token-bg-elevated-secondary corner-superellipse/1.1 overflow-clip rounded-3xl lxnfua_clipPathFallback"><div class="pointer-events-none absolute end-1.5 top-1 z-2 md:end-2 md:top-1"></div><div class="relative"><div class="pe-11 pt-3"><div class="relative z-0 flex max-w-full"><div id="code-block-viewer" dir="ltr" class="q9tKkq_viewer cm-editor z-10 light:cm-light dark:cm-light flex h-full w-full flex-col items-stretch ͼd ͼr"><div class="cm-scroller"><pre class="cm-content q9tKkq_readonly m-0"><code><span>DRAW transistor</span><br/><span>HIGHLIGHT gate</span><br/><span>SPAWN electrons</span><br/><span>FORM channel</span><br/><span>FLOW current</span></code></pre></div></div></div></div></div></div></div></div></div><div class=""><div class=""></div></div></div></div></div></pre>

---

# 七、Animation Engine（动画引擎）

动画引擎负责：

* 绘制图形
* 执行动画
* 生成镜头
* 管理节奏
* 同步旁白

---

# 动画类型：

---

## 1️⃣ Whiteboard Animation

* 手绘线条
* 图形逐步出现
* 文字绘制
* 箭头绘制

---

## 2️⃣ STEM Animation

* 坐标轴
* 曲线
* 数学公式
* 电场
* 粒子流
* 网络结构

---

## 3️⃣ Data Animation

* 动态图表
* KPI 增长
* 数据变化
* 对比动画

---

# 八、Scene Composition（场景组合）

系统不会：

# “自由生成视频”

而是：

# “组合场景模块”

---

## 例如：

MOS 管：

<pre class="overflow-visible! px-0!" data-start="2777" data-end="2838"><div class="relative w-full mt-4 mb-1"><div class=""><div class="relative"><div class="h-full min-h-0 min-w-0"><div class="h-full min-h-0 min-w-0"><div class="border border-token-border-light border-radius-3xl corner-superellipse/1.1 rounded-3xl"><div class="h-full w-full border-radius-3xl bg-token-bg-elevated-secondary corner-superellipse/1.1 overflow-clip rounded-3xl lxnfua_clipPathFallback"><div class="pointer-events-none absolute end-1.5 top-1 z-2 md:end-2 md:top-1"></div><div class="relative"><div class="pe-11 pt-3"><div class="relative z-0 flex max-w-full"><div id="code-block-viewer" dir="ltr" class="q9tKkq_viewer cm-editor z-10 light:cm-light dark:cm-light flex h-full w-full flex-col items-stretch ͼd ͼr"><div class="cm-scroller"><pre class="cm-content q9tKkq_readonly m-0"><code><span>MOS剖面图</span><br/><span>+</span><br/><span>电子粒子</span><br/><span>+</span><br/><span>箭头</span><br/><span>+</span><br/><span>高亮</span><br/><span>+</span><br/><span>文字标签</span><br/><span>+</span><br/><span>镜头推进</span></code></pre></div></div></div></div></div></div></div></div></div><div class=""><div class=""></div></div></div></div></div></pre>

---

# 九、Narration Engine（旁白系统）

支持：

| 功能     | 支持 |
| -------- | ---- |
| AI 配音  | ✅   |
| 多语言   | ✅   |
| 语速控制 | ✅   |
| 停顿控制 | ✅   |
| 声音风格 | ✅   |
| 声音克隆 | 后期 |

---

# 十、Storyboard Studio（故事板）

系统自动生成：

# 卡片式分镜

每张卡片：

* 场景
* 动画
* 旁白
* 转场
* 时间

---

## 用户可：

* 调整顺序
* 删除
* 修改文案
* AI 重生成

---

# 十一、视频风格系统

---

# 第一阶段重点：

# Whiteboard STEM

---

## 风格：

### 1️⃣ Khan Academy 风格

* 白背景
* 手绘
* 逐步推导

---

### 2️⃣ Technical Minimal

* 极简
* 工程风
* 蓝白灰

---

### 3️⃣ Data Storytelling

* 动态图表
* 商业讲解

---

# 十二、用户流程

---

# Step 1：输入内容

用户：

* 上传 PDF
* 输入 Prompt
* 上传 PPT

---

# Step 2：AI 分析

系统：

* 提取概念
* 建立 Explain Graph
* 分析教学逻辑

---

# Step 3：生成 Storyboard

显示：

* 场景
* 旁白
* 动画结构

---

# Step 4：生成视频

系统：

* 自动动画
* 自动旁白
* 自动转场

---

# Step 5：导出

支持：

* MP4
* Shorts
* GIF

---

# 十三、MVP 范围（极重要）

---

# 第一阶段只做：

# STEM 白板讲解

---

## 原因：

| 原因           | 说明         |
| -------------- | ------------ |
| 最结构化       | 易 Explain   |
| 最适合动画     | 天然图解     |
| 最容易形成壁垒 | 需要理解能力 |
| 最容易传播     | YouTube/教育 |

---

# MVP 功能：

| 功能           | 是否支持 |
| -------------- | -------- |
| Prompt 输入    | ✅       |
| PDF 输入       | ✅       |
| AI 理解        | ✅       |
| 自动脚本       | ✅       |
| 白板动画       | ✅       |
| 自动旁白       | ✅       |
| MP4 导出       | ✅       |
| 分镜编辑       | 简化版   |
| AI 虚拟人      | ❌       |
| diffusion 视频 | ❌       |
| 高级时间轴     | ❌       |

---

# 十四、产品护城河

---

# ❌ 不是视频生成

---

# ✅ 而是：

# “AI Explain Capability”

---

## 核心壁垒：

| 能力        | 价值 |
| ----------- | ---- |
| 知识理解    | 极高 |
| 教学规划    | 极高 |
| 视觉推理    | 极高 |
| Explain DSL | 极高 |
| STEM 模型   | 极高 |

---

# 十五、商业模式

---

# 免费版

* 水印
* 时长限制
* 分辨率限制

---

# Pro

* 无水印
* 1080P
* 更多风格
* 更长视频

---

# Team / Enterprise

* 团队协作
* 品牌系统
* 企业模板
* API

---

# 十六、长期发展方向

未来：

ExplainFlow 将逐渐演化为：

# AI Explain Platform

支持：

* AI Tutor
* AI 企业培训
* AI 技术教育
* AI 交互课程
* AI 动态教材

---

# 十七、一句话总结

> ExplainFlow 不是 AI 视频工具。
>
> 它是：
>
> # 一个让 AI 自动“讲明白复杂知识”的动态解释系统。
>
