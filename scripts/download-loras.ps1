# ExplainFlow LoRA 下载脚本
# 自动下载推荐的 LoRA 文件到 ComfyUI models 目录

$ErrorActionPreference = "Stop"

# 配置
$LORA_DIR = "E:\MYLLM\loras"
$BACKUP_DIR = "D:\ck\ComfyUI\models\loras"

# 确保目录存在
if (-not (Test-Path $LORA_DIR)) {
    New-Item -ItemType Directory -Path $LORA_DIR -Force | Out-Null
    Write-Host "✓ 创建目录: $LORA_DIR" -ForegroundColor Green
}

if (-not (Test-Path $BACKUP_DIR)) {
    New-Item -ItemType Directory -Path $BACKUP_DIR -Force | Out-Null
    Write-Host "✓ 创建目录: $BACKUP_DIR" -ForegroundColor Green
}

# LoRA 下载清单
$LORAS = @(
    @{
        Name = "Chalkboard Drawing - CE"
        File = "chalkboard-drawing-ce.safetensors"
        Url = "https://civitai.com/api/download/models/846058"
        Description = "黑板粉笔手绘风格（推荐用于板书讲解）"
        Trigger = "chlkbrdCE style"
        Strength = 0.8
        Priority = 1
    },
    @{
        Name = "SDXL ChalkBoardDrawing LoRA"
        File = "sdxl-chalkboard-drawing.safetensors"
        Url = "https://civitai.com/api/download/models/259365"
        Description = "SDXL 黑板绘画风格（备选）"
        Trigger = "chalkboard drawing"
        Strength = 0.75
        Priority = 2
    },
    @{
        Name = "Chalkboard art (黒板アート)"
        File = "chalkboard-art-ilsdxl.safetensors"
        Url = "https://civitai.com/api/download/models/1413078"
        Description = "日式黑板艺术风格（备选）"
        Trigger = "chalkboard art"
        Strength = 0.7
        Priority = 3
    }
)

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "ExplainFlow LoRA 自动下载器" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan

Write-Host "目标目录: $LORA_DIR`n" -ForegroundColor Yellow

# 下载函数
function Download-Lora {
    param (
        [string]$Name,
        [string]$File,
        [string]$Url,
        [string]$Description
    )

    $FilePath = Join-Path $LORA_DIR $File

    if (Test-Path $FilePath) {
        Write-Host "✓ 已存在: $File" -ForegroundColor Green
        return $true
    }

    Write-Host "→ 下载: $Name" -ForegroundColor Yellow
    Write-Host "  描述: $Description" -ForegroundColor Gray
    Write-Host "  文件: $File" -ForegroundColor Gray

    try {
        # 使用 Invoke-WebRequest 下载（带进度条）
        $ProgressPreference = 'SilentlyContinue'
        Invoke-WebRequest -Uri $Url -OutFile $FilePath -UseBasicParsing
        $ProgressPreference = 'Continue'

        # 验证文件大小
        $FileSize = (Get-Item $FilePath).Length / 1MB
        if ($FileSize -lt 1) {
            throw "下载的文件太小（$([Math]::Round($FileSize, 2)) MB），可能下载失败"
        }

        Write-Host "✓ 下载成功: $([Math]::Round($FileSize, 2)) MB" -ForegroundColor Green

        # 复制到备用目录
        $BackupPath = Join-Path $BACKUP_DIR $File
        Copy-Item $FilePath $BackupPath -Force
        Write-Host "  → 已备份到: $BACKUP_DIR" -ForegroundColor Gray

        return $true
    }
    catch {
        Write-Host "✗ 下载失败: $_" -ForegroundColor Red
        if (Test-Path $FilePath) {
            Remove-Item $FilePath -Force
        }
        return $false
    }
}

# 下载所有 LoRA
$SuccessCount = 0
$FailedCount = 0

foreach ($Lora in $LORAS | Sort-Object Priority) {
    Write-Host "`n[$($Lora.Priority)/$($LORAS.Count)] " -NoNewline -ForegroundColor Cyan

    if (Download-Lora -Name $Lora.Name -File $Lora.File -Url $Lora.Url -Description $Lora.Description) {
        $SuccessCount++
    }
    else {
        $FailedCount++
    }

    Start-Sleep -Seconds 1
}

# 总结
Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "下载完成" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "成功: $SuccessCount" -ForegroundColor Green
Write-Host "失败: $FailedCount" -ForegroundColor $(if ($FailedCount -gt 0) { "Red" } else { "Gray" })

# 显示推荐配置
Write-Host "`n推荐配置 (services/api/.env):" -ForegroundColor Yellow
Write-Host "COMFYUI_LORA=$($LORAS[0].File)" -ForegroundColor White
Write-Host "COMFYUI_LORA_STRENGTH=$($LORAS[0].Strength)" -ForegroundColor White
Write-Host "COMFYUI_LORA_TRIGGER=$($LORAS[0].Trigger)" -ForegroundColor White

Write-Host "`n提示: 如果 Civitai 下载失败，请手动访问以下链接下载：" -ForegroundColor Yellow
Write-Host "https://civitai.com/models/648912/chalkboard-drawing-ce" -ForegroundColor Cyan

if ($FailedCount -gt 0) {
    Write-Host "`n注意: 部分 LoRA 下载失败。可能原因：" -ForegroundColor Red
    Write-Host "1. 需要 Civitai 账号登录" -ForegroundColor Gray
    Write-Host "2. 网络连接问题" -ForegroundColor Gray
    Write-Host "3. API 限流" -ForegroundColor Gray
    Write-Host "`n建议手动下载并放到: $LORA_DIR" -ForegroundColor Yellow
}
else {
    Write-Host "`n✓ 所有 LoRA 文件已就绪！" -ForegroundColor Green
}
