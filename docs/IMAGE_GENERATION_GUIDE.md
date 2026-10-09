# 图像生成风格指南

## 当前配置：Chalkboard Drawing - CE

ExplainFlow 使用 **Chalkboard Drawing - CE** LoRA 来生成简洁的教学风格插图。

### 为什么选择这个风格？

1. **黑板粉笔手绘感** - 最贴近"白板板书讲解"的教学氛围
2. **简洁清晰** - 避免过度复杂的细节，观众一眼就能看懂核心概念
3. **不喧宾夺主** - 图像作为辅助，不会抢走旁白和手写动画的焦点

### LoRA 配置

在 `services/api/.env` 中设置：

```env
COMFYUI_LORA=chalkboard-drawing-ce.safetensors
COMFYUI_LORA_STRENGTH=0.8
COMFYUI_LORA_TRIGGER=chlkbrdCE style
```

### 其他可选风格

如果需要切换风格，可以考虑：

#### UndrawPurple
- **特点**：极简矢量插画风，线条干净，配色清爽
- **适用场景**：概念示意图（如被手机吸住的人、碎片化的注意力图标）
- **配置**：
  ```env
  COMFYUI_LORA=undraw-purple.safetensors
  COMFYUI_LORA_TRIGGER=undraw style, flat illustration
  ```

#### Azat Nurgaleev
- **特点**：有笔触质感的数字绘画风
- **适用场景**：需要一点"手绘温度"但不过于幼稚的场景（如人物情绪表达）
- **配置**：
  ```env
  COMFYUI_LORA=azat-nurgaleev.safetensors
  COMFYUI_LORA_TRIGGER=painting style, brush strokes
  ```

## 简洁度控制

系统已在代码中强制添加简洁度约束：

1. **正面提示前缀**：`simple illustration, minimal details, 3-5 main objects only, clean composition`
2. **负面提示增强**：排除过度细节、复杂背景、密集元素等
3. **ComfyUI 步数**：默认 12 步，平衡质量和生成速度

## 调试建议

如果生成的图像仍然过于复杂：

1. **降低 LoRA 强度**：将 `COMFYUI_LORA_STRENGTH` 从 0.8 降到 0.6
2. **调整采样步数**：将 `COMFYUI_STEPS` 从 12 降到 8-10
3. **检查 Checkpoint**：确认使用的是 meinaPastelV5，而不是写实风格的模型

## 文件位置

- LoRA 文件应放在：`D:/ck/ComfyUI/models/loras/` 或 `E:/MYLLM/loras/`
- 工作流配置：`config/comfyui/scene-image-api.json`
- 代码实现：`services/api/src/imagegen/service.py`
