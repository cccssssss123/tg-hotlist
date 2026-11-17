# tg-hotlist 本地网页版（浏览 + 互动榜）

一个只在本机运行的 Telegram **只读**客户端：用于浏览群/频道消息、
查看按点赞量或互动量排序的榜单。**不替代 AyuGram**，聊天继续用原来的客户端。

- 全程只读：不发消息、不点赞、不修改任何聊天数据
- 本地原生进程直连 MTProto，没有浏览器插件那种 DOM 渲染开销
- 不需要 my.telegram.org、不需要短信验证码、不需要申请 api_id/api_hash
- 只监听 `127.0.0.1`，数据不出本机

## 启动（重要：每次用之前先启动）

**双击 `run_web.bat`** —— 它会启动本地服务，并在约 3 秒后自动打开浏览器
（http://127.0.0.1:8765）。**那个黑色窗口要保持开着**，关掉它 = 服务停止。

> 为什么打不开链接？因为服务只在你双击 bat 后运行，用完关窗就没了。
> 这不是坏了 —— 下次用之前**再双击一次 `run_web.bat`** 即可。
> （不要用我之前在对话里临时起的后台服务，那是绑在会话上的，会话一结束就没了。）

三个启动脚本按需选：

| 脚本 | 行为 | 适用 |
|---|---|---|
| `run_web.bat` | 开一个黑窗口跑服务 + 自动开浏览器；关窗即停 | **推荐**，最直观 |
| `run_web_silent.bat` | 无黑窗口，后台静默启动 + 开浏览器 | 嫌黑窗口烦 |
| `stop_web.bat` | 一键停掉上面启动的服务 | 想彻底关闭时 |
| `run_panel.bat` | 用 Edge `--app=` 开成无地址栏的侧边小窗 | 想贴着 AyuGram 用 |

> 这些 `.bat` 特意只用英文写：Windows 的 `cmd.exe` 无法可靠解析 bat 文件里
> 的 UTF-8 中文注释（会把中文字节当命令拆开，导致启动失败）。别往里加中文。

首次打开会显示二维码：手机 Telegram → **设置 → 设备 → 连接桌面设备** → 扫码。
（如果已有 `tg_hotlist.session`，会直接进入主界面，不用再登录。）

也可手动命令行启动：

```
.venv\Scripts\python.exe -X utf8 web_app.py
.venv\Scripts\python.exe -X utf8 web_app.py --port 9000   # 换端口
```

停止：在窗口里按 `Ctrl+C`，或双击 `stop_web.bat`。

### 和 AyuGram 一起用（侧边面板）

双击 **`run_panel.bat`**：它会先确保后端在跑，再用 Edge 的 `--app=` 模式
把网页版开成一个**没有地址栏、没有标签栏**的独立小窗，看起来就像
AyuGram 旁边的一个原生面板。可以用 `Win + 方向键` 贴靠，或改脚本里的
`--window-position=1440,40` 让它固定在右侧。

这不修改 AyuGram 任何文件；两边通过同一份 tdata 凭证共享登录，
网页版每条消息的 `t.me` 链接点开就跳回 AyuGram。

> 真要「AyuGram 菜单里多一项」必须改 C++/Qt 源码并全量编译，
> 门槛与替代方案见 [评估_自建Telegram客户端.md](评估_自建Telegram客户端.md) 第 9 节。

## 界面

| 区域 | 说明 |
|---|---|
| 左侧 | 你加入的群组/频道列表，可搜索；点一个即加载 |
| 顶部工具栏 | 时间范围、排序方式、榜单条数、扫描上限、强制刷新、导出 |
| 🏆 互动榜 | 按所选字段排序的 Top N，每条都有「在客户端打开」按钮，点一下直接跳到客户端里的原消息 |
| 💬 消息流 | 同一批消息按时间倒序浏览（最多 300 条） |

**时间范围**可选：最近 1 / 2 / 3 / 7 / 30 天、**最近 1 年（365 天）**、
**历史全部**。

- 选「最近 1 年」或「历史全部」时，扫描上限会自动提到 5 万条
  （可手动调，最高 20 万）；有时间下界的范围遇到下界就停，设大上限不会变慢，
  反而能避免默认 5000 条把一年/全历史截断。全历史结果里会显示实际扫到的最早日期。
- 全历史（以及消息很多的一年范围）会逐页拉取，`wait_time=0.5` 秒/页，
  **几万条可能要几分钟到十几分钟**，期间请耐心等待（群列表和状态仍可访问，
  但切群要等当前扫描结束）。实测「最近 1 年」在两万条消息的群里约 2 分钟。
  超过 5 万条会非常慢，还可能触发 Telegram 限流，不建议轻易拉满 20 万上限。
- 若消息数超过扫描上限，页面会提示「更早的消息没有统计」，调大上限后
  点「强制刷新」即可。结果按「群 + 时间范围 + 上限」缓存 5 分钟，
  切换排序方式不会重新联网。
- 命令行同样支持：`run.bat top -g 群名 -d 365`、`-d 0`（全历史）。

排序方式：

- `互动分` = 1×点赞 + 1×回复 + 2×转发 + 0.05×min(浏览量, 20)
- `点赞量` / `回复数` / `转发数` / `浏览量` = 单独按该字段排

群和频道的互动形态不同：群以点赞/回复为主，频道以浏览/转发为主，
看频道时建议切到「浏览量」或「转发数」。

## 一点直达：在客户端里打开消息

榜单/消息流里的每条都有「**在客户端打开 ↗**」按钮。它用的是
Telegram 客户端的**内部深链**，不经过 `t.me` 网页：

```
私有群/频道： tg://privatepost?channel=<id>&post=<msg_id>
公开群/频道： tg://resolve?domain=<username>&post=<msg_id>
```

