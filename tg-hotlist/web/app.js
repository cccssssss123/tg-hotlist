/* tg-hotlist 本地网页版 前端逻辑（原生 JS，无依赖） */
'use strict';

const $ = (s) => document.querySelector(s);
const $$ = (s) => Array.from(document.querySelectorAll(s));

const state = {
  loggedIn: false,
  chats: [],
  selected: null,      // {id, title, type, members, username}
  data: null,
  tab: 'rank',
  qrTimer: null,
  busy: false,
  openMode: 'browser',
};

/* ---------------- 工具 ---------------- */
function esc(s) {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}
function fmt(n) {
  n = Number(n || 0);
  return n >= 10000 ? (n / 10000).toFixed(1) + 'w' : String(n);
}
function showErr(sel, msg) {
  const el = $(sel);
  if (!msg) { el.classList.add('hidden'); el.textContent = ''; return; }
  el.textContent = msg;
  el.classList.remove('hidden');
}
async function api(path, opts) {
  let r;
  try {
    r = await fetch(path, opts);
  } catch (e) {
    // fetch 直接抛错 = 后端服务根本没启动（最常见原因）
    const err = new Error('BACKEND_DOWN');
    err.backendDown = true;
    throw err;
  }
  if (!r.ok) throw new Error('HTTP ' + r.status);
  return r.json();
}
async function post(path, body) {
  return api(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body || {}),
  });
}

/* ---------------- 启动 ---------------- */
async function init() {
  try {
    const st = await api('/api/state');
    if (st.ok && st.logged_in) enterApp(st);
    else showLogin(st);
  } catch (e) {
    showLogin({});
    if (e.backendDown) {
      showErr('#loginErr',
        '连不上本地服务 —— 后端没有启动。\n'
        + '请先回到项目文件夹，双击 run_web.bat，\n'
        + '等黑色窗口出现「按 Ctrl+C 停止」后，再刷新本页面。\n'
        + '（关掉那个黑窗口 = 服务停止；每次要用都要先双击它。）');
    } else {
      showErr('#loginErr', '无法连接本地服务：' + e.message);
    }
  }
}

function showLogin(st) {
  state.loggedIn = false;
  state.openMode = (st && st.open_mode) || 'browser';
  $('#login').classList.remove('hidden');
  $('#app').classList.add('hidden');
  if (st && st.proxy) $('#qrUrlHint').textContent = '当前代理 ' + st.proxy;
  if (st && st.last_error) showErr('#loginErr', st.last_error);
  startQr();
}

function enterApp(st) {
  state.loggedIn = true;
  state.openMode = (st && st.open_mode) || 'browser';
  stopQrPoll();
  $('#login').classList.add('hidden');
  $('#app').classList.remove('hidden');
  const u = st.user || {};
  $('#userChip').textContent = (u.name || '已登录') + (u.id ? ' · ' + u.id : '');
  loadChats();
}

/* ---------------- 扫码登录 ---------------- */
async function startQr() {
  $('#qrMsg').className = 'qr-msg';
  $('#qrMsg').textContent = '正在生成二维码…';
  $('#qrBox').innerHTML = '<div class="qr-placeholder">生成中…</div>';
  showErr('#loginErr', '');
  try {
    const r = await post('/api/login/qr/start', {});
    if (!r.ok) throw new Error(r.error || '生成二维码失败');
    $('#qrBox').innerHTML = r.svg;
    $('#qrMsg').textContent = '请用手机 Telegram 扫码（设置 → 设备 → 连接桌面设备）';
    $('#qrUrlHint').textContent = r.url ? '令牌链接：' + r.url.slice(0, 42) + '…' : '';
    stopQrPoll();
    state.qrTimer = setInterval(pollQr, 1500);
  } catch (e) {
    $('#qrMsg').className = 'qr-msg bad';
    $('#qrMsg').textContent = '二维码生成失败：' + e.message;
    $('#qrBox').innerHTML = '<div class="qr-placeholder">点击「刷新二维码」重试</div>';
  }
}

function stopQrPoll() {
  if (state.qrTimer) { clearInterval(state.qrTimer); state.qrTimer = null; }
}

