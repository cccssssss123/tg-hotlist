# tg-hotlist —— Telegram 群组热门消息排行 / 本地浏览

在本地运行的只读工具：用你自己的 Telegram 账号登录，
拉取群组最近消息，**按点赞量 / 互动量排序**，生成 Top 榜单。

**两种用法（选一个即可）：**

| | 怎么用 | 适合 |
|---|---|---|
| **本地网页版**（推荐） | 双击 `run_web.bat` → 浏览器开 http://127.0.0.1:8765 | 日常浏览、看榜、切排序、导出 |
| **命令行版** | `run.bat chats` / `run.bat top -g 群名` | 批处理、定时脚本 |

- 不修改、不干扰你正在用的任何 Telegram 客户端（AyuGram 照常用）
- 只读操作：不会发消息、不会点赞，只拉取数据
- 本地原生进程 + MTProto 协议，没有浏览器插件那种 DOM 渲染开销
- 每条消息带 `t.me` 直达链接，点开跳回 AyuGram 看原文
- **不需要 my.telegram.org、不需要短信验证码**（扫码登录 / tdata 导入）

> 网页版完整说明见 **[README_WEB.md](README_WEB.md)**；
> 自建客户端的可行性评估见 **[评估_自建Telegram客户端.md](评估_自建Telegram客户端.md)**。

## 为什么不能做成 AyuGram 的插件

官方 AyuGram Desktop 目前没有插件系统（官方仓库 issue #230 仍为
open 状态）；第三方 PLEngine fork 的插件是 C++ DLL，且只有消息过滤、
右键菜单等 hook，没有"重排聊天视图"的接口。所以这个功能只能做成
外部工具。AyuGram 负责聊天，tg-hotlist 负责看榜，互不冲突。

## 安装 / 登录（一次性）

本项目已自带配好的 `.venv`（telethon / tdata-reader / segno 等已装好），
`run_web.bat` 和 `run.bat` 会自动使用它，**不需要再装任何东西**。

**登录三选一，都不需要 my.telegram.org：**

1. **网页版扫码**（推荐）：双击 `run_web.bat`，页面显示二维码，
   手机 Telegram → 设置 → 设备 → 连接桌面设备 → 扫码。
2. **复用 AyuGram 凭证**：
   `run_web.bat` 页面的「从 tdata 导入」，或命令行
   `python import_tdata.py "C:/Users/你/Downloads/AyuGram/tdata"`。
3. **命令行扫码**：`python tg_hotlist.py qrlogin` 生成 `qr_login.svg`，
   用浏览器打开后手机扫码。

`config.json` 里 `api_id` / `api_hash` 留空即可（用 Telegram Desktop
官方公开常量）。需要走代理就改 `proxy`（本机默认是
`socks5://127.0.0.1:7890`，按你代理软件的实际端口改）。

换机器时重建环境：

```
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

## 使用 · 网页版

双击 `run_web.bat` → 浏览器打开 **http://127.0.0.1:8765**。

左侧选群 → 顶部设「时间范围 / 排序方式 / 条数 / 扫描上限」→
点「加载榜单」。两个标签页：

- **🏆 互动榜**：按所选字段排序的 Top N
- **💬 消息流**：同一批消息按时间倒序浏览

右上角可导出 Markdown / HTML。详见 [README_WEB.md](README_WEB.md)。

## 使用 · 命令行版

```
run.bat chats            # 查看你加入的群/频道列表和 ID
run.bat top -g 群组名     # 生成热门榜（默认按互动分排）
```

（命令行里也可以 `python tg_hotlist.py ...`，效果相同）

`top` 常用参数：

| 参数 | 说明 | 默认 |
|------|------|------|
| `-g` | 群组：ID / @用户名 / t.me 链接 / 名称（支持部分匹配） | config 里的 defaults.group |
| `-d` | 统计最近几天；`365` = 最近一年，`0` = 历史全部（不限时间） | 3 |
| `-n` | 榜单条数 | 20 |
| `--by` | `score` 互动分 / `reactions` 点赞量 / `replies` 回复数 / `views` 浏览量 / `forwards` 转发数 | score |
| `--limit` | 最多扫描多少条消息 | 5000 |
| `--json x.json` | 额外导出 JSON | 无 |

例：

```
run.bat top -g 某某交流群 -d 7 -n 30 --by reactions
python tg_hotlist.py top -g -1001234567890 -d 1 --by views
```

需要走代理的话，把 config.json 的 proxy 改成（按你代理软件的实际端口）：

```json
"proxy": { "scheme": "socks5", "host": "127.0.0.1", "port": 7890 }
```

注：socks 代理需要 `python-socks`（.venv 里已装好）；http 代理不需要。

输出文件在 `output/` 目录：`hotlist_群名_时间.md` / `.html`，
双击 HTML 就能在浏览器里看带样式的榜单，点链接直达原消息。

### 互动分是什么

`score = 1×点赞 + 1×回复 + 2×转发 + 0.05×min(浏览量, 20)`

点赞和回复是"深度互动"，权重 1；转发传播力最强，权重 2；浏览量
刷分太容易所以封顶 20 再乘 0.05（最多贡献 1 分）。权重可以在
config.json 的 `defaults.weights` 里自己调。

## 常见问题

- **my.telegram.org 登不上 / 收不到验证码？** 完全不用它。
  用网页版扫码登录，或 `import_tdata.py` 复用 AyuGram 的凭证。
  见 [README_WEB.md](README_WEB.md) 的「登录方式」。
- **扫码后一直没反应？** 二维码约 30–60 秒过期，点「刷新二维码」重试；
  确认手机 Telegram 能联网，且「设置 → 设备」里能看到自己。
- **提示 FloodWait / 限流？** Telegram 对拉历史消息有频率限制，等它
  提示的秒数再跑；`--limit` 别一次设几十万。网页版已内置 5 分钟缓存
  和 2 秒抓取间隔。
- **想换账号？** 网页版点右上「退出」，或命令行
  `python tg_hotlist.py logout`，然后重新扫码。
- **安全性？** 配置和 session 文件都只在你本地；本工具全程只读。
  不要把 `tg_hotlist.session` 发给任何人。
- **登录会不会把 AyuGram 挤下线？** 不会。同一个账号可以多端同时在线
  （就像手机 + 电脑同时登录一样）。退出按钮只删本机会话，不会登出 AyuGram。

## 文件说明

```
web_app.py          网页版后端（常驻连接 + HTTP 服务 + 缓存/限速）
web\                网页版前端（index.html / style.css / app.js）
run_web.bat         网页版一键启动（双击后自动开浏览器）
run_web_silent.bat  网页版静默启动（无黑窗口）
run_panel.bat       侧边面板启动（Edge 无地址栏窗口）
stop_web.bat        一键停止网页版服务
README_WEB.md       网页版完整说明
评估_自建Telegram客户端.md   可行性评估
tg_hotlist.py       命令行主程序 + 数据/排序核心
import_tdata.py     tdata 免验证码导入
periodic_likes.py   按年/月点赞榜（CLI）
test_offline.py     离线单元测试（不联网，可随时跑）
.venv\              自带虚拟环境（依赖已装好）
config.json         你的配置（含代理设置）
config.example.json 配置模板
tg_hotlist.session  登录会话（勿外传）
tdata_import.json   会话来源元数据
output/             榜单输出目录
run.bat             CLI 快捷脚本
```
