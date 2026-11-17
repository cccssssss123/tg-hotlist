#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tg-hotlist 本地网页版后端（只读浏览 + 互动榜）。

启动后浏览器打开 http://127.0.0.1:8765

架构：
  - 一个后台线程持有 asyncio 事件循环和一条常驻的 Telethon 连接；
  - HTTP 服务用标准库 ThreadingHTTPServer（不装任何 Web 框架）；
  - 请求线程通过 run_coroutine_threadsafe 把协程投递到事件循环执行；
  - 消息抓取结果按 (群, 天数, 上限) 缓存 5 分钟，且两次抓取之间强制
    间隔 2 秒，避免触发 Telegram 的 FLOOD_WAIT。

全程只读：不发消息、不点赞、不改任何聊天数据。
"""

import argparse
import asyncio
import json
import os
import re
import subprocess
import sys
import threading
import time
import traceback
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

# pythonw.exe（无控制台窗口）运行时 sys.stdout / sys.stderr 为 None，
# 直接 print 会抛异常。这里重定向到日志文件，保证后台静默运行也能排错。
if sys.stdout is None or sys.stderr is None:
    try:
        _logf = open(SCRIPT_DIR / "backend.log", "a",
                     encoding="utf-8", buffering=1)
    except Exception:
        _logf = None
    if _logf is not None:
        if sys.stdout is None:
            sys.stdout = _logf
        if sys.stderr is None:
            sys.stderr = _logf

import tg_hotlist as h
from telethon import TelegramClient, errors
from telethon.sessions import StringSession
from telethon.tl.types import Channel, Chat

try:
    import segno
except ImportError:
    segno = None

WEB_DIR = SCRIPT_DIR / "web"
OUTPUT_DIR = SCRIPT_DIR / "output"
CACHE_TTL = 300.0          # 消息缓存 5 分钟
CHATS_TTL = 300.0          # 群列表缓存 5 分钟
MIN_FETCH_GAP = 2.0        # 两次真实抓取之间的最小间隔（秒）
DEFAULT_PORT = 8765


def _svg_with_viewbox(svg: str) -> str:
    """segno 输出的 SVG 只有固定 width/height、没有 viewBox，
    被 CSS 按百分比缩放时不会等比缩小，会按原始像素绘制而被容器裁切
    （表现为二维码底部/右侧被切掉）。补上 viewBox 即可正常缩放。"""
    if "viewBox" in svg:
        return svg
    m = re.search(r'width="(\d+)"\s+height="(\d+)"', svg)
    if not m:
        return svg
    w, h = m.group(1), m.group(2)
    return svg.replace(
        m.group(0), f'{m.group(0)} viewBox="0 0 {w} {h}"', 1
    )


# ---------------------------------------------------------------- 核心服务

class Service:
    def __init__(self):
        self.loop = asyncio.new_event_loop()
        self._loop_thread = threading.Thread(target=self._run_loop, daemon=True)
        self._loop_thread.start()

        self.cfg = self._read_cfg()
        self.client = None
        self.user = None             # {"id", "name"}
        self.source = None           # "tdata" | "qr" | "sqlite"
        self.last_error = ""

        self._lock = threading.RLock()
        self._msgs_cache = {}        # key -> (ts, entity, msgs, start, truncated)
        self._chats_cache = None
        self._chats_ts = 0.0
        self._last_fetch = 0.0
        self._last_raw = None        # (meta, top, entity) 供导出复用
        self._author_cache = {}      # user_id -> 显示名，跨排序切换复用

        # 扫码登录状态
        self.qr_client = None
        self.qr_obj = None
        self.qr_url = ""
        self.qr_svg = ""
        self._qr_state = "idle"      # idle | waiting | success | expired | error
        self.qr_gen = 0              # 代次号，用于丢弃已取消的等待任务
        self.qr_error = ""

        self._init_client()

    # ---- 事件循环 ----
    def _run_loop(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def run(self, coro, timeout=120):
        fut = asyncio.run_coroutine_threadsafe(coro, self.loop)
        return fut.result(timeout=timeout)

    def _read_cfg(self):
        if not h.CONFIG_PATH.exists():
            h.CONFIG_PATH.write_text(
                json.dumps(h.CONFIG_TEMPLATE, ensure_ascii=False, indent=4),
                encoding="utf-8",
            )
        try:
            return json.loads(h.CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception:
            return json.loads(json.dumps(h.CONFIG_TEMPLATE))

    # ---- 已有会话：启动即连 ----
    def _init_client(self):
        if not h.SESSION_PATH.exists():
            return
        try:
            client = h.make_client(self.cfg)
            client, me = self.run(self._connect(client), timeout=90)
            if me:
                self.client = client
                self.user = {"id": me.id, "name": h.display_name(me)}
                self.source = self._detect_source()
            else:
                self.last_error = "本地会话已失效，请重新扫码或导入 tdata"
        except Exception as e:
            self.last_error = f"连接失败: {type(e).__name__}: {e}"

    def _detect_source(self):
        meta = SCRIPT_DIR / "tdata_import.json"
        if meta.exists():
            try:
                return json.loads(meta.read_text(encoding="utf-8")).get("source") or "tdata"
            except Exception:
                return "tdata"
        return "sqlite"

    async def _connect(self, client):
        await client.connect()
        if await client.is_user_authorized():
            return client, await client.get_me()
        await client.disconnect()
        return client, None

    def state(self):
        proxy = self.cfg.get("proxy")
        proxy_s = ""
        if isinstance(proxy, dict) and proxy.get("host"):
            proxy_s = f"{proxy.get('scheme','socks5')}://{proxy['host']}:{proxy.get('port','')}"
        return {
            "logged_in": self.client is not None and self.user is not None,
            "user": self.user,
            "source": self.source,
            "proxy": proxy_s,
            "qr_supported": segno is not None,
            "open_mode": (self.cfg.get("open_mode") or "browser").strip(),
            "client_exe": (self.cfg.get("client_exe") or "").strip(),
            "last_error": self.last_error,
        }

    # ---- 扫码登录 ----
    def qr_start(self):
        if segno is None:
            raise RuntimeError("缺少 segno 库，无法生成二维码")
        return self.run(self._qr_start(), timeout=90)

    async def _qr_start(self):
        if self.qr_client is not None:
            try:
                await self.qr_client.disconnect()
            except Exception:
                pass
            self.qr_client = None

        proxy = h._parse_proxy(self.cfg)
        self.qr_client = TelegramClient(
            StringSession(), h.OFFICIAL_API_ID, h.OFFICIAL_API_HASH, proxy=proxy
        )
        await self.qr_client.connect()
        self.qr_obj = await self.qr_client.qr_login()
        self.qr_url = self.qr_obj.url
        self.qr_svg = _svg_with_viewbox(segno.make(self.qr_url, error="m").svg_inline(
            scale=7, dark="#000000", light="#ffffff", border=3
        ))
        self._qr_state = "waiting"
        self.qr_error = ""
        self.qr_gen += 1
        gen = self.qr_gen
        self.loop.create_task(self._qr_wait(gen))
        return {"svg": self.qr_svg, "url": self.qr_url}

    async def _qr_wait(self, gen):
        try:
            user = await self.qr_obj.wait()
        except Exception as e:
            if gen != self.qr_gen:
                return  # 已被取消/重新生成，丢弃这次结果
            self._qr_state = "expired"
            self.qr_error = f"{type(e).__name__}: {e}"
            return
        if gen != self.qr_gen:
            return
        try:
            h.save_qr_session(self.qr_client, user.id)
            # 这个 client 已连接且已授权，直接作为主连接复用
            self.client = self.qr_client
            self.qr_client = None
            self.user = {"id": user.id, "name": h.display_name(user)}
            self.source = "qr"
            self.last_error = ""
            self._qr_state = "success"
            self._msgs_cache.clear()
            self._author_cache.clear()
            self._chats_cache = None
        except Exception as e:
            self._qr_state = "error"
            self.qr_error = str(e)

    def qr_status(self):
        return {
            "status": self._qr_state,
            "error": self.qr_error,
            "user": self.user,
        }

    def qr_cancel(self):
        self._qr_state = "idle"
        self.qr_error = ""
        self.qr_gen += 1         # 让旧的 _qr_wait 任务结果失效
        return self.run(self._qr_cancel(), timeout=30)

    async def _qr_cancel(self):
        if self.qr_client is not None:
            await self.qr_client.disconnect()
            self.qr_client = None
        return True

    # ---- 备用：从 AyuGram 的 tdata 导入 ----
    def tdata_import(self, path, passcode=""):
        path = (path or "").strip().strip('"')
        if not path:
            raise ValueError("请填写 tdata 目录路径")
        cmd = [sys.executable, str(SCRIPT_DIR / "import_tdata.py"), path]
        if passcode:
            cmd += ["--passcode", passcode]
        r = subprocess.run(
            cmd, capture_output=True, timeout=180, cwd=str(SCRIPT_DIR)
        )
        text = (r.stdout + r.stderr).decode("utf-8", "replace").strip()
        if r.returncode != 0:
            raise RuntimeError(text or "导入失败")
        self.cfg = self._read_cfg()
        self.run(self._rebuild(), timeout=90)
        if not self.user:
            raise RuntimeError("导入完成但会话不可用，请检查日志")
        return text

    async def _rebuild(self):
        if self.client is not None:
            try:
                await self.client.disconnect()
            except Exception:
                pass
        client = h.make_client(self.cfg)
        await client.connect()
        me = await client.get_me() if await client.is_user_authorized() else None
        self.client = client
        self.user = {"id": me.id, "name": h.display_name(me)} if me else None
        self.source = "tdata"
        self.last_error = ""
        self._msgs_cache.clear()
        self._author_cache.clear()
        self._chats_cache = None

    # ---- 退出（只删本地文件，绝不调用 auth.logOut）----
    def logout(self):
        self.run(self._disconnect(), timeout=30)
        h.SESSION_PATH.unlink(missing_ok=True)
        (SCRIPT_DIR / "tdata_import.json").unlink(missing_ok=True)
        self.client = None
        self.user = None
        self.source = None
        self._qr_state = "idle"
        self.qr_gen += 1
        self._msgs_cache.clear()
        self._author_cache.clear()
        self._chats_cache = None
        self._last_raw = None
        return True

    async def _disconnect(self):
        if self.client is not None:
            await self.client.disconnect()
        if self.qr_client is not None:
            await self.qr_client.disconnect()
            self.qr_client = None

    # ---- 群列表 ----
    def chats(self):
        self._require_login()
        # 缓存命中时不拿 _lock：全历史抓取可能持有锁数分钟，
        # 不能让它把群列表/状态也一起卡住。
        if self._chats_cache and time.time() - self._chats_ts < CHATS_TTL:
            return self._chats_cache
        with self._lock:
            if self._chats_cache and time.time() - self._chats_ts < CHATS_TTL:
                return self._chats_cache
            rows = self.run(self._fetch_chats(), timeout=180)
            self._chats_cache = rows
            self._chats_ts = time.time()
            return rows

    async def _fetch_chats(self):
        rows = []
        async for d in self.client.iter_dialogs():
            e = d.entity
            if isinstance(e, Channel):
                kind = "频道" if e.broadcast else "群组"
            elif isinstance(e, Chat):
                kind = "群组"
            else:
                continue
            rows.append({
                "id": str(d.id),
                "title": d.title or "",
                "type": kind,
                "members": getattr(e, "participants_count", 0) or 0,
                "username": ("@" + e.username) if getattr(e, "username", None) else "",
            })
        return rows

    # ---- 解析群组（不会 sys.exit / 不会断开连接）----
    async def _resolve(self, raw):
        s = raw.strip()
        m = re.match(r"^(?:https?://)?t\.me/(?:c/)?([^/]+)", s, re.IGNORECASE)
        if m:
            s = m.group(1)
            if s.isdigit():
                s = "-100" + s
        try:
            return await self.client.get_entity(int(s))
        except (ValueError, TypeError):
            pass
        except Exception:
            pass
        if s.startswith("@") or not re.match(r"^\+?\d+$", s):
            try:
                return await self.client.get_entity(s)
            except Exception:
                pass
        matches = []
        async for d in self.client.iter_dialogs():
            if not isinstance(d.entity, (Channel, Chat)):
                continue
            title = (d.title or "").casefold()
            if title == s.casefold():
                return d.entity
            if s.casefold() in title:
                matches.append(d.entity)
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise ValueError(f"找到 {len(matches)} 个名称包含「{raw}」的群，请用 ID 精确指定")
        raise ValueError(f"找不到群组「{raw}」，请从左侧列表选择")

    # ---- 数据：一次抓取，同时产出「互动榜」和「消息流」----
    def data(self, group, days, by, top_n, limit, force=False):
        self._require_login()
        if by not in h.SORT_CHOICES:
            raise ValueError(f"排序方式不支持: {by}")
        group = (group or "").strip()
        if not group:
            raise ValueError("请先选择一个群组")
        raw_days = str(days).strip().lower() if days is not None else "3"
        if raw_days in ("0", "all", "max"):
            days = 0.0                       # 历史全部
        else:
            try:
                days = float(raw_days)
            except ValueError:
                days = 3.0
        all_time = days <= 0
        top_n = max(1, min(200, int(top_n or 20)))
        limit = max(100, min(200000, int(limit or 5000)))

        key = (group, days, limit)
        with self._lock:
            now = time.time()
            hit = self._msgs_cache.get(key)
            need_fetch = force or not hit or (now - hit[0] > CACHE_TTL)
            if need_fetch:
                gap = now - self._last_fetch
                if gap < MIN_FETCH_GAP:
                    time.sleep(MIN_FETCH_GAP - gap)
                # 全历史/一年可能拉几万条，给更长的超时
                entity, msgs, start, truncated = self.run(
                    self._fetch_msgs(group, days, limit),
                    timeout=1800 if (all_time or days >= 365) else 300,
                )
                self._last_fetch = time.time()
                self._msgs_cache[key] = (
                    self._last_fetch, entity, msgs, start, truncated
                )
                _, entity, msgs, start, truncated = self._msgs_cache[key]
            else:
                _, entity, msgs, start, truncated = hit

        weights = (self.cfg.get("defaults") or {}).get("weights") or {}
        entries, author_name = self.run(
            h.build_stats(self.client, entity, msgs, weights), timeout=60
        )
        ranked = h.sort_entries(entries, by)
        top = ranked[:top_n]

        async def fill_authors():
            # 用服务级缓存，切换排序/条数时不再重复向服务器查用户名
            for e in top:
                m = e["msg"]
                fid = getattr(m, "from_id", None)
                if fid is None:      # 频道自己发的
                    e["author"] = getattr(entity, "title", None) or h.display_name(entity)
                    continue
                uid = getattr(fid, "user_id", None)
                if uid is None:
                    e["author"] = "未知"
                    continue
                if uid not in self._author_cache:
                    try:
                        self._author_cache[uid] = h.display_name(
                            await self.client.get_entity(uid)
                        )
                    except Exception:
                        self._author_cache[uid] = f"用户{uid}"
                e["author"] = self._author_cache[uid]
            return top

        self.run(fill_authors(), timeout=120)

        title = getattr(entity, "title", None) or h.display_name(entity)
        oldest = ""
        if all_time and msgs:
            dates = [m.date for m in msgs if m.date is not None]
            if dates:
                oldest = min(dates).astimezone().strftime("%Y-%m-%d")
        meta = {
            "group": title,
            "by": by,
            "by_label": h.SORT_LABEL[by],
            "days": days,
            "count": len(msgs),
            "start": "全部历史" if all_time
                     else start.astimezone().strftime("%Y-%m-%d %H:%M"),
            "end": datetime.now().astimezone().strftime("%Y-%m-%d %H:%M"),
            "all_time": all_time,
            "oldest": oldest,
            "truncated": truncated,
            "top_n": top_n,
            "limit": limit,
            "fetched_at": datetime.fromtimestamp(
                hit[0] if (hit and not need_fetch) else self._last_fetch
            ).astimezone().strftime("%H:%M:%S"),
        }

        rank_items = []
        for i, e in enumerate(top, 1):
            m = e["msg"]
            rank_items.append({
                "rank": i,
                "id": m.id,
                "score": round(e["score"], 1),
                "reactions": e["reactions"],
                "reaction_detail": e["react_detail"],
                "replies": e["replies"],
                "forwards": e["forwards"],
                "views": e["views"],
                "date": m.date.astimezone().strftime("%m-%d %H:%M"),
                "author": e["author"],
                "text": (m.message or "")[:4000],
                "preview": h.preview_text(m, 90),
                "media": h.media_label(m),
                "link": h.msg_link(entity, m),
                "deep": h.tg_deep_link(entity, m),
            })

        # 消息流：按时间倒序，最多 300 条
        feed_items = []
        for m in sorted(msgs, key=lambda x: x.date, reverse=True)[:300]:
            total, detail = h.reaction_summary(m)
            feed_items.append({
                "id": m.id,
                "date": m.date.astimezone().strftime("%m-%d %H:%M"),
                "text": (m.message or "")[:2000],
                "preview": h.preview_text(m, 100),
                "media": h.media_label(m),
                "reactions": total,
                "reaction_detail": detail,
                "replies": getattr(getattr(m, "replies", None), "replies", 0) or 0,
                "forwards": getattr(m, "forwards", 0) or 0,
                "views": getattr(m, "views", 0) or 0,
                "link": h.msg_link(entity, m),
                "deep": h.tg_deep_link(entity, m),
            })

        self._last_raw = (meta, top, entity)
        return {"meta": meta, "rank": rank_items, "feed": feed_items}

    async def _fetch_msgs(self, group, days, limit):
        entity = await self._resolve(group)
        msgs, start, truncated = await h.collect_messages(
            self.client, entity, days, limit, quiet=True
        )
        return entity, msgs, start, truncated

    # ---- 在桌面客户端里直接打开某条消息 ----
    # 只允许 privatepost / resolve 两种消息深链，避免 tg:// 被用于
    # 改代理、加群、登录码等其他动作。
    _DEEP_ALLOWED = {
        "privatepost": {"channel", "post"},
        "resolve": {"domain", "post"},
    }

    def _client_exe(self):
        """返回用于打开 tg:// 的桌面客户端路径。
        优先用 config.json 的 client_exe；否则从注册表读 tg:// 的处理器。
        这样换了客户端（AyuGram → exDesktop）不用改配置。"""
        exe = (self.cfg.get("client_exe") or "").strip()
        if exe and Path(exe).is_file():
            return str(Path(exe))
        if sys.platform == "win32":
            try:
                import winreg
                for root, sub in (
                    (winreg.HKEY_CURRENT_USER,
                     r"Software\Classes\tg\shell\open\command"),
                    (winreg.HKEY_CLASSES_ROOT, r"tg\shell\open\command"),
                ):
                    try:
                        with winreg.OpenKey(root, sub) as k:
                            cmd = winreg.QueryValue(k, "")
                        m = re.match(r'^"([^"]+)"', cmd or "")
                        if m and Path(m.group(1)).is_file():
                            return m.group(1)
                    except OSError:
                        continue
            except Exception:
                pass
        return None

    def open_in_client(self, url, dry=False):
        """返回 dict。成功时 ok=True；唤起失败时 ok=False/fallback=True，
        前端会自动改用浏览器打开 tg:// 链接。"""
        url = (url or "").strip()
        p = urlparse(url)
        if p.scheme != "tg" or p.netloc not in self._DEEP_ALLOWED:
            raise ValueError("不是合法的 tg:// 消息深链")
        params = {k: v[0] for k, v in parse_qs(p.query).items()}
        allowed = self._DEEP_ALLOWED[p.netloc]
        if not params or set(params) - allowed:
            raise ValueError("深链参数不合法")
        if not re.fullmatch(r"\d+", params.get("post", "")):
            raise ValueError("消息 ID 不合法")
        if p.netloc == "privatepost":
            if not re.fullmatch(r"-?\d+", params.get("channel", "")):
                raise ValueError("频道 ID 不合法")
        elif not re.fullmatch(r"[A-Za-z0-9_.]+", params.get("domain", "")):
            raise ValueError("用户名不合法")
        # 规范化，丢掉多余参数
        clean = f"tg://{p.netloc}?" + "&".join(
            f"{k}={params[k]}" for k in sorted(params)
        )
        if dry:
            return {"ok": True, "dry": True, "url": clean}

        launched = None
        exe = self._client_exe()
        if exe:
            # 与注册表命令一致：AyuGram.exe -- "tg://..."
            # 指定 cwd 到客户端目录，保证它写对日志、找得到 tdata。
            opts = dict(
                cwd=str(Path(exe).parent),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=True,
            )

            def spawn(flags):
                return subprocess.Popen([exe, "--", clean],
                                        creationflags=flags, **opts)

            if sys.platform == "win32":
                # 尽量脱离父进程可能所在的 Job Object / 控制台：
                # 从后台服务启动的 GUI 进程若不脱离，可能卡在初始化阶段。
                try:
                    launched = spawn(subprocess.DETACHED_PROCESS
                                     | subprocess.CREATE_NEW_PROCESS_GROUP
                                     | 0x01000000)  # CREATE_BREAKAWAY_FROM_JOB
                except OSError:
                    launched = spawn(subprocess.DETACHED_PROCESS
                                     | subprocess.CREATE_NEW_PROCESS_GROUP)
            else:
                launched = subprocess.Popen([exe, "--", clean], **opts)
        elif sys.platform == "win32":
            os.startfile(clean)
        else:
            launched = subprocess.Popen(["xdg-open", clean])

        # 正常情况第二个实例把 URL 转发给主实例后会立刻退出。
        # 若超时仍存活，说明它卡在初始化（后台服务环境常见）：
        # 清理残留进程，并让前端回退到浏览器方式打开 tg://。
        if launched is not None:
            try:
                launched.wait(timeout=2.5)
            except subprocess.TimeoutExpired:
                try:
                    launched.kill()
                except Exception:
                    pass
                return {
                    "ok": False, "fallback": True, "url": clean,
                    "error": "客户端未响应，已自动改用浏览器方式",
                }
        return {"ok": True, "url": clean}

    # ---- 导出 ----
    def export(self, fmt):
        if not self._last_raw:
            raise ValueError("请先加载一个群组")
        meta, top, entity = self._last_raw
        OUTPUT_DIR.mkdir(exist_ok=True)
        safe = re.sub(r'[\\/:*?"<>|]', "_", meta["group"])[:30] or "group"
        stamp = datetime.now().strftime("%Y%m%d_%H%M")
        base = OUTPUT_DIR / f"hotlist_{safe}_{stamp}"
        if fmt == "md":
            path = base.with_suffix(".md")
            h.write_markdown(path, meta, top, entity)
            ctype = "text/markdown; charset=utf-8"
        elif fmt == "html":
            path = base.with_suffix(".html")
            h.write_html(path, meta, top, entity)
            ctype = "text/html; charset=utf-8"
        else:
            raise ValueError("格式只能是 md 或 html")
        return path.name, path.read_bytes(), ctype

    def _require_login(self):
        if self.client is None or self.user is None:
            raise RuntimeError("尚未登录，请先扫码或导入 tdata")


