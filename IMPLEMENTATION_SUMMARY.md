# ExplainFlow 视频质量改进 - 实现总结

**完成日期**: 2026-10-08  
**状态**: ✅ 已完成所有功能实现

---

## 目标

解决两个关键的视频质量问题：

1. **视频开始没有图片** - 标题卡片缺少视觉吸引力
2. **图像过于复杂** - 生成的插图不符合简洁教学风格

---

## 解决方案概述

### 问题 1 解决方案：为标题卡片添加主题插图

**实现逻辑：**
1. Storyboard 生成时自动为标题创建一个主题插图
2. 标题图片在右侧显示（520×520），使用淡入动画
3. 标题文字自动调整宽度以避免与图片重叠

**关键改动：**

| 文件 | 变更 |
|-----|------|
| `apps/render/src/primitives/types.ts` | 添加 `Storyboard.titleImageUrl?: string` |
| `apps/web/src/lib/types.ts` | 添加前端类型同步 |
| `services/api/src/planner/models.py` | 添加 Python Pydantic 模型字段 |
| `apps/render/src/compositions/WhiteboardVideo.tsx` | 修改 TitleCard 组件显示图片 |
| `services/api/src/planner/title_image.py` | **新增** 标题图片生成模块 |
| `services/api/src/planner/storyboard_gen/builder.py` | 集成标题图片生成逻辑 |

**用户效果：**
```
┌─────────────────────────────────────────────┐
│ 【主题标题】                    ┌─────────┐ │
│ ═════════                      │ 主题    │ │
│                                │ 插图    │ │
│ AI 白板动画 · ExplainFlow      │ 520×520 │ │
│                                └─────────┘ │
└─────────────────────────────────────────────┘
```

---

### 问题 2 解决方案：控制图像复杂度

**三层控制策略：**

#### 1️⃣ LoRA 风格选择（推荐使用 Chalkboard Drawing - CE）

三种可选风格：

| 风格 | 触发词 | 适用场景 | 特点 |
|-----|-------|---------|------|
| **Chalkboard Drawing - CE** | `chlkbrdCE style` | 板书讲解（推荐） | 黑板粉笔手绘感 |
| UndrawPurple | `undraw style, flat illustration` | 概念示意图 | 极简矢量风格 |
| Azat Nurgaleev | `painting style, brush strokes` | 情感表达 | 笔触质感 |

#### 2️⃣ 增强的负面提示词

从基础的排除（文字、logo、水印）扩展到：
- 排除过度细节（`overly detailed`）
- 排除复杂背景（`busy background`）
- 排除密集元素（`clustered composition`）
- 排除过多主体对象（`more than 5 main objects`）
- 排除细微纹理（`fine textures`，`intricate shading`）

#### 3️⃣ 简洁度强制前缀

在所有 prompt 开头添加：
```
simple illustration, minimal details, 3-5 main objects only, clean composition, 
```

**关键改动：**

| 文件 | 变更 |
|-----|------|
| `services/api/src/imagegen/service.py:186-195` | 增强负面提示词 |
| `services/api/src/imagegen/service.py:153-158` | 添加简洁度前缀 |
| `services/api/.env.example:19-21` | 推荐 LoRA 配置 |

---

## 文件变更清单

### 代码修改（7 个文件）

1. ✅ `apps/render/src/primitives/types.ts` - 添加类型
2. ✅ `apps/web/src/lib/types.ts` - 前端类型同步
3. ✅ `services/api/src/planner/models.py` - Pydantic 模型更新
4. ✅ `apps/render/src/compositions/WhiteboardVideo.tsx` - TitleCard 组件改进
5. ✅ `services/api/src/planner/title_image.py` - **新增** 标题图片生成
6. ✅ `services/api/src/planner/storyboard_gen/builder.py` - 集成标题图片生成
7. ✅ `services/api/src/imagegen/service.py` - 图像简洁度控制

### 配置文件修改（1 个文件）

8. ✅ `services/api/.env.example` - 推荐的 LoRA 配置

### 文档新增（5 个文件）

9. ✅ `docs/VIDEO_QUALITY_IMPROVEMENTS.md` - 完整改进方案说明
10. ✅ `docs/QUICK_SETUP_LORA.md` - LoRA 快速配置指南
11. ✅ `docs/LORA_DOWNLOAD_GUIDE.md` - LoRA 下载安装指南
12. ✅ `docs/IMAGE_GENERATION_GUIDE.md` - 图像生成详细指南
13. ✅ `CLAUDE.md` - 项目文档更新

### 工具脚本新增（3 个文件）

14. ✅ `scripts/download-loras.ps1` - **新增** LoRA 自动下载脚本（PowerShell）
15. ✅ `scripts/test_video_quality.py` - **新增** 功能测试脚本
16. ✅ `scripts/test-video-quality.sh` - **新增** 测试便捷脚本

---

## 快速开始

### 1. 下载推荐的 LoRA 文件

```powershell
# Windows PowerShell
cd D:\aiapp\ExplainFlow
.\scripts\download-loras.ps1
```

