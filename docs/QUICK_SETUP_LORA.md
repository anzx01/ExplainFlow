# LoRA 风格快速配置指南

ExplainFlow 支持三种可选的图像生成风格，通过不同的 LoRA 模型实现。

---

## 三种可选风格

### 1. Chalkboard Drawing - CE（推荐用于板书讲解）

**特点：**
- 黑板粉笔手绘感
- 最贴近"白板板书讲解"的教学氛围
- 简洁清晰，适合教学视频

**适用场景：**
- 数学/物理公式推导
- 概念框架讲解
- 流程图和示意图

**配置：**
```env
COMFYUI_LORA=chalkboard-drawing-ce.safetensors
COMFYUI_LORA_STRENGTH=0.8
COMFYUI_LORA_TRIGGER=chlkbrdCE style
```

**示例 Prompt：**
```
chlkbrdCE style, simple illustration, minimal details, 3-5 main objects only, 
clean composition, a person holding smartphone with colorful video feed, 
attention arrows, clean chalkboard background, text-free artwork
```

---

### 2. UndrawPurple（推荐用于概念示意图）

**特点：**
- 极简矢量插画风
- 线条干净，配色清爽
- 扁平化设计风格

**适用场景：**
- 概念隐喻（如被手机吸住的人）
- 抽象关系图（如碎片化的注意力）
- 用户流程示意图

**配置：**
```env
COMFYUI_LORA=undraw-purple.safetensors
COMFYUI_LORA_STRENGTH=0.75
COMFYUI_LORA_TRIGGER=undraw style, flat illustration
```

**示例 Prompt：**
```
undraw style, flat illustration, simple illustration, minimal details, 
a person sitting on couch absorbed in phone, glowing screen light, 
clean purple and blue color scheme, text-free artwork
```

---

### 3. Azat Nurgaleev（推荐用于情感表达）

**特点：**
- 有笔触质感的数字绘画风
- 手绘温度，不过于幼稚
- 适合表现人物情绪和氛围

**适用场景：**
- 人物情绪场景（焦虑、沉迷、放松）
- 生活场景插图（卧室、沙发、工作台）
- 需要温度感的画面

**配置：**
```env
COMFYUI_LORA=azat-nurgaleev.safetensors
COMFYUI_LORA_STRENGTH=0.7
COMFYUI_LORA_TRIGGER=painting style, brush strokes
```

**示例 Prompt：**
```
painting style, brush strokes, simple illustration, minimal details,
a person on sofa illuminated by phone glow at night, cozy room setting,
warm color palette, text-free artwork
```

---

## 快速切换配置

### 方法 1：编辑 .env 文件

编辑 `services/api/.env`，修改以下三行：

```env
COMFYUI_LORA=<选择的文件名>
COMFYUI_LORA_STRENGTH=<强度值>
COMFYUI_LORA_TRIGGER=<触发词>
```

然后重启 API 服务：
```bash
scripts/stop.bat
scripts/start.bat
```

### 方法 2：环境变量覆盖（临时测试）

Windows PowerShell:
```powershell
$env:COMFYUI_LORA="chalkboard-drawing-ce.safetensors"
$env:COMFYUI_LORA_TRIGGER="chlkbrdCE style"
uv run python services/api/main.py
```

Bash:
```bash
export COMFYUI_LORA="undraw-purple.safetensors"
export COMFYUI_LORA_TRIGGER="undraw style, flat illustration"
bash scripts/dev-api.sh
```

---

## LoRA 文件位置

将下载的 LoRA 文件（`.safetensors` 格式）放到以下任一目录：

- `D:/ck/ComfyUI/models/loras/`
- `E:/MYLLM/loras/`
- ComfyUI 安装目录的 `models/loras/`

**验证：**
```bash
# 检查文件是否存在
ls "D:/ck/ComfyUI/models/loras/*.safetensors"
```

---

## 风格选择建议

### 根据主题类型选择

