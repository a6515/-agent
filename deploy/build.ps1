<#
.SYNOPSIS
    本地构建 Docker 镜像并导出部署包

.DESCRIPTION
    在本地开发电脑上执行：
    1. 构建前端（npm run build）
    2. 构建后端 Docker 镜像
    3. 构建前端 Nginx Docker 镜像
    4. （可选）导出镜像为 tar 文件
    5. （可选）打包完整部署包

.PARAMETER ExportImages
    是否导出 Docker 镜像为 tar 文件（用于离线部署到客户服务器）

.PARAMETER PackageDeploy
    是否打包完整部署包（含镜像 tar + 配置 + 向量库）

.PARAMETER Tag
    镜像版本标签（默认 latest）

.EXAMPLE
    .\deploy\build.ps1
    仅构建 Docker 镜像

.EXAMPLE
    .\deploy\build.ps1 -ExportImages -Tag 1.0.0
    构建并导出镜像

.EXAMPLE
    .\deploy\build.ps1 -PackageDeploy -Tag 1.0.0
    构建并打包完整部署包用于传输到服务器
#>

param(
    [switch]$ExportImages,
    [switch]$PackageDeploy,
    [string]$Tag = "latest"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  致远 OA 公文 Agent — Docker 构建脚本" -ForegroundColor Cyan
Write-Host "  版本标签：$Tag" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

# ---- Step 1：构建前端 ----
Write-Host "`n[1/3] 构建 Vue 前端..." -ForegroundColor Yellow
Push-Location frontend
try {
    npm ci --registry=https://registry.npmmirror.com
    if ($LASTEXITCODE -ne 0) { throw "npm ci 失败" }
    npm run build
    if ($LASTEXITCODE -ne 0) { throw "npm run build 失败" }
    Write-Host "  前端构建完成 → frontend/dist/" -ForegroundColor Green
} finally {
    Pop-Location
}

# ---- Step 2：构建 Docker 镜像 ----
Write-Host "`n[2/3] 构建 Docker 镜像..." -ForegroundColor Yellow

Write-Host "  构建后端镜像 oa-agent:$Tag ..."
docker build -t "oa-agent:$Tag" -f deploy/Dockerfile .
if ($LASTEXITCODE -ne 0) { throw "后端镜像构建失败" }
Write-Host "  后端镜像构建完成" -ForegroundColor Green

Write-Host "  构建前端镜像 oa-agent-nginx:$Tag ..."
docker build -t "oa-agent-nginx:$Tag" -f deploy/Dockerfile.nginx .
if ($LASTEXITCODE -ne 0) { throw "前端镜像构建失败" }
Write-Host "  前端镜像构建完成" -ForegroundColor Green

# ---- Step 3：导出 / 打包 ----
if ($ExportImages -or $PackageDeploy) {
    Write-Host "`n[3/3] 导出镜像..." -ForegroundColor Yellow
    $tarFile = "oa-agent-images-$Tag.tar"
    docker save -o $tarFile "oa-agent:$Tag" "oa-agent-nginx:$Tag"
    if ($LASTEXITCODE -ne 0) { throw "镜像导出失败" }
    Write-Host "  镜像导出完成 → $tarFile" -ForegroundColor Green

    if ($PackageDeploy) {
        Write-Host "  打包部署包..." -ForegroundColor Yellow
        $zipFile = "oa-agent-deploy-$Tag.zip"

        # 打包：镜像 tar + 部署配置 + 向量库（如存在）
        $items = @($tarFile, "deploy/.env.example", "deploy/docker-compose.yml",
                   "deploy/nginx.conf", "deploy/部署说明.md")
        if (Test-Path "data/vector_db") {
            $items += "data/vector_db"
        }

        Compress-Archive -Path $items -DestinationPath $zipFile -Force
        Write-Host "  部署包打包完成 → $zipFile" -ForegroundColor Green
    }
}

Write-Host "`n============================================================" -ForegroundColor Cyan
Write-Host "  构建完成！" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  后端镜像：oa-agent:$Tag" -ForegroundColor White
Write-Host "  前端镜像：oa-agent-nginx:$Tag" -ForegroundColor White
if ($ExportImages) {
    Write-Host "  镜像文件：$tarFile" -ForegroundColor White
}
if ($PackageDeploy) {
    Write-Host "  部署包：$zipFile" -ForegroundColor White
}
Write-Host ""
Write-Host "  本地测试启动：" -ForegroundColor Gray
Write-Host "    cd deploy" -ForegroundColor Gray
Write-Host "    copy .env.example .env  （并编辑填入 API Key）" -ForegroundColor Gray
Write-Host "    docker compose up -d" -ForegroundColor Gray
Write-Host "    http://localhost" -ForegroundColor Gray
