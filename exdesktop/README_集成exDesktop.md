# tg-hotlist × exDesktop 集成版

把「群组热门消息榜」做成**客户端内的原生功能**：打开群 → 菜单 → 热门消息榜，
直接弹列表，点条目就在客户端里定位到原消息。不用再开浏览器。

---

## 一、这是什么、不是什么

**是**：一个现成的开源 Telegram 桌面客户端 [exDesktop](https://github.com/metawka/exDesktop)
（tdesktop 分支，GPL-3.0，带 AyuGram 的隐私特性 + exteraGram 的 Python 插件引擎）
\+ 我写的插件 `hotlist.plugin`。两者结合 = 你想要的「一个 App 里看热榜」。

**不是**：从零写一个新客户端，也不是魔改官方 AyuGram。原因见最后一节。

---

## 二、目录

```
exdesktop\
├── app\                     exDesktop 程序（解压好的 portable 版）
│   ├── Telegram.exe         主程序（260 MB）
│   ├── python\extera\       插件运行时 SDK
│   └── tdata\plugins\plugins\hotlist.plugin   ← 插件已装好
├── hotlist.plugin           插件源文件（和上面那份相同，便于备份/改）
├── update.bat / update.ps1  一键更新 exDesktop（保留 tdata 与插件）
├── start_all.bat            启动后端 + exDesktop（本地服务兜底时才用）
├── test_plugin.py           插件逻辑测试（21 项断言，打真实后端）
└── README_集成exDesktop.md  本文件
```

配套的后端在 `..\tg-hotlist\`（`run_web.bat` / `web_app.py`），**仅作「本地服务 8765」兜底**；
默认的「客户端直连」完全不需要它。

---

## 三、怎么用（3 步）

### 1. 启动

直接双击桌面「**exDesktop 热榜**」快捷方式（图标就是 exDesktop 原生图标），
或双击 `app\Telegram.exe`。插件在客户端内加载，**不需要先开任何后台进程**。

> 数据来源默认「客户端直连」：插件用 exDesktop 自己的会话发 MTProto
> `messages.getHistory`，不需要 Python / 网页。
> 只有切到「本地服务 8765」兜底时，才先双击 `..\tg-hotlist\run_web.bat`
> （或用 `setup.ps1 -WithBackend` 装好后端）。

### 1.5 更新 exDesktop（升级版本）

exDesktop 自带的「检查更新」在便携版上经常失败——它直接请求
`github.com/metawka/exDesktop/releases/latest`（GitHub API），
国内网络 / 代理没被它接管 / API 限流时会报“无法更新”。

用 **`update.bat`** 更新最稳：它会下载最新官方 portable 包，
**只覆盖 `Telegram.exe` / `modules` / `python`，保留 `tdata`（登录、聊天、设置）
与插件目录**，然后重启。旧程序会备份到 `backup_before_update\<旧版本>`。

```bat
update.bat                     :: 自动查最新版并更新
update.bat -Version v7.4.3.2   :: 指定版本（API 被限流时）
update.bat -ZipPath D:\x.zip   :: 用已下载的 zip
```

### 2. 首次登录 exDesktop

exDesktop 是独立客户端，**数据与 AyuGram 分开**，需要单独登录一次：

- 界面上会显示二维码
- 手机 Telegram → **设置 → 设备 → 连接桌面设备** → 扫码
- 这是官方 QR 登录，**不需要 my.telegram.org，也不需要短信验证码**

### 3. 用热榜

- 打开任意群组/频道
- 点右上角菜单（或左侧抽屉）→ **🏆 热门消息榜**
- 弹窗显示 Top N，点任意一条 → 在客户端内跳到那条消息

**弹窗里可以直接操作**（不用去设置页）：

| 弹窗顶部项 | 作用 |
|---|---|
| 🔄 刷新数据 | 跳过缓存，重新从 Telegram 扫描一遍 |
| 🔀 排序：xxx | 切换排序方式（互动分/点赞/回复/转发/浏览） |
| 📅 时间：xxx | 切换时间范围（1天~1年/历史全部）**仅对当前群生效** |
| 🏆 条数：Top xx | 切换榜单条数（Top 10/15/20/30/50/100/200/500） |
| 底部「刷新」「关闭」按钮 | 同上 |

切换排序/时间会**复用同一次抓取的数据在内存里重排**，几乎瞬间完成；
只有「刷新」会重新联网扫描。

> 若这个群在当前时间范围（如最近 3 天 / 本月）里没有消息，弹窗**不会只报一句错**，
> 而是直接列出时间范围选项——选「最近 1 年 / 历史全部」再扫即可。

> **重要（已经帮你设好）**：exDesktop 默认会拦截「来源不明的插件」，
> 自写插件会被标记 `blocked: UNKNOWN_SOURCE` 而不加载。
> 我已把 `app\tdata\extera.json` 里的 `plugins_unknown_sources` 设为 `true`，
> 日志确认插件已 `loaded`。
> 如果以后重装 exDesktop，需要再开一次：**设置 → 插件 → 允许未知来源的插件**
> （或在 extera.json 里加 `"plugins_unknown_sources": true`）。

设置里（插件设置页）可以改默认值：
| 项 | 说明 |
|---|---|
| 数据来源 | **客户端直连（默认）** / 本地服务 8765（兜底） |
| 时间范围（默认） | 新群首次打开用的默认值（**每个群之后各自记忆**），默认「最近 3 天」 |
| 排序方式（默认） | 互动分 / 点赞量 / 回复数 / 转发数 / 浏览量 |
| 榜单条数 | Top 10/15/20/30/50/100/200/500，或设置里填 1–500 任意数 |
| 扫描上限（条） | 默认 3000；想排更多历史消息就调大（如 20000） |
| 本地服务地址 | 默认 `http://127.0.0.1:8765`，改端口时同步改这里 |

### 数据来源：直连 vs 本地服务

| 模式 | 怎么取数 | 需要后端进程吗 |
|---|---|---|
| **客户端直连**（默认） | 插件用 exDesktop **自己的登录会话**，直接发 MTProto `messages.getHistory` | **不需要** |
| 本地服务 8765 | 走 tg-hotlist 后端（独立 Telethon 会话） | 需要（run_web.bat） |

**本地缓存 + 增量拉取**（v3 起）：

- 每个群首次扫描后，消息落盘到插件自己的 SQLite 缓存；**再打开直接读缓存，秒开**。
- 点「刷新」只拉上次之后的新消息（`getHistory` 增量），**几乎瞬间**。
- 切到更长时间范围时，**只补拉更早的部分**，不会从头重扫。
- 重启客户端缓存仍在。
- **相册合并**：一条消息里的多张图片/视频（共享 `grouped_id`）会合并成**一条**上榜，
  不会出现同一相册的每个媒体各占一名；文本取相册说明，转发/浏览取成员最大值。
- 扫描时会有「正在扫描… 已获取 N 条」的进度提示；单页 20s 超时、单次扫描
  180s 上限，超时先显示已抓到的部分（下次继续补），不会无限卡住。
- 扫描期间重复点击会被拦截并提示「正在扫描中」，不会叠加重启多个扫描。

> 注意：直连并不是"读客户端已下载的本地缓存"——插件沙箱禁止访问 `tdata`，
> SDK 也没有枚举客户端内存消息的接口。两种模式本质都是"再向 Telegram 请求
> 历史消息"，区别是用客户端自己的连接 vs 另开后端的连接。上面的"本地缓存"
> 是**我们自己另存的**（存在插件目录），不是客户端缓存。

---

## 四、已经验证了什么 / 没验证什么

### ✅ 已验证
- exDesktop **能正常启动**：进程起来、窗口标题 `exDesktop`、自动生成 `tdata`、
  日志显示 `Plugins: runtime ... installed`（插件运行时初始化成功）
- **插件已成功加载**：日志 `Plugins: plugin hotlist_exd loaded`
  （踩到一个坑：默认 `blocked: UNKNOWN_SOURCE`，开启
  `plugins_unknown_sources` 后解决）
- 插件 **语法无误**（262 行，编译通过），元数据符合 SDK 规范
- 插件 **逻辑正确**：`test_plugin.py` 用 stub 模拟 SDK、**打真实后端**，21 项断言全过：
  - 菜单注册（聊天菜单 + 抽屉各一个）
  - 设置项构造、默认值、越界值收敛、backend 地址自动补全
  - 真实拉取榜单 → 弹窗标题/条数/条目格式正确
    （实测：「某交流群 · 互动分 Top 5，扫描 424 条」）
  - 点条目 → 生成 `tg://privatepost?channel=...&post=...` 深链
  - 后端不可达 → 提示「请先双击 run_web.bat」
  - 未打开群组 → 提示「请先打开一个群组或频道」
- SDK 关键 API 逐一核对过源码：`add_menu_item` / `create_settings` /
  `on_plugin_load` / `get_current_dialog_id` / `AlertDialogBuilder.set_items(listener)` /
  `BulletinHelper` / `Browser.openUrl`

### ⚠ 没法验证（需要你实际点一下）
- 弹窗在真机 UI 上的**视觉效果**（我能验证数据正确，看不到渲染）
- 「点条目跳转」在 UI 里的实际手感
- 插件加载后是否需要在「设置 → 插件」里**手动启用一次**
  （日志已显示 `loaded`，通常即为启用状态；若菜单里没看到条目，去插件页确认一下开关）
- 我无法从这边把 GUI 程序长期保活（这个执行环境会把工具启动的 GUI
  进程连带回收），所以 exDesktop 必须**你自己双击启动**

---

## 五、和「自己写一个新客户端」的差别

你问「能不能做一个新的桌面端接入这两个」。实际有两条路：

| 做法 | 成本 | 结果 |
|---|---|---|
| **A. 现成客户端 + 插件**（本方案） | 已完成 | 一个 App 内看热榜，插件是 Python，随时改 |
| B. 从零写/魔改 tdesktop 源码 | 需 VS2022 + Qt + 几十 GB 依赖，编译数小时，之后每次上游更新要重新合并 | 同样是「一个 App 内看热榜」 |

A 和 B 的**最终效果几乎一样**，但成本差一个数量级。所以选 A。

另外有一条**硬限制**必须知道：
桌面客户端（tdesktop 系）的插件 API **拿不到消息列表的渲染层**
（`ChatMessageCell` / `onDraw` 之类在桌面端不起作用），
所以**做不到「把聊天列表按点赞量重排」**。
能做的是「另开一个榜单视图」——也就是本方案的样子。
真能重排的只有 Web 端（DOM），而那正是你嫌卡的方案。

---

## 六、卸载 / 回退

- 不想用 exDesktop：整个 `exdesktop` 文件夹删掉即可，不影响 AyuGram。
- 只想关掉热榜：删 `app\tdata\plugins\plugins\hotlist.plugin`
  或在设置→插件里禁用。
- tg-hotlist 后端仍可独立使用（`..\tg-hotlist\run_web.bat` + 浏览器）。

---

## 七、风险提示

- exDesktop 是**第三方构建**（2026-10 才创建，更新很勤），请自行评估信任度。
  它基于 tdesktop 源码，数据目录独立，与官方客户端互不影响。
- 插件运行在沙箱里：不能启动外部程序、不能碰 `tdata`、访问非 localhost
  的网络需要授权；本插件只连 `127.0.0.1:8765`，不需要任何额外授权。
- 全程只读：不发消息、不点赞、不修改任何聊天数据。
