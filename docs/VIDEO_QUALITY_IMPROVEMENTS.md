# 视频质量改进总结

本文档总结了针对"视频开始没有图片"和"图像过于复杂"两个问题的修复方案。

## 问题 1：视频开始没有图片

### 问题描述
标题卡片（TitleCard）只显示文字和装饰网格线，缺少视觉吸引力，不符合教学视频的最佳实践。

### 解决方案
为标题卡片添加主题相关的插图，在右侧显示一个 520×520 的圆角图片框。

### 修改的文件

1. **类型定义**
   - [apps/render/src/primitives/types.ts](../apps/render/src/primitives/types.ts#L108-L112)
   - [apps/web/src/lib/types.ts](../apps/web/src/lib/types.ts#L220-L232)
   - [services/api/src/planner/models.py](../services/api/src/planner/models.py#L166-L180)
   
   添加了 `titleImageUrl` 字段到 `Storyboard` 类型。

2. **前端组件**
   - [apps/render/src/compositions/WhiteboardVideo.tsx](../apps/render/src/compositions/WhiteboardVideo.tsx#L15-L95)
   
   修改了 `TitleCard` 组件：
   - 接收 `imageUrl` 参数
   - 在右侧显示主题插图（如果提供）
   - 当有图片时，标题文字区域缩窄以避免重叠

### 视觉效果

**有图片时的布局：**
```
┌────────────────────────────────────────────────────────┐
│  ░░░░░░░░ 网格线背景 ░░░░░░░░                         │
│                                     ┌───────────────┐  │
│  【主题标题】                        │               │  │
│  ═════════                          │  主题插图      │  │
│                                     │  520×520      │  │
│  AI 白板动画 · ExplainFlow           │               │  │
│                                     └───────────────┘  │
└────────────────────────────────────────────────────────┘
```

### 使用方法

在生成 Storyboard 时，为 `titleImageUrl` 字段提供主题相关的图片 URL：

```python
storyboard = Storyboard(
    topic="短视频如何让人停不下来",
    title_image_url="http://localhost:3001/images/topic-intro.png",
    scenes=[...]
)
```

---

## 问题 2：图像过于复杂

### 问题描述
使用 SD 1.5 meinaPastel checkpoint 生成的图像过于精细，包含过多细节，不符合简洁教学视频的需求。

### 解决方案
通过三个层面控制图像复杂度：

1. **推荐使用 Chalkboard Drawing - CE LoRA**
2. **增强负面提示词**
3. **添加简洁度强制前缀**

### 修改的文件

1. **图像生成服务**
   - [services/api/src/imagegen/service.py](../services/api/src/imagegen/service.py#L182-L198)
   
   **修改内容：**
   
   a) 增强的负面提示词（第 186-195 行）：
   ```python
   negative = (
       "text, letters, words, logo, watermark, blurry, low quality, malformed hands, duplicate objects, "
       "overly detailed, too many elements, cluttered composition, busy background, complex patterns, "
       "photorealistic details, fine textures, intricate shading, realistic rendering, "
       "anime style details, hair strands, fabric folds, glossy highlights, "
       "small objects, tiny icons, miniature details, dense infographic, "
       "more than 5 main objects, crowded scene, overlapping elements"
   )
   ```
   
   b) 简洁度强制前缀（第 153-158 行）：
   ```python
   simplicity_prefix = "simple illustration, minimal details, 3-5 main objects only, clean composition, "
   if settings.comfyui_lora.strip() and settings.comfyui_lora_trigger.strip():
       prompt = f"{settings.comfyui_lora_trigger}, {simplicity_prefix}{prompt}"
   else:
       prompt = f"{simplicity_prefix}{prompt}"
   ```

2. **配置示例**
   - [services/api/.env.example](../services/api/.env.example#L19-L21)
   
   更新为推荐的 Chalkboard Drawing - CE LoRA：
   ```env
   COMFYUI_LORA=chalkboard-drawing-ce.safetensors
   COMFYUI_LORA_STRENGTH=0.8
   COMFYUI_LORA_TRIGGER=chlkbrdCE style
   ```

### 推荐的 LoRA 风格

#### 首选：Chalkboard Drawing - CE
- **特点**：黑板粉笔手绘感
- **适用场景**：板书讲解风格的教学视频
- **触发词**：`chlkbrdCE style`
- **配置**：
  ```env
  COMFYUI_LORA=chalkboard-drawing-ce.safetensors
  COMFYUI_LORA_STRENGTH=0.8
  COMFYUI_LORA_TRIGGER=chlkbrdCE style
  ```

#### 备选 1：UndrawPurple
- **特点**：极简矢量插画风，线条干净，配色清爽
- **适用场景**：概念示意图（如被手机吸住的人、碎片化的注意力图标）
- **配置**：
  ```env
  COMFYUI_LORA=undraw-purple.safetensors
  COMFYUI_LORA_TRIGGER=undraw style, flat illustration
  ```

#### 备选 2：Azat Nurgaleev
- **特点**：有笔触质感的数字绘画风
- **适用场景**：需要手绘温度的人物情绪表达场景
- **配置**：
  ```env
  COMFYUI_LORA=azat-nurgaleev.safetensors
  COMFYUI_LORA_TRIGGER=painting style, brush strokes
  ```

### 调试建议

如果生成的图像仍然过于复杂：

1. **降低 LoRA 强度**
   ```env
   COMFYUI_LORA_STRENGTH=0.6  # 从 0.8 降到 0.6
   ```

2. **减少采样步数**
   ```env
   COMFYUI_STEPS=8  # 从 12 降到 8-10
   ```

3. **检查 Checkpoint**
   确认使用的是 `meinaPastelV5_bakedVAE.safetensors`，而不是写实风格的模型。

---

## 配置步骤

### 1. 下载 LoRA 文件

将推荐的 LoRA 文件放到以下任一目录：
- `D:/ck/ComfyUI/models/loras/`
- `E:/MYLLM/loras/`

### 2. 更新环境变量

编辑 `services/api/.env`：

```env
# 图像生成配置
IMAGEGEN_PROVIDER=comfyui
COMFYUI_BASE_URL=http://127.0.0.1:8188
COMFYUI_WORKFLOW=D:\\aiapp\\ExplainFlow\\config\\comfyui\\scene-image-api.json
COMFYUI_CHECKPOINT=meinaPastelV5_bakedVAE.safetensors
COMFYUI_LORA=chalkboard-drawing-ce.safetensors
COMFYUI_LORA_STRENGTH=0.8
COMFYUI_LORA_TRIGGER=chlkbrdCE style
COMFYUI_STEPS=12
```

### 3. 重启服务

```bash
# 停止所有服务
scripts/stop.bat

# 重新启动
scripts/start.bat
```

---

## 验证修改

### 测试标题卡片图片

1. 生成一个新的 Storyboard
2. 检查 `storyboard.titleImageUrl` 是否有值
3. 渲染视频，观察开场是否显示主题插图

### 测试图像简洁度

1. 生成场景图片
2. 检查图片是否符合以下标准：
   - ✅ 主要元素 3-5 个
   - ✅ 背景干净简洁
   - ✅ 线条清晰，粉笔/马克笔手绘风格
   - ✅ 无过度细节（如头发丝、褶皱等）
   - ✅ 无复杂纹理和光影
   - ✅ 无文字、标签、水印

---

## 相关文档

- [IMAGE_GENERATION_GUIDE.md](./IMAGE_GENERATION_GUIDE.md) - 图像生成风格指南
- [CLAUDE.md](../CLAUDE.md) - 项目整体架构文档

---

## 修改记录

- **2026-10-08**: 初始版本
  - 添加标题卡片图片功能
  - 增强图像简洁度控制
  - 推荐使用 Chalkboard Drawing - CE LoRA