async function pollQr() {
  if (state.loggedIn) return stopQrPoll();
  try {
    const r = await api('/api/login/qr/status');
    if (!r.ok) return;
    if (r.status === 'success') {
      stopQrPoll();
      $('#qrMsg').className = 'qr-msg ok';
      $('#qrMsg').textContent = '登录成功，正在进入…';
      const st = await api('/api/state');
      setTimeout(() => enterApp(st), 400);
    } else if (r.status === 'expired' || r.status === 'error') {
      stopQrPoll();
      $('#qrMsg').className = 'qr-msg bad';
      $('#qrMsg').textContent = r.status === 'expired'
        ? '二维码已过期，请点「刷新二维码」重新生成'
        : '登录出错：' + (r.error || '未知错误');
    }
  } catch (e) { /* 忽略轮询时的瞬时错误 */ }
}

/* ---------------- tdata 导入 ---------------- */
async function doTdata() {
  const path = $('#tdataPath').value.trim();
  const passcode = $('#tdataPass').value;
  if (!path) { showErr('#loginErr', '请填写 tdata 目录路径'); return; }
  $('#btnTdata').disabled = true;
  $('#tdataLog').classList.remove('hidden');
  $('#tdataLog').textContent = '正在导入，可能需要十几秒…';
  showErr('#loginErr', '');
  try {
    const r = await post('/api/login/tdata', { path, passcode });
    if (!r.ok) throw new Error(r.error || '导入失败');
    $('#tdataLog').textContent = r.log || '导入成功';
    stopQrPoll();
    setTimeout(() => enterApp(r), 300);
  } catch (e) {
    showErr('#loginErr', e.message);
  } finally {
    $('#btnTdata').disabled = false;
  }
}

/* ---------------- 群列表 ---------------- */
async function loadChats() {
  $('#chatList').innerHTML = '<div class="muted pad">加载群列表…</div>';
  try {
    const r = await api('/api/chats');
    if (!r.ok) throw new Error(r.error || '加载失败');
    state.chats = r.chats || [];
    renderChats('');
    $('#chatCount').textContent = '共 ' + state.chats.length + ' 个群组 / 频道';
  } catch (e) {
    $('#chatList').innerHTML = '<div class="muted pad">加载失败：' + esc(e.message) + '</div>';
  }
}

function renderChats(filter) {
  const f = (filter || '').trim().toLowerCase();
  const list = state.chats.filter(c =>
    !f || c.title.toLowerCase().includes(f) || c.username.toLowerCase().includes(f) || c.id.includes(f)
  );
  if (!list.length) {
    $('#chatList').innerHTML = '<div class="muted pad">没有匹配的群组</div>';
    return;
  }
  $('#chatList').innerHTML = list.map(c => {
    const active = state.selected && state.selected.id === c.id ? ' active' : '';
    const kind = c.type === '频道' ? '<span class="k channel">频道</span>' : '<span class="k">群组</span>';
    return `<button class="chat-item${active}" data-id="${esc(c.id)}">
      <div class="chat-title">${esc(c.title)}</div>
      <div class="chat-sub">${kind}${esc(c.username || c.id)} · ${fmt(c.members)} 人</div>
    </button>`;
  }).join('');
  $$('#chatList .chat-item').forEach(el => {
    el.addEventListener('click', () => selectChat(el.dataset.id));
  });
}

function selectChat(id) {
  const c = state.chats.find(x => x.id === id);
  if (!c) return;
  state.selected = c;
  renderChats($('#chatSearch').value);
  $('#metaBar').textContent = c.title + ' · ' + c.type;
  loadData(false);
}

/* ---------------- 数据 ---------------- */
function params() {
  return {
    group: state.selected ? state.selected.id : '',
    days: $('#days').value,
    by: $('#by').value,
    top: $('#topN').value,
    limit: $('#limitN').value,
  };
}

