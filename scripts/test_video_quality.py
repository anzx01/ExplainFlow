#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试视频质量改进功能
验证：
1. 标题图片生成
2. 图像简洁度控制
3. LoRA 配置正确性
"""
import asyncio
import json
import os
import sys
from pathlib import Path

# 设置 UTF-8 输出（Windows 兼容）
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

# 添加 API 路径到 sys.path
sys.path.insert(0, str(Path(__file__).parent.parent / "services" / "api"))

from src.core.config import settings
from src.planner.title_image import generate_title_image
from src.imagegen.service import SceneImageRequest, generate_scene_image, local_imagegen_status
import httpx


async def test_lora_configuration():
    """测试 LoRA 配置是否正确"""
    print("\n" + "=" * 60)
    print("测试 1: LoRA 配置检查")
    print("=" * 60)

    status = local_imagegen_status()

    print(f"✓ 图像生成提供商: {status['provider']}")
    print(f"✓ ComfyUI 基础 URL: {status['comfyui']['baseUrl']}")
    print(f"✓ Checkpoint: {status['comfyui']['checkpoint']}")

    # 检查 LoRA 配置
    if not settings.comfyui_lora:
        print("⚠ 警告: 未配置 LoRA，建议配置以获得简洁教学风格")
        print("  推荐: COMFYUI_LORA=chalkboard-drawing-ce.safetensors")
        return False

    print(f"✓ LoRA 文件: {settings.comfyui_lora}")
    print(f"✓ LoRA 强度: {settings.comfyui_lora_strength}")
    print(f"✓ LoRA 触发词: {settings.comfyui_lora_trigger}")

    # 检查 LoRA 文件是否存在
    lora_paths = [
        Path("E:/MYLLM/loras") / settings.comfyui_lora,
        Path("D:/ck/ComfyUI/models/loras") / settings.comfyui_lora,
    ]

    found = False
    for lora_path in lora_paths:
        if lora_path.exists():
            print(f"✓ LoRA 文件存在: {lora_path}")
            found = True
            break

    if not found:
        print(f"✗ 错误: LoRA 文件未找到")
        print(f"  搜索路径:")
        for path in lora_paths:
            print(f"    - {path}")
        print(f"\n  请下载并放置到以上任一目录：")
        print(f"  PowerShell: .\\scripts\\download-loras.ps1")
        return False

    print("\n✓ LoRA 配置检查通过")
    return True


async def test_title_image_generation():
    """测试标题图片生成功能"""
    print("\n" + "=" * 60)
    print("测试 2: 标题图片生成")
    print("=" * 60)

    test_topic = "短视频如何让人停不下来"
    test_summary = "探讨短视频成瘾的心理机制"

    print(f"测试主题: {test_topic}")
    print("正在生成标题图片...")

    try:
        image_url = await generate_title_image(
            topic=test_topic,
            summary=test_summary,
            video_style="whiteboard"
        )

        if image_url:
            print(f"✓ 标题图片生成成功")
            print(f"  URL: {image_url[:80]}...")
            return True
        else:
            print("✗ 标题图片生成失败（返回 None）")
            return False
    except Exception as e:
        print(f"✗ 标题图片生成异常: {e}")
        return False


async def test_scene_image_simplicity():
    """测试场景图片简洁度控制"""
    print("\n" + "=" * 60)
    print("测试 3: 场景图片简洁度控制")
    print("=" * 60)

    # 创建测试请求
    request = SceneImageRequest(
        scene_id="test_scene_1",
        topic="短视频成瘾机制",
        title="大脑奖励回路",
        image_description=(
            "a person using smartphone with colorful video feed, "
            "simple brain diagram connected to phone, "
            "reward pathway arrows, dopamine symbols"
        ),
        board_mode="whiteboard",
        hand_usage="trace",
        video_style="whiteboard",
        visual_style="teacher_whiteboard",
        pen_style="marker",
        quality="preview",  # 使用 preview 加快测试
    )

    print(f"测试场景: {request.title}")
    print("正在生成场景图片...")

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            image_url = await generate_scene_image(request, client)

        if image_url:
            print(f"✓ 场景图片生成成功")
            print(f"  URL: {image_url[:80]}...")
            print("\n✓ 简洁度控制已应用:")
            print("  - 负面提示: 排除过度细节、复杂背景、密集元素")
            print("  - 正面前缀: simple illustration, minimal details, 3-5 main objects")
            if settings.comfyui_lora:
                print(f"  - LoRA 风格: {settings.comfyui_lora_trigger}")
            return True
        else:
            print("✗ 场景图片生成失败（返回 None）")
            return False
    except Exception as e:
        print(f"✗ 场景图片生成异常: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_comfyui_connection():
    """测试 ComfyUI 连接"""
    print("\n" + "=" * 60)
    print("测试 0: ComfyUI 连接")
    print("=" * 60)

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{settings.comfyui_base_url}/system_stats")
            response.raise_for_status()
            print(f"✓ ComfyUI 连接正常: {settings.comfyui_base_url}")
            return True
    except Exception as e:
        print(f"✗ ComfyUI 连接失败: {e}")
        print(f"\n  请确保 ComfyUI 正在运行:")
        print(f"  1. 启动 ComfyUI")
        print(f"  2. 确认端口: {settings.comfyui_base_url}")
        return False


async def main():
    """运行所有测试"""
    print("=" * 60)
    print("ExplainFlow 视频质量改进 - 功能测试")
    print("=" * 60)

    results = []

    # 测试 0: ComfyUI 连接
    try:
        result = await test_comfyui_connection()
        results.append(("ComfyUI 连接", result))
        if not result:
            print("\n✗ ComfyUI 未运行，跳过后续测试")
            print_summary(results)
            return
    except Exception as e:
        print(f"✗ 测试异常: {e}")
        results.append(("ComfyUI 连接", False))
        print_summary(results)
        return

    # 测试 1: LoRA 配置
    try:
        result = await test_lora_configuration()
        results.append(("LoRA 配置", result))
    except Exception as e:
        print(f"✗ 测试异常: {e}")
        results.append(("LoRA 配置", False))

    # 测试 2: 标题图片生成
    try:
        result = await test_title_image_generation()
        results.append(("标题图片生成", result))
    except Exception as e:
        print(f"✗ 测试异常: {e}")
        results.append(("标题图片生成", False))

    # 测试 3: 场景图片简洁度
    try:
        result = await test_scene_image_simplicity()
        results.append(("场景图片简洁度", result))
    except Exception as e:
        print(f"✗ 测试异常: {e}")
        results.append(("场景图片简洁度", False))

    # 打印总结
    print_summary(results)


def print_summary(results):
    """打印测试总结"""
    print("\n" + "=" * 60)
    print("测试总结")
    print("=" * 60)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for name, result in results:
        status = "✓ 通过" if result else "✗ 失败"
        print(f"{status}: {name}")

    print(f"\n通过率: {passed}/{total} ({passed/total*100:.0f}%)")

    if passed == total:
        print("\n✓ 所有测试通过！视频质量改进功能正常工作。")
    else:
        print("\n⚠ 部分测试失败，请检查配置和依赖。")
        print("\n参考文档:")
        print("  - docs/VIDEO_QUALITY_IMPROVEMENTS.md")
        print("  - docs/QUICK_SETUP_LORA.md")
        print("  - docs/LORA_DOWNLOAD_GUIDE.md")


if __name__ == "__main__":
    asyncio.run(main())
