# LoRA 下载指南

本指南提供了推荐 LoRA 文件的下载方法和手动安装步骤。

---

## 方法 1：自动下载脚本（推荐）

使用 PowerShell 脚本自动下载推荐的 LoRA 文件：

```powershell
# 以管理员身份运行 PowerShell
cd D:\aiapp\ExplainFlow
.\scripts\download-loras.ps1
```

脚本会自动：
1. 创建目标目录（如果不存在）
2. 下载推荐的 LoRA 文件
3. 验证文件完整性
4. 备份到多个目录
5. 显示推荐配置

**注意：** Civitai API 可能需要账号认证，脚本可能无法直接下载。如果失败，请使用方法 2 手动下载。

---

## 方法 2：手动下载（稳定可靠）

**注意：** Civitai 的大部分模型需要登录才能下载。如果不想注册账号，请跳到 **方法 3：无需登录的替代方案**。

### 首选：Chalkboard Drawing - CE

**推荐理由：** 黑板粉笔手绘感，最贴近"白板板书讲解"的教学氛围。

**下载步骤：**

1. **访问 Civitai 页面：**
   - 链接：[Chalkboard Drawing - CE - V1.1](https://civitai.com/models/648912/chalkboard-drawing-ce?modelVersionId=846058)

2. **登录 Civitai 账号**（如果没有账号，需要先注册）

3. **选择版本：**
   - 查找 **SD 1.5 兼容版本**（不是 Flux.1 D 版本）
   - 确认是 `.safetensors` 格式

4. **下载文件：**
   - 点击"Download"按钮
   - 文件大小约 **150-300 MB**
   - 保存为 `chalkboard-drawing-ce.safetensors`

5. **放到目录：**
   ```
   E:\MYLLM\loras\chalkboard-drawing-ce.safetensors
   或
   D:\ck\ComfyUI\models\loras\chalkboard-drawing-ce.safetensors
   ```

6. **配置环境变量** (`services/api/.env`)：
   ```env
   COMFYUI_LORA=chalkboard-drawing-ce.safetensors
   COMFYUI_LORA_STRENGTH=0.8
   COMFYUI_LORA_TRIGGER=chlkbrdCE style
   ```

---

### 备选 1：SDXL ChalkBoardDrawing LoRA

**适用场景：** 如果首选 LoRA 不兼容或效果不理想。

**下载步骤：**

1. 访问：[SDXL ChalkBoardDrawing LoRA](https://civitai.com/models/259365)
2. 下载 SD 1.5 兼容版本（不是 SDXL）
3. 保存到 `E:\MYLLM\loras\sdxl-chalkboard-drawing.safetensors`
4. 配置：
   ```env
   COMFYUI_LORA=sdxl-chalkboard-drawing.safetensors
   COMFYUI_LORA_STRENGTH=0.75
   COMFYUI_LORA_TRIGGER=chalkboard drawing
   ```

---

### 备选 2：Chalkboard art (黒板アート)

**适用场景：** 需要日式黑板艺术风格。

**下载步骤：**

1. 访问：[Chalkboard art / Blackboard art](https://civitai.com/models/1413078/chalkboard-art-blackboard-art-or-ilsdxl)
2. 下载文件
3. 保存到 `E:\MYLLM\loras\chalkboard-art-ilsdxl.safetensors`
4. 配置：
   ```env
   COMFYUI_LORA=chalkboard-art-ilsdxl.safetensors
   COMFYUI_LORA_STRENGTH=0.7
   COMFYUI_LORA_TRIGGER=chalkboard art
   ```

---

## 方法 3：无需登录的替代方案

如果不想注册 Civitai 账号，可以使用以下方法：

### A. 从 Hugging Face 下载（完全无需登录）

Hugging Face 是开源 AI 模型的最大仓库，很多 LoRA 有镜像：

```bash
# 搜索黑板/粉笔风格 LoRA
# 访问：https://huggingface.co/models?search=chalkboard+lora

# 直接下载示例（如果找到合适的模型）
wget https://huggingface.co/USERNAME/MODEL_NAME/resolve/main/lora.safetensors \
  -O E:/MYLLM/loras/chalkboard-hf.safetensors
```

**推荐搜索关键词：**
- `chalkboard lora`
- `blackboard drawing lora`
- `chalk art sd15`
- `educational illustration lora`

---

### B. 使用第三方下载工具

#### 1. Civitai Scraper（完全无需账号）

- **工具**: [Civitai Scraper · Apify](https://apify.com/fanndev/civitai-scraper)
- **特点**: 无需账号或 API key，直接抓取下载链接
- **使用**: 在网页界面输入模型 ID，获取下载链接

#### 2. CivitFetch（Python CLI 工具）

```bash
# 安装
git clone https://github.com/official-imvoiid/CivitFetch
cd CivitFetch
pip install -r requirements.txt

# 下载模型（通过模型 ID）
python CiviFetch.py --model-id 648912 --version-id 846058
```

来源：[CivitFetch GitHub](https://github.com/official-imvoiid/CivitFetch)

#### 3. CivitAI Model Grabber（批量下载）

```bash
# 安装
git clone https://github.com/Confuzu/CivitAI-Model-grabber
cd CivitAI-Model-grabber
pip install -r requirements.txt

# 下载
python main.py --model-id 648912
```

来源：[CivitAI Model Grabber GitHub](https://github.com/Confuzu/CivitAI-Model-grabber)

---

### C. 使用替代平台

以下平台提供类似的 LoRA 模型，下载政策可能更宽松：

| 平台 | 网址 | 特点 |
|-----|------|------|
| **Hugging Face** | [huggingface.co](https://huggingface.co/models) | 完全开放，无需登录 |
| **SeaArt.ai** | [seaart.ai](https://www.seaart.ai/) | 替代 Civitai |
| **TensorArt** | [tensor.art](https://tensor.art/) | 社区模型分享 |

来源：[Best Civitai Alternatives 2025](https://apatero.com/blog/best-civitai-alternatives-ai-model-platforms-2025)

---

### D. ComfyUI 插件（推荐）

如果你使用 ComfyUI，可以安装浏览器插件直接在 UI 中下载：

**Civitai Browser for ComfyUI**
```bash
cd D:\ck\ComfyUI\custom_nodes
git clone https://github.com/Fasd800/CivLens
```

来源：[CivLens GitHub](https://github.com/Fasd800/CivLens)

---

## 方法 4：使用现有 LoRA（最简单）

某些 LoRA 可能在 Hugging Face 上有镜像：

```bash
# 使用 huggingface-cli 下载（需要先安装）
pip install huggingface-hub

# 下载命令示例
huggingface-cli download <username>/<repo-name> --local-dir E:\MYLLM\loras
```

---

## 验证安装

下载完成后，验证 LoRA 是否可用：

### 1. 检查文件存在

```powershell
# PowerShell
ls "E:\MYLLM\loras\*.safetensors"
```

### 2. 检查文件大小

LoRA 文件通常在 **50 MB - 500 MB** 之间。如果文件太小（< 10 MB），可能是下载失败的占位文件。

### 3. 在 ComfyUI 中测试

1. 启动 ComfyUI：
   ```bash
   # 启动 ComfyUI 服务（如果还没运行）
   cd D:\ck\ComfyUI
   python main.py
   ```

2. 访问 `http://127.0.0.1:8188`

3. 在工作流中添加 `LoraLoader` 节点

4. 查看下拉菜单中是否出现下载的 LoRA 文件名

---

## 常见问题

### Q: Civitai 下载需要登录怎么办？

A: Civitai 对大部分模型文件要求登录才能下载。请：
1. 注册免费账号：https://civitai.com/signup
2. 登录后重新访问下载链接
3. 下载时浏览器会自动携带认证 Cookie

### Q: 下载速度很慢怎么办？

A: 可以尝试：
1. 使用代理或 VPN
2. 从 Hugging Face 镜像下载（如果有）
3. 使用下载工具（如 IDM、迅雷）加速

### Q: 找不到 SD 1.5 版本，只有 SDXL/Flux 版本？

A: 某些 LoRA 只支持新架构。可以：
1. 在该 LoRA 的"Versions"标签中查找旧版本
2. 搜索其他类似的 SD 1.5 兼容 LoRA
3. 考虑升级 checkpoint 到 SDXL（需要更多显存）

### Q: 下载的文件是 `.ckpt` 而不是 `.safetensors`？

A: `.safetensors` 更安全且加载更快。如果只有 `.ckpt`：
1. 优先寻找 `.safetensors` 版本
2. 如果必须使用 `.ckpt`，确保来源可信
3. 可以使用转换工具转为 `.safetensors`

### Q: 如何知道 LoRA 是否与 meinaPastelV5 checkpoint 兼容？

A: 检查以下几点：
1. LoRA 页面标注的"Base Model"是否为 SD 1.5
2. 查看评论区是否有兼容性报告
3. 实际测试：加载后如果生成图像崩坏，说明不兼容

---

## 推荐资源

### Civitai 搜索关键词
- `chalkboard SD1.5`
- `blackboard drawing lora`
- `chalk art stable diffusion 1.5`
- `educational illustration lora`

### 相关 LoRA 集合
- [Educational Style LoRAs](https://civitai.com/collections/24389)
- [Hand-drawn Illustration LoRAs](https://civitai.com/collections/18762)
- [Whiteboard/Chalkboard Art](https://civitai.com/search/models?query=chalkboard)

---

## 下一步

下载完成后：

1. **更新配置文件：**
   ```bash
   # 编辑 services/api/.env
   notepad services/api/.env
   ```

2. **重启服务：**
   ```bash
   scripts/stop.bat
   scripts/start.bat
   ```

3. **测试生成：**
   - 访问 http://localhost:3000
   - 生成一个新视频
   - 检查场景图片是否使用了黑板粉笔风格

4. **查看完整指南：**
   - [QUICK_SETUP_LORA.md](./QUICK_SETUP_LORA.md) - 快速配置指南
   - [VIDEO_QUALITY_IMPROVEMENTS.md](./VIDEO_QUALITY_IMPROVEMENTS.md) - 完整改进方案

---

**更新日期：** 2026-10-08  
**维护者：** ExplainFlow 开发团队