# ---------------------------------------------------------------- HTTP

class Handler(BaseHTTPRequestHandler):
    server_version = "tg-hotlist/1.0"

    def log_message(self, fmt, *args):
        # 只打印 API 调用，静态资源不刷屏
        try:
            msg = fmt % args
            if "/api/" in msg:
                print("[http] " + msg, flush=True)
        except Exception:
            pass

    def _send(self, body: bytes, ctype: str, status=200, extra=None):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _json(self, obj, status=200):
        self._send(
            json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8"),
            "application/json; charset=utf-8",
            status,
        )

    def _ok(self, **kw):
        self._json({"ok": True, **kw})

    def _err(self, e, status=200):
        if isinstance(e, errors.FloodWaitError):
            self._json({
                "ok": False,
                "code": "flood_wait",
                "wait": e.seconds,
                "error": f"Telegram 触发限流，请等待 {e.seconds} 秒后再试",
            }, status)
            return
        self._json({
            "ok": False,
            "code": type(e).__name__,
            "error": str(e),
        }, status)

    def _static(self, name, ctype):
        p = WEB_DIR / name
        if not p.is_file():
            self._send(b"not found", "text/plain; charset=utf-8", 404)
            return
        self._send(p.read_bytes(), ctype)

    def _body(self):
        n = int(self.headers.get("Content-Length", 0) or 0)
        if not n:
            return {}
        try:
            return json.loads(self.rfile.read(n).decode("utf-8"))
        except Exception:
            return {}

    def do_GET(self):
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        path = u.path

        if path in ("/", "/index.html"):
            return self._static("index.html", "text/html; charset=utf-8")
        if path == "/app.js":
            return self._static("app.js", "application/javascript; charset=utf-8")
        if path == "/style.css":
            return self._static("style.css", "text/css; charset=utf-8")
        if path == "/favicon.ico":
            return self._send(b"", "image/x-icon", 204)

        svc: Service = self.server.svc
        try:
            if path == "/api/state":
                return self._ok(**svc.state())
            if path == "/api/login/qr/status":
                return self._ok(**svc.qr_status())
            if path == "/api/chats":
                return self._ok(chats=svc.chats())
            if path == "/api/open":
                return self._json(svc.open_in_client(
                    q.get("url", ""), dry=q.get("dry", "0") in ("1", "true")
                ))
            if path == "/api/data":
                return self._ok(**svc.data(
                    group=q.get("group", ""),
                    days=q.get("days", "3"),
                    by=q.get("by", "score"),
                    top_n=q.get("top", "20"),
                    limit=q.get("limit", "5000"),
                    force=q.get("force", "0") in ("1", "true"),
                ))
            if path == "/api/export":
                name, data, ctype = svc.export(q.get("format", "html"))
                return self._send(
                    data, ctype,
                    extra={"Content-Disposition": f'attachment; filename="hotlist.{q.get("format","html")}"'},
                )
            return self._json({"ok": False, "error": "未知接口 " + path}, 404)
        except Exception as e:
            if "TGHL_DEBUG" in os.environ:
                traceback.print_exc()
            return self._err(e)

    def do_POST(self):
        u = urlparse(self.path)
        path = u.path
        body = self._body()
        svc: Service = self.server.svc
        try:
            if path == "/api/login/qr/start":
                return self._ok(**svc.qr_start())
            if path == "/api/login/qr/cancel":
                return self._ok(cancelled=svc.qr_cancel())
            if path == "/api/login/tdata":
                return self._ok(log=svc.tdata_import(
                    body.get("path", ""), body.get("passcode", "")
                ), **svc.state())
            if path == "/api/logout":
                return self._ok(logged_out=svc.logout())
            return self._json({"ok": False, "error": "未知接口 " + path}, 404)
        except Exception as e:
            if "TGHL_DEBUG" in os.environ:
                traceback.print_exc()
            return self._err(e)


