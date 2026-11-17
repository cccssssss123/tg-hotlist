# 自建 Telegram 应用（内置点赞量 / 互动量排名）可行性评估

> 评估日期：2026-11-15 · 状态：**只评估，未开始开发**
> 背景：官方 AyuGram Desktop 无插件系统；浏览器插件方案卡顿；已交付的
> `tg-hotlist` 命令行工具已跑通只读热榜。本评估回答「能否按同样逻辑做一个
> 自己用的 Telegram 应用，把排名做成内置功能」。

---

## 0. 结论先行

**可行，而且前置条件基本已经全部解决。** 但「做一个 Telegram 应用」有两种含义，
成本和推荐度差 10 倍以上：

| 理解 | 含义 | 推荐 |
|---|---|---|
| **A. 自研轻量客户端** | 自己写一个带界面的客户端（登录 + 群列表 + 消息浏览 + 内置排名），AyuGram 可以继续用 | ✅ **推荐** |
| **B. 改造 AyuGram** | Fork AyuGram Desktop 的 C++/Qt 源码，在原生聊天窗口里加排序 | ❌ 性价比极低 |

**推荐路线**：把现有 `tg-hotlist` 从「命令行工具」升级为「本地 GUI 应用」
（Python/Telethon 后端 + 本地 Web UI 或 pywebview 桌面窗口），
并补上**扫码登录**。这样：

- 不需要 my.telegram.org、不需要手机验证码（你收不到的那个）；
- 不需要编译 AyuGram 的 C++ 源码；
- 不碰浏览器插件那套 DOM 注入，不会卡；
- 排名逻辑 100% 复用现有已验证代码。

---

## 1. 已有资产盘点（可复用度极高）

| 文件 | 行数 | 作用 | 新应用里可复用 |
|---|---:|---|---|
| `tg_hotlist.py` | 852 | 登录、解析群组、拉取消息、反应/回复/转发/浏览统计、5 种排序、控制台+MD+HTML 渲染 | ✅ 直接当后端核心 |
| `import_tdata.py` | 200 | 从 AyuGram 的 `tdata` 免验证码导入会话、代理连接、服务器验证 | ✅ 备用登录通道 |
| `periodic_likes.py` | 242 | 按年 / 按月统计点赞 Top N 榜 | ✅ 直接复用 |
| `test_offline.py` | 153 | 29 项离线单元测试（全部通过） | ✅ 回归测试底座 |
| `config.json` | — | 代理 `socks5://127.0.0.1:7890`（mihomo） | ✅ 直接复用 |
| `.venv` | — | telethon 1.45 / tdata-reader / python-socks / pyaes / rsa | ✅ 依赖已装齐 |
| `tdata_import.json` + `tg_hotlist.session` | — | 已验证可用的登录会话（已导入账号） | ✅ 开箱即用 |

合计约 **1,450 行已跑通代码**。实测结果：成功列出 89 个群组/频道，
并对「某交流群」生成了真实榜单（259 条消息、Top 10、带 t.me 直达链接）。

> 也就是说：**数据层、排序层、网络层、登录层都已经完成**，缺的只是「界面层」
> 和「把它包装成一个持续运行的应用」。

---

## 2. 关键技术验证（本次评估实测 / 查证）

### 2.1 登录：扫码完全可行，彻底绕开 my.telegram.org ✅

这是你最关心的点。查了本机已安装的 Telethon 源码
（`.venv/Lib/site-packages/telethon/tl/custom/qrlogin.py`）：

- Telethon 自带 `client.qr_login()` → 生成 `tg://login?token=...` →
  把这个 URL 画成二维码 → 用手机上已登录的 Telegram 扫码 → `await qr_login.wait()`
  即完成登录。
- 你**已经能用扫码登录 web.telegram**，说明这条链路对你完全可用。
- 因此新的自建应用可以直接做「显示二维码 → 手机扫一下 → 登录成功」，
  **不需要短信验证码，也不需要 my.telegram.org**。
- 备用通道：现有 `import_tdata.py`（复用 AyuGram 的 tdata 凭证）继续保留。

### 2.2 api_id / api_hash：不需要自己申请 ✅

Telegram Desktop 官方客户端的公开常量（`tdata_reader/api.py` 实测）：

