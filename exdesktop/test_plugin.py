# -*- coding: utf-8 -*-
"""插件 v3.4 测试：TL 消息解析(_row/_reactions) + 菜单 + 真实后端端到端。
无后端时自动 SKIP（供 CI 使用）。"""
import importlib.machinery
import importlib.util
import shutil
import sys
import tempfile
import time
import types
from pathlib import Path
from types import SimpleNamespace

import os
PLUGIN = str(Path(__file__).resolve().parent / "hotlist.plugin")
BACKEND = "http://127.0.0.1:8765"
# 端到端测试需要真实群 id，用环境变量传入；仓库里不写死任何真实会话
GROUP = int(os.environ.get("TGHL_TEST_GROUP", "0") or "0")

# 需要本地后端；没有就跳过
import urllib.request as _urlreq
try:
    _urlreq.urlopen(BACKEND + "/api/state", timeout=3).read()
except Exception:
    print("SKIP: 本地后端 %s 不可用，跳过需真实后端的插件测试" % BACKEND)
    sys.exit(0)

if not GROUP:
    print("SKIP: 未设置 TGHL_TEST_GROUP（真实群 id），跳过端到端测试")
    sys.exit(0)

FAIL = 0
def check(name, got, want):
    global FAIL
    ok = got == want
    if not ok:
        FAIL += 1
    print(("PASS" if ok else "FAIL"), name, "→", repr(got), "" if ok else f"(期望 {want!r})")

record = {"menu": [], "alerts": [], "bulletins": [], "opened": []}
TMP = tempfile.mkdtemp(prefix="hlplug_")

# ---------- SDK stubs ----------
bp = types.ModuleType("base_plugin")
class _BasePlugin:
    def __init__(self): self._settings = {}
    def add_menu_item(self, d): record["menu"].append(d); return "id"
    def get_setting(self, k, d=None): return self._settings.get(k, d)
    def set_setting(self, k, v, reload_settings=False): self._settings[k] = v
    def log(self, m): pass
class _MID:
    def __init__(self, menu_type, text, on_click=None, item_id=None, icon=None,
                 subtext=None, condition=None, priority=0):
        self.menu_type = menu_type; self.text = text; self.on_click = on_click; self.priority = priority
class _MT:
    MESSAGE_CONTEXT_MENU="MESSAGE_CONTEXT_MENU"; DRAWER_MENU="DRAWER_MENU"
    CHAT_ACTION_MENU="CHAT_ACTION_MENU"; PROFILE_ACTION_MENU="PROFILE_ACTION_MENU"
bp.BasePlugin=_BasePlugin; bp.MenuItemData=_MID; bp.MenuItemType=_MT
sys.modules["base_plugin"]=bp

ui=types.ModuleType("ui"); ui.__path__=[]; sys.modules["ui"]=ui
us=types.ModuleType("ui.settings")
class _W:
    def __init__(self,*a,**k): self.args=a; self.kw=k
for n in ("Header","Divider","Selector","Input","Text","Switch"): setattr(us,n,_W)
sys.modules["ui.settings"]=us

ua=types.ModuleType("ui.alert")
class _B:
    def __init__(self): self.title=None; self.message=None; self.items=None; self.listener=None; self.buttons={}
    def set_title(self,t): self.title=t; return self
    def set_message(self,m): self.message=m; return self
    def set_items(self,i,l=None): self.items=list(i); self.listener=l; return self
    def set_positive_button(self,t,l=None): self.buttons[-1]=(t,l); return self
    def set_negative_button(self,t,l=None): self.buttons[-2]=(t,l); return self
    def set_neutral_button(self,t,l=None): self.buttons[-3]=(t,l); return self
    def dismiss(self): pass
    def show(self): record["alerts"].append(self)
ua.AlertDialogBuilder=_B; sys.modules["ui.alert"]=ua

ub=types.ModuleType("ui.bulletin")
class _Bl:
    @staticmethod
    def show_error(m): record["bulletins"].append(("error", m))
    @staticmethod
    def show_info(m): record["bulletins"].append(("info", m))
    @staticmethod
    def show_success(m): record["bulletins"].append(("success", m))
ub.BulletinHelper=_Bl; sys.modules["ui.bulletin"]=ub

cu=types.ModuleType("client_utils")
cu.get_current_dialog_id=lambda: GROUP
cu.send_request=lambda *a, **k: 1
sys.modules["client_utils"]=cu

