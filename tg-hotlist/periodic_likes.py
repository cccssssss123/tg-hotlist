#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
按时间段(年/月)统计频道/群组的点赞 Top N 榜单。

用法:
  python periodic_likes.py -g @examplechannel  --mode year
  python periodic_likes.py -g @examplechannel --mode month
  可选: -n 每期条数(默认10) --min-likes 最少点赞数(默认1)
"""

import argparse
import asyncio
import html as html_mod
import re
import sys
from collections import OrderedDict
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import tg_hotlist as h

SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = SCRIPT_DIR / "output"

MODE_LABEL = {"year": "按年", "month": "按月"}


def group_key(dt, mode: str) -> str:
    return dt.strftime("%Y") if mode == "year" else dt.strftime("%Y-%m")


async def fetch_all(client, entity, cap=200000):
    msgs, seen, truncated = [], set(), False
    async for m in client.iter_messages(entity, limit=cap, wait_time=0.5):
        if getattr(m, "action", None) is not None:
            continue
        gid = getattr(m, "grouped_id", None)
        if gid:
            if gid in seen:
                continue
            seen.add(gid)
        msgs.append(m)
        if len(msgs) % 500 == 0:
            print(f"\r  已获取 {len(msgs)} 条…", end="", flush=True)
    print("\r" + " " * 30 + "\r", end="")
    if len(msgs) >= cap:
        truncated = True
    return msgs, truncated


def build_periods(msgs, mode: str, top_n: int, min_likes: int):
    """按时间分组，每组内按点赞降序取前 N（只保留点赞≥min_likes 的帖子）。"""
    buckets = {}
    for m in msgs:
        k = group_key(m.date.astimezone(), mode)
        total, detail = h.reaction_summary(m)
        buckets.setdefault(k, []).append({
            "msg": m,
            "reactions": total,
            "detail": detail,
            "views": getattr(m, "views", 0) or 0,
            "forwards": getattr(m, "forwards", 0) or 0,
        })

    periods = OrderedDict()
    for k in sorted(buckets.keys()):
        items = [e for e in buckets[k] if e["reactions"] >= min_likes]
        items.sort(key=lambda e: (e["reactions"], e["views"]), reverse=True)
        periods[k] = {
            "total_posts": len(buckets[k]),
            "liked_posts": len(items),
            "top": items[:top_n],
        }
    return periods


def author_of(entity, m):
    if getattr(m, "from_id", None) is None:
        return getattr(entity, "title", None) or "频道"
    return "成员"


def render_md(path: Path, title, entity, mode, periods, min_likes):
    lines = [f"# {title} · {MODE_LABEL[mode]}点赞榜 (每期Top {10})", ""]
    oldest = newest = ""
    lines.append(f"> 点赞 ≥ {min_likes} 才入榜; 「帖子」为该期总发帖数")
    lines.append("")
    for k, p in periods.items():
        lines.append(f"## {k}  ({p['total_posts']} 帖, {p['liked_posts']} 帖有点赞)")
        lines.append("")
        if not p["top"]:
            lines.append(f"_(该期没有点赞 ≥ {min_likes} 的帖子)_")
            lines.append("")
            continue
        lines.append("| # | 👍 | 明细 | 转发 | 浏览 | 日期 | 内容 |")
        lines.append("|---|----|------|------|------|------|------|")
        for i, e in enumerate(p["top"], 1):
            m = e["msg"]
            link = h.msg_link(entity, m)
            text = h.md_escape(h.preview_text(m, 60))
            cell = f"[{text}]({link})" if link else text
            lines.append(
                f"| {i} | {e['reactions']} | {h.md_escape(e['detail'])} "
                f"| {e['forwards']} | {h.fmt_num(e['views'])} "
                f"| {m.date.astimezone().strftime('%Y-%m-%d')} | {cell} |"
            )
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def render_html(path: Path, title, entity, mode, periods, min_likes):
    sections = []
    for k, p in periods.items():
        if not p["top"]:
            body = f'<p class="none">该期没有点赞 ≥ {min_likes} 的帖子</p>'
        else:
            rows = []
            for i, e in enumerate(p["top"], 1):
                m = e["msg"]
                link = h.msg_link(entity, m)
                text = html_mod.escape(h.preview_text(m, 70))
                inner = (f'<a href="{html_mod.escape(link)}" target="_blank">{text}</a>'
                         if link else text)
                rows.append(
                    f"<tr><td class='rank'>{i}</td>"
                    f"<td class='lk'>{e['reactions']}</td>"
                    f"<td class='dt'>{html_mod.escape(e['detail'])}</td>"
                    f"<td>{e['forwards']}</td><td>{h.fmt_num(e['views'])}</td>"
                    f"<td class='dt'>{m.date.astimezone().strftime('%Y-%m-%d')}</td>"
                    f"<td class='tx'>{inner}</td></tr>"
                )
            body = (
                "<table><tr><th>#</th><th>👍</th><th>明细</th><th>转发</th>"
                "<th>浏览</th><th>日期</th><th>内容</th></tr>"
                + "".join(rows) + "</table>"
            )
        sections.append(
            f"<h2>{k} <span class='cnt'>({p['total_posts']} 帖 / {p['liked_posts']} 有点赞)</span></h2>{body}"
        )
    doc = f"""<!doctype html>
