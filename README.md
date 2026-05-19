# ExplainFlow

ExplainFlow 是一个本地化教学视频生成工具。目标是把用户输入的主题、讲解要求或参考图，生成带旁白、板书节奏、手写/标注过程和最终 MP4 输出的白板讲解视频。

## 当前状态

- MVP 主链路已打通：主题输入 -> 讲解规划 -> Storyboard -> TTS -> Remotion 代码生成 -> MP4 渲染。
- 生成策略已经从“针对单一题材打补丁”改为通用课堂表达：按教学关系、信息密度、画面复杂度和讲画同步要求决定呈现方式。
- 普通白板讲解不再默认生成参考位图，避免图形和文字背后出现像纸片一样的底板、阴影或卡片面。
- 通用题材不再特殊考虑 MOS/FinFET，统一走“全局地图、结构拆解、优先取舍、目标路径、反馈闭环”等通用解释框架。
- 文案和图形提示已强化为更生动的课堂表达，避免只有单调勾选、空泛标题或枯燥列表。
- 最新通过验证的样例：`outputs\通用问题解决框架_4c9f0c6c.mp4`。

## 项目结构

```text
apps/
  render/      Remotion 渲染服务，负责 TTS、代码校验、bundle 和 MP4 输出
  web/         Next.js 前端
services/
  api/         FastAPI 服务，负责规划、故事板、旁白和任务编排
evals/         评测脚本与评分说明
discuss/       设计讨论、开发进度和评审记录
outputs/       本地视频输出目录，默认不入库
```

## 环境变量

项目从 `.env` 或进程环境读取配置。不要把真实 key 写入文档或提交到仓库。

常用变量：

- `OPENAI_API_KEY`
- `OPENAI_BASE_URL`
- `LLM_MODEL`
- `CODER_MODEL`
- `ARK_API_KEY`
- `ARK_IMAGE_MODEL`
- `ARK_IMAGE_BASE_URL`

## 本地启动

启动 API：

```powershell
cd services/api
uv run uvicorn main:app --host 127.0.0.1 --port 8000
```

启动渲染服务：

```powershell
cd apps/render
node server.mjs
```

启动前端：

```powershell
cd apps/web
npm run dev
```

## 质量规则

当前渲染链路重点保证：

- 白板场景不能出现内层纸张、卡片、面板、投影、渐变底影或 `drop-shadow`。
- 普通 `whiteboard + teacher_whiteboard + trace` 场景只画矢量板书和课堂 doodle，不默认塞入参考图片。
- Storyboard 和渲染端都会过滤乱码、异常文本和不合规画面代码。
- 复杂参考图走直接呈现或混合标注；简单结构图才逐笔追踪。
- 通用问题解决类视频使用稳定的 5 段结构，避免被补齐逻辑重新追加重复场景。

## 验证命令

```powershell
python -m compileall services/api/main.py services/api/src
node --check apps/render/server.mjs
```

## 最近进展

2026-05-19 完成了一轮白板质量修复：

- 移除了普通白板图形背后的纸片感底影。
- 禁止生成代码使用阴影、滤镜、渐变和内层纸面。
- 通用问题解决框架改为确定性 5 场景。
- 把裸露勾选符号改成有标签的轻松提示，例如“有谱”“别慌”“下一步”。
- 清理 `.tmp` 临时日志、e2e 中间产物和抽帧图片，并将 `.tmp/` 加入忽略列表。
