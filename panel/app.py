#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""雷神加速器管理面板（Docker Web 应用）。

替代原来的 QQ 固定指令入口：所有操作改在网页上完成。
数据仍然存放在青龙：Token 在环境变量、事件在 LEIGOD_CMDLOG、暂停结果在 LEIGOD_PAUSE_STATE。
定时暂停仍由青龙任务执行，本面板只是控制台。

仅标准库依赖，镜像用 python:3.11-slim 即可，无需 pip。
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys
import time
import urllib.parse
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from leigod_common import (  # noqa: E402
    Config,
    QinglongClient,
    QinglongError,
    Store,
    build_status,
    do_pause,
    fetch_logs,
    fmt_ts,
    get_token,
    now,
    update_token,
)

PANEL_PASSWORD = os.environ.get("LEIGOD_PANEL_PASSWORD", "")
PANEL_PORT = int(os.environ.get("LEIGOD_PANEL_PORT", "5788"))
SESSION_COOKIE = "lg_sid"
SESSION_TTL = 7 * 86400


# --------------------------------------------------------------------------
# 会话
# --------------------------------------------------------------------------


def _sign(ts: str) -> str:
    return hmac.new(PANEL_PASSWORD.encode("utf-8"), ts.encode("utf-8"), hashlib.sha256).hexdigest()


def make_session() -> str:
    ts = str(int(time.time()))
    return f"{ts}.{_sign(ts)}"


def session_ok(cookie_header: str | None) -> bool:
    if not cookie_header:
        return False
    try:
        jar = SimpleCookie()
        jar.load(cookie_header)
        raw = jar[SESSION_COOKIE].value
        ts, sig = raw.split(".", 1)
    except Exception:  # noqa: BLE001
        return False
    if not hmac.compare_digest(sig, _sign(ts)):
        return False
    try:
        return time.time() - int(ts) < SESSION_TTL
    except ValueError:
        return False


# --------------------------------------------------------------------------
# 业务
# --------------------------------------------------------------------------


def clients():
    cfg = Config()
    ql = QinglongClient(cfg.ql_base, cfg.ql_client_id, cfg.ql_client_secret, cfg.http_timeout)
    store = Store(cfg, ql)
    return cfg, ql, store


def summary() -> dict:
    cfg, ql, store = clients()
    events = store.read_events()

    def last_of(op):
        found = [e for e in events if e.get("op") == op]
        return found[-1] if found else None

    try:
        token = get_token(cfg, ql)
        token_info = {"configured": bool(token), "length": len(token or "")}
    except QinglongError as exc:
        token_info = {"configured": False, "length": 0, "error": str(exc)}

    return {
        "now": fmt_ts(cfg),
        "token": token_info,
        "token_env": cfg.token_env,
        "last_token_update": last_of("token_update"),
        "pause_state": store.get_pause_state() or None,
        "last_log_query": last_of("logs_query"),
        "event_count": len(events),
        "errors": [e for e in events if e.get("result") == "失败"][-3:],
        "config": cfg.describe(),
        "status_text": build_status(cfg, ql, store),
    }


def history(limit: int = 20) -> dict:
    _cfg, _ql, store = clients()
    events = store.read_events()
    return {"rows": events[-limit:][::-1]}


def run_pause() -> dict:
    cfg, ql, store = clients()
    ok, text = do_pause(cfg, ql, store, trigger="manual")
    if not ok:
        try:
            from leigod_common import qq_send

            qq_send(cfg, f"【雷神暂停失败（手动）】\n{text}", markdown=False)
        except Exception:  # noqa: BLE001
            pass
    return {"ok": ok, "text": text}


def run_logs(limit: int = 3) -> dict:
    cfg, ql, store = clients()
    ok, text = fetch_logs(cfg, ql, store, limit=limit)
    return {"ok": ok, "text": text}


def save_token(token: str) -> dict:
    cfg, ql, store = clients()
    ok, text = update_token(cfg, ql, store, token)
    return {"ok": ok, "text": text}


# --------------------------------------------------------------------------
# 页面
# --------------------------------------------------------------------------

