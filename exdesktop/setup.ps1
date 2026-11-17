# ============================================================
#  tg-hotlist 一键安装脚本
#  - 下载 exDesktop（官方 Releases，portable）
#  - 安装热榜插件、开启“未知来源插件”
#  - 创建桌面/开机启动快捷方式：直接启动 exDesktop，用原生图标
#  说明：插件默认「客户端直连」取数，不依赖本地后台/Python。
#        仅当你想用「本地服务 8765」兜底时，才需要装 Python 后端：
#        双击 setup.bat 默认不装；高级用法：powershell -File setup.ps1 -WithBackend
#  用法：双击同目录的 setup.bat，或在 PowerShell 里执行本脚本
# ============================================================
param([switch]$WithBackend)
$ErrorActionPreference = "Stop"
try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 } catch {}

$ExDir  = $PSScriptRoot                       # ...\exdesktop
$Root   = Split-Path $ExDir -Parent           # ...\default-workspace
$TgDir  = Join-Path $Root "tg-hotlist"
$AppDir = Join-Path $ExDir "app"
$Exe    = Join-Path $AppDir "Telegram.exe"
$PyExe  = Join-Path $TgDir ".venv\Scripts\python.exe"
$Plugin = Join-Path $ExDir "hotlist.plugin"

function Step($n, $msg) { Write-Host "`n[$n/4] $msg" -ForegroundColor Cyan }
function Ok($msg)   { Write-Host "      OK  $msg" -ForegroundColor Green }
function Warn($msg) { Write-Host "      !!  $msg" -ForegroundColor Yellow }

Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "  tg-hotlist 一键安装" -ForegroundColor Cyan
Write-Host "  项目根目录: $Root"
Write-Host "==================================================" -ForegroundColor Cyan

# ---------- 1) exDesktop ----------
Step 1 "检查 exDesktop"
if (Test-Path $Exe) {
    Ok "已存在，跳过下载：$Exe"
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
    if (-not (Test-Path $Exe)) {
        throw "解压后仍未找到 Telegram.exe，请手动从 https://github.com/metawka/exDesktop/releases 下载 portable 版解压到 exdesktop\app"
    }
    Ok "exDesktop 已就绪"
}
# 去掉“来自网络”的标记，减少首次运行的“未知发布者”安全警告
try { Get-ChildItem $AppDir -Recurse -File -ErrorAction SilentlyContinue | Unblock-File -ErrorAction SilentlyContinue } catch {}

# ---------- 2) Python 后端（可选，默认跳过）----------
Step 2 "本地后台（可选）"
if (-not $WithBackend) {
    Ok "已跳过：插件默认走「客户端直连」，不需要后台进程"
    Write-Host "      若想启用「本地服务 8765」兜底：powershell -File setup.ps1 -WithBackend" -ForegroundColor DarkGray
} elseif (Test-Path $PyExe) {
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
# exDesktop 按插件内部 id 命名文件：本插件 __id__ = hotlist_exd，
# 因此必须装成 hotlist_exd.plugin，否则新版沙箱会把它自己的缓存目录判为“受保护路径”。
$PluginTarget = Join-Path $PPlug "hotlist_exd.plugin"
Copy-Item $Plugin $PluginTarget -Force
Remove-Item (Join-Path $PPlug "hotlist.plugin") -Force -ErrorAction SilentlyContinue
Ok "插件已安装：$PluginTarget"

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

# ---------- 4) 快捷方式（直接指向 exDesktop，用原生图标）----------
Step 4 "创建快捷方式"
try {
    $ws = New-Object -ComObject WScript.Shell
    $desk = [Environment]::GetFolderPath("Desktop")
    $lnk = Join-Path $desk "exDesktop 热榜.lnk"
    $s = $ws.CreateShortcut($lnk)
    $s.TargetPath = $Exe
    $s.WorkingDirectory = $AppDir
    $s.IconLocation = "$Exe,0"
    $s.Description = "打开 exDesktop（热榜插件已内置，客户端内直接出榜）"
    $s.Save()
    Ok "桌面快捷方式：$lnk"

    $startup = [Environment]::GetFolderPath("Startup")
    $lnk2 = Join-Path $startup "exDesktop 热榜.lnk"
    $s2 = $ws.CreateShortcut($lnk2)
    $s2.TargetPath = $Exe
    $s2.WorkingDirectory = $AppDir
    $s2.IconLocation = "$Exe,0"
    $s2.Description = "开机启动 exDesktop"
    $s2.Save()
    Ok "开机启动项：$lnk2"

    # 清理旧版（会拉起后台 + 走 wscript 的）快捷方式
    foreach ($oldLnk in @((Join-Path $desk "启动 热榜+exDesktop.lnk"),
                          (Join-Path $startup "tg-hotlist 热榜+exDesktop.lnk"))) {
        if (Test-Path $oldLnk) { Remove-Item $oldLnk -Force -ErrorAction SilentlyContinue }
    }
} catch {
    Warn "创建快捷方式失败（不影响使用）：$($_.Exception.Message)"
}

Write-Host "`n==================================================" -ForegroundColor Green
Write-Host "  安装完成！" -ForegroundColor Green
Write-Host "==================================================" -ForegroundColor Green
Write-Host @"

下一步：
  1. 双击桌面「exDesktop 热榜」（图标就是 exDesktop 原生图标）
  2. exDesktop 首次用手机 Telegram 扫码登录
     （设置 → 设备 → 连接桌面设备）
  3. 打开任意群 → 右上角菜单 / 抽屉 → 「🏆 热门消息榜」

说明：
  · 插件用 exDesktop 自己的会话直连读取，无需额外后台进程，界面就是原生客户端；
  · 若直连偶尔出错，可在插件设置里切到「本地服务 8765」兜底
    （需先按 -WithBackend 装好后端，或双击 tg-hotlist\run_web.bat）；
  · 本项目以 GPL-3.0 发布，详见 LICENSE 与 THIRD-PARTY-NOTICES.md
"@ -ForegroundColor Gray
