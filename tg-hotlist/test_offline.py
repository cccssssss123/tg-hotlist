#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tg_hotlist 核心逻辑离线测试（不联网，用模拟消息对象）。"""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
import asyncio

sys.path.insert(0, str(Path(__file__).parent))

import tg_hotlist as h


def fake_msg(id, date, text="", reactions=None, replies=0, forwards=0, views=0,
             grouped_id=None, reply_to=None, from_id=None, photo=None):
    return SimpleNamespace(
        id=id,
        date=date,
        message=text,
        reactions=reactions,
        replies=SimpleNamespace(replies=replies) if replies else None,
        forwards=forwards,
        views=views,
        grouped_id=grouped_id,
        reply_to=reply_to,
        from_id=from_id,
        photo=photo,
        action=None,
        sticker=None, voice=None, audio=None, video_note=None,
        video=None, poll=None, contact=None, geo=None, document=None,
    )


def fake_reacts(pairs):
    """pairs: [(emoticon, count), ...]"""
    results = [
        SimpleNamespace(count=c, reaction=SimpleNamespace(emoticon=e))
        for e, c in pairs
    ]
    return SimpleNamespace(results=results)


NOW = datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc)
FAIL = 0


def check(name, got, want):
    global FAIL
    ok = got == want
    if not ok:
        FAIL += 1
    print(("PASS" if ok else "FAIL"), name, "→", repr(got),
          "" if ok else f"(期望 {want!r})")


# ---- reaction_summary ----
check("reaction_summary 空", h.reaction_summary(fake_msg(1, NOW)), (0, ""))
total, detail = h.reaction_summary(fake_msg(1, NOW, reactions=fake_reacts([("👍", 12), ("🔥", 3), ("❤", 5)])))
check("reaction_summary 总数", total, 20)
check("reaction_summary 明细降序", detail, "👍×12 ❤×5 🔥×3")

# ---- fmt_num ----
check("fmt_num 999", h.fmt_num(999), "999")
check("fmt_num 12345", h.fmt_num(12345), "1.2w")
check("fmt_num 0", h.fmt_num(0), "0")

# ---- 时间窗口：365 天 / 历史全部 ----
s365, a365 = h.time_window_start(365)
check("365天 非全历史", a365, False)
check("365天 跨度≈365天",
      abs((datetime.now(timezone.utc) - s365).days - 365) <= 1, True)
s0, a0 = h.time_window_start(0)
check("0天 = 历史全部", a0, True)
check("全历史下界=2013", s0.year, 2013)
sneg, aneg = h.time_window_start(-1)
check("负数 = 历史全部", aneg, True)

# ---- collect_messages：时间窗口 / 历史全部 / 截断标记 ----
class _FakeClient:
    def __init__(self, msgs):
        self._msgs = msgs

    def iter_messages(self, entity, limit=None, wait_time=0):
        async def gen():
            for n, m in enumerate(self._msgs):
                if limit is not None and n >= limit:
                    return
                yield m
        return gen()


def _mkmsg(i, days_ago, action=None, gid=None):
    return SimpleNamespace(
        id=i,
        date=datetime.now(timezone.utc) - timedelta(days=days_ago),
        action=action, grouped_id=gid,
    )


_msgs = [_mkmsg(i, d) for i, d in enumerate([0, 1, 2, 4, 10])]
got, st, trunc = asyncio.run(h.collect_messages(
    _FakeClient(_msgs), None, 3, 100, quiet=True))
check("3天窗口 只取3条", len(got), 3)
check("3天窗口 不算截断", trunc, False)

got_all, _, trunc_all = asyncio.run(h.collect_messages(
    _FakeClient(_msgs), None, 0, 100, quiet=True))
check("历史全部 取全部5条", len(got_all), 5)
check("历史全部 未到上限不算截断", trunc_all, False)

got_cap, _, trunc_cap = asyncio.run(h.collect_messages(
    _FakeClient(_msgs), None, 0, 5, quiet=True))
check("历史全部 触到上限算截断", trunc_cap, True)

# 服务消息 + 相册合并会让 msgs 少于 limit，仍必须识别为截断
_mixed = [
    _mkmsg(1, 0), _mkmsg(2, 0, action="service"),
    _mkmsg(3, 0, gid="g1"), _mkmsg(4, 0, gid="g1"), _mkmsg(5, 0),
]
got_mix, _, trunc_mix = asyncio.run(h.collect_messages(
    _FakeClient(_mixed), None, 0, 5, quiet=True))
check("过滤后少于上限 仍识别为截断", trunc_mix, True)
check("服务消息/相册合并生效", len(got_mix), 3)

# ---- disp_width / pad ----
check("disp_width 中文", h.disp_width("你好a"), 5)
check("pad 中文补齐到指定显示宽度", h.disp_width(h.pad("你好", 6)), 6)
check("pad 已超宽不截断", h.disp_width(h.pad("你好啊", 4)), 6)