| 主题类型 | 推荐风格 | 理由 |
|---------|---------|------|
| 技术原理、算法、数学 | Chalkboard Drawing - CE | 板书风格最适合理性讲解 |
| 产品设计、用户体验 | UndrawPurple | 扁平风格契合现代设计语言 |
| 心理学、行为分析 | Azat Nurgaleev | 手绘质感适合表达情感 |
| 美食烹饪、手工制作 | Chalkboard Drawing - CE | 手绘感贴近实操演示 |

### 根据目标观众选择

| 观众群体 | 推荐风格 | 理由 |
|---------|---------|------|
| 学生、学术群体 | Chalkboard Drawing - CE | 黑板风格符合学习场景预期 |
| 产品经理、设计师 | UndrawPurple | 简洁现代，专业感强 |
| 大众科普、生活类 | Azat Nurgaleev | 亲和力强，易于接受 |

---

## 调试和优化

### 如果图像仍然过于复杂

1. **降低 LoRA 强度**
   ```env
   COMFYUI_LORA_STRENGTH=0.5  # 从 0.7-0.8 降低
   ```

2. **减少采样步数**
   ```env
   COMFYUI_STEPS=8  # 从 12 降低
   ```

3. **增强负面提示**（已在代码中自动处理）
   - 系统会自动添加排除复杂细节的负面提示
   - 无需手动配置

### 如果图像过于简单

1. **提高 LoRA 强度**
   ```env
   COMFYUI_LORA_STRENGTH=0.9
   ```

2. **增加采样步数**
   ```env
   COMFYUI_STEPS=15
   ```

3. **在 Prompt 中添加细节描述**
   - 不要只写"一个人"，而是"一个年轻人穿着休闲T恤坐在沙发上"
   - 具体化物体状态："冒着热气的红色麻婆豆腐"而不是"豆腐"

---

## 混合使用策略

同一个视频中可以混合使用不同风格的场景图片：

```python
# 场景 1：概念介绍（使用 UndrawPurple）
scene1.image_description = "undraw style, flat illustration, person with phone..."

# 场景 2：原理讲解（使用 Chalkboard Drawing）
scene2.image_description = "chlkbrdCE style, brain reward loop diagram..."

# 场景 3：情感场景（使用 Azat Nurgaleev）
scene3.image_description = "painting style, tired person in bed with phone..."
```

**注意：** 目前系统使用全局 LoRA 配置，混合风格需要在 Storyboard 生成阶段分批调用不同配置。

---

## 常见问题

### Q: LoRA 文件从哪里下载？
A: 请从 Civitai 或 Hugging Face 等模型分享平台搜索对应的 LoRA 名称。确保下载 SD 1.5 兼容版本。

### Q: 能同时加载多个 LoRA 吗？
A: 当前配置只支持单个 LoRA。如需混合风格，需要修改 ComfyUI 工作流。

### Q: 某个 LoRA 生成失败怎么办？
A: 检查以下几点：
1. LoRA 文件路径是否正确
2. LoRA 是否与 meinaPastelV5 checkpoint 兼容（SD 1.5 架构）
3. 触发词是否正确（触发词区分大小写）
4. ComfyUI 日志中是否有错误信息

### Q: 不使用 LoRA 可以吗？
A: 可以。将 `COMFYUI_LORA` 设为空即可：
```env
COMFYUI_LORA=
```
系统会使用基础 checkpoint 生成图像，但建议使用 LoRA 以获得更一致的简洁风格。

---

## 相关文档

- [VIDEO_QUALITY_IMPROVEMENTS.md](./VIDEO_QUALITY_IMPROVEMENTS.md) - 完整的改进方案说明
- [IMAGE_GENERATION_GUIDE.md](./IMAGE_GENERATION_GUIDE.md) - 图像生成详细指南
- [CLAUDE.md](../CLAUDE.md) - 项目架构总览

---

**更新日期：** 2026-10-08  
**适用版本：** ExplainFlow v1.0+
