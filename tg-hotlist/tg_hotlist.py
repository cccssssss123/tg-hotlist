#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tg-hotlist —— Telegram 群组热门消息排行工具（只读）

在你的电脑本地运行，用你自己的 Telegram 账号登录（官方 API），
拉取指定群组最近的消息，按点赞量/互动量排序，输出 Top 榜单
（控制台 + Markdown + HTML），并附上每条消息的直达链接。

用法:
  python tg_hotlist.py login              # 首次登录（需要先填 config.json）
  python tg_hotlist.py chats              # 列出你加入的群组/频道
  python tg_hotlist.py top -g <群组>      # 生成热门消息榜
  python tg_hotlist.py top -g <群组> --by reactions   # 只按点赞量排
  python tg_hotlist.py logout             # 退出登录并删除本地会话

免验证码登录:
  python tg_hotlist.py qrlogin     # 推荐：扫码登录（不需要 my.telegram.org）
  python import_tdata.py "C:/path/to/AyuGram/tdata"
  （从已登录的 AyuGram/Telegram Desktop 的 tdata 直接导入会话，
    不需要 my.telegram.org 的 api_id/api_hash，详见 README）

本地网页版（浏览 + 看榜）:
  run_web.bat   然后浏览器打开 http://127.0.0.1:8765
