# tg-hotlist · Telegram 群组热门消息榜

[![CI](https://github.com/cccssssss123/tg-hotlist/actions/workflows/ci.yml/badge.svg)](https://github.com/cccssssss123/tg-hotlist/actions/workflows/ci.yml)

[English](README.en.md) | **简体中文**

给 Telegram 群组/频道按**点赞量 / 互动量**排「热门消息榜」的本地工具。
全程**只读**：不发消息、不点赞、不修改任何聊天数据。

提供两种形态，任选其一即可：

| 形态 | 说明 | 适合 |
|---|---|---|
| **A. 本地网页版** | 浏览器打开 `127.0.0.1:8765`，选群出榜、导出 | 不想装第三方客户端 |
| **B. exDesktop 插件** | 在开源客户端 [exDesktop](https://github.com/metawka/exDesktop) 内，右键菜单直接出榜 | 想在聊天客户端里一键看榜（推荐） |

两者共享同一套统计/排序逻辑，数据都只在**你自己的电脑**上。

---

## 目录结构

```
default-workspace/
├── tg-hotlist/                 # 后端 + 网页版 + CLI
│   ├── tg_hotlist.py           # 核心：登录、拉消息、反应/回复/转发/浏览统计、排序、渲染
│   ├── web_app.py              # 本地网页版后端（常驻连接 + HTTP 服务 + 缓存/限速）
│   ├── web/                    # 网页前端（原生 JS，无框架）
│   ├── import_tdata.py         # 从 AyuGram/Telegram Desktop 的 tdata 免验证码导入会话
│   ├── periodic_likes.py       # 按年/月点赞榜（CLI）
│   ├── run_web.bat             # 一键启动网页版（自动开浏览器）
│   ├── run_web_silent.bat      # 静默启动（无黑框）
│   ├── run_panel.bat           # 侧边面板（Edge 无地址栏小窗）
│   ├── stop_web.bat            # 停止服务
│   ├── run.bat                 # CLI 快捷入口
│   ├── README.md               # 详细说明（CLI + 登录）
│   ├── README_WEB.md           # 网页版详细说明
│   ├── 评估_自建Telegram客户端.md   # 技术路线评估
│   └── test_offline.py         # 离线单元测试
│
├── exdesktop/                  # exDesktop 插件（形态 B）
│   ├── hotlist.plugin          # 插件源码（Python，exteraGram 格式）
│   ├── setup.bat               # 一键安装（下载客户端 + 装插件 + 建快捷方式）
│   ├── update.bat              # 一键更新（换成新版程序，保留 tdata 与插件）
│   ├── start_all.bat           # 启动后端 + exDesktop（可选兜底）
│   ├── start_silent_all.vbs    # 无窗口静默启动（可放开机启动）
│   ├── README_集成exDesktop.md # 插件安装与使用
│   ├── 官方插件清单.txt         # exDesktop 官方插件目录（518 个）
│   ├── test_plugin.py          # 插件逻辑测试（stub SDK + 真后端）
│   └── test_cache.py           # 缓存/增量/相册合并测试
│
└── README.md                   # ← 本文件
```

> 注：`tg-hotlist/.venv`、`exdesktop/app`（260MB 客户端）、登录会话、`config.json`
> 等属于运行产物或敏感数据，**不入库**（见 `.gitignore`）。

---

## 快速开始

### 一键安装（推荐）

双击 **`exdesktop/setup.bat`**，它会自动：

1. 从 exDesktop 官方 Releases 下载 portable 版并解压到 `exdesktop/app`
2. 安装热榜插件，并开启「允许未知来源插件」（写 `extera.json`，注意无 BOM）
3. 创建桌面快捷方式 + 开机启动项，**直接启动 exDesktop（原生图标 / 原生界面）**

> **不需要本地后台**：插件默认走「客户端直连」（用 exDesktop 自己的登录会话发
> MTProto），没有额外进程、没有网页跳转。只有当你想用「本地服务 8765」兜底时，
> 才需要 Python 后端：`powershell -File exdesktop\setup.ps1 -WithBackend`。

装完双击桌面「exDesktop 热榜」→ exDesktop 首次扫码登录 → 打开群 → 菜单 →
「🏆 热门消息榜」即可。

> **以后要升级 exDesktop**：双击 **`exdesktop/update.bat`** 即可（自动拉最新
> portable 包、只覆盖程序文件，**保留 tdata 与插件**，不用重新扫码）。
> exDesktop 自带的「检查更新」在便携版上常失败（它直连 GitHub API，国内网络/
> 代理限流时就会报“无法更新”），用这个脚本最稳。

> 脚本只下载官方 exDesktop，**不随仓库分发任何客户端二进制**。
> 若下载失败，可自行到 https://github.com/metawka/exDesktop/releases 下载
> portable 版解压到 `exdesktop/app` 后重跑。

### 形态 A：网页版（不装第三方客户端）

1. 双击 `tg-hotlist/run_web.bat`
2. 浏览器自动打开 `http://127.0.0.1:8765`
3. 首次用**手机 Telegram 扫码**登录（不需要 my.telegram.org、不需要短信验证码）
4. 左侧选群 → 顶部设「时间范围 / 排序 / 条数」→ 加载榜单

### 形态 B：exDesktop 插件（推荐）

见上面「一键安装」。手动步骤详见
[exdesktop/README_集成exDesktop.md](exdesktop/README_集成exDesktop.md)。

---

## 功能

- **排序**：互动分 / 点赞量 / 回复数 / 转发数 / 浏览量
- **时间范围**：最近 1/3/7/30 天、最近 1 年、历史全部（**每个群独立记忆**，新群默认 3 天）
- **榜单条数**：Top 10/15/20/30/50/100/200/500
- **相册合并**：同一条消息里的多图/多视频（共享 `grouped_id`）合并为一条，不重复占榜
- **一点直达**：榜单条目点击 → 用 `tg://` 深链在客户端内跳到原消息（不经网页跳转）
- **本地缓存 + 增量**：SQLite 落盘，同一群第二次起秒开；「刷新」只拉新消息
- **导出**：Markdown / HTML（含直达链接）
- **互动分公式**：`1×点赞 + 1×回复 + 2×转发 + 0.05×min(浏览量, 20)`

---

## 登录方式（都不需要 my.telegram.org）

1. **扫码（推荐）**：网页版/插件首次打开显示二维码，手机 Telegram → 设置 → 设备 → 连接桌面设备 → 扫码。
2. **复用 AyuGram 凭证**：`python import_tdata.py "C:/.../AyuGram/tdata"`（免验证码）。
3. **命令行扫码**：`python tg_hotlist.py qrlogin`（生成 `qr_login.svg`）。

> 桌面版 exDesktop 插件用**客户端自己的登录会话**直连读取；网页版后端用独立会话。
> 二者互不影响，可同时使用。

---

## 架构与关键限制

**取数两条路**（插件里可切换）：

| 模式 | 说明 | 需要后端进程 |
|---|---|---|
| 客户端直连（默认） | 插件用 exDesktop 自己的会话发 MTProto `messages.getHistory` | 不需要 |
| 本地服务 8765 | 走 tg-hotlist 后端（独立 Telethon 会话） | 需要 |

**能力边界（重要，避免误解）**：

- 桌面客户端（tdesktop 系）的插件 API **不提供消息视图/单元格/绘制**相关 hook，
  因此**不能把聊天列表本身按点赞重排**——只能"另开一个榜单视图"（这就是本工具）。
- 插件沙箱**禁止访问 `tdata` 本地缓存**，SDK 也没有枚举内存消息的接口。
  所以任何方案本质都是"再向 Telegram 请求一次历史消息"；本工具的"本地缓存"
  是我们自己另存的（插件目录），不是客户端缓存。

---

## 依赖

- Python 3.9+（已在 `tg-hotlist/.venv` 内置）
- `telethon`、`tdata-reader`、`python-socks`、`segno`（`tg-hotlist/requirements.txt`）
- 可选：`exDesktop`（形态 B，第三方开源客户端，GPL-3.0）

重建环境：

```
cd tg-hotlist
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

---

## 测试

```
cd tg-hotlist   && .venv\Scripts\python.exe -X utf8 test_offline.py
cd exdesktop    && ..\tg-hotlist\.venv\Scripts\python.exe -X utf8 test_plugin.py
                    ..\tg-hotlist\.venv\Scripts\python.exe -X utf8 test_cache.py
```

`test_plugin.py` / `test_cache.py` 会打真实后端 8765（需先启动），用于验证
弹窗结构、排序切换、缓存增量、相册合并、离线兜底等。

---

## 风险与合规

- 使用非官方客户端登录的账号会被 Telegram「置于观察」；刷量/批量写操作可能被封。
  本工具坚持**只读 + 限速 + 缓存**。
- `exDesktop` 是第三方构建，请自行评估信任；其数据目录独立，出问题不影响 AyuGram。
- 登录会话文件（`*.session`、`tdata_import.json`）等同账号凭证，**切勿外传**。
- 榜单是**快照**：点赞/反应会随时间变化，需要时点「刷新」。

---

## 许可证

本项目以 **GNU GPL v3.0** 发布，见 [LICENSE](LICENSE)；第三方组件与合规说明见
[THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md)。

**关于「能否修改后上传 GitHub 开源」（重点）：**

- exDesktop 采用 **GPL-3.0**。GPL-3.0 **允许**修改、再分发、上传到 GitHub 开源，
  也允许商用；但必须遵守：
  1. 衍生作品同样以 **GPL-3.0** 发布；
  2. 提供**完整对应源码**；
  3. 保留版权与许可声明，并**注明你的修改**；
  4. **不得**附加超出 GPL 的额外限制（不能变成闭源/专有附加条款）。
- 本项目**没有修改 exDesktop 的 C++ 源码**，而是以**插件**形式扩展（独立 Python
  文件，运行时导入其 SDK）。该插件通常被视为与 GPL 程序结合，因此本项目整体以
  **GPL-3.0** 发布最稳妥、最省事。
- **本仓库不分发 exDesktop 二进制**（一键安装时才从官方 Releases 下载）。
  如果你把 exDesktop 二进制**一并打包分发**，则触发 GPL "提供完整对应源码"义务，
  需附带 exDesktop 的完整源码 —— 建议保持"只发插件、让用户自行下载客户端"的方式。
- **商标**：GPL 不授予 "exDesktop" 名称/图标的商标使用权，宣传时请勿让人误以为
  是官方版本（建议表述为 "exDesktop 插件"）。

## 变更记录 / 检查点

- **v1.2.4（当前检查点）**
  - 兼容 exDesktop **7.4.3.2** 收紧后的插件沙箱：插件的**文件名必须等于内部
    id**（本插件装成 `hotlist_exd.plugin`），否则它自己的 `.cache/.data/<id>`
    会被判为“受保护路径”，表现为「直连失败 + 本地服务未启动」
  - 插件 v3.6：缓存目录解析更健壮（文件名/id 不一致也能兜底），
    加载时自检缓存可写，日志出现 `cache ready: ...` 即正常
  - 已实测 7.4.3.2 下插件直连恢复、缓存与插件均保留

- **v1.2.3**
  - 新增 `exdesktop/update.bat` / `update.ps1`：原地升级 exDesktop
    （只覆盖程序文件，保留 `tdata` 与插件），绕开便携版上失效的“检查更新”
  - 插件 v3.5：**当前时间范围内没有消息时，弹窗直接让你改时间范围**
    （最近 1 天/3 天/7 天/30 天/1 年/全部），不再只提示一句“没有消息”
  - 已实测升级 7.4.3.1 → 7.4.3.2，登录状态与插件均保留

- **v1.2.2（当前检查点）**
  - 桌面快捷方式改为**直接启动 exDesktop**，使用**原生图标与原生界面**
    （不再经 `wscript` 拉起后台，图标不再是空白脚本图标）
  - 安装脚本**默认不再安装 Python 后端**：插件「客户端直连」无需后台；
    需要「本地服务 8765」兜底时才用 `setup.ps1 -WithBackend`
  - 首次运行自动 `Unblock-File` 去掉「来自网络」标记，减少“未知发布者”安全提示

- **v1.2.1**
  - 清理文档/示例中的本机路径、账号与群组等个人标识（示例统一为占位符）
  - 测试脚本改为可移植：`test_plugin.py` 的测试群通过环境变量
    `TGHL_TEST_GROUP` 传入，仓库不写死任何真实会话
  - 重建 Git 历史，确保公开历史中不含个人标识

- **v1.2**
  - 英文 README（`README.en.md`）、GitHub Actions CI、测试脚本可移植化

- **v1.1**
  - 新增一键安装 `exdesktop/setup.bat`：自动下载 exDesktop + 建 venv + 装插件 +
    开启未知来源 + 建快捷方式（含 UTF-8/BOM、JSON 无 BOM 等编码坑处理）
  - 明确许可证：整体 **GPL-3.0**，附 `LICENSE`、`THIRD-PARTY-NOTICES.md`
  - 修复：setup 写 `extera.json` 不带 BOM（否则 Qt 解析失败）

- **v1.0**
  - 网页版：扫码登录、群列表、互动榜、消息流、导出、深链直达
  - 插件：exDesktop 直连取数 + 本地服务兜底
  - 缓存：SQLite 落盘 + 双向增量拉取（持久、秒开）
  - 交互：弹窗内切换排序 / 时间范围 / 条数 / 刷新；防重入；进度提示；超时保护
  - 按群记忆时间范围（新群默认 3 天）
  - 相册（grouped_id）合并
  - 命令行：`top`（含 `-d 365` / `-d 0` 全历史）、`qrlogin`、`chats`、`logout`、`import_tdata`

---

## 免责声明

仅供个人学习与研究使用。请遵守 Telegram 服务条款及当地法律法规；
因使用本工具产生的任何后果由使用者自行承担。