```
api_id   = 2040
api_hash = b18441a1ff607e10a989891a5462e627
```

非官方客户端可以用它初始化 MTProto 连接，不需要去 my.telegram.org 创建应用。
GramJS 同样支持二维码登录（`UserAuthParams.qrCode`）。

> ⚠️ 顺手修正：评估中发现 `tg_hotlist.py` 的兜底分支把 api_hash 末段写错了
> （`2e6ad` → 应为 `2e627`），已改正。因现走 `tdata_import.json` 通道，
> 此前的运行不受影响。

### 2.3 数据字段：排名所需数据全部可得 ✅

`messages.getHistory` 返回的消息对象里直接带有：
`reactions`（各表情及数量）、`replies`（回复数）、`forwards`（转发数）、
`views`（浏览量）、`date`、`from_id`、`message`、`media`。
真实榜单已验证这些数据能正确统计与排序。

### 2.4 网络：代理已打通 ✅

本机 本地代理端口（示例 7890） 已验证可用，`config.json` 已配好 socks5。
自建应用沿用即可。

**结论：登录、凭证、网络、数据四大前置条件全部已解决，不存在拦路虎。**

---

## 3. 技术路线对比

| 路线 | 做法 | 保留完整聊天体验 | 工作量 | 本机门槛 | 主要风险 | 结论 |
|---|---|---|---|---|---|---|
| **A. 本地自研客户端** | Python + Telethon 后端 + 本地 Web UI / pywebview 窗口 | 可做成只读浏览，聊天仍用 AyuGram | **小**（约 3–7 天） | 低，Node/Python 已有 | 需自己实现消息/媒体渲染 | ✅ **推荐** |
| **B. Tauri / Electron + GramJS** | 全 TS/JS 桌面应用，GramJS 负责 MTProto | 同上 | **中**（约 2–3 周） | 中：Node v24 已有，**Rust/cargo 未装** | 排名逻辑需用 JS 重写一遍 | ⭕ 备选 |
| **C. Fork AyuGram Desktop** | 改 C++/Qt 源码，编译自己的 exe | ✅ 完整保留 | **很大**（数周 + 长期维护） | 高：本机无 VS、无 Qt（磁盘不是瓶颈，见 3.1） | 构建环境 + 上游每次更新要合并 | ❌ 不建议 |
| **D. Fork Telegram Web K** | 改 `morethanwords/tweb`（GPL v3）源码加排名面板 | ✅ 完整 | 中（1–2 周） | 低，pnpm 可用 | 仍是浏览器 DOM；几万条消息吃力 | ⭕ 备选 |
| **E. Bot / Mini App** | 机器人或小程序 | — | — | — | **不可行** | ❌ 排除 |

### 3.1 为什么 C（Fork AyuGram）不推荐