"""

import argparse
import asyncio
import getpass
import html as html_mod
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    from telethon import TelegramClient, errors
    from telethon.tl.types import Channel, Chat, User
except ImportError:
    print("错误: 缺少 telethon 库。")
    print("请先在项目目录执行: pip install -r requirements.txt")
    sys.exit(1)

SCRIPT_DIR = Path(__file__).resolve().parent
CONFIG_PATH = SCRIPT_DIR / "config.json"
SESSION_PATH = SCRIPT_DIR / "tg_hotlist.session"
OUTPUT_DIR = SCRIPT_DIR / "output"

CONFIG_TEMPLATE = {
    "api_id": 0,
    "api_hash": "",
    "phone": "",
    "proxy": None,
    # 可选：指定用哪个客户端打开 tg:// 深链。留空 = 用系统注册的
    # tg:// 处理器（当前是 AyuGram.exe）。换了客户端想强制指定时填绝对路径。
    "client_exe": "",
    # 打开方式: browser = 交给浏览器处理 tg:// 链接(默认, 最可靠; 首次一次
    #           确认框, 勾选"始终允许"后即一点直达);
    #           backend = 本地服务静默唤起客户端(无确认框, 但需要服务运行
    #           在普通桌面会话中; 失败会自动回退到 browser 方式)
    "open_mode": "browser",
    "defaults": {
        "group": "",
        "days": 3,
        "top": 20,
        "limit": 5000,
        "by": "score",
        "weights": {
            "reaction": 1,
            "reply": 1,
            "forward": 2,
            "view": 0.05,
            "view_cap": 20,
        },
    },
}

SORT_CHOICES = ("score", "reactions", "replies", "views", "forwards")
SORT_LABEL = {
    "score": "互动分",
    "reactions": "点赞量",
    "replies": "回复数",
    "views": "浏览量",
    "forwards": "转发数",
}

# Telegram Desktop 官方客户端公开常量（不需要去 my.telegram.org 申请）
OFFICIAL_API_ID = 2040
OFFICIAL_API_HASH = "b18441a1ff607e10a989891a5462e627"


# ---------------------------------------------------------------- 控制台输出

for _stream in (sys.stdout, sys.stderr):
    if _stream and hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def disp_width(s: str) -> int:
    """终端显示宽度（中日韩算 2 列）。"""
    return sum(2 if ord(ch) > 0x2E7F else 1 for ch in s)


def pad(s: str, width: int) -> str:
    return s + " " * max(0, width - disp_width(s))


def print_table(rows):
    if not rows:
        return
    ncol = len(rows[0])
    widths = [max(disp_width(str(r[i])) for r in rows) for i in range(ncol)]
    for i, r in enumerate(rows):
        print("  ".join(pad(str(c), w) for c, w in zip(r, widths)).rstrip())
        if i == 0:
            print("  ".join("-" * w for w in widths))


def fmt_num(n) -> str:
    n = n or 0
    if n >= 10000:
        return f"{n / 10000:.1f}w"
    return str(n)


# ---------------------------------------------------------------- 配置

def load_config(need_api=True) -> dict:
    if not SESSION_PATH.exists():
        if not CONFIG_PATH.exists():
            CONFIG_PATH.write_text(
                json.dumps(CONFIG_TEMPLATE, ensure_ascii=False, indent=4),
                encoding="utf-8",
            )
        print("错误: 尚未登录。两种方式任选其一:")
        print("  A. 免验证码(推荐): python import_tdata.py AyuGram的tdata目录")
        print("     例如: python import_tdata.py C:/Users/你/Downloads/AyuGram/tdata")
        print("  B. 验证码方式: 在 config.json 填 api_id/api_hash 后运行 login")
        print("     申请地址: https://my.telegram.org → API development tools")
        sys.exit(1)
    session_is_string = _session_is_string()
    if not CONFIG_PATH.exists():
        CONFIG_PATH.write_text(
            json.dumps(CONFIG_TEMPLATE, ensure_ascii=False, indent=4),
            encoding="utf-8",
        )
    try:
        cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"错误: config.json 解析失败: {e}")
        sys.exit(1)
    if need_api and not session_is_string and (not cfg.get("api_id") or not cfg.get("api_hash")):
        print("错误: 请先在 config.json 中填入 api_id 和 api_hash")
        print("      申请地址: https://my.telegram.org → API development tools")
        print("      （或免验证码导入: python import_tdata.py AyuGram的tdata目录）")
        sys.exit(1)
    return cfg


def _session_is_string() -> bool:
    """判断 tg_hotlist.session 是 StringSession 文本（import_tdata 导入）
    还是 SQLite 文件会话（login 生成）。"""
    try:
        with SESSION_PATH.open("rb") as f:
            head = f.read(16)
        if head.startswith(b"SQLite format 3"):
            return False
        return True  # 其他情况视为文本会话
    except Exception:
        return False


def make_client(cfg: dict) -> TelegramClient:
    # tdata 导入模式
    if _session_is_string():
        from tdata_reader import read_tdata  # noqa: F401 仅为说明依赖
        from telethon.sessions import StringSession

        # 读取 tdata 导入时记录的连接参数（api_id 等）
        meta_path = SCRIPT_DIR / "tdata_import.json"
        if meta_path.exists():
            try:
                kw = json.loads(meta_path.read_text(encoding="utf-8"))
                return TelegramClient(
                    StringSession(SESSION_PATH.read_text(encoding="utf-8").strip()),
                    int(kw["api_id"]),
                    str(kw["api_hash"]),
                    proxy=_parse_proxy(cfg),
                )
            except Exception:
                pass
        # 没有记录就用 Telegram Desktop 官方 api
        return TelegramClient(
            StringSession(SESSION_PATH.read_text(encoding="utf-8").strip()),
            OFFICIAL_API_ID,
            OFFICIAL_API_HASH,
            proxy=_parse_proxy(cfg),
        )

    proxy = _parse_proxy(cfg)
    return TelegramClient(
        str(SESSION_PATH), int(cfg["api_id"]), str(cfg["api_hash"]), proxy=proxy
    )


def _parse_proxy(cfg: dict):
    proxy = None
    p = cfg.get("proxy")
    if isinstance(p, dict) and p.get("host"):
        proxy = {
            "proxy_type": str(p.get("scheme", "socks5")).lower(),
            "addr": str(p["host"]),
            "port": int(p.get("port", 0)),
        }
        for k in ("username", "password"):
            if p.get(k):
                proxy[k] = str(p[k])
        print(f"（使用代理 {proxy['proxy_type']}://{proxy['addr']}:{proxy['port']}）")
    return proxy


async def require_authorized(client: TelegramClient):
    if not await client.is_user_authorized():
        print("错误: 尚未登录。请先运行: python tg_hotlist.py login")
        await client.disconnect()
        sys.exit(1)


# ---------------------------------------------------------------- login / logout

async def cmd_login(args):
    cfg = load_config()
    phone = (cfg.get("phone") or "").strip()
    if phone and not phone.startswith("+"):
        phone = "+" + phone
    client = make_client(cfg)
    await client.connect()
    if await client.is_user_authorized():
        me = await client.get_me()
        print(f"已经是登录状态: {display_name(me)} (id {me.id})，无需重复登录。")
        await client.disconnect()
        return
    if not phone:
        phone = input("手机号（国际格式，如 +8613800138000）: ").strip()
        if not phone.startswith("+"):
            phone = "+" + phone
    try:
        await client.send_code_request(phone)
    except errors.PhoneNumberInvalidError:
        print("错误: 手机号格式不正确，需要国际格式（如 +8613800138000）")
        await client.disconnect()
        sys.exit(1)
    code = input("Telegram 发给你的登录验证码（注意是私聊里的验证码，不是短信）: ").strip()
    try:
        await client.sign_in(phone=phone, code=code)
    except errors.SessionPasswordNeededError:
        pw = getpass.getpass("两步验证密码（输入时不显示）: ")
        await client.sign_in(password=pw)
    except errors.PhoneCodeInvalidError:
        print("错误: 验证码不正确")
        await client.disconnect()
        sys.exit(1)
    me = await client.get_me()
    print()
    print(f"登录成功: {display_name(me)} (id {me.id})")
    print(f"登录状态已保存到 {SESSION_PATH.name}，以后运行不需要再验证。")
    print("（请妥善保管该文件，等于你的登录凭证；不想用了可运行 logout 删除）")
    await client.disconnect()


async def cmd_logout(args):
    if not SESSION_PATH.exists():
        print("没有已保存的登录会话，无需退出。")
        return
    cfg = load_config()
    client = make_client(cfg)
    try:
        await client.connect()
        if await client.is_user_authorized():
            await client.log_out()  # 会同时删除会话文件
            print("已退出登录，并删除了本地会话文件。")
            return
        await client.disconnect()
    except Exception:
        pass
    SESSION_PATH.unlink(missing_ok=True)
    print("已删除本地会话文件。")


# ---------------------------------------------------------------- chats

async def cmd_chats(args):
    cfg = load_config()
    client = make_client(cfg)
    await client.connect()
    await require_authorized(client)

    rows = [("#", "ID（-g 参数用这个）", "类型", "成员", "名称", "用户名")]
    async for d in client.iter_dialogs():
        e = d.entity
        if isinstance(e, Channel):
            kind = "频道" if e.broadcast else "群组"
        elif isinstance(e, Chat):
            kind = "群组"
        else:
            continue
        members = getattr(e, "participants_count", None)
        rows.append([
            str(len(rows)),
            str(d.id),
            kind,
            fmt_num(members) if members else "-",
            d.title or "",
            "@" + e.username if getattr(e, "username", None) else "",
        ])
    await client.disconnect()
    print()
    print_table(rows)
    print()
    print("提示: top 命令的 -g 参数可以用上表中的 ID、@用户名 或名称（支持部分匹配）。")


# ---------------------------------------------------------------- 群组解析

async def resolve_group(client: TelegramClient, raw: str):
    s = raw.strip()
    # t.me 链接
    m = re.match(r"^(?:https?://)?t\.me/(?:c/)?([^/]+)", s, re.IGNORECASE)
    if m:
        s = m.group(1)
        if s.isdigit():  # t.me/c/1234567 私有频道/群
            s = "-100" + s
    # 纯数字 ID
    try:
        return await client.get_entity(int(s))
    except ValueError:
        pass
    # @用户名 / 用户名
    if not s.startswith("@") and not re.match(r"^\+?\d+$", s):
        try:
            return await client.get_entity(s)
        except Exception:
            pass
    elif s.startswith("@"):
        try:
            return await client.get_entity(s)
        except Exception:
            pass
    # 按名称模糊匹配
    matches = []
    async for d in client.iter_dialogs():
        if not isinstance(d.entity, (Channel, Chat)):
            continue
        title = (d.title or "").casefold()
        if title == s.casefold():
            return d.entity
        if s.casefold() in title:
            matches.append(d)
    if len(matches) == 1:
        return matches[0].entity
    if matches:
        print(f"找到 {len(matches)} 个名称包含“{s}”的群组，请用 ID 精确指定:")
        for d in matches:
            print(f"  {d.id}  {d.title}")
        await client.disconnect()
        sys.exit(1)
    print(f"错误: 找不到群组 “{raw}”")
    print("提示: 先运行 python tg_hotlist.py chats 查看你加入的群列表")
    await client.disconnect()
    sys.exit(1)


# ---------------------------------------------------------------- 消息统计

def reaction_summary(msg):
    """返回 (总点赞数, '👍×12 🔥×3' 明细)。"""
    r = getattr(msg, "reactions", None)
    results = getattr(r, "results", None) if r else None
    if not results:
        return 0, ""
    total = 0
    parts = []
    for rc in results:
        cnt = rc.count or 0
        total += cnt
        emot = getattr(getattr(rc, "reaction", None), "emoticon", None)
        parts.append((emot or "★", cnt))
    parts.sort(key=lambda x: -x[1])
    detail = " ".join(f"{e}×{c}" for e, c in parts[:5])
    return total, detail


def media_label(m) -> str:
    if getattr(m, "photo", None):
        return "[图片]"
    if getattr(m, "sticker", None):
        return "[贴纸]"
    if getattr(m, "voice", None):
        return "[语音]"
    if getattr(m, "audio", None):
        return "[音乐]"
    if getattr(m, "video_note", None):
        return "[视频留言]"
    if getattr(m, "video", None):
        return "[视频]"
    if getattr(m, "poll", None):
        return "[投票]"
    if getattr(m, "contact", None):
        return "[联系人]"
    if getattr(m, "geo", None):
        return "[位置]"
    if getattr(m, "document", None):
        return "[文件]"
    return "[消息]"


def display_name(u) -> str:
    if isinstance(u, Channel):
        return u.title or f"频道{u.id}"
    if isinstance(u, Chat):
        return u.title or f"群{u.id}"
    if isinstance(u, User):
        name = " ".join(x for x in (u.first_name, u.last_name) if x).strip()
        return name or (f"@{u.username}" if u.username else f"用户{u.id}")
    return str(u)


def msg_link(entity, msg):
    username = getattr(entity, "username", None)
    if username:
        return f"https://t.me/{username}/{msg.id}"
    if isinstance(entity, Channel):
        return f"https://t.me/c/{entity.id}/{msg.id}"
    return None


def tg_deep_link(entity, msg):
    """生成 tg:// 内部深链：点击直接在桌面客户端里定位到这条消息，
    不经过 t.me 网页跳转。

    格式与 tdesktop 源码 Core::TryConvertUrlToLocal() 把 t.me 链接
    转换成的本地链接完全一致：
      公开:  tg://resolve?domain=<username>&post=<msg_id>
      私有:  tg://privatepost?channel=<bare_channel_id>&post=<msg_id>
    基本群（非超级群）没有可用的消息深链，返回 None。
    """
    username = getattr(entity, "username", None)
    if username:
        return f"tg://resolve?domain={username}&post={msg.id}"
    if isinstance(entity, Channel):
        return f"tg://privatepost?channel={entity.id}&post={msg.id}"
    return None


# Telegram 上线于 2013 年，用它作为「历史全部」的下界，早于任何真实消息。
ALL_TIME_START = datetime(2013, 1, 1, tzinfo=timezone.utc)


def time_window_start(days: float):
    """返回 (起始时间, 是否全历史)。days <= 0 表示不限时间（历史全部）。"""
    if days <= 0:
        return ALL_TIME_START, True
    return datetime.now(timezone.utc) - timedelta(days=days), False


async def collect_messages(client, entity, days: float, limit: int, quiet: bool = False):
    start, all_time = time_window_start(days)
    msgs = []
    seen_grouped = {}   # grouped_id -> msgs 中的下标（相册合并，保留文字最全的那条）
    scanned = 0
    reached_start = False
    # wait_time: 每页请求之间主动歇 0.5 秒，降低触发服务器限流的概率；
    # 即使触发，telethon 对 ≤60s 的 FloodWait 也会自动等待重试
    async for msg in client.iter_messages(entity, limit=limit, wait_time=0.5):
        scanned += 1
        if not all_time and (msg.date is None or msg.date < start):
            reached_start = True
            break
        if msg.date is None:
            continue
        if getattr(msg, "action", None) is not None:
            continue  # 服务消息（加群、置顶等）
        gid = getattr(msg, "grouped_id", None)
        if gid:
            idx = seen_grouped.get(gid)
            if idx is not None:
                prev = msgs[idx]
                if (len(getattr(msg, "message", "") or "")
                        > len(getattr(prev, "message", "") or "")):
                    msgs[idx] = msg
                continue  # 相册合并算一条
            seen_grouped[gid] = len(msgs)
        msgs.append(msg)
        if not quiet and len(msgs) % 200 == 0:
            print(f"\r  已获取 {len(msgs)} 条消息…", end="", flush=True)
    # 用「原始迭代数」判断，而不是过滤后的 msgs 数：服务消息、相册合并
    # 会让 msgs 少于 limit，此时其实已经触到扫描上限，必须如实标记。
    # 若是因为遇到时间下界而 break，则不算截断。
    truncated = (not reached_start) and scanned >= limit
    if not quiet:
        print("\r" + " " * 40 + "\r", end="")
    return msgs, start, truncated


async def build_stats(client, entity, msgs, weights):
    by_id = {m.id: m for m in msgs}
    # 窗口内逐条统计“谁回复了谁”
    reply_counts = {}
    for m in msgs:
        rt = getattr(m, "reply_to", None)
        target = getattr(rt, "reply_to_msg_id", None) if rt else None
        if target and target in by_id:
            reply_counts[target] = reply_counts.get(target, 0) + 1

    entries = []
    for m in msgs:
        react_total, react_detail = reaction_summary(m)
        own_replies = reply_counts.get(m.id, 0)
        server_replies = getattr(getattr(m, "replies", None), "replies", 0) or 0
        replies = max(own_replies, server_replies)
        forwards = getattr(m, "forwards", 0) or 0
        views = getattr(m, "views", 0) or 0
        score = (
            weights.get("reaction", 1) * react_total
            + weights.get("reply", 1) * replies
            + weights.get("forward", 2) * forwards
            + weights.get("view", 0.05) * min(views, weights.get("view_cap", 20))
        )
        entries.append({
            "msg": m,
            "reactions": react_total,
            "react_detail": react_detail,
            "replies": replies,
            "forwards": forwards,
            "views": views,
            "score": score,
        })

    # 给作者取名（只处理靠前的，避免多余请求）
    name_cache = {}

    async def author_name(m):
        fid = getattr(m, "from_id", None)
        if fid is None:
            return display_name(entity)  # 频道自己发的
        uid = getattr(fid, "user_id", None)
        if uid is None:
            return "未知"
        if uid not in name_cache:
            try:
                name_cache[uid] = display_name(await client.get_entity(uid))
            except Exception:
                name_cache[uid] = f"用户{uid}"
        return name_cache[uid]

    return entries, author_name


def sort_entries(entries, by: str):
    keymap = {
        "score": lambda e: e["score"],
        "reactions": lambda e: e["reactions"],
        "replies": lambda e: e["replies"],
        "views": lambda e: e["views"],
        "forwards": lambda e: e["forwards"],
    }
    return sorted(entries, key=keymap[by], reverse=True)


def preview_text(m, maxlen=60) -> str:
    text = (m.message or "").replace("\n", " ").strip()
    if not text:
        text = media_label(m)
    if len(text) > maxlen:
        text = text[:maxlen] + "…"
    return text


# ---------------------------------------------------------------- top 主命令

async def cmd_top(args):
    cfg = load_config()
    defaults = cfg.get("defaults") or {}
    group = args.group or defaults.get("group") or ""
    if not group:
        print("错误: 请用 -g 指定群组（或写进 config.json 的 defaults.group）")
        sys.exit(1)
    days = args.days if args.days is not None else defaults.get("days", 3)
    top_n = args.top if args.top is not None else defaults.get("top", 20)
    limit = args.limit or defaults.get("limit", 5000)
    by = args.by or defaults.get("by", "score")
    if by not in SORT_CHOICES:
        print(f"错误: --by 只能是 {'/'.join(SORT_CHOICES)}")
        sys.exit(1)
    weights = (defaults.get("weights") or {})

    client = make_client(cfg)
    await client.connect()
    await require_authorized(client)

    print(f"正在解析群组: {group}")
    entity = await resolve_group(client, group)
    title = getattr(entity, "title", None) or display_name(entity)
    print(f"目标: {title}")
    print(f"范围: 最近 {days:g} 天，最多 {limit} 条，排序方式: {SORT_LABEL[by]}")

    msgs, start_utc, truncated = await collect_messages(client, entity, days, limit)
    if not msgs:
        print("该时间范围内没有消息。")
        await client.disconnect()
        return
    if truncated:
        print(f"注意: 消息数达到上限 {limit}，更早的消息没有统计（可用 --limit 调大）")
    print(f"共获取 {len(msgs)} 条消息，正在统计…")

    entries, author_name = await build_stats(client, entity, msgs, weights)
    ranked = sort_entries(entries, by)
    top = ranked[: top_n]

    # 补齐作者名
    for e in top:
        e["author"] = await author_name(e["msg"])

    await client.disconnect()

    all_time = days <= 0
    now_local = datetime.now().astimezone()
    start_local = start_utc.astimezone()
    meta = {
        "group": title,
        "by": by,
        "by_label": SORT_LABEL[by],
        "days": days,
        "count": len(msgs),
        "start": "全部历史" if all_time
                 else start_local.strftime("%Y-%m-%d %H:%M"),
        "end": now_local.strftime("%Y-%m-%d %H:%M"),
        "all_time": all_time,
        "truncated": truncated,
        "top_n": top_n,
    }

    print()
    print(f"===== {title} · {SORT_LABEL[by]} Top {len(top)} =====")
    print(f"（{meta['start']} ~ {meta['end']}，共 {len(msgs)} 条消息）")
    print()
    rows = [("#", SORT_LABEL[by], "点赞", "回复", "转发", "浏览", "日期", "作者", "内容")]
    for i, e in enumerate(top, 1):
        m = e["msg"]
        rows.append([
            str(i),
            fmt_num(round(e["score"])) if by == "score" else fmt_num(e[by]),
            fmt_num(e["reactions"]),
            fmt_num(e["replies"]),
            fmt_num(e["forwards"]),
            fmt_num(e["views"]),
            m.date.astimezone().strftime("%m-%d %H:%M"),
            e["author"],
            preview_text(m),
        ])
    print_table(rows)

    # 输出文件
    OUTPUT_DIR.mkdir(exist_ok=True)
    safe = re.sub(r'[\\/:*?"<>|]', "_", title)[:30] or "group"
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    base = OUTPUT_DIR / f"hotlist_{safe}_{stamp}"
    md_path = base.with_suffix(".md")
    html_path = base.with_suffix(".html")
    write_markdown(md_path, meta, top, entity)
    write_html(html_path, meta, top, entity)
    print()
    print(f"已生成: {md_path}")
    print(f"已生成: {html_path}")

    if args.json:
        dump_json(Path(args.json), meta, top, entity)
        print(f"已生成: {args.json}")


# ---------------------------------------------------------------- 输出文件

def md_escape(s: str) -> str:
    return s.replace("|", "\\|").replace("\n", " ")


def write_markdown(path: Path, meta: dict, top: list, entity):
    lines = []
    lines.append(f"# {meta['group']} · {meta['by_label']} Top {len(top)}")
    lines.append("")
    span = ("全部历史" if meta.get("all_time")
            else f"最近 {meta['days']:g} 天")
    lines.append(
        f"> 时间范围 **{meta['start']} ~ {meta['end']}**（{span}，"
        f"共扫描 {meta['count']} 条消息）· 排序方式: {meta['by_label']}"
    )
    if meta["truncated"]:
        lines.append(">")
        lines.append("> ⚠ 消息数达到扫描上限，更早的消息未统计")
    lines.append("")
    lines.append(
        "| # | 互动 | 👍 | 回复 | 转发 | 浏览 | 时间 | 作者 | 内容 |"
    )
    lines.append("|---|-----|----|-----|-----|-----|------|------|------|")
    for i, e in enumerate(top, 1):
        m = e["msg"]
        link = msg_link(entity, m)
        text = md_escape(preview_text(m, 80))
        cell = f"[{text}]({link})" if link else text
        score = fmt_num(round(e["score"]))
        lines.append(
            f"| {i} | {score} | {fmt_num(e['reactions'])} | {fmt_num(e['replies'])} "
            f"| {fmt_num(e['forwards'])} | {fmt_num(e['views'])} "
            f"| {m.date.astimezone().strftime('%m-%d %H:%M')} "
            f"| {md_escape(e['author'])} | {cell} |"
        )
    lines.append("")
    lines.append("## 明细")
    lines.append("")
    for i, e in enumerate(top, 1):
        m = e["msg"]
        lines.append(f"### #{i} {e['author']} · {m.date.astimezone().strftime('%Y-%m-%d %H:%M')}")
        lines.append("")
        stats = (
            f"👍 {e['reactions']}"
            + (f"（{e['react_detail']}）" if e["react_detail"] else "")
            + f" · 回复 {e['replies']} · 转发 {e['forwards']}"
            + (f" · 浏览 {fmt_num(e['views'])}" if e["views"] else "")
            + f" · 互动分 {round(e['score'])}"
        )
        lines.append(stats)
        lines.append("")
        body = (m.message or media_label(m)).strip()
        if len(body) > 500:
            body = body[:500] + "…"
        lines.append(f"> {body}" if "\n" not in body else "")
        if "\n" in body:
            for ln in body.splitlines():
                lines.append(f"> {ln}")
        link = msg_link(entity, m)
        if link:
            lines.append("")
            lines.append(f"[在 Telegram 中打开]({link})")
            deep = tg_deep_link(entity, m)
            if deep:
                lines.append(f" · [直接在客户端打开]({deep})")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def write_html(path: Path, meta: dict, top: list, entity):
    span = ("全部历史" if meta.get("all_time")
            else f"最近 {meta['days']:g} 天")
    cards = []
    for i, e in enumerate(top, 1):
        m = e["msg"]
        link = msg_link(entity, m)
        body = html_mod.escape((m.message or media_label(m)).strip()[:500])
        body = body.replace("\n", "<br>")
        badge = (
            f'<span class="b r">👍 {fmt_num(e["reactions"])}</span>'
            f'<span class="b">💬 {fmt_num(e["replies"])}</span>'
            f'<span class="b">↗ {fmt_num(e["forwards"])}</span>'
        )
        if e["views"]:
            badge += f'<span class="b">👁 {fmt_num(e["views"])}</span>'
        badge += f'<span class="b s">⭐ {round(e["score"])}</span>'
        detail = (
            f'<div class="detail">{html_mod.escape(e["react_detail"])}</div>'
            if e["react_detail"]
            else ""
        )
        open_btn = (
            f'<a class="open" href="{html_mod.escape(link)}" target="_blank">网页 ↗</a>'
            if link
            else ""
        )
        deep = tg_deep_link(entity, m)
        if deep:
            open_btn += (
                f'<a class="open" href="{html_mod.escape(deep)}">客户端直达 ↗</a>'
            )
        cards.append(
            f"""<div class="card">
  <div class="rank">{i}</div>
  <div class="main">
    <div class="stats">{badge}</div>
    {detail}
    <div class="text">{body}</div>
    <div class="foot">{html_mod.escape(e['author'])}
      · {m.date.astimezone().strftime('%m-%d %H:%M')} · 消息 #{m.id} {open_btn}</div>
  </div>