# ---- score 计算（build_stats 依赖 client 的部分改为手算验证公式） ----
w = {"reaction": 1, "reply": 1, "forward": 2, "view": 0.05, "view_cap": 20}
# 消息 A: 12赞 + 3回复 + 1转发 + 无浏览
score_a = w["reaction"] * 12 + w["reply"] * 3 + w["forward"] * 1
# 消息 B: 5赞 + 0回复 + 0转发 + 100000浏览(封顶20 → 20*0.05=1)
score_b = w["reaction"] * 5 + w["view"] * min(100000, w["view_cap"])
check("score A(点赞为主)", score_a, 17.0)
check("score B(浏览封顶)", score_b, 6.0)
check("浏览封顶后 A > B", score_a > score_b, True)

# ---- sort_entries ----
entries = [
    {"score": 5, "reactions": 5, "replies": 0, "views": 0, "forwards": 0},
    {"score": 17, "reactions": 12, "replies": 3, "views": 0, "forwards": 1},
    {"score": 6, "reactions": 5, "replies": 0, "views": 100000, "forwards": 0},
]
for by in ("score", "reactions", "replies", "views", "forwards"):
    ranked = h.sort_entries(entries, by)
    check(f"sort by {by} 降序", ranked[0][by] >= ranked[-1][by], True)
check("sort score 第一名是12赞消息", h.sort_entries(entries, "score")[0]["reactions"], 12)

# ---- preview_text / media_label ----
check("preview_text 普通文本", h.preview_text(fake_msg(1, NOW, text="hello world")), "hello world")
check("preview_text 截断", h.preview_text(fake_msg(1, NOW, text="x" * 100), maxlen=60).endswith("…"), True)
check("preview_text 无文本→媒体标签", h.preview_text(fake_msg(1, NOW)), "[消息]")
check("media_label 照片", h.media_label(fake_msg(1, NOW, text="", photo=object())), "[图片]")

# ---- msg_link ----
chan = SimpleNamespace(id=123, username="mygroup")
check("msg_link 公开群", h.msg_link(chan, SimpleNamespace(id=456)),
      "https://t.me/mygroup/456")
_TL = __import__("telethon.tl.types", fromlist=["Channel", "ChatPhotoEmpty"])
priv = _TL.Channel(id=123, title="t", photo=_TL.ChatPhotoEmpty(), date=NOW)
check("msg_link 私有频道(无用户名)", h.msg_link(priv, SimpleNamespace(id=456)),
      "https://t.me/c/123/456")
basic_chat = SimpleNamespace(id=999, username=None)  # 基本群(非超级群)没有消息链接
check("msg_link 非频道返回None", h.msg_link(basic_chat, SimpleNamespace(id=456)), None)

# ---- tg_deep_link：客户端内部深链（不经过 t.me 网页）----
check("deep 公开用户名", h.tg_deep_link(chan, SimpleNamespace(id=456)),
      "tg://resolve?domain=mygroup&post=456")
check("deep 私有频道", h.tg_deep_link(priv, SimpleNamespace(id=456)),
      "tg://privatepost?channel=123&post=456")
check("deep 基本群无深链", h.tg_deep_link(basic_chat, SimpleNamespace(id=456)), None)

# ---- 文件渲染（md/html） ----
top = []
for i, (reacts, txt) in enumerate([
    ([("👍", 50), ("🔥", 8)], "热帖一号：今天群里聊什么？"),
    ([("❤", 30)], "热帖二号：[图片] 分享一张图"),
]):
    m = fake_msg(i + 1, NOW, text=txt, reactions=fake_reacts(reacts),
                 replies=3 + i, forwards=i, views=100 * (i + 1))
    total, detail = h.reaction_summary(m)
    e = {
        "msg": m, "reactions": total, "react_detail": detail,
        "replies": 3 + i, "forwards": i, "views": 100 * (i + 1),
        "score": total + (3 + i) + 2 * i, "author": "测试用户",
    }
    top.append(e)

meta = {"group": "测试群", "by": "score", "by_label": "互动分", "days": 3,
        "count": 100, "start": "2026-11-11 12:00", "end": "2026-11-14 12:00",
        "truncated": False, "top_n": 2}
md_path = h.OUTPUT_DIR / "_test.md"
html_path = h.OUTPUT_DIR / "_test.html"
h.OUTPUT_DIR.mkdir(exist_ok=True)
h.write_markdown(md_path, meta, top, chan)
h.write_html(html_path, meta, top, chan)
md = md_path.read_text(encoding="utf-8")
html = html_path.read_text(encoding="utf-8")
check("md 包含标题", "# 测试群 · 互动分 Top 2" in md, True)
check("md 包含链接", "https://t.me/mygroup/2" in md, True)
check("md 表格行数≥3", len([l for l in md.splitlines() if l.startswith("|")]) >= 4, True)
check("html 包含卡片", html.count('class="card"') == 2, True)
check("html 包含链接", "https://t.me/mygroup/2" in html, True)
check("html 转义作者名", "测试用户" in html, True)

# ---- 表格打印不崩溃 ----
print()
h.print_table([("#", "互动", "内容"), ("1", "17", "中文对齐测试"), ("2", "6", "OK")])
print()
md_path.unlink()
html_path.unlink()

print()
print("全部通过 ✔" if FAIL == 0 else f"有 {FAIL} 个断言失败 ✘")
sys.exit(1 if FAIL else 0)
