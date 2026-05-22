# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目简介

ExplainFlow 是 AI 驱动的中文白板动画视频生成平台，面向 AI/ML 技术博主。用户输入主题，AI 生成 Khan Academy 风格的中文白板动画视频（1-3 分钟 1080p MP4）。

## 启动与开发

**首次初始化（安装依赖）：**
```bash
bash scripts/setup.sh
# 然后编辑 services/api/.env，填写 OPENAI_API_KEY
```

**三个服务需分别在独立终端中启动：**
```bash
bash scripts/dev-api.sh     # Python API，端口 8000
bash scripts/dev-web.sh     # Next.js 前端，端口 3000
bash scripts/dev-render.sh  # Remotion 渲染服务器，端口 3001
```

**Windows 快捷方式：**
```bat
scripts\start.bat   # 在独立 cmd 窗口启动全部服务
scripts\stop.bat    # 停止全部服务
```

日志输出到 `logs/` 目录（`api.log`、`web.log`、`render.log`）。

**永远通过 scripts/ 下的 .sh 脚本启停服务，不直接用 npm / uv / python 命令。**

## 架构总览

三个独立服务，通过 HTTP 通信：

```
Browser
  ↓ localhost:3000
Next.js (apps/web)
  ↓ POST /explain/graph, /planner/storyboard, /render/job
FastAPI (services/api, :8000)
  ↓ POST localhost:3001/render  +  POST :8000/narration/synthesize（回调）
Render Server (apps/render/server.mjs, :3001)
```

渲染视频时，`apps/render/server.mjs` 会回调 Python API 的 `/narration/synthesize` 生成每个场景的 TTS 音频（edge-tts，Microsoft 免费服务），音频文件托管在 `:3001/audio/:filename`，通过 Remotion `<Audio src>` 嵌入视频。

**视频下载 URL 直接指向 `:3001/download/:id`**（不经 FastAPI 代理），因为 FastAPI 的 `Response` 代理不支持浏览器 `<video>` 所需的 HTTP 206 Range 请求。

## 数据流水线

1. **ExplainGraph**：LLM 将用户 Prompt 转为结构化概念图（节点类型：concept / formula / example / conclusion / process）
2. **Storyboard**：LLM 将概念图规划为场景序列，每场景含旁白文案（`narration`）和动画指令列表
3. **Render**：Remotion 按 Storyboard 渲染视频，每场景 `WhiteboardScene` 组件串联动画原语 + TTS 音频

## 核心文件位置

| 功能 | 文件 |
|------|------|
| API 入口 / 路由注册 | `services/api/main.py` |
| LLM 调用封装 | `services/api/src/core/llm.py` |
| 概念图生成 | `services/api/src/explain/service.py` |
| 分镜规划 | `services/api/src/planner/service.py` |
| TTS 合成 | `services/api/src/narration/service.py` |
| 渲染服务器（HTTP + 作业管理） | `apps/render/server.mjs` |
| Remotion 视频合成 | `apps/render/src/compositions/WhiteboardVideo.tsx` |
| 场景渲染（含 Audio） | `apps/render/src/compositions/WhiteboardScene.tsx` |
| 动画原语 | `apps/render/src/primitives/` |
| 前端 API 客户端 | `apps/web/src/lib/api.ts` |
| 分镜页面 | `apps/web/src/app/storyboard/page.tsx` |

## 类型系统

TypeScript 类型定义在两处，需保持同步：
- `apps/web/src/lib/types.ts` — 前端类型
- `apps/render/src/primitives/types.ts` — Remotion 渲染端类型

Python Pydantic 模型在各模块 `models.py`，与上述类型对应。`Scene` 含 `audioUrl?: string | null` 字段（仅渲染时由 server.mjs 注入，前端无需传递）。

## 环境变量

**`services/api/.env`（从 `.env.example` 复制）：**
- `OPENAI_API_KEY` — DeepSeek API Key（必填）
- `OPENAI_BASE_URL` — 默认 `https://api.deepseek.com/v1`
- `LLM_MODEL` — 默认 `deepseek-chat`
- `LLM_MAX_RETRIES` — LLM 调用最大重试次数，默认 3
- `LLM_RETRY_BASE_DELAY_S` — 重试基础延迟（秒），默认 1.0
- `CORS_ALLOWED_ORIGINS` — CORS 允许的 origin 列表（逗号分隔），默认 `http://localhost:3000,http://127.0.0.1:3000`

**`apps/web/.env.local`（从 `.env.local.example` 复制）：**
- `NEXT_PUBLIC_API_URL` — 默认 `http://localhost:8000`

**`apps/render/.env`（从 `.env.example` 复制，可选）：**
- `REMOTION_BROWSER_EXECUTABLE` / `REMOTION_CHROME_HEADLESS_SHELL` — 可选，手动指定 Chrome/Chromium；留空时自动探测 Playwright、Chrome、Chromium 或 Edge
- `EXPLAINFLOW_OUTPUT_DIR` / `EXPLAINFLOW_MUSIC_DIR` — 可选，覆盖输出和音乐目录，相对路径按仓库根目录解析
- `EXPLAINFLOW_GLYPH_FONT` / `EXPLAINFLOW_GLYPH_FONTS` — 可选，覆盖字体；默认自动探测常见 Windows/macOS/Linux 字体
- `FFMPEG_PATH` / `FFPROBE_PATH` — 可选，手动指定 ffmpeg/ffprobe

## 渲染服务器关键细节

- Remotion bundle 的静态文件服务默认从端口 **3100** 开始寻找可用端口（通过 `REMOTION_STATIC_PORT` 环境变量配置），避免与 Next.js 3000 和主服务 3001 冲突，通过 `RenderInternals.serveStatic()` 显式指定
- 浏览器路径不硬编码：渲染服务会按环境变量、Playwright 缓存、系统 Chrome/Chromium/Edge 和 PATH 自动探测；若失败，可在 `apps/render/.env` 设置 `REMOTION_BROWSER_EXECUTABLE`
- 作业状态持久化到 `outputs/jobs.json`，服务器重启时 `processing` 状态的作业自动置为 `failed`
- 视频输出到 `outputs/{topic}_{jobId8}.mp4`，TTS 音频临时文件在 `outputs/audio/`

## 技术栈版本约束

- Next.js **15.4**，React **19**，Tailwind CSS **4**（强制，不降级）
- Python **3.11+**，包管理用 **uv**（`uv sync` / `uv run`，不用 pip）
- Remotion **4.0.462**

## 运行评估

```bash
bash scripts/eval.sh   # 需要 services/api/.env 中有有效的 API Key
```
