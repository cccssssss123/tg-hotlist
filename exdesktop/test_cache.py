# -*- coding: utf-8 -*-
"""v3.1 测试：SQLite 缓存 + 增量拉取 + 防重入 + 进度 + 离线兜底（全用假数据，不需要真网络）。"""
import importlib.machinery
import importlib.util
import os
import shutil
import sys
import tempfile
import time
import types
from pathlib import Path
from types import SimpleNamespace

PLUGIN = str(Path(__file__).resolve().parent / "hotlist.plugin")

FAIL = 0
def check(name, got, want):
    global FAIL
    ok = got == want
    if not ok:
        FAIL += 1
    print(("PASS" if ok else "FAIL"), name, "→", repr(got), "" if ok else f"(期望 {want!r})")

record = {"menu": [], "alerts": [], "bulletins": [], "opened": []}
TMP = tempfile.mkdtemp(prefix="hlcache_")

# ---- SDK stubs ----
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
ua.AlertDialogBuilder=_B
sys.modules["ui.alert"]=ua

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
cu.get_current_dialog_id=lambda: -100123
cu.send_request=lambda *a, **k: 1
sys.modules["client_utils"]=cu

tb=types.ModuleType("tgnet_bridge")
_ST={"peer_raise": False}
def _peer_info(d):
    if _ST["peer_raise"]: raise RuntimeError("no native")
    return {"type":"channel","bare_id":123,"username":"mygrp","name":"测试频道"}
tb.peer_info=_peer_info
def _gip(d):
    if _ST["peer_raise"]: raise RuntimeError("no native")
    return object()
tb.get_input_peer=_gip
sys.modules["tgnet_bridge"]=tb

fu=types.ModuleType("file_utils")
fu.get_plugin_cache_dir=lambda pid=None: TMP
fu.get_plugin_dir=lambda pid=None: TMP
sys.modules["file_utils"]=fu

hu=types.ModuleType("hook_utils")
class _Br:
    @staticmethod
    def openUrl(c,u): record["opened"].append(u)
hu.find_class=lambda n:_Br
sys.modules["hook_utils"]=hu

au=types.ModuleType("android_utils")
au.run_on_ui_thread=lambda fn,*a,**k: fn()
au.copy_to_clipboard=lambda t: None
au.safe_call=lambda fn,*a: fn(*a)
sys.modules["android_utils"]=au

# ---- load ----
loader=importlib.machinery.SourceFileLoader("hp", PLUGIN)
spec=importlib.util.spec_from_loader("hp", loader)
mod=importlib.util.module_from_spec(spec); loader.exec_module(mod)

check("version", mod.__version__, "3.5")
p=mod.HotlistPlugin(); p.on_plugin_load()
p._settings={"source":"0","days":"1","by":"0","top":"5","limit":"3000",
             "backend":"http://127.0.0.1:1"}

# ---- 假服务端：250 条消息，id 从 250 递减，date 每天一条 ----
NOW=int(time.time())
def fake_server():
    msgs=[]
    for i in range(2500, 2500-250, -1):   # 250 msgs, id 2500..2251
        m=SimpleNamespace(id=i, date=NOW-(2500-i)*3600, message="msg%d"%i,
                          forwards=(i%7), views=(i*13)%5000)
        if i%5==0:
            m.reactions=SimpleNamespace(results=[SimpleNamespace(count=i%50, reaction=SimpleNamespace(emoticon="👍"))])
        if i%9==0:
            m.replies=SimpleNamespace(replies=i%20)
        msgs.append(m)
    return msgs  # newest first
SERVER=fake_server()
CALLS={"n":0}
def fake_page(peer, offset_id, limit, min_id=0):
    CALLS["n"]+=1
    # newest first, return msgs with id < offset_id (or from top)
    if offset_id:
        cand=[m for m in SERVER if m.id < offset_id]
    else:
        cand=[m for m in SERVER if (not min_id or m.id > min_id)]
    return cand[:limit]
