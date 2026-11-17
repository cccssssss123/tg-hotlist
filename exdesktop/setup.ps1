# ============================================================
#  tg-hotlist 一键安装脚本
#  - 下载 exDesktop（官方 Releases，portable）
#  - 建 Python 虚拟环境并装依赖
#  - 安装热榜插件、开启“未知来源插件”
#  - 创建桌面/开机启动快捷方式
#  用法：双击同目录的 setup.bat，或在 PowerShell 里执行本脚本
# ============================================================
$ErrorActionPreference = "Stop"
try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 } catch {}

$ExDir  = $PSScriptRoot                       # ...\exdesktop
$Root   = Split-Path $ExDir -Parent           # ...\default-workspace
$TgDir  = Join-Path $Root "tg-hotlist"
$AppDir = Join-Path $ExDir "app"
$PyExe  = Join-Path $TgDir ".venv\Scripts\python.exe"
$Plugin = Join-Path $ExDir "hotlist.plugin"
$Vbs    = Join-Path $ExDir "start_silent_all.vbs"

function Step($n, $msg) { Write-Host "`n[$n/4] $msg" -ForegroundColor Cyan }
function Ok($msg)   { Write-Host "      OK  $msg" -ForegroundColor Green }
function Warn($msg) { Write-Host "      !!  $msg" -ForegroundColor Yellow }

Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "  tg-hotlist 一键安装" -ForegroundColor Cyan
Write-Host "  项目根目录: $Root"
Write-Host "==================================================" -ForegroundColor Cyan

# ---------- 1) exDesktop ----------
Step 1 "检查 exDesktop"
if (Test-Path (Join-Path $AppDir "Telegram.exe")) {
    Ok "已存在，跳过下载：$AppDir\Telegram.exe"
} else {
    Write-Host "      正在查询 GitHub 最新版本..."
    $rel = Invoke-RestMethod "https://api.github.com/repos/metawka/exDesktop/releases/latest" -TimeoutSec 60
    $asset = $rel.assets | Where-Object { $_.name -like "*portable*x64*.zip" } | Select-Object -First 1
    if (-not $asset) { throw "未找到 portable x64 资源（版本 $($rel.tag_name)）" }
    Ok "最新版 $($rel.tag_name)：$($asset.name)（$([math]::Round($asset.size/1MB)) MB）"
    $zip = Join-Path $ExDir "_dl_exdesktop.zip"
    Write-Host "      下载中（可能需几分钟）..."
    Invoke-WebRequest $asset.browser_download_url -OutFile $zip -UseBasicParsing -TimeoutSec 900
    Write-Host "      解压中..."
    New-Item -ItemType Directory -Path $AppDir -Force | Out-Null
    Expand-Archive -Path $zip -DestinationPath $AppDir -Force
    Remove-Item $zip -Force -ErrorAction SilentlyContinue
    if (-not (Test-Path (Join-Path $AppDir "Telegram.exe"))) {
        throw "解压后仍未找到 Telegram.exe，请手动从 https://github.com/metawka/exDesktop/releases 下载 portable 版解压到 exdesktop\app"
    }
    Ok "exDesktop 已就绪"
}

# ---------- 2) Python 依赖 ----------
Step 2 "检查 Python 虚拟环境"
if (Test-Path $PyExe) {
    Ok "已存在，跳过：$PyExe"
} else {
    $py = $null
    foreach ($cand in @("py", "python")) {
        $cmd = Get-Command $cand -ErrorAction SilentlyContinue
        if ($cmd) { $py = $cmd.Source; break }
    }
    if (-not $py) {
        throw "未找到 Python。请先安装 Python 3.9+（勾选 Add to PATH）后重试：https://www.python.org/downloads/"
    }
    Ok "使用 Python：$py"
    Write-Host "      创建虚拟环境..."
    if ((Split-Path $py -Leaf) -ieq "py.exe") { & $py -3 -m venv (Join-Path $TgDir ".venv") }
    else { & $py -m venv (Join-Path $TgDir ".venv") }
    if (-not (Test-Path $PyExe)) { throw "虚拟环境创建失败" }
    Write-Host "      安装依赖（若网络慢会自动换清华镜像）..."
    & $PyExe -m pip install --upgrade pip -q
    $okdeps = $true
    try {
        & $PyExe -m pip install -r (Join-Path $TgDir "requirements.txt") -q
    } catch {
        $okdeps = $false
    }
    if (-not $okdeps) {
        Warn "默认源安装失败，改用清华镜像重试..."
        & $PyExe -m pip install -r (Join-Path $TgDir "requirements.txt") -q -i https://pypi.tuna.tsinghua.edu.cn/simple
    }
    Ok "Python 依赖安装完成"
}

