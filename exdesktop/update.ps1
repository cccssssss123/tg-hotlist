# ============================================================
#  exDesktop 更新脚本
#  用官方 portable 包替换「程序文件」，保留 tdata（登录/聊天记录/设置）
#  与已安装插件 —— 相当于“原地升级”，不用重新扫码、不用重装插件。
#
#  为什么需要它：exDesktop 自带的「检查更新」在便携版上经常失败
#  （它直接请求 github.com/metawka/exDesktop/releases/latest，国内网络/
#   代理未走/API 限流 时就会报“无法更新”）。本脚本改走同样的 GitHub
#   Release，但下载的是 portable zip，解压后只覆盖程序文件，最稳。
#
#  用法：
#    update.bat                      # 自动查最新版并更新
#    update.bat -Version v7.4.3.2    # 指定版本（GitHub API 被限流时用）
#    update.bat -ZipPath D:\xxx.zip  # 用本地已下载的 zip
#    update.bat -NoBackup            # 不备份旧程序文件（省空间）
#    update.bat -NoLaunch            # 更新后不自动启动
# ============================================================
param(
    [string]$Version = "",
    [string]$ZipPath = "",
    [switch]$NoBackup,
    [switch]$NoLaunch,
    [switch]$Force
)
$ErrorActionPreference = "Stop"
try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 } catch {}

$ExDir  = $PSScriptRoot
$AppDir = Join-Path $ExDir "app"
$Exe    = Join-Path $AppDir "Telegram.exe"
if (-not (Test-Path $Exe)) { throw "未找到 $Exe，请先运行 setup.bat 安装 exDesktop" }

function Get-LocalVer { (Get-Item $Exe).VersionInfo.FileVersion }

$localVer = Get-LocalVer
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "  exDesktop 更新" -ForegroundColor Cyan
Write-Host "  当前版本：$localVer"
Write-Host "  程序目录：$AppDir"
Write-Host "==================================================" -ForegroundColor Cyan

# ---------- 1) 准备 zip ----------
$zip = $ZipPath
$verTag = $null
$dl = $null
if (-not $zip) {
    try {
        $rel = Invoke-RestMethod "https://api.github.com/repos/metawka/exDesktop/releases/latest" `
            -Headers @{ 'User-Agent' = 'exDesktop-updater'; 'Accept' = 'application/vnd.github+json' } -TimeoutSec 60
        $verTag = $rel.tag_name
        $asset = $rel.assets | Where-Object { $_.name -like '*portable*x64*.zip' } | Select-Object -First 1
        if ($asset) { $dl = $asset.browser_download_url }
        Write-Host "最新版本：$verTag" -ForegroundColor Green
    } catch {
        Write-Warning "查询 GitHub 最新版失败：$($_.Exception.Message)"
    }
}
if (-not $zip) {
    if (-not $verTag) {
        if ($Version) { $verTag = if ($Version.StartsWith('v')) { $Version } else { "v$Version" } }
        else { throw "无法获取最新版本。请加 -Version（如 v7.4.3.2）或 -ZipPath（本地 zip）。" }
    }
    $verNum = $verTag.TrimStart('v')
    if (-not $dl) {
        $dl = "https://github.com/metawka/exDesktop/releases/download/$verTag/exDesktop-portable-x64.$verNum.zip"
    }
    $zip = Join-Path $env:TEMP "exDesktop-portable-$verNum.zip"
    if (Test-Path $zip) { Remove-Item $zip -Force }
    Write-Host "下载：$dl"
    $ProgressPreference = 'SilentlyContinue'
    Invoke-WebRequest $dl -OutFile $zip -UseBasicParsing -TimeoutSec 1800
    Write-Host "已下载：$zip（$([math]::Round((Get-Item $zip).Length/1MB,1)) MB）" -ForegroundColor Green
}
if (-not (Test-Path $zip)) { throw "找不到 zip：$zip" }

# ---------- 2) 解压到临时目录并校验 ----------
$tmp = Join-Path $env:TEMP "exd_update_extract"
if (Test-Path $tmp) { Remove-Item $tmp -Recurse -Force }
Add-Type -AssemblyName System.IO.Compression.FileSystem
[System.IO.Compression.ZipFile]::ExtractToDirectory($zip, $tmp)
$newExe = Join-Path $tmp "Telegram.exe"
if (-not (Test-Path $newExe)) { throw "zip 内未找到 Telegram.exe，包可能不完整" }
$newVer = (Get-Item $newExe).VersionInfo.FileVersion
Write-Host "包内版本：$newVer"

if ($newVer -eq $localVer -and -not $Force) {
    Write-Host "已经是最新版本（$localVer），无需更新。" -ForegroundColor Green
    exit 0
}

# ---------- 3) 关闭正在运行的 exDesktop（含其 python 子进程）----------
Write-Host "关闭正在运行的 exDesktop ..."
$killed = 0
Get-Process -ErrorAction SilentlyContinue | ForEach-Object {
    try {
        $p = $_.Path
        if ($p -and $p.StartsWith($AppDir, [StringComparison]::OrdinalIgnoreCase)) {
            Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
            $killed++
        }
    } catch {}
}
if ($killed -gt 0) { Start-Sleep -Seconds 2; Write-Host "  已关闭 $killed 个进程" }

# ---------- 4) 备份旧程序文件（保留 tdata / plugins）----------
if (-not $NoBackup) {
    $bk = Join-Path $ExDir ("backup_before_update\" + $localVer)
    Write-Host "备份旧版本到：$bk"
    New-Item -ItemType Directory -Path $bk -Force | Out-Null
    foreach ($item in @("Telegram.exe", "modules", "python")) {
        $src = Join-Path $AppDir $item
        if (Test-Path $src) {
            $dst = Join-Path $bk $item
            if ((Get-Item $src).PSIsContainer) {
                robocopy $src $dst /E /NFL /NDL /NJH /NJS /NP | Out-Null
            } else {
                Copy-Item $src $dst -Force
            }
        }
    }
}

# ---------- 5) 覆盖程序文件（不碰 tdata、plugins）----------
Write-Host "覆盖程序文件 ..."
Copy-Item $newExe $Exe -Force
foreach ($d in @("modules", "python")) {
    $src = Join-Path $tmp $d
    if (Test-Path $src) {
        $dst = Join-Path $AppDir $d
        robocopy $src $dst /E /NFL /NDL /NJH /NJS /NP | Out-Null
        if ($LASTEXITCODE -ge 8) { throw "复制 $d 失败（robocopy 退出码 $LASTEXITCODE）" }
    }
}
# 去掉“来自网络”标记
try { Get-ChildItem $AppDir -Recurse -File -ErrorAction SilentlyContinue | Unblock-File -ErrorAction SilentlyContinue } catch {}

$nowVer = Get-LocalVer
Write-Host "更新完成：$localVer -> $nowVer" -ForegroundColor Green
Write-Host "（tdata / 插件目录保持不变，登录状态与插件都还在）" -ForegroundColor Gray

# ---------- 6) 启动 ----------
if (-not $NoLaunch) {
    Write-Host "启动 exDesktop ..."
    Start-Process -FilePath $Exe -WorkingDirectory $AppDir
}