</div>"""
        )
    warn = (
        '<p class="warn">⚠ 消息数达到扫描上限，更早的消息未统计</p>'
        if meta["truncated"]
        else ""
    )
    doc = f"""<!doctype html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html_mod.escape(meta['group'])} · {meta['by_label']} Top {len(top)}</title>
<style>
  :root {{ color-scheme: dark; }}
  body {{ background:#14161a; color:#e8eaed; font:15px/1.6 -apple-system,"Segoe UI",
         "Microsoft YaHei",sans-serif; margin:0; padding:24px; }}
  h1 {{ font-size:20px; margin:0 0 4px; }}
  .meta {{ color:#9aa0a6; font-size:13px; margin-bottom:20px; }}
  .warn {{ color:#f6c744; font-size:13px; }}
  .card {{ display:flex; gap:14px; background:#1e2126; border:1px solid #2b2f36;
          border-radius:12px; padding:14px 16px; margin-bottom:12px; }}
  .rank {{ flex:none; width:34px; font-size:22px; font-weight:700; color:#5ea8ff; text-align:center; }}
  .main {{ min-width:0; flex:1; }}
  .stats {{ margin-bottom:6px; }}
  .b {{ display:inline-block; background:#2a2e35; border-radius:999px; padding:1px 10px;
       font-size:12.5px; margin-right:6px; }}
  .b.r {{ background:#33272a; color:#ff8f8f; }}
  .b.s {{ background:#2b3320; color:#c8e68a; }}
  .detail {{ color:#9aa0a6; font-size:12.5px; margin-bottom:6px; }}
  .text {{ white-space:pre-wrap; word-break:break-word; }}
  .foot {{ color:#9aa0a6; font-size:12.5px; margin-top:8px; }}
  .open {{ color:#5ea8ff; text-decoration:none; margin-left:8px; }}
</style>
</head>
<body>
<h1>{html_mod.escape(meta['group'])} · {meta['by_label']} Top {len(top)}</h1>
<div class="meta">{html_mod.escape(meta['start'])} ~ {meta['end']}（{span}，共扫描 {meta['count']} 条消息）</div>
{warn}
{''.join(cards)}
<p class="meta">由 tg-hotlist 生成 · {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
</body>
</html>"""
    path.write_text(doc, encoding="utf-8")


def dump_json(path: Path, meta: dict, top: list, entity):
    data = {
        "meta": meta,
        "items": [
            {
                "rank": i,
                "message_id": e["msg"].id,
                "date": e["msg"].date.isoformat(),
                "author": e["author"],
                "text": (e["msg"].message or "")[:1000],
                "reactions": e["reactions"],
                "reaction_detail": e["react_detail"],
                "replies": e["replies"],
                "forwards": e["forwards"],
                "views": e["views"],
                "score": e["score"],
                "link": msg_link(entity, e["msg"]),
            }
            for i, e in enumerate(top, 1)
        ],
    }
    Path(path).write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# ---------------------------------------------------------------- 扫码登录

def save_qr_session(client, user_id: int):
    """把扫码登录得到的会话写成 tg_hotlist.py 能识别的 StringSession + 元数据。"""
    from telethon.sessions import StringSession

    SESSION_PATH.write_text(StringSession.save(client.session), encoding="utf-8")
    (SCRIPT_DIR / "tdata_import.json").write_text(
        json.dumps(
            {
                "api_id": OFFICIAL_API_ID,
                "api_hash": OFFICIAL_API_HASH,
                "user_id": user_id,
                "source": "qr",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


async def cmd_qrlogin(args):
    """扫码登录：不需要 my.telegram.org，也不需要手机验证码。"""
    try:
        import segno
    except ImportError:
        print("错误: 缺少 segno 库（.venv 里应已装好）")
        sys.exit(1)
    from telethon.sessions import StringSession

    cfg = {}
    if CONFIG_PATH.exists():
        try:
            cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    proxy = _parse_proxy(cfg)

    client = TelegramClient(
        StringSession(), OFFICIAL_API_ID, OFFICIAL_API_HASH, proxy=proxy
    )
    await client.connect()
    if await client.is_user_authorized():
        me = await client.get_me()
        print(f"已经是登录状态: {display_name(me)} (id {me.id})，无需重复登录。")
        await client.disconnect()
        return

    print("正在向 Telegram 申请登录令牌…")
    qr = await client.qr_login()
    url = qr.url
    svg = segno.make(url, error="m").svg_inline(
        scale=8, dark="#000000", light="#ffffff"
    )
    # 补 viewBox，避免某些查看器/缩放时按原始像素绘制被裁切
    if "viewBox" not in svg:
        _m = __import__("re").search(r'width="(\d+)"\s+height="(\d+)"', svg)
        if _m:
            svg = svg.replace(
                _m.group(0),
                f'{_m.group(0)} viewBox="0 0 {_m.group(1)} {_m.group(2)}"',
                1,
            )
    svg_path = SCRIPT_DIR / "qr_login.svg"
    svg_path.write_text(svg, encoding="utf-8")

    print()
    print("请用浏览器打开二维码文件（或直接用手机扫屏幕上的链接）：")
    print(f"  {svg_path}")
    print()
    print("手机 Telegram → 设置 → 设备 → 连接桌面设备 → 扫描二维码")
    print(f"登录链接: {url}")
    print()
    print("等待扫码（二维码过期会自动提示重来）…")
    try:
        user = await qr.wait()
    except Exception as e:
        print(f"\n扫码未完成: {type(e).__name__}: {e}")
        print("请重新运行本命令生成新二维码。")
        await client.disconnect()
        sys.exit(1)

    save_qr_session(client, user.id)
    await client.disconnect()
    print()
    print(f"登录成功: {display_name(user)} (id {user.id})")
    print(f"会话已保存到 {SESSION_PATH.name}，之后所有命令都不需要再登录。")


# ---------------------------------------------------------------- 入口

def parse_args():
    ap = argparse.ArgumentParser(
        prog="tg_hotlist.py",
        description="Telegram 群组热门消息排行工具（只读，不改你的聊天数据）",
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("login", help="首次登录（手机号验证码，需要 api_id/api_hash）")
    p.set_defaults(func=cmd_login)

    p = sub.add_parser("qrlogin", help="扫码登录（推荐，不需要验证码/不需要申请凭证）")
    p.set_defaults(func=cmd_qrlogin)

    p = sub.add_parser("logout", help="退出登录并删除本地会话")
    p.set_defaults(func=cmd_logout)

    p = sub.add_parser("chats", help="列出你加入的群组/频道")
    p.set_defaults(func=cmd_chats)

    p = sub.add_parser("top", help="生成热门消息榜")
    p.add_argument("-g", "--group", help="群组 ID / @用户名 / 名称（支持部分匹配）")
    p.add_argument("-d", "--days", type=float, help="统计最近几天（默认 3）")
    p.add_argument("-n", "--top", type=int, help="榜单条数（默认 20）")
    p.add_argument("--limit", type=int, help="最多扫描多少条消息（默认 5000）")
    p.add_argument(
        "--by",
        choices=SORT_CHOICES,
        help="排序方式: score 互动分(默认) / reactions 点赞量 / replies 回复数 / views 浏览量 / forwards 转发数",
    )
    p.add_argument("--json", help="额外导出 JSON 文件路径")
    p.set_defaults(func=cmd_top)
    return ap.parse_args()


def main():
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    args = parse_args()
    try:
        asyncio.run(args.func(args))
    except KeyboardInterrupt:
        print("\n已取消。")
    except errors.FloodWaitError as e:
        print(f"\n触发 Telegram 服务器限流，请等 {e.seconds} 秒后再试。")
        sys.exit(2)
    except SystemExit:
        raise
    except Exception as e:
        if os.environ.get("TGHL_DEBUG"):
            raise
        print(f"\n错误: {type(e).__name__}: {e}")
        print("（可用 TGHL_DEBUG=1 运行查看详细堆栈）")
        sys.exit(1)


if __name__ == "__main__":
    main()