PAGE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>雷神管理器</title>
<style>
:root{--bg:#0f1115;--card:#171a21;--line:#252a34;--fg:#e6e8ee;--dim:#8b93a3;--ok:#22c55e;--warn:#f59e0b;--err:#ef4444;--accent:#3b82f6}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif}
.wrap{max-width:860px;margin:0 auto;padding:20px 16px 60px}
h1{font-size:18px;margin:0 0 4px}
.sub{color:var(--dim);font-size:12px;margin-bottom:18px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:16px;margin-bottom:14px}
.card h2{font-size:13px;margin:0 0 12px;color:var(--dim);font-weight:600;letter-spacing:.4px;text-transform:uppercase}
.row{display:flex;flex-wrap:wrap;gap:10px;align-items:center}
.kv{display:grid;grid-template-columns:110px 1fr;gap:6px 10px;font-size:13px}
.kv div:nth-child(odd){color:var(--dim)}
button{background:var(--accent);color:#fff;border:0;border-radius:8px;padding:9px 16px;font-size:14px;cursor:pointer}
button:hover{filter:brightness(1.1)}
button:disabled{opacity:.5;cursor:not-allowed}
button.ghost{background:transparent;border:1px solid var(--line);color:var(--fg)}
button.warn{background:#b45309}
input{width:100%;padding:10px 12px;border-radius:8px;border:1px solid var(--line);background:#0b0d11;color:var(--fg);font-size:14px}
pre{background:#0b0d11;border:1px solid var(--line);border-radius:8px;padding:12px;overflow:auto;font-size:12.5px;white-space:pre-wrap;word-break:break-all;margin:0}
.tag{display:inline-block;padding:2px 8px;border-radius:999px;font-size:12px}
.tag.ok{background:rgba(34,197,94,.15);color:var(--ok)}
.tag.err{background:rgba(239,68,68,.15);color:var(--err)}
.tag.dim{background:rgba(139,147,163,.15);color:var(--dim)}
.muted{color:var(--dim);font-size:12px}
#toast{position:fixed;left:50%;transform:translateX(-50%);bottom:24px;background:#1f2430;border:1px solid var(--line);padding:10px 16px;border-radius:8px;display:none;max-width:80vw;font-size:13px;box-shadow:0 6px 24px rgba(0,0,0,.4)}
.hidden{display:none}
</style>
</head>
<body>
<div class="wrap">
  <h1>雷神加速器管理器</h1>
  <div class="sub" id="now">加载中…</div>

  <div class="card">
    <h2>概览</h2>
    <div class="kv" id="overview"></div>
  </div>

  <div class="card">
    <h2>更新 Token</h2>
    <div class="row" style="margin-bottom:10px">
      <input id="tokenInput" type="password" placeholder="粘贴从网上提取的 account_token（不会显示明文）" autocomplete="off">
    </div>
    <div class="row">
      <button id="btnSave">保存 Token</button>
      <span class="muted">只确认写入青龙，不验证 Token 有效性</span>
    </div>
    <pre id="tokenOut" class="hidden" style="margin-top:12px"></pre>
  </div>

  <div class="card">
    <h2>操作</h2>
    <div class="row">
      <button id="btnPause" class="warn">立即暂停</button>
      <button id="btnLogs" class="ghost">查官网时长日志</button>
      <button id="btnRefresh" class="ghost">刷新</button>
    </div>
    <pre id="actionOut" class="hidden" style="margin-top:12px"></pre>
  </div>

  <div class="card">
    <h2>最近执行记录</h2>
    <pre id="history">加载中…</pre>
  </div>

  <div class="card">
    <h2>状态详情</h2>
    <pre id="statusText" style="color:#aab">加载中…</pre>
  </div>
</div>
<div id="toast"></div>

<script>
const $ = (id) => document.getElementById(id);
function toast(msg, ms=3200){
  const t = $('toast'); t.textContent = msg; t.style.display='block';
  clearTimeout(window._tt); window._tt = setTimeout(()=>t.style.display='none', ms);
}
async function api(path, opts){
  const res = await fetch(path, Object.assign({credentials:'same-origin'}, opts||{}));
  if (res.status === 401) { location.reload(); throw new Error('未登录'); }
  const data = await res.json().catch(()=>({}));
  return data;
}
function esc(s){ return String(s==null?'':s).replace(/[&<>]/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c])); }

async function loadSummary(){
  const d = await api('/api/summary');
  $('now').textContent = '当前时间 ' + (d.now||'') + ' · 时区 ' + (d.config&&d.config['时区']||'');
  const token = d.token||{};
  const ps = d.pause_state;
  const lu = d.last_token_update;
  const ll = d.last_log_query;
  const rows = [
    ['Token', token.configured ? '<span class="tag ok">已配置</span> 长度 ' + token.length : '<span class="tag err">未配置</span>'],
    ['Token 变量', esc(d.token_env)],
    ['最近更新', lu ? esc(lu.time) + ' · ' + esc(lu.result) : '<span class="tag dim">无记录</span>'],
    ['最近暂停', ps ? esc(ps.time) + ' · ' + esc(ps.result) : '<span class="tag dim">无记录</span>'],
    ['最近日志查询', ll ? esc(ll.time) + ' · ' + esc(ll.result) : '<span class="tag dim">无记录</span>'],
    ['事件条数', d.event_count],
  ];
  if (d.errors && d.errors.length) {
    rows.push(['最近错误', d.errors.map(e=>esc(e.time+' '+e.detail)).join('<br>')]);
  }
  $('overview').innerHTML = rows.map(([k,v])=>`<div>${k}</div><div>${v}</div>`).join('');
  $('statusText').textContent = d.status_text || '';
}

async function loadHistory(){
  const d = await api('/api/history?n=20');
  const rows = d.rows||[];
  $('history').textContent = rows.length
    ? rows.map(r=>`${r.time} · ${r.op_label||r.op} · ${r.result}${r.detail?(' · '+r.detail):''}`).join('\\n')
    : '暂无记录';
}

async function post(path, body){
  return api(path, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body||{})});
}

$('btnSave').onclick = async () => {
  const tk = $('tokenInput').value.trim();
  if (!tk) { toast('请先粘贴 Token'); return; }
  $('btnSave').disabled = true;
  try {
    const d = await post('/api/token', {token: tk});
    $('tokenOut').classList.remove('hidden');
    $('tokenOut').textContent = d.text || '';
    toast(d.ok ? '已写入' : '写入失败');
    if (d.ok) $('tokenInput').value = '';
    await loadSummary(); await loadHistory();
  } finally { $('btnSave').disabled = false; }
};

$('btnPause').onclick = async () => {
  $('btnPause').disabled = true;
  $('actionOut').classList.remove('hidden');
  $('actionOut').textContent = '执行中…';
  try {
    const d = await post('/api/pause');
    $('actionOut').textContent = d.text || '';
    toast(d.ok ? '暂停成功' : '暂停失败，已推送 QQ');
    await loadSummary(); await loadHistory();
  } finally { $('btnPause').disabled = false; }
};

$('btnLogs').onclick = async () => {
  $('btnLogs').disabled = true;
  $('actionOut').classList.remove('hidden');
  $('actionOut').textContent = '查询中…';
  try {
    const d = await api('/api/logs?n=3');
    $('actionOut').textContent = d.text || '';
    await loadSummary(); await loadHistory();
  } finally { $('btnLogs').disabled = false; }
};

$('btnRefresh').onclick = () => { loadSummary(); loadHistory(); toast('已刷新'); };

loadSummary().catch(e=>toast('加载失败: '+e.message));
loadHistory().catch(()=>{});
setInterval(()=>{ loadSummary().catch(()=>{}); }, 60000);
</script>
</body>
</html>
"""

LOGIN = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>登录 · 雷神管理器</title>
<style>
body{margin:0;background:#0f1115;color:#e6e8ee;font:14px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
display:flex;align-items:center;justify-content:center;height:100vh}
form{background:#171a21;border:1px solid #252a34;border-radius:12px;padding:26px;width:min(340px,88vw)}
h1{font-size:16px;margin:0 0 18px;font-weight:600}
input{width:100%;padding:11px 12px;border-radius:8px;border:1px solid #252a34;background:#0b0d11;color:#e6e8ee;font-size:14px;margin-bottom:12px}
button{width:100%;background:#3b82f6;color:#fff;border:0;border-radius:8px;padding:11px;font-size:14px;cursor:pointer}
.err{color:#ef4444;font-size:13px;margin-bottom:10px;display:none}
</style></head><body>
<form id="f">
  <h1>雷神加速器管理器</h1>
  <div class="err" id="err">密码错误</div>
  <input id="pw" type="password" placeholder="访问密码" autocomplete="current-password" autofocus>
  <button type="submit">进入</button>
</form>
<script>
document.getElementById('f').onsubmit = async (e) => {
  e.preventDefault();
  const res = await fetch('/api/login', {method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({password: document.getElementById('pw').value})});
  if (res.ok) location.reload();
  else document.getElementById('err').style.display='block';
};
</script>
</body></html>
"""


# --------------------------------------------------------------------------
# HTTP
# --------------------------------------------------------------------------


class Handler(BaseHTTPRequestHandler):
    server_version = "LeigodPanel/1.0"

    def log_message(self, fmt, *args):  # 安静一点
        print(f"[{self.log_date_time_string()}] {fmt % args}", flush=True)

    # ---- 工具 ----
    def _send(self, code: int, body: bytes, ctype: str, extra: dict | None = None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, data, code: int = 200, extra: dict | None = None):
        self._send(code, json.dumps(data, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8", extra)

    def _html(self, text: str, code: int = 200, extra: dict | None = None):
        self._send(code, text.encode("utf-8"), "text/html; charset=utf-8", extra)

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except Exception:  # noqa: BLE001
            return {}

    def _authed(self) -> bool:
        return session_ok(self.headers.get("Cookie"))

    # ---- 路由 ----
    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)

        if path == "/healthz":
            self._json({"ok": True, "time": fmt_ts(Config())})
            return

        if not self._authed():
            if path.startswith("/api/"):
                self._json({"ok": False, "error": "未登录"}, 401)
            else:
                self._html(LOGIN)
            return

        try:
            if path in ("/", "/index.html"):
                self._html(PAGE)
            elif path == "/api/summary":
                self._json(summary())
            elif path == "/api/history":
                limit = int((query.get("n") or ["20"])[0])
                self._json(history(max(1, min(limit, 100))))
            elif path == "/api/logs":
                limit = int((query.get("n") or ["3"])[0])
                self._json(run_logs(max(1, min(limit, 10))))
            else:
                self._json({"error": "not found"}, 404)
        except Exception as exc:  # noqa: BLE001
            self._json({"ok": False, "error": str(exc)}, 500)

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        body = self._body()

        if path == "/api/login":
            if not PANEL_PASSWORD:
                self._json({"ok": False, "error": "服务端未设置 LEIGOD_PANEL_PASSWORD"}, 500)
                return
            if hmac.compare_digest(str(body.get("password") or ""), PANEL_PASSWORD):
                cookie = f"{SESSION_COOKIE}={make_session()}; Path=/; HttpOnly; SameSite=Lax; Max-Age={SESSION_TTL}"
                self._json({"ok": True}, 200, {"Set-Cookie": cookie})
            else:
                self._json({"ok": False, "error": "密码错误"}, 401)
            return

        if path == "/api/logout":
            self._json({"ok": True}, 200, {"Set-Cookie": f"{SESSION_COOKIE}=; Path=/; Max-Age=0"})
            return

        if not self._authed():
            self._json({"ok": False, "error": "未登录"}, 401)
            return

        try:
            if path == "/api/token":
                self._json(save_token(str(body.get("token") or "")))
            elif path == "/api/pause":
                self._json(run_pause())
            else:
                self._json({"error": "not found"}, 404)
        except Exception as exc:  # noqa: BLE001
            self._json({"ok": False, "error": str(exc)}, 500)


def main() -> int:
    if not PANEL_PASSWORD:
        print("错误：必须设置 LEIGOD_PANEL_PASSWORD 环境变量", file=sys.stderr)
        return 1
    cfg = Config()
    server = ThreadingHTTPServer(("0.0.0.0", PANEL_PORT), Handler)
    print(f"雷神管理器面板已启动 http://0.0.0.0:{PANEL_PORT}", flush=True)
    print(f"青龙地址 {cfg.ql_base} · Token 变量 {cfg.token_env} · 时区 {cfg.tz_name}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