这与 tdesktop 源码 `Core::TryConvertUrlToLocal()` 把 `https://t.me/c/...`
转换成的本地链接完全一致。点一下 → 直接唤起 AyuGram 并定位到那条消息，
**不再有「网页 → 再点一次进 App」的中间跳转**。旁边保留「网页 ↗」小链接
作为备用（分享/在别的机器上看时用），导出的 MD/HTML 里也带直达链接。

本机 `tg://` 协议已注册到
`C:\...\AyuGram\AyuGram.exe`，换了客户端会自动跟随
注册表，无需改配置（也可在 `config.json` 用 `client_exe` 强制指定）。

两种打开方式（`config.json` 的 `open_mode`）：

| 值 | 行为 | 适用 |
|---|---|---|
| `browser`（默认） | 交给浏览器打开 `tg://`，首次弹一次「打开 AyuGram？」确认框，勾选「始终允许」后即一点直达 | **所有场景，最可靠** |
| `backend` | 本地服务静默唤起客户端，**无确认框** | 服务运行在普通桌面会话（双击 `run_web.bat`）且验证有效时 |

`backend` 模式会等待客户端响应；若没响应（例如服务被后台/受限会话启动时
GUI 进程卡在初始化），会**自动清理残留进程并回退到浏览器方式**，
不会出现点了没反应的情况。所以默认 `browser` 最省心。

> 安全：后端只接受 `privatepost` / `resolve` 两种消息深链，并严格校验
> 参数，拒绝 `tg://socks`、`tg://join` 等其他动作。

## 登录方式

**方式一：扫码（推荐）**
利用 Telegram 官方的 QR 登录流程（`auth.exportLoginToken`），
不需要 my.telegram.org，也不需要短信验证码。登录结果保存到
`tg_hotlist.session` + `tdata_import.json`，之后免登录。

**方式二：从 AyuGram 的 tdata 导入**
登录页填 `C:/Users/你/Downloads/AyuGram/tdata`（设置过本地密码就填密码）。
复用桌面客户端已有的登录凭证。命令行等价：

```
.venv\Scripts\python.exe import_tdata.py "C:/Users/你/Downloads/AyuGram/tdata"
```

**命令行备用**：`tg_hotlist.py qrlogin` 会生成 `qr_login.svg`，
用浏览器打开后手机扫码，适合网页服务暂时起不来的情况。

> ⚠️ 「退出」按钮只删除本机会话文件，**不会**调用 Telegram 的
> `auth.logOut`。因为 tdata 导入的会话与 AyuGram 共享授权密钥，
> 调用 logOut 会把 AyuGram 一起登出。

## 缓存与限流

为避免触发 Telegram 的 `FLOOD_WAIT`：

- 一次抓取的结果按「群 + 天数 + 扫描上限」缓存 **5 分钟**；
  切换排序方式 / 条数只重算内存，不重新联网。
- 两次真实抓取之间强制间隔 **2 秒**。
- `collect_messages` 每页请求之间自带 0.5 秒间隔。
- 触发限流时页面会提示等待秒数，不会疯狂重试。

「强制刷新」会跳过缓存重新拉取，请节制使用。

## 配置

`config.json`（首次运行自动生成）：

```json
{
  "api_id": 0,
  "api_hash": "",
  "phone": "",
  "proxy": { "scheme": "socks5", "host": "127.0.0.1", "port": 7890 },
  "client_exe": "",
  "open_mode": "browser",
  "defaults": {
    "days": 3, "top": 20, "limit": 5000, "by": "score",
    "weights": { "reaction": 1, "reply": 1, "forward": 2, "view": 0.05, "view_cap": 20 }
  }
}
```

`api_id` / `api_hash` 留空即可（网页版用 Telegram Desktop 官方公开常量）。
代理按你本机代理软件的实际端口改；`socks5` 需要 `python-socks`，
`http` 不需要。`client_exe` 留空 = 用系统注册的 `tg://` 客户端；
`open_mode` 见上节。改完配置重启网页服务生效。

## 文件

```
web_app.py            后端：常驻 Telethon 连接 + 标准库 HTTP 服务 + 缓存/限速
web/index.html        前端页面结构
web/style.css         样式（深色）
web/app.js            前端逻辑（原生 JS，无框架、无 CDN）
run_web.bat           Windows 启动脚本
tg_hotlist.py         数据/排序核心（同时也保留全部 CLI 命令）
import_tdata.py       tdata 免验证码导入
periodic_likes.py     按年/月点赞榜（CLI 工具）
README_WEB.md         本文件
```

## 依赖

`.venv` 里已装好（离线安装的，无需联网）：

```
telethon 1.45.0
tdata-reader 0.1.0
python-socks 3.2.1
pyaes 1.6.1 / rsa 4.9.1 / pyasn1 0.6.5
segno 1.6.6        （二维码生成）
```

重建环境（换机器时）：

```
python -m venv .venv
.venv\Scripts\pip install telethon tdata-reader python-socks segno
```

## 与原 CLI 的关系

网页版复用 `tg_hotlist.py` 的登录、群解析、消息统计、排序、渲染函数，
原来的命令行完全保留：

```
run.bat chats
run.bat top -g 群名 --by reactions
python periodic_likes.py -g @examplechannel --mode month
```

## 风险提示

- 使用非官方客户端登录的账号会被 Telegram 置于观察之下；刷量/批量写操作
  可能导致永久封号。本工具坚持只读、限速、缓存。
- 本地缓存只在内存中（不落盘聊天内容），但 `tg_hotlist.session`
  等同登录凭证，请勿外传。
- 榜单是**快照**：点赞/反应会随时间变化，需要时点「强制刷新」。