或手动访问：[Chalkboard Drawing - CE](https://civitai.com/models/648912/chalkboard-drawing-ce)

### 2. 配置环境变量

编辑 `services/api/.env`：

```env
COMFYUI_LORA=chalkboard-drawing-ce.safetensors
COMFYUI_LORA_STRENGTH=0.8
COMFYUI_LORA_TRIGGER=chlkbrdCE style
```

### 3. 重启服务

```bash
scripts\stop.bat
scripts\start.bat
```

### 4. 测试功能

```bash
# 运行功能测试
bash scripts/test-video-quality.sh

# 或 Windows 环境
cd services/api && uv run python ../../scripts/test_video_quality.py
```

### 5. 生成视频并验证

1. 访问 http://localhost:3000
2. 输入主题并生成视频
3. 检查效果：
   - ✓ 标题卡片右侧显示主题插图
   - ✓ 场景图片简洁清晰（3-5 个主要对象）
   - ✓ 风格一致的黑板粉笔手绘感

---

## 核心功能说明

### 标题图片生成流程

```
generate_storyboard()
  ↓
1. LLM 生成 Storyboard
  ↓
2. 调用 generate_title_image(topic, summary)
  ↓
3. 创建 SceneImageRequest（标题图片专用）
  ↓
4. 调用 generate_scene_image() → ComfyUI
  ↓
5. 返回图片 URL，注入 storyboard.titleImageUrl
  ↓
6. 前端渲染时从 titleImageUrl 加载图片
```

### 图像简洁度控制流程

```
scene_image_prompt
  ↓
1. 添加简洁度前缀
   "simple illustration, minimal details, 3-5 main objects..."
  ↓
2. 组织 positive prompt
  ↓
3. 组织 negative prompt（含扩展的复杂度排除）
  ↓
4. 加载 LoRA（如 Chalkboard Drawing - CE）
  ↓
5. ComfyUI 生成
```

---

## 文档导航

| 文档 | 用途 |
|-----|------|
| **[CLAUDE.md](CLAUDE.md)** | 项目总体指南（已更新） |
| **[docs/VIDEO_QUALITY_IMPROVEMENTS.md](docs/VIDEO_QUALITY_IMPROVEMENTS.md)** | 完整的改进方案说明 |
| **[docs/QUICK_SETUP_LORA.md](docs/QUICK_SETUP_LORA.md)** | LoRA 快速配置指南 |
| **[docs/LORA_DOWNLOAD_GUIDE.md](docs/LORA_DOWNLOAD_GUIDE.md)** | LoRA 下载与安装指南 |
| **[docs/IMAGE_GENERATION_GUIDE.md](docs/IMAGE_GENERATION_GUIDE.md)** | 图像生成详细指南 |
| **本文件** | 实现总结与快速开始 |

---

## 测试清单

- [ ] ComfyUI 运行正常（端口 8188 可访问）
- [ ] LoRA 文件已下载（`chalkboard-drawing-ce.safetensors`）
- [ ] 环境变量已配置（`COMFYUI_LORA` 等）
- [ ] 功能测试通过：`bash scripts/test-video-quality.sh`
- [ ] 标题图片生成：生成视频后检查标题卡片右侧是否显示图片
- [ ] 场景图片简洁度：检查场景图片是否符合简洁教学风格

---

## 常见问题

### Q: LoRA 文件在哪里下载？
A: 使用脚本自动下载：`.\scripts\download-loras.ps1`  
或访问 Civitai：[Chalkboard Drawing - CE](https://civitai.com/models/648912/chalkboard-drawing-ce)

### Q: 标题图片没有显示？
A: 
1. 检查 ComfyUI 是否运行（`http://127.0.0.1:8188`）
2. 检查日志中是否有错误信息
3. 如果生成失败，系统会自动使用无图片版本

### Q: 生成的图像仍然过于复杂？
A:
1. 降低 LoRA 强度：`COMFYUI_LORA_STRENGTH=0.6`
2. 减少采样步数：`COMFYUI_STEPS=8`
3. 检查是否使用了正确的 checkpoint（meinaPastelV5）

### Q: 如何切换其他 LoRA 风格？
A: 编辑 `services/api/.env`，参考 [docs/QUICK_SETUP_LORA.md](docs/QUICK_SETUP_LORA.md)

---

## 后续优化方向

1. **并行生成** - 标题图片和场景图片并行生成以加快速度
2. **缓存机制** - 相同主题的标题图片缓存以避免重复生成
3. **混合风格** - 支持在同一视频中混合使用不同 LoRA 风格
4. **质量指标** - 自动评估生成图像的简洁度，不符合则重新生成
5. **用户定制** - 前端界面允许用户选择 LoRA 风格和参数

---

## 支持与反馈

- 📖 查看文档：[docs/](docs/)
- 🐛 报告问题：检查日志文件 `logs/api.log` 等
- 🔧 自定义配置：编辑 `services/api/.env`

---

**版本**: 1.0.0  
**最后更新**: 2026-10-08  
**维护者**: ExplainFlow 开发团队