p._get_history_page=fake_page

# ---- 1) 首次扫描 ----
rows, meta = p._direct_cached(-100123, "0", 150, force=False)
check("首次扫描条数=150", len(rows), 150)
check("首次扫描有网络请求", CALLS["n"] > 0, True)
first_calls = CALLS["n"]
check("按日期降序", rows[0]["date_ts"] >= rows[-1]["date_ts"], True)
check("含链接", rows[0]["link"].startswith("https://t.me/mygrp/"), True)
check("含深链", rows[0]["deep"].startswith("tg://resolve?domain=mygrp"), True)
check("互动分非负", rows[0]["score"] >= 0, True)

# ---- 2) 再次读取（新鲜期内）应几乎不发请求 ----
CALLS["n"]=0
rows2, meta2 = p._direct_cached(-100123, "0", 150, force=False)
check("二次读取命中缓存(无新请求)", CALLS["n"], 0)
check("二次条数一致", len(rows2), len(rows))

# ---- 3) 强制刷新：只增量拉新，不应全量重扫 ----
CALLS["n"]=0
rows3, _ = p._direct_cached(-100123, "0", 150, force=True)
check("刷新只发少量请求", CALLS["n"] <= 2, True)

# ---- 4) 更大上限：只补拉更早，不全量重来 ----
CALLS["n"]=0
rows4, _ = p._direct_cached(-100123, "0", 200, force=False)
check("扩到200条", len(rows4), 200)
check("补拉页数不多于新增量", CALLS["n"] <= 3, True)

# ---- 5) 缩到最近1天：应裁掉老消息，且不发请求 ----
CALLS["n"]=0
rows5, _ = p._direct_cached(-100123, "1", 3000, force=False)
check("1天范围不重复请求", CALLS["n"], 0)
check("1天范围条数变少", len(rows5) < len(rows4), True)

# ---- 6) 进度提示 ----
record["bulletins"].clear()
p._last_prog=0
p._progress(-100123)
check("进度提示出现", len(record["bulletins"]) >= 1 and "扫描" in record["bulletins"][-1][1], True)

# ---- 7) 防重入：正在扫时再点，直接提示 ----
with p._busy_lock:
    p._busy.add(-100123)
record["bulletins"].clear(); record["alerts"].clear()
p._show(-100123, False)
check("重入被拦截(无新弹窗)", len(record["alerts"]), 0)
check("重入提示", any("正在扫描" in b[1] for b in record["bulletins"]), True)
with p._busy_lock:
    p._busy.discard(-100123)

# ---- 8) 网络失败 → 用离线缓存 ----
_ST["peer_raise"]=True
record["bulletins"].clear()
print("  (离线兜底测试)")
rows_off, meta_off = None, None
# 直接验证 _read_cache_only 能用
rows_c, m_c = p._read_cache_only(-100123, "0", 150)
check("离线缓存可读", len(rows_c) > 0, True)

# ---- 9) 弹窗渲染结构（用缓存数据）----
record["alerts"].clear()
p._settings={"source":"0","days":"0","by":"0","top":"5","limit":"3000","backend":"http://127.0.0.1:1"}
p._busy.clear()
# 让直连抛错 → 走缓存 → 渲染
def boom(*a, **k): raise RuntimeError("no native")
p._get_history_page = boom
p._direct_cached_orig = p._direct_cached
def direct_boom(*a, **k): raise RuntimeError("simulate offline")
p._direct_cached = direct_boom
p._show(-100123, False)
p._direct_cached = p._direct_cached_orig
check("离线也能出弹窗", len(record["alerts"]), 1)
if record["alerts"]:
    a=record["alerts"][0]
    check("items[0] 刷新", a.items[0].startswith("🔄"), True)
    check("items[3] 条数", "条数" in a.items[3], True)
    check("items[4] 分隔", a.items[4]=="─────────────", True)
    check("items[5] #1", a.items[5].startswith("#1"), True)
    check("消息含来源", "来源：" in a.message, True)