AyuGram 自己的 [Windows x64 构建文档](https://github.com/ayugram/ayugramdesktop/blob/b25513a06ff88be0b3f4c928252b56c3da39cec7/docs/building-win-x64.md) 要求：
Visual Studio **2022**、Windows SDK **10.0.26100.0**、Python 3.10、Git、
**x64 Native Tools Command Prompt for VS 2022**、`prepare\win.bat` 拉取第三方库
（文档明确提示可能遇到 IP 限制，需要开代理），最后 `configure.bat x64`。

> 补充事实：该文档的 configure 命令用的正是公开常量
> `TDESKTOP_API_ID=2040` / `TDESKTOP_API_HASH=b18441a1ff607e10a989891a5462e627`
> —— 与本项目用的完全一致。也就是说 AyuGram 官方构建本身**不需要**
> 去 my.telegram.org 申请凭证。这一点我们已经在网页版里用上了。

实测本机状态（2026-11-15 复核）：
**没有装 Visual Studio（18 / 2022 均无）、没有 Qt**；
C 盘可用 45.6 GB、**D 盘可用 329.5 GB**（构建目录可放 `D:\TBuild`）。
所以磁盘不是瓶颈，真正的门槛是：要下载安装 VS2022 + SDK + 几十 GB
第三方依赖、编译数小时，以及之后每次上游更新都要重新合并。

更关键的是**功能层面**：Telegram Desktop 的聊天视图是按时间线渲染的
（`HistoryView`，含消息分组、动画、虚拟列表），把「按点赞量重排」塞进去
要动深层渲染代码；而且每跟一次上游更新都要重新合并冲突。
对一个「自己用」的工具，这个代价不成比例。

### 3.2 为什么 E（Bot / Mini App）直接排除

- Bot 在群里默认处于隐私模式，读不到普通历史消息；即便是管理员也拿不到
  每条消息的反应数明细。
- Telegram Mini App 没有「读取某个群聊天历史」的 API。
- 所以点赞/互动量排名在 Bot 体系里做不出来。

### 3.3 关于你之前说的「浏览器插件卡」

那卡的是**注入式插件**（在 web.telegram 的 DOM 里遍历/改写大量节点）。
路线 D 是**改源码后自己编译**的客户端，性能特征不同；
但本质仍是浏览器 DOM，历史消息上万条时依然会有压力。
路线 A/B 是原生进程直接拿结构化数据排序，开销最小。

---

## 4. 功能设计建议：排名该长什么样

**不要重排聊天时间线。** Telegram 的会话是上下文连续的（回复链、置顶、
日期分组、未读分隔），按点赞重排会破坏阅读。建议做成：

1. **每个群/频道一个「榜单」标签页**，与「消息时间线」并列。
2. 榜单支持：时间范围（最近 1/3/7/30 天、自定义）、排序字段切换
   （点赞量 / 回复数 / 转发数 / 浏览量 / 互动分）、每页条数、最低门槛。
3. 每条带 **t.me 直达链接**，点一下跳回 AyuGram 看原文和上下文。
4. 复用 `periodic_likes.py` 的「按年 / 按月」历史榜单。
5. **群 vs 频道自动适配**：群以 reactions / replies 为主，
   频道以 views / forwards 为主（实测 某交流群 Top 4 全是转发/浏览，
   而点赞集中在讨论型消息上），排序字段默认值应按类型切换。
6. **本地 SQLite 缓存**：存 `msg_id / date / author / text / media_ref /
   reactions / replies / forwards / views / updated_at`，避免每次重拉。
   反应数会随时间变化，需增量刷新（监听 `UpdateMessageReactions` 或按需重拉）。
7. **登录**：首次扫码 → 保存 StringSession；tdata 导入作为备用通道。

界面形态两个选择：
- 本地网页（浏览器打开 `127.0.0.1:端口`）—— 实现最快；
- 独立桌面窗口（pywebview / Tauri 包一层）—— 更像「一个应用」。

---

## 5. 风险与合规

| 风险 | 说明 | 缓解 |
|---|---|---|
| **账号被「观察」** | Telegram 官方文档被社区转述为：使用非官方客户端登录的账号会自动置于观察之下；刷 flooding/spam 会永久封号（[gotd/td SUPPORT.md](https://github.com/gotd/td/blob/v0.61.0/.github/SUPPORT.md) 引述 [官方 API 条款](https://core.telegram.org/api/terms)） | 坚持**只读**、不批量写、不刷量；用官方客户端 api_id 伪装 |
| **FLOOD_WAIT 限流** | `messages.getHistory` 社区实测约 30 次 / 30 秒 即触发（[telethon-floodgate 证据表](https://pypi.org/project/telethon-floodgate/)）；[MadelineProto 文档](https://docs.madelineproto.xyz/API_docs/methods/messages.getHistory.html) 明确警告该方法易触发限流甚至封号 | 客户端限速 + 本地缓存 + 指数退避 + 尊重 `FloodWaitError.seconds` |
| **本地数据隐私** | 缓存会落盘聊天文本/媒体，`tg_hotlist.session` 等同登录凭证 | 缓存目录可一键清空；会话文件不外发；可选加密 |
| **GPL 义务** | tdesktop / AyuGram / [tweb](https://github.com/morethanwords/tweb) 均为 GPL-3.0 | 纯自用不分发不触发；若分发需开源 |
| **维护成本** | Telegram API layer 会更新，MTProto 库需跟进 | 自研轻量客户端依赖少，比 fork 300 MB 的 C++ 项目好维护得多 |
| **内容合规** | 你的群列表中包含大量成人内容频道 | 本工具只做本地统计，不上传、不转发、不分享任何数据 |

---

## 6. 分阶段实施计划（若决定做）

| 阶段 | 内容 | 估算 |
|---|---|---|
| **P0 整理** | 清理遗留调试文件（`_debug_import.py`、`_imp_test.py`、`_run_import.py`、`import_log.txt`、`_tdata_tmp/`）；补 `qrlogin` 命令；把 CLI 明确拆成可 import 的 core 模块 | 0.5 天 |
| **P1 MVP** | 本地 Web UI：扫码登录 / 群列表 / 榜单 / 排序切换 / 时间范围 / 导出 HTML·MD；后台常驻服务 | 1–2 天 |
| **P2 浏览能力** | 消息时间线视图 + 按需下载图片/视频 + SQLite 缓存 + 反应数增量刷新 | 2–4 天 |
| **P3 可选** | 基础发消息/回复、多账号、打包成单文件 exe、pywebview 桌面窗口 | 2–5 天 |

> 估算口径：AI 辅助编码 + 你本机验证；不含你自己学习/调试的时间。

---

## 7. 建议

**走路线 A，分两期**：先把 P0+P1 做出来，得到一个「自己的 Telegram 热榜客户端」
（扫码登录、选群、看互动榜、点链接跳回 AyuGram）。用一段时间确认好用，
再决定要不要做 P2 的完整消息浏览，甚至 P3 的聊天能力。

不建议一上来就 Fork AyuGram：本机工具链不具备，且收益（在原生窗口里排序）
远小于成本（编译环境 + 深层 UI 改动 + 长期合并上游）。

---

## 8. 需要你拍板的两个问题

1. **这个应用是「替换 AyuGram」（要能在里面聊天），还是「AyuGram 继续聊天、
   新应用只负责浏览和看榜」？** —— 这决定要不要做 P2/P3，工作量差 3 倍以上。
2. **界面形态**：本地网页（浏览器开 `127.0.0.1`）就行，还是要一个独立的
   桌面窗口（更像「应用」）？

确认后再开工；本轮只做评估，未改动任何功能代码（仅修正了上述一个 api_hash 常量）。

> 后续：两个问题已确认（只浏览看榜 / 本地网页），P0+P1 已实现并跑通，
> 见 [README_WEB.md](README_WEB.md)。

---

## 9. 补充评估：能不能「集成进 AyuGram 里」？（2026-11-15）

**先澄清措辞**：AyuGram 开源，确实意味着可以拿源码改完自己编译出一个
带这功能的 `AyuGram.exe`。本评估前面说的「不能」，准确含义是
**「不能像浏览器插件那样装进去 / 热插拔」**——官方桌面版没有插件或扩展
加载机制（[issue #230](https://github.com/AyuGram/AyuGramDesktop/issues/230)
仍为 open；本机 `AyuGram.exe` 二进制扫描也无加载器特征）。
`shortcuts-custom.json` 只能把内置动作映射到按键，不能加自定义菜单项
或绑定外部程序。

### 三档集成度

| 档 | 做法 | 改 AyuGram 源码 | 成本 | 体感 |
|---|---|---|---|---|
| **L0 已具备** | 网页版复用 AyuGram 的 tdata 凭证（同一账号/同一份会话）；每条消息带 t.me 链接点开回 AyuGram | 0 | 0 | 两个程序，但**数据层已打通** |
| **L1 推荐** | `run_panel.bat`：用 Edge `--app=` 把网页版开成无地址栏/无标签栏的独立小窗，贴到 AyuGram 旁边；或 pywebview 打包 | 0 | 半天 | 几乎等于一个侧边面板 |
| **L2 真·同一窗口** | Fork 源码，在抽屉/设置页加入口，内嵌 WebView 指向 `127.0.0.1:8765` | 改 C++/Qt + 全量编译 | 数天~数周 + 长期维护 | 菜单里有这一项 |
| **L2′ 折中** | 换第三方 [PLEngine](https://github.com/MrCheatEugene/AyuGramDesktop-PLEngine) 构建 + 写 DLL 插件当启动器 | 换客户端 | 中高 | 菜单里有入口 |

### L2 的具体障碍

1. **工具链**：见 3.1 —— 本机没有 VS2022 / Qt，需下载安装 + 几十 GB 依赖 +
   数小时编译；`prepare\win.bat` 还要求代理环境。
2. **WebView 白名单**：tdesktop 的内置 WebView 主要服务于 Telegram Mini Apps，
   有 URL/域名校验，加载 `127.0.0.1` 预计需要改代码放开（此项为推断，
   未在本机源码上验证）。
3. **维护**：AyuGram 上游每次发版都要重新合并、重新编译。
4. **收益有限**：聊天视图按时间线渲染，本来就不适合「重排」；
   最合理的形态依然是「并列一个榜单面板」——**这正是网页版现在的样子**。
   L2 换来的实质收益只是「少一个窗口」。

### L2′ 的坑

PLEngine fork 提供 DLL 插件与预编译 exe，但
[插件文档](https://github.com/MrCheatEugene/AyuGramDesktop-PLEngine/blob/dev/README-pluginEngine.md)
明确写着「开发插件仍需本地构建该版本的 AyuGram」，插件 GUI 作者自己也标注
「new and not fully developed, expect crashes」；而且换过去等于改用第三方
构建（更新滞后、需迁移 tdata）。并不比 L2 省多少。

### 结论

**推荐 L1**：零改动、零风险、立刻可用，且不动官方客户端。
只有当「必须是 AyuGram 菜单里的一项」是硬性要求时才值得做 L2。

---

## 10. 调研：换一个「能装插件」的开源客户端（2026-11-15）

用户提出可以接受换客户端，最好是能装插件的开源项目。调研结论如下。

### 10.1 先说一个决定性的限制

**桌面原生客户端的插件，都拿不到「消息渲染层」的 hook。**

- exDesktop 的[插件开发文档](https://github.com/metawka/exdesktop/blob/main/docs/sdk/exdesktop-plugins-skill.md)
  明确写着：`ChatMessageCell` / `DialogCell` / `onDraw` / `setMessageObject`
  这类单元格与绘制 hook **在桌面端 do nothing**，必须删掉。
- [PLEngine 文档](https://github.com/MrCheatEugene/AyuGramDesktop-PLEngine/blob/dev/README-pluginEngine.md)
  的 hook 列表也没有任何一条能重排消息视图。
- 原因：tdesktop 系客户端的聊天列表是 C++/Qt 时间线渲染（分组、动画、
  虚拟列表），插件 API 只暴露了请求/更新/菜单/设置，没有视图层。

所以**换客户端能让你「装插件、在客户端里有个热门榜入口」，但做不到
「把聊天消息列表按点赞量重排」**。真正能重排消息列表的只有 Web 端
（消息是 DOM，可任意排序）—— 而那正是用户一开始嫌卡的方案。
这两个目标不可兼得，必须先讲清楚，避免换过去失望。

### 10.2 候选项目对比

| 项目 | 平台 | 插件 | 开源 | 预编译 | 成熟度 | 结论 |
|---|---|---|---|---|---|---|
| **[exDesktop](https://github.com/metawka/exDesktop)** | Win/Linux/mac | **Python**（exteraGram SDK 1.4.x，`.plugin`/`.py`/`.elyx`） | GPL-3.0 | ✅ 有 Windows exe 与 portable zip | 2026-10 新建，59★/12 fork，但**日更** | ⭐ **最对口** |
| [PLEngine](https://github.com/MrCheatEugene/AyuGramDesktop-PLEngine) | Win | C++ DLL | 否(NOASSERTION) | ✅ | 20★，2026-09 后无新版 | ❌ 需本地构建整个客户端、hook 不含视图 |
| [BummerGram](https://github.com/crimecrew/BummerGram) | Win (Qt6) | Lua | 否 | ❌ 无 release | **0★，仓库 120 KB，3 个月未更新** | ❌ 空壳，排除 |
| exteraGram / AyuGram **Android** | Android | Python（生态最成熟） | 是 | ✅ | 成熟 | ⭕ 桌面用不了；Android 上 UI hook 理论上可重排 |
| [Telegram Web K / tweb](https://github.com/morethanwords/tweb) | 浏览器 | 油猴脚本 / 改源码 | GPL-3.0 | — | 成熟 | ⭕ **DOM 可重排**，但用户已反馈插件卡 |
| Forkgram / 64Gram / Kotatogram / materialgram / rabbitGram / Telegreat / iMe / BetterGram / Unigram | 桌面 | **无插件系统** | 多为 GPL | ✅ | 成熟 | ❌ 与 AyuGram 同类，无扩展点 |

> 注：exteraGram 官方[插件文档](https://plugins.exteragram.app/docs) 是
> Python + Chaquopy + Xposed 风格 hook，运行在 Android；exDesktop 把它
> 移植到了桌面（用 Python 模拟 Java/Android 类），所以插件格式兼容。

### 10.3 为什么 exDesktop 最合适

查证来源：[README](https://github.com/metawka/exDesktop)、
[SDK 文档](https://github.com/metawka/exdesktop/blob/main/docs/sdk/desktop-sdk.md)、
[插件示例](https://github.com/metawka/exdesktop/blob/main/docs/sdk/exdesktop-plugins-skill.md)、
[最新 release](https://github.com/metawka/exDesktop/releases/tag/v7.4.3.1)。

- **Windows 有预编译**：`exDesktop-setup-x64.7.4.3.1.exe`（88 MB）
  或 `exDesktop-portable-x64.7.4.3.1.zip`（120 MB），不用自己编译。
  版本跟随 Telegram Desktop 7.4.3，2026-11-13 发布。
- **插件是 Python 单文件**，不是 C++ DLL：写起来和我们现在的技术栈
  完全一致，元数据 + 一个继承 `BasePlugin` 的类即可。
- **内置 AyuGram 特性**：Ghost mode、防撤回/编辑历史、显示用户 ID、
  Streamer mode、本地 Premium 等（README Privacy 一节，release notes
  也提到 "AyuGram features are controlled by one switch in Privacy"）。
  换过去**不会丢你现在用的功能**。
- **插件能做我们这个需求**：`client_utils.send_request` 可直接发
  `messages.getHistory` 拿 reactions/replies/forwards/views；
  `create_settings` 可做设置页/子页，`AlertDialogBuilder.set_items`
  可弹一个 Top 榜列表，`Browser.openUrl` 可跳到原消息；
  也允许访问 localhost（授权一次），能直接复用我们已写好的
  `127.0.0.1:8765` 后端，不必重写统计逻辑。
- **沙箱**：限制 `subprocess` / `ctypes` / `tdata` 访问、网站与文件夹
  按次授权、PluginGuard 检查；对第三方插件是好事。
- 内置 tg-ws-proxy（Windows），对当前代理环境可能更省事。

### 10.4 风险

- **非常新**：仓库 2026-10-24 创建，59 stars / 12 forks，不到一个月；
  README 把 Python 插件引擎标为 `[in development]`，v7.3.3.10 的
  release notes 说「约 61% exteraGram 插件完全可用、29% 部分可用」，
  「Android 界面 hook 将在后续版本加入」。
- 第三方构建，需要自行信任；数据目录与官方客户端**独立**
  （"installs beside Telegram Desktop and keeps its data separate"），
  要重新登录。基于 tdesktop 应支持扫码（**未实测**）。
- 插件**不能改 UI、不能启动外部程序**；本地网络访问需一次授权。
- 项目迭代快（几乎日更），可能存在稳定性波动。

### 10.5 建议路径

1. 先用 **portable 版**试，不要卸载 AyuGram，数据独立、随时可删。
2. 扫码登录（避开 my.telegram.org 验证码问题）。
3. 我按 [插件示例](https://github.com/metawka/exdesktop/blob/main/docs/sdk/exdesktop-plugins-skill.md)
   写一个 `hotlist_exd.plugin`：在抽屉/聊天菜单加「热门消息」入口，
   复用现有后端或直接用 `send_request` 拉数据，弹窗展示 Top 榜。
4. 用一段时间再决定是否把 AyuGram 完全换掉。

**本质提醒**：这一步换来的是「一个 App 里装插件 + 榜单入口」，
不是「聊天列表按赞重排」。后者的桌面端方案目前不存在；
最接近的仍是本项目的「并列榜单面板」。