<html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html_mod.escape(str(title))} · {MODE_LABEL[mode]}点赞榜</title>
<style>
  :root {{ color-scheme: dark; }}
  body {{ background:#14161a; color:#e8eaed; font:14px/1.6 -apple-system,"Segoe UI","Microsoft YaHei",sans-serif; margin:0; padding:24px; }}
  h1 {{ font-size:20px; margin:0 0 2px; }}
  .meta {{ color:#9aa0a6; font-size:13px; margin-bottom:8px; }}
  h2 {{ font-size:16px; margin:26px 0 8px; color:#5ea8ff; }}
  .cnt {{ color:#9aa0a6; font-size:12.5px; font-weight:400; }}
  table {{ border-collapse:collapse; width:100%; }}
  th,td {{ border-bottom:1px solid #262b32; padding:5px 8px; text-align:left; vertical-align:top; }}
  th {{ color:#9aa0a6; font-weight:500; font-size:12.5px; }}
  .rank {{ color:#5ea8ff; font-weight:700; width:30px; }}
  .lk {{ color:#ff8f8f; font-weight:700; }}
  .dt {{ color:#9aa0a6; font-size:12.5px; white-space:nowrap; }}
  .tx {{ word-break:break-word; }}
  .tx a {{ color:#e8eaed; text-decoration:none; }}
  .tx a:hover {{ color:#5ea8ff; }}
  .none {{ color:#9aa0a6; }}
</style></head><body>
<h1>{html_mod.escape(str(title))} · {MODE_LABEL[mode]}点赞榜</h1>
<div class="meta">每期 Top 10 · 点赞 ≥ {min_likes} 才入榜 · 由 tg-hotlist 生成 {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M')}</div>
{''.join(sections)}
</body></html>"""
    path.write_text(doc, encoding="utf-8")


async def run(args):
    cfg = h.load_config()
    client = h.make_client(cfg)
    await client.connect()
    await h.require_authorized(client)

    print(f"解析目标: {args.group}")
    entity = await h.resolve_group(client, args.group)
    title = getattr(entity, "title", None) or h.display_name(entity)
    print(f"目标: {title} · {MODE_LABEL[args.mode]} · 每期Top {args.n} · 点赞≥{args.min_likes}")

    msgs, truncated = await fetch_all(client, entity)
    await client.disconnect()
    if not msgs:
        print("没有任何消息。")
        return
    if truncated:
        print(f"⚠ 达到扫描上限 {200000}")
    dates = [m.date.astimezone() for m in msgs]
    print(f"共 {len(msgs)} 条消息, 时间跨度 {min(dates):%Y-%m-%d} ~ {max(dates):%Y-%m-%d}")

    periods = build_periods(msgs, args.mode, args.n, args.min_likes)

    # 控制台输出
    rows_head = ("期", "#", "点赞", "明细", "转发", "浏览", "日期", "内容")
    for k, p in periods.items():
        print()
        print(f"===== {k} ({p['total_posts']} 帖 / {p['liked_posts']} 有点赞) =====")
        if not p["top"]:
            print("  (无符合点赞门槛的帖子)")
            continue
        rows = [rows_head]
        for i, e in enumerate(p["top"], 1):
            rows.append([
                "", str(i), str(e["reactions"]), e["detail"] or "-",
                str(e["forwards"]), h.fmt_num(e["views"]),
                e["msg"].date.astimezone().strftime("%Y-%m-%d"),
                h.preview_text(e["msg"], 36),
            ])
        h.print_table(rows)

    # 文件输出
    OUTPUT_DIR.mkdir(exist_ok=True)
    safe = re.sub(r'[\\/:*?"<>|\s]', "", title)[:24] or "group"
    tag = "year" if args.mode == "year" else "month"
    md_path = OUTPUT_DIR / f"likes_by_{tag}_{safe}.md"
    html_path = OUTPUT_DIR / f"likes_by_{tag}_{safe}.html"
    render_md(md_path, title, entity, args.mode, periods, args.min_likes)
    render_html(html_path, title, entity, args.mode, periods, args.min_likes)
    print()
    print(f"已生成: {md_path}")
    print(f"已生成: {html_path}")


def main():
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    ap = argparse.ArgumentParser(prog="periodic_likes.py")
    ap.add_argument("-g", "--group", required=True)
    ap.add_argument("--mode", choices=("year", "month"), default="year")
    ap.add_argument("-n", type=int, default=10)
    ap.add_argument("--min-likes", type=int, default=1)
    args = ap.parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