# ---- 10) Top 条数可切换 ----
record["alerts"].clear()
p._settings={"source":"0","days":"0","by":"0","top":"5","limit":"3000","backend":"http://127.0.0.1:1"}
p._busy.clear()
p._show(-100123, False)
cur=record["alerts"][0]
record["alerts"].clear()
cur.listener(cur, 3)          # 点“条数”
check("条数选择弹出", len(record["alerts"]), 1)
tp=record["alerts"][0]
check("档位 8 个", len(tp.items), 8)
check("含 Top 200", "Top 200" in tp.items, True)
record["alerts"].clear()
tp.listener(tp, 6)            # 选 Top 200
check("top 已保存=200", p._settings.get("top"), 200)
time.sleep(2)
check("切条数后重出榜", len(record["alerts"]), 1)

# ---- 11) top 上限 500 ----
p._settings={"source":"0","days":"1","by":"0","top":"9999","limit":"3000","backend":"http://127.0.0.1:1"}
s,d,b,t,l,be=p._state()
check("top 上限 500", t, 500)

# ---- 12) 每个群独立记忆时间范围 ----
p._settings={"source":"0","days":"5","by":"0","top":"5","limit":"3000","backend":"http://127.0.0.1:1"}
A=-100111; B=-100222
check("新群A按默认5播种", p._days_idx(A), 5)
p._set_days(A, 1)                      # A 改成最近3天
check("A 记住=1(3天)", p._days_idx(A), 1)
check("B 不受影响=5", p._days_idx(B), 5)
p._settings["days"]="0"                # 全局默认改成历史全部
check("改全局默认后 A 不变", p._days_idx(A), 1)
check("改全局默认后 B 仍5(已播种)", p._days_idx(B), 5)
C=-100333
check("新群C用新默认0", p._days_idx(C), 0)

# ---- 13) 相册(grouped_id)合并 ----
def mkrow(mid, text, react, rep, fwd, views, gid):
    return {"id":mid,"text":text,"reactions":react,"replies":rep,"forwards":fwd,
            "views":views,"grouped_id":gid,"detail":"👍×%d"%react if react else "",
            "author":"","link":"https://t.me/x/%d"%mid,"deep":"tg://resolve?domain=x&post=%d"%mid,
            "date":"01-01 00:00","date_ts":0,"score":0}
rows=[mkrow(100,"相册说明",9,2,500,90000,777),
      mkrow(101,"",0,0,499,90000,777),
      mkrow(102,"",0,0,498,90100,777),
      mkrow(103,"单条消息",1,0,10,500,None)]
merged,nalb=p._merge_albums(rows)
check("相册合并后条数=2", len(merged), 2)
check("合并相册计数=1", nalb, 1)
m_alb=[x for x in merged if x["grouped_id"]==777][0]
check("合并取最大转发", m_alb["forwards"], 500)
check("合并取最大浏览", m_alb["views"], 90100)
check("合并保留文字", m_alb["text"], "相册说明")
check("合并保留反应", m_alb["reactions"], 9)
check("单条不受影响", len([x for x in merged if x["grouped_id"] is None]), 1)

# ---- 14) 空时间范围：要能让用户当场换范围，而不是只弹个错误 ----
record["alerts"].clear()
p._render(-100999, [], {"group": "群X", "count": 0, "all_time": False, "oldest": ""},
          1, 0, 15, 3000, "直连")
check("空范围弹出选择框", len(record["alerts"]), 1)
if record["alerts"]:
    ea = record["alerts"][0]
    check("空范围标题提示", "没有消息" in (ea.title or ""), True)
    check("空范围可选时间范围", ea.items == mod.DAYS_LABELS, True)

print()
print("全部通过 ✔" if FAIL==0 else f"有 {FAIL} 项失败 ✘")
try: shutil.rmtree(TMP, ignore_errors=True)
except Exception: pass
sys.exit(1 if FAIL else 0)