# ---------- 3) 安装插件 + 开启未知来源 ----------
Step 3 "安装热榜插件"
$PPlug = Join-Path $AppDir "tdata\plugins\plugins"
New-Item -ItemType Directory -Path $PPlug -Force | Out-Null
if (-not (Test-Path $Plugin)) { throw "找不到插件文件：$Plugin" }
Copy-Item $Plugin (Join-Path $PPlug "hotlist.plugin") -Force
Ok "插件已安装：$PPlug\hotlist.plugin"

$cfgDir = Join-Path $AppDir "tdata"
New-Item -ItemType Directory -Path $cfgDir -Force | Out-Null
$cfg = Join-Path $cfgDir "extera.json"
try {
    if (Test-Path $cfg) {
        $j = Get-Content $cfg -Raw -Encoding UTF8 | ConvertFrom-Json
        $j | Add-Member -NotePropertyName plugins_unknown_sources -NotePropertyValue $true -Force
        $jsonText = $j | ConvertTo-Json -Depth 30
    } else {
        $jsonText = @{ plugins_unknown_sources = $true } | ConvertTo-Json
    }
    # 注意：extera.json 必须是无 BOM 的 UTF-8，否则 Qt 解析会失败
    [System.IO.File]::WriteAllText($cfg, $jsonText, (New-Object System.Text.UTF8Encoding($false)))
    Ok "已允许未知来源插件（plugins_unknown_sources=true）"
} catch {
    Warn "写 extera.json 失败：$($_.Exception.Message)。请稍后在 exDesktop 设置→插件里手动开启“允许未知来源插件”。"
}

# ---------- 4) 快捷方式 ----------
Step 4 "创建快捷方式"
try {
    $ws = New-Object -ComObject WScript.Shell
    $desk = [Environment]::GetFolderPath("Desktop")
    $lnk = Join-Path $desk "启动 热榜+exDesktop.lnk"
    $s = $ws.CreateShortcut($lnk)
    $s.TargetPath = "$env:SystemRoot\System32\wscript.exe"
    $s.Arguments = '"' + $Vbs + '"'
    $s.WorkingDirectory = $ExDir
    $s.Description = "静默启动 tg-hotlist 后端 + exDesktop"
    $exeIcon = Join-Path $AppDir "Telegram.exe"
    if (Test-Path $exeIcon) { $s.IconLocation = "$exeIcon,0" }
    $s.Save()
    Ok "桌面快捷方式：$lnk"

    $startup = [Environment]::GetFolderPath("Startup")
    $lnk2 = Join-Path $startup "tg-hotlist 热榜+exDesktop.lnk"
    $s2 = $ws.CreateShortcut($lnk2)
    $s2.TargetPath = "$env:SystemRoot\System32\wscript.exe"
    $s2.Arguments = '"' + $Vbs + '"'
    $s2.WorkingDirectory = $ExDir
    $s2.Description = "开机静默启动 tg-hotlist 后端 + exDesktop"
    $s2.Save()
    Ok "开机启动项：$lnk2"
} catch {
    Warn "创建快捷方式失败（不影响使用）：$($_.Exception.Message)"
}

Write-Host "`n==================================================" -ForegroundColor Green
Write-Host "  安装完成！" -ForegroundColor Green
Write-Host "==================================================" -ForegroundColor Green
Write-Host @"

下一步：
  1. 双击桌面「启动 热榜+exDesktop」（或已设置的开机自启）
  2. exDesktop 首次用手机 Telegram 扫码登录
     （设置 → 设备 → 连接桌面设备）
  3. 打开任意群 → 菜单/抽屉 → 「热门消息榜」

说明：
  · 插件用 exDesktop 自己的会话直连读取，不需要额外进程；
  · 若直连出错会自动改用本地服务（run_web.bat）。
  · 本项目以 GPL-3.0 发布，详见 LICENSE 与 THIRD-PARTY-NOTICES.md
"@ -ForegroundColor Gray