async function loadData(force) {
  if (!state.selected || state.busy) return;
  const isAll = $('#days').value === '0';
  state.busy = true;
  $('#loading').classList.remove('hidden');
  showErr('#err', '');
  $('#warn').classList.add('hidden');
  // 全历史扫描较久，先给个明确提示（加载中一直显示）
  if (isAll) {
    $('#warn').textContent = '⏳ 历史全部：最多扫描 ' + $('#limitN').value +
      ' 条消息，可能需要几分钟，请勿关闭页面。';
    $('#warn').classList.remove('hidden');
    $('#loading').textContent = '正在扫描全部历史消息，请耐心等待…';
  } else {
    $('#loading').textContent = '正在从 Telegram 拉取消息，请稍候…';
  }
  $('#btnLoad').disabled = true;
  const q = new URLSearchParams({ ...params(), force: force ? '1' : '0' });
  try {
    const r = await api('/api/data?' + q.toString());
    if (!r.ok) throw new Error(r.error || '加载失败');
    state.data = r;
    renderMeta(r.meta);
    renderRank(r.rank);
    renderFeed(r.feed);
    if (r.meta.truncated) {
      $('#warn').textContent = '⚠ 消息数达到扫描上限 ' + r.meta.limit +
        '，更早的消息没有统计。可调大「扫描上限」后强制刷新。';
      $('#warn').classList.remove('hidden');
    } else if (isAll) {
      $('#warn').textContent = '✓ 已扫描全部历史' +
        (r.meta.oldest ? '（最早到 ' + r.meta.oldest + '）' : '') +
        '，共 ' + r.meta.count + ' 条。';
      $('#warn').classList.remove('hidden');
    } else {
      $('#warn').classList.add('hidden');
    }
  } catch (e) {
    if (e.backendDown) {
      showErr('#err', '本地服务已停止。请双击 run_web.bat 重新启动，然后刷新本页面。');
    } else {
      showErr('#err', e.message);
    }
  } finally {
    state.busy = false;
    $('#loading').classList.add('hidden');
    $('#btnLoad').disabled = false;
  }
}

function renderMeta(m) {
  const range = m.all_time
    ? ('全部历史' + (m.oldest ? '（最早 ' + m.oldest + '）' : ''))
    : (m.start + ' ~ ' + m.end);
  $('#metaBar').textContent =
    `${m.group} · ${m.by_label} Top ${m.top_n} · 扫描 ${m.count} 条 · ${range}`;
  $('#fetchInfo').textContent = '数据抓取于 ' + m.fetched_at;
}

function statChips(x, withScore) {
  let s = '';
  if (withScore) s += `<span class="b score">⭐ ${fmt(x.score)}</span>`;
  s += `<span class="b hot">👍 ${fmt(x.reactions)}</span>`;
  if (x.replies) s += `<span class="b">💬 ${fmt(x.replies)}</span>`;
  if (x.forwards) s += `<span class="b">↗ ${fmt(x.forwards)}</span>`;
  if (x.views) s += `<span class="b">👁 ${fmt(x.views)}</span>`;
  return s;
}

function textBlock(x, id) {
  const body = (x.text || '').trim() || (x.media || '[消息]');
  const long = body.length > 160 || body.includes('\n');
  return `<div class="text${long ? ' clamp' : ''}" id="${id}">${esc(body)}</div>` +
    (long ? `<button class="expand" data-target="${id}">展开全文 ▾</button>` : '');
}

function foot(x, extra) {
  const open = x.deep
    ? `<a class="linkbtn" href="${esc(x.deep)}" data-deep="${esc(x.deep)}">在客户端打开 ↗</a>`
    : '';
  const web = x.link
    ? `<a href="${esc(x.link)}" target="_blank" rel="noopener">网页 ↗</a>`
    : '';
  return `<div class="foot">${esc(x.date || '')}${extra || ''} · 消息 #${esc(x.id)}${open}${web}</div>`;
}

function bindOpen(scope) {
  $$(scope + ' .linkbtn').forEach(a => {
    a.addEventListener('click', async (ev) => {
      // browser 模式：不拦截，让浏览器直接处理 tg:// 链接
      // （首次会弹一次"打开 AyuGram？"，勾选"始终允许"后即为一点直达）
      if (state.openMode !== 'backend') return;
      ev.preventDefault();
      const label = '在客户端打开 ↗';
      a.textContent = '正在打开…';
      try {
        const r = await api('/api/open?url=' + encodeURIComponent(a.dataset.deep));
        if (!r.ok) throw new Error(r.error || '打开失败');
        a.textContent = '已打开 ✓';
      } catch (e) {
        // 后端静默唤起失败 → 退回浏览器直接打开 tg://
        showErr('#err', '已改用浏览器方式打开客户端。首次会弹一次确认框，'
          + '勾选「始终允许」后即为一点直达。');
        window.location.href = a.dataset.deep;
      }
      setTimeout(() => { a.textContent = label; }, 1600);
    });
  });
}

