#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从 AyuGram/Telegram Desktop 的 tdata 目录导入登录会话。

不需要 my.telegram.org 的 api_id/api_hash，也不需要验证码——
直接复用你已登录的桌面客户端的凭证。

用法:
  python import_tdata.py "C:/path/to/AyuGram/tdata"
  python import_tdata.py "C:/path/to/AyuGram/tdata" --passcode 本地密码
  python import_tdata.py "C:/path/to/AyuGram/tdata" --account 1   (多账号选第2个)
"""

import argparse
import asyncio
import json
import shutil
import sys
import traceback
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from tdata_reader import read_all_tdata

SCRIPT_DIR = Path(__file__).resolve().parent
SESSION_PATH = SCRIPT_DIR / "tg_hotlist.session"
META_PATH = SCRIPT_DIR / "tdata_import.json"
LOG_PATH = SCRIPT_DIR / "import_log.txt"

# tdata_reader 只需要这些：顶层密钥文件 + 账号数据目录。
# AyuGram 运行时 user_data/temp/dumps 等大目录会被锁定，直接跳过。
SKIP_DIRS = {"ayu", "dictionaries", "dumps", "emoji", "tdummy", "temp", "user_data", "modules"}


def log(msg: str = ""):
    print(msg, flush=True)
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(msg + "\n")


def robust_copy(src: Path, dst: Path):
    """逐文件复制，被占用的文件跳过并记录。"""
    dst.mkdir(parents=True, exist_ok=True)
    copied, skipped = [], []
    for item in src.iterdir():
        if item.is_dir() and item.name.lower() in SKIP_DIRS:
            skipped.append(item.name + "/ (无关或被锁定,跳过)")
            continue
        try:
            if item.is_dir():
                _copy_dir(item, dst / item.name, copied, skipped)
            else:
                shutil.copy2(item, dst / item.name)
                copied.append(item.name)
        except OSError as e:
            skipped.append(f"{item.name} ({e.winerror if hasattr(e,'winerror') else ''})")
    return copied, skipped


def _copy_dir(src: Path, dst: Path, copied: list, skipped: list, depth=0):
    if depth > 3:
        return
    dst.mkdir(parents=True, exist_ok=True)
    for item in src.iterdir():
        try:
            if item.is_dir():
                _copy_dir(item, dst / item.name, copied, skipped, depth + 1)
            else:
                shutil.copy2(item, dst / item.name)
                copied.append(str(item.relative_to(src.parent)))
        except OSError:
            skipped.append(str(item.relative_to(src.parent)) + " (被锁定)")


def _proxy_from_config():
    """读取 config.json 里的 proxy 配置（可没有）。"""
    cfg_path = SCRIPT_DIR / "config.json"
    if cfg_path.exists():
        try:
            p = json.loads(cfg_path.read_text(encoding="utf-8")).get("proxy")
        except Exception:
            p = None
        if isinstance(p, dict) and p.get("host"):
            proxy = {
                "proxy_type": str(p.get("scheme", "socks5")).lower(),
                "addr": str(p["host"]),
                "port": int(p.get("port", 0)),
            }
            for k in ("username", "password"):
                if p.get(k):
                    proxy[k] = str(p[k])
            return proxy
    return None


def main():
    ap = argparse.ArgumentParser(
        prog="import_tdata.py",
        description="把 AyuGram/Telegram Desktop 的 tdata 登录凭证导入为 tg-hotlist 会话",
    )
    ap.add_argument("tdata_dir", help='tdata 目录路径, 例如 "C:/Users/你/Downloads/AyuGram/tdata"')
    ap.add_argument("--passcode", default=None, help="桌面客户端本地密码(如果设置过)")
    ap.add_argument("--account", type=int, default=0, help="多账号时选择第几个(从0开始)")
    args = ap.parse_args()

    LOG_PATH.write_text("", encoding="utf-8")  # 清空旧日志
    log("=== tg-hotlist tdata 导入 ===")

    src = Path(args.tdata_dir)
    if not src.is_dir():
        log(f"错误: 目录不存在: {src}")
        sys.exit(1)
    if not list(src.glob("key_data*")) and (src / "tdata").is_dir():
        src = src / "tdata"
    if not list(src.glob("key_data*")):
        log(f"错误: {src} 里没有 key_data* 文件, 这不是有效的 tdata 目录")
        sys.exit(1)

    tmp = SCRIPT_DIR / "_tdata_tmp"
    if tmp.exists():
        shutil.rmtree(tmp, ignore_errors=True)

    log("复制凭证文件到临时目录(跳过运行中被锁定的大文件)...")
    copied, skipped = robust_copy(src, tmp)
    log(f"  已复制 {len(copied)} 个文件; 跳过 {len(skipped)} 项")
    for s in skipped:
        log(f"    跳过: {s}")

    try:
        log("解析 tdata 账号...")
        accounts = list(read_all_tdata(str(tmp), passcode=(args.passcode or "")))
        if not accounts:
            log("错误: tdata 里没有找到任何账号。"
                "如果设置过桌面端本地密码, 请加 --passcode 参数重试")
            sys.exit(1)
        for i, acc in enumerate(accounts):
            mark = "  <-- 将导入" if i == args.account else ""
            log(f"  账号[{i}]  用户ID {acc.user_id}  (DC{acc.dc_id}){mark}")
        if args.account >= len(accounts):
            log(f"错误: 只有 {len(accounts)} 个账号, --account 最大 {len(accounts) - 1}")
            sys.exit(1)
        acc = accounts[args.account]

        kw = acc.as_init_connection_kwargs()
        proxy = _proxy_from_config()
        if proxy:
            log(f"使用代理 {proxy['proxy_type']}://{proxy['addr']}:{proxy['port']}")
            kw["proxy"] = proxy
        log(f"以 Telegram Desktop 官方 API (api_id={kw['api_id']}) 连接服务器验证...")
        from telethon import TelegramClient
        from telethon.sessions import StringSession

        client = TelegramClient(StringSession(acc.to_string_session()), **kw)

        async def connect():
            await client.connect()
            ok = await client.is_user_authorized()
            me = await client.get_me() if ok else None
            await client.disconnect()
            return ok, me

        ok, me = asyncio.run(connect())
        if not ok:
            log("错误: tdata 凭证未通过服务器验证(可能 tdata 太旧或账号已在那边登出)")
            sys.exit(1)

        name = " ".join(x for x in (me.first_name, me.last_name) if x) if me else ""
        log(f"验证通过: {name} (id {me.id})")

        SESSION_PATH.write_text(StringSession.save(client.session), encoding="utf-8")
        META_PATH.write_text(json.dumps({
            "api_id": kw["api_id"],
            "api_hash": kw["api_hash"],
            "user_id": acc.user_id,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        log(f"会话已写入: {SESSION_PATH.name}")
        log("完成! 现在可以直接运行:")
        log("  run.bat chats         查看群列表")
        log('  run.bat top -g 群名   生成热门榜')
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        err = traceback.format_exc()
        print(err, file=sys.stderr)
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(err)
        sys.exit(1)
