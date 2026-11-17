# tg-hotlist · Telegram Group Hot-Message Ranking

[![CI](https://github.com/cccssssss123/tg-hotlist/actions/workflows/ci.yml/badge.svg)](https://github.com/cccssssss123/tg-hotlist/actions/workflows/ci.yml)

Rank **hot messages in Telegram groups/channels by reactions / interactions**.
Runs entirely on your own machine and is **read-only** — it never sends messages,
never adds reactions, and never modifies your chat data.

Two delivery forms — pick one:

| Form | What it is | Best for |
|---|---|---|
| **A. Local web panel** | Open `127.0.0.1:8765` in a browser, pick a group, view ranking, export | No third-party client needed |
| **B. exDesktop plugin** | Inside the open-source client [exDesktop](https://github.com/metawka/exDesktop), open ranking from the chat menu | One-click ranking inside a chat client (recommended) |

Both share the same statistics/ranking engine and keep data local.

> 中文说明见 [README.md](README.md)。

---

## Quick start

### One-click install (recommended)

Double-click **`exdesktop/setup.bat`**. It will:

1. Download the latest exDesktop **portable** build from official GitHub Releases and extract it to `exdesktop/app`
2. Create a Python virtualenv and install dependencies (auto-falls back to a PyPI mirror)
3. Install the plugin and enable *allow plugins from unknown sources* (writes `extera.json` **without BOM**)
4. Create a desktop shortcut + a startup entry (silent, no console window)

Then: double-click the desktop shortcut → log in to exDesktop by scanning the QR
code → open any group → **Hot Messages** in the menu.

> The script only *downloads* exDesktop; this repo does **not** ship any client binary.
> If download fails, get the portable build from
> https://github.com/metawka/exDesktop/releases, extract to `exdesktop/app`, and rerun.

### Form A: web panel

1. Double-click `tg-hotlist/run_web.bat`
2. Browser opens `http://127.0.0.1:8765`
3. First run: scan the QR code with your phone (Telegram → Settings → Devices → Link Desktop Device). **No my.telegram.org, no SMS code needed.**
4. Pick a group on the left → set time range / sort / count → load the ranking

---

## Directory layout

```
.
├── tg-hotlist/                 # backend + web panel + CLI
│   ├── tg_hotlist.py           # core: login, fetch, reactions/replies/forwards/views stats, ranking, render
│   ├── web_app.py              # local web backend (persistent client + HTTP + cache/rate-limit)
│   ├── web/                    # frontend (vanilla JS, no framework)
│   ├── import_tdata.py         # import session from AyuGram/Telegram Desktop tdata (no code)
│   ├── periodic_likes.py       # yearly/monthly like ranking (CLI)
│   ├── run_web.bat / run_web_silent.bat / run_panel.bat / stop_web.bat / run.bat
│   ├── README.md / README_WEB.md
│   └── test_offline.py
├── exdesktop/                  # exDesktop plugin (Form B)
│   ├── hotlist.plugin          # plugin source (Python, exteraGram format)
│   ├── setup.bat / setup.ps1   # one-click installer
│   ├── start_all.bat / start_silent_all.vbs
│   ├── README_集成exDesktop.md
│   ├── test_plugin.py / test_cache.py
│   └── 官方插件清单.txt
├── .github/workflows/ci.yml    # CI
├── LICENSE                     # GPL-3.0
├── THIRD-PARTY-NOTICES.md
└── README.md / README.en.md
```

---

## Features

- **Sort by**: interaction score / reactions / replies / forwards / views
- **Time range**: last 1/3/7/30 days, last year, all history (**remembered per group**, new groups default to 3 days)
- **Top N**: 10/15/20/30/50/100/200/500
- **Album merge**: multiple photos/videos of one message (shared `grouped_id`) are merged into one entry
- **Jump to message**: clicking an entry opens it in the client via a `tg://` deep link
- **Local cache + incremental**: SQLite on disk; second visit is instant; refresh only pulls new messages
- **Export**: Markdown / HTML (with deep links)
- **Score formula**: `1×reactions + 1×replies + 2×forwards + 0.05×min(views, 20)`

---

## Architecture & hard limits

Two data paths (switchable in the plugin):

| Mode | How | Needs backend process |
|---|---|---|
| Client-direct (default) | Plugin uses exDesktop's own session to send MTProto `messages.getHistory` | No |
| Local service 8765 | Goes through the tg-hotlist backend (separate Telethon session) | Yes |

**Boundaries (important):**

- Desktop clients (tdesktop family) expose **no message-view/cell/drawing hooks** to plugins,
  so they **cannot reorder the chat list itself** — only an *additional ranking view* is possible (this tool).
- The plugin sandbox **forbids reading `tdata`** and the SDK has no API to enumerate loaded
  in-memory messages. Any solution must re-request history from Telegram; the "local cache"
  here is our own (stored in the plugin dir), not the client's cache.

---

## Requirements

- Python 3.9+ (bundled in `tg-hotlist/.venv`)
- `telethon`, `tdata-reader`, `python-socks`, `segno` (see `tg-hotlist/requirements.txt`)
- Optional: `exDesktop` (Form B; third-party, GPL-3.0)

Rebuild the env:

```
cd tg-hotlist
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt
```

---

## Tests

```
# fully offline (core logic)
python tg-hotlist/test_offline.py
# plugin cache/incremental/album-merge (offline, stubbed SDK)
python exdesktop/test_cache.py
# plugin dialog logic (needs a running backend on 127.0.0.1:8765, skips otherwise)
python exdesktop/test_plugin.py
```

CI runs `test_offline.py` and `test_cache.py` (plus syntax checks) on every push.

---

## License

**GNU GPL v3.0** — see [LICENSE](LICENSE) and [THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md).

- exDesktop is **GPL-3.0**; this project is released under GPL-3.0 for compatibility
  (the plugin imports exDesktop's plugin SDK, so it is a combined work).
- This repo does **not** redistribute the exDesktop binary; the installer downloads it
  from official Releases. If you bundle the exDesktop binary yourself, you must also
  provide exDesktop's complete corresponding source (GPL obligation).
- GPL grants no trademark rights to the "exDesktop" name/logo — don't imply official status.

## Disclaimer

For personal study and research only. Follow Telegram's Terms of Service and local laws.
Use at your own risk.