function bindExpand(scope) {
  $$(scope + ' .expand').forEach(btn => {
    btn.addEventListener('click', () => {
      const el = document.getElementById(btn.dataset.target);
      if (!el) return;
      const open = el.classList.toggle('open');
      el.classList.toggle('clamp', !open);
      btn.textContent = open ? '收起 ▴' : '展开全文 ▾';
    });
  });
}

function renderRank(items) {
  const p = $('#panelRank');
  if (!items || !items.length) {
    p.innerHTML = '<div class="empty">这个时间范围内没有消息，或都未达到排序门槛。</div>';
    return;
  }
  p.innerHTML = items.map(x => `
    <div class="card">
      <div class="rank">${x.rank}</div>
      <div class="card-body">
        <div class="stats">${statChips(x, true)}</div>
        ${x.reaction_detail ? `<div class="foot" style="margin:0 0 6px">${esc(x.reaction_detail)}</div>` : ''}
        ${textBlock(x, 't' + x.id)}
        ${foot(x, ' · ' + esc(x.author))}
      </div>
    </div>`).join('');
  bindExpand('#panelRank');
  bindOpen('#panelRank');
}

function renderFeed(items) {
  const p = $('#panelFeed');
  if (!items || !items.length) {
    p.innerHTML = '<div class="empty">没有消息。</div>';
    return;
  }
  p.innerHTML = items.map(x => `
    <div class="card">
      <div class="feed-dot"></div>
      <div class="card-body">
        <div class="stats">${statChips(x, false)}</div>
        ${textBlock(x, 'f' + x.id)}
        ${foot(x)}
      </div>
    </div>`).join('');
  bindExpand('#panelFeed');
  bindOpen('#panelFeed');
}

/* ---------------- 导出 ---------------- */
async function doExport(fmtType) {
  if (!state.data) { showErr('#err', '请先加载一个群组'); return; }
  const q = new URLSearchParams({ ...params(), format: fmtType });
  try {
    const r = await fetch('/api/export?' + q.toString());
    if (!r.ok) throw new Error('HTTP ' + r.status);
    const blob = await r.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'hotlist.' + fmtType;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  } catch (e) {
    showErr('#err', '导出失败：' + e.message);
  }
}

/* ---------------- 事件绑定 ---------------- */
$('#btnQrRefresh').addEventListener('click', startQr);
$('#btnTdata').addEventListener('click', doTdata);
$('#tdataPath').addEventListener('keydown', e => { if (e.key === 'Enter') doTdata(); });

$('#btnLogout').addEventListener('click', async () => {
  if (!confirm('退出只会删除本机保存的登录会话，不会影响 AyuGram / 手机上的登录。确定退出？')) return;
  const r = await post('/api/logout', {});
  if (r.ok) { location.reload(); }
  else showErr('#err', r.error || '退出失败');
});

$('#chatSearch').addEventListener('input', e => renderChats(e.target.value));
$('#btnLoad').addEventListener('click', () => loadData(false));
$('#btnForce').addEventListener('click', () => loadData(true));
$('#btnMd').addEventListener('click', () => doExport('md'));
$('#btnHtml').addEventListener('click', () => doExport('html'));

$$('.tab').forEach(tab => {
  tab.addEventListener('click', () => {
    state.tab = tab.dataset.tab;
    $$('.tab').forEach(t => t.classList.toggle('active', t === tab));
    $('#panelRank').classList.toggle('hidden', state.tab !== 'rank');
    $('#panelFeed').classList.toggle('hidden', state.tab !== 'feed');
  });
});

// 选「最近 1 年」或「历史全部」时自动把扫描上限提到 5 万。
// 有时间下界的范围（1/2/3/7/30/365 天）遇到下界就停，设大上限不会变慢，
// 反而能避免默认 5000 条把一年/全历史截断。用户仍可手动调。
$('#days').addEventListener('change', () => {
  const v = $('#days').value;
  const wide = v === '0' || v === '365';
  if (wide && Number($('#limitN').value) < 50000) $('#limitN').value = 50000;
  else if (!wide && Number($('#limitN').value) > 50000) $('#limitN').value = 5000;
  if (state.selected) loadData(false);
});

['#by', '#topN', '#limitN'].forEach(sel => {
  $(sel).addEventListener('change', () => { if (state.selected) loadData(false); });
});

init();