tb=types.ModuleType("tgnet_bridge")
tb.peer_info=lambda d: {"type":"channel","bare_id":123,"username":"mygrp","name":"测试群","access_hash":1}
tb.get_input_peer=lambda d: object()
sys.modules["tgnet_bridge"]=tb

fu=types.ModuleType("file_utils")
fu.get_plugin_cache_dir=lambda pid=None: TMP
fu.get_plugin_dir=lambda pid=None: TMP
sys.modules["file_utils"]=fu

hu=types.ModuleType("hook_utils")
class _Br:
    @staticmethod
    def openUrl(c,u): record["opened"].append(u)
hu.find_class=lambda n:_Br; sys.modules["hook_utils"]=hu

au=types.ModuleType("android_utils")
au.run_on_ui_thread=lambda fn,*a,**k: fn()
au.copy_to_clipboard=lambda t: None
au.safe_call=lambda fn,*a: fn(*a)
sys.modules["android_utils"]=au

# ---------- load ----------
loader=importlib.machinery.SourceFileLoader("hp", PLUGIN)
spec=importlib.util.spec_from_loader("hp", loader)
mod=importlib.util.module_from_spec(spec); loader.exec_module(mod)

check("version", mod.__version__, "3.4")
p=mod.HotlistPlugin(); p.on_plugin_load()
check("菜单项 2 个", len(record["menu"]), 2)
check("有聊天菜单", "CHAT_ACTION_MENU" in [m.menu_type for m in record["menu"]], True)
check("有抽屉", "DRAWER_MENU" in [m.menu_type for m in record["menu"]], True)

# ---------- TL 消息 -> 行 ----------
def fmsg(mid, date, text="", reactions=None, replies=0, forwards=0, views=0, gid=None, from_user=None):
    m=SimpleNamespace(id=mid, date=date, message=text, forwards=forwards, views=views, grouped_id=gid)
    if reactions:
        m.reactions=SimpleNamespace(results=[SimpleNamespace(count=c, reaction=SimpleNamespace(emoticon=e)) for e,c in reactions])
    if replies:
        m.replies=SimpleNamespace(replies=replies)
    if from_user:
        m.from_id=SimpleNamespace(user_id=from_user)
    return m

info={"type":"channel","bare_id":123,"username":"mygrp","name":"测试群"}
row=p._row(fmsg(5, 1700000000, "hi", reactions=[("👍",4),("🔥",1)], replies=2, forwards=3, views=900, gid=777), info)
check("row id", row[0], 5)
check("row reactions", row[3], 5)
check("row 明细", row[4].startswith("👍×4"), True)
check("row replies", row[5], 2)
check("row forwards", row[6], 3)
check("row views", row[7], 900)
check("row link", row[9], "https://t.me/mygrp/5")
check("row deep", row[10], "tg://resolve?domain=mygrp&post=5")
check("row grouped_id", row[11], 777)

# 私有群
info2={"type":"channel","bare_id":999,"username":None,"name":"私群"}
row2=p._row(fmsg(6, 1700000000, "x"), info2)
check("私有群 link", row2[9], "https://t.me/c/999/6")
check("私有群 deep", row2[10], "tg://privatepost?channel=999&post=6")

# ---------- 真实后端端到端 ----------
p._settings={"source":"1","days":"1","by":"0","top":"5","limit":"1500","backend":BACKEND}
p._busy.clear()
record["alerts"].clear(); record["bulletins"].clear()
p._run({})
check("后端出榜", len(record["alerts"]), 1)
if record["alerts"]:
    a=record["alerts"][0]
    check("items[0] 刷新", a.items[0].startswith("🔄"), True)
    check("items[3] 条数", "条数" in a.items[3], True)
    check("items[4] 分隔", a.items[4]=="─────────────", True)
    check("items[5] #1", a.items[5].startswith("#1"), True)
    record["opened"].clear()
    a.listener(a, 5)
    check("点条目开深链", bool(record["opened"]) and record["opened"][0].startswith("tg://"), True)
    print("  标题:", a.title)

print()
print("全部通过 ✔" if FAIL==0 else f"有 {FAIL} 项失败 ✘")
try: shutil.rmtree(TMP, ignore_errors=True)
except Exception: pass
sys.exit(1 if FAIL else 0)
