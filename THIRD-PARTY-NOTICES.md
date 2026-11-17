# 第三方组件与许可（THIRD-PARTY NOTICES）

本项目（tg-hotlist）**自身代码**以 **GNU GPL v3.0** 发布（见仓库根目录 `LICENSE`）。
之所以选 GPL-3.0：本项目的 exDesktop 插件（`exdesktop/hotlist.plugin`）在运行时
导入 exDesktop 的插件 SDK（`base_plugin`、`ui.*`、`client_utils` 等），属于与
GPL 程序结合的衍生作品，按 GPL 要求需以 GPL-3.0 分发。

---

## 1. exDesktop（本项目的运行宿主，**未随本仓库分发**）

- 名称：exDesktop
- 仓库：https://github.com/metawka/exDesktop
- 许可：**GNU GPL v3.0**
- 说明：本项目**不包含、不分发** exDesktop 的任何二进制或源码副本。
  一键安装脚本（`exdesktop/setup.ps1`）在运行时从其**官方 GitHub Releases**
  下载 portable 包到本地，用户自行获取。
- 本项目与 exDesktop 作者无隶属关系，也未获其背书。

## 2. Telegram Desktop（exDesktop 的上游）

- 仓库：https://github.com/telegramdesktop/tdesktop
- 许可：GNU GPL v3.0（含 OpenSSL 例外，详见其仓库）
- 说明：exDesktop 基于它开发；本项目同样不分发其代码。

## 3. Python 依赖（`tg-hotlist/requirements.txt`）

| 包 | 许可 | 用途 |
|---|---|---|
| Telethon | MIT | MTProto 客户端 |
| tdata-reader | MIT | 读取 tdata 会话 |
| python-socks | Apache-2.0 | SOCKS 代理 |
| segno | BSD-3-Clause | 二维码生成 |
| pyaes / rsa / pyasn1 | MIT / Apache-2.0 / BSD | Telethon 传递依赖 |

以上均通过 pip 安装，**未随本仓库分发**。

## 4. 本项目对 exDesktop 的改动说明

本项目**没有修改** exDesktop 的 C++ 源码，而是以**插件**（`hotlist.plugin`，
一个独立的 Python 文件）形式扩展其功能。因此：
- 不需要、也不涉及对 exDesktop 二进制进行修改或再分发；
- 若你自行把 exDesktop 二进制与本项目一并分发，则触发 GPL-3.0 的
  "提供完整对应源码"义务（需附带 exDesktop 完整源码），请务必遵守。

---

## 分发本项目的合规要点（GPL-3.0）

1. 以 GPL-3.0 分发，并附带 `LICENSE` 全文；
2. 提供完整对应源码（本仓库即源码）；
3. 保留版权与许可声明，注明修改（本项目的插件为新作品，非 exDesktop 修改）；
4. 不得对本项目施加超出 GPL 的额外限制；
5. 不提供担保（见 GPL 第 15、16 条）。
