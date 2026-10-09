#!/bin/bash
# 测试视频质量改进功能的便捷脚本

cd "$(dirname "$0")/.."

echo "ExplainFlow 视频质量改进 - 功能测试"
echo "========================================"
echo ""

# 检查 Python 环境
if ! command -v uv &> /dev/null; then
    echo "✗ 错误: 未找到 uv 命令"
    echo "  请先安装: pip install uv"
    exit 1
fi

# 检查 .env 文件
if [ ! -f "services/api/.env" ]; then
    echo "✗ 错误: 未找到 services/api/.env"
    echo "  请复制 .env.example 并配置"
    exit 1
fi

# 运行测试
echo "运行测试..."
echo ""
cd services/api
uv run python ../../scripts/test_video_quality.py

exit_code=$?

echo ""
if [ $exit_code -eq 0 ]; then
    echo "✓ 测试完成"
else
    echo "✗ 测试失败，退出码: $exit_code"
fi

exit $exit_code