class Server(ThreadingHTTPServer):
    daemon_threads = True
    # Windows 下 SO_REUSEADDR 允许多个进程绑定同一端口，会导致请求随机落到
    # 旧进程。禁用它，端口被占用时直接失败并自动换端口。
    allow_reuse_address = False


def main():
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    ap = argparse.ArgumentParser(prog="web_app.py")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--no-fallback", action="store_true",
                    help="端口被占用时直接退出，不自动换端口（供开机自启用，"
                         "避免重复启动出第二个实例）")
    args = ap.parse_args()

    # 先绑定端口，再连 Telegram：避免端口占用时还去做昂贵的网络连接
    httpd = None
    last_err = None
    last_port = args.port if args.no_fallback else args.port + 7
    for port in range(args.port, last_port + 1):
        try:
            httpd = Server((args.host, port), Handler)
            args.port = port
            break
        except OSError as e:
            last_err = e
    if httpd is None:
        if args.no_fallback:
            # 自启模式下端口已占用 = 已有实例在运行，安静退出
            sys.exit(0)
        raise SystemExit(
            f"无法监听 {args.host}:{args.port}~{args.port + 7}：{last_err}\n"
            "可用 --port 指定其他端口"
        )

    svc = Service()
    httpd.svc = svc
    st = svc.state()
    print("=" * 56)
    print("  tg-hotlist 本地网页版")
    print(f"  打开浏览器: http://{args.host}:{args.port}")
    print("=" * 56)
    if st["logged_in"]:
        u = st["user"] or {}
        print(f"  已登录: {u.get('name','')} (id {u.get('id','')}) · 来源 {st['source']}")
    else:
        print("  尚未登录 → 页面会显示二维码，用手机 Telegram 扫码")
    if st["proxy"]:
        print(f"  代理: {st['proxy']}")
    if st["last_error"]:
        print(f"  提示: {st['last_error']}")
    print("  按 Ctrl+C 停止")
    print("=" * 56, flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止。")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
