#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""雷神加速器管理面板（Docker Web 应用）。

无密码，局域网直连；所有操作走青龙 OpenAPI 与雷神官网接口。
- 展示当前是否处于暂停状态（直接问官网）
- 更新 Token（只确认写入，不验证有效性）
- 手动暂停 / 查官网最近时长日志
- 编辑定时暂停的 cron（支持工作日/休息日等预设）
- 查看本地执行记录

仅标准库依赖，镜像用 python:3.11-slim 即可，无需 pip。
"""

from __future__ import annotations

import json
import os
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from leigod_common import (  # noqa: E402
    Config,
    QinglongClient,
    QinglongError,
    Store,
    build_status,
    cron_presets,
    do_pause,
    fetch_logs,
    fmt_ts,
    get_token,
    parse_cron,
    query_pause_state,
    update_token,
)

PANEL_PORT = int(os.environ.get("LEIGOD_PANEL_PORT", "5788"))
PAUSE_TASK_NAME = os.environ.get("LEIGOD_PAUSE_TASK_NAME", "雷神定时暂停")


# --------------------------------------------------------------------------
# 业务
# --------------------------------------------------------------------------


def clients():
    cfg = Config()
    ql = QinglongClient(cfg.ql_base, cfg.ql_client_id, cfg.ql_client_secret, cfg.http_timeout)
    store = Store(cfg, ql)
    return cfg, ql, store


def _schedule_block(ql: QinglongClient) -> dict:
    try:
        cron = ql.find_cron(PAUSE_TASK_NAME)
    except QinglongError as exc:
        return {"ok": False, "error": str(exc)}
    if not cron:
        return {"ok": False, "error": f"未找到任务「{PAUSE_TASK_NAME}」"}
    expr = cron.get("schedule") or ""
    parsed = parse_cron(expr)
    return {
        "ok": True,
        "id": cron.get("id"),
        "name": cron.get("name"),
        "command": cron.get("command"),
        "cron": expr,
        "desc": parsed.get("desc") if parsed.get("ok") else parsed.get("error"),
        "presets": cron_presets(),
    }


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
        "pause_state": query_pause_state(cfg, ql),
        "schedule": _schedule_block(ql),
        "last_job_result": store.get_pause_state() or None,
        "last_token_update": last_of("token_update"),
        "last_log_query": last_of("logs_query"),
        "event_count": len(events),
        "errors": [e for e in events if e.get("result") == "失败"][-3:],
        "config": cfg.describe(),
        "status_text": build_status(cfg, ql, store),
    }


def history(limit: int = 20) -> dict:
    _cfg, _ql, store = clients()
    return {"rows": store.read_events()[-limit:][::-1]}


def run_pause() -> dict:
    cfg, ql, store = clients()
    ok, text = do_pause(cfg, ql, store, trigger="manual")
    if not ok:
        try:
            from leigod_common import qq_send

            qq_send(cfg, f"【雷神暂停失败（手动）】\n{text}", markdown=False)
        except Exception:  # noqa: BLE001
            pass
    return {"ok": ok, "text": text, "state": query_pause_state(cfg, ql)}


def run_logs(limit: int = 3) -> dict:
    cfg, ql, store = clients()
    ok, text = fetch_logs(cfg, ql, store, limit=limit)
    return {"ok": ok, "text": text}


def save_token(token: str) -> dict:
    cfg, ql, store = clients()
    ok, text = update_token(cfg, ql, store, token)
    return {"ok": ok, "text": text}


def set_schedule(expr: str) -> dict:
    expr = (expr or "").strip()
    parsed = parse_cron(expr)
    if not parsed.get("ok"):
        return {"ok": False, "text": f"定时规则无效：{parsed.get('error')}"}

    _cfg, ql, _store = clients()
    try:
        cron = ql.find_cron(PAUSE_TASK_NAME)
        if not cron:
            return {"ok": False, "text": f"未找到任务「{PAUSE_TASK_NAME}」"}
        ql.update_cron_schedule(cron["id"], expr)
    except QinglongError as exc:
        return {"ok": False, "text": f"保存失败：{exc}"}

    # 复核：重新读一遍，确认真的落库
    check = ql.find_cron(PAUSE_TASK_NAME) or {}
    saved = check.get("schedule")
    if saved != expr:
        return {"ok": False, "text": f"保存后复核不一致：写入 {expr}，实际 {saved}"}
    return {
        "ok": True,
        "text": f"定时规则已更新\ncron：{expr}\n含义：{parsed.get('desc')}",
        "cron": expr,
        "desc": parsed.get("desc"),
    }


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
.wrap{max-width:880px;margin:0 auto;padding:20px 16px 60px}
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
button.chip{padding:6px 12px;font-size:13px;background:transparent;border:1px solid var(--line);color:var(--fg)}
button.chip:hover{border-color:var(--accent);color:#dbeafe}
input{width:100%;padding:10px 12px;border-radius:8px;border:1px solid var(--line);background:#0b0d11;color:var(--fg);font-size:14px}
input.mono{font-family:ui-monospace,SFMono-Regular,Menlo,monospace}
pre{background:#0b0d11;border:1px solid var(--line);border-radius:8px;padding:12px;overflow:auto;font-size:12.5px;white-space:pre-wrap;word-break:break-all;margin:0}
.tag{display:inline-block;padding:2px 9px;border-radius:999px;font-size:12px}
.tag.ok{background:rgba(34,197,94,.15);color:var(--ok)}
.tag.err{background:rgba(239,68,68,.15);color:var(--err)}
.tag.warn{background:rgba(245,158,11,.15);color:var(--warn)}
.tag.dim{background:rgba(139,147,163,.15);color:var(--dim)}
.muted{color:var(--dim);font-size:12px}
.big{font-size:22px;font-weight:600;letter-spacing:.5px}
.state{display:flex;gap:14px;align-items:center;flex-wrap:wrap}
.dot{width:12px;height:12px;border-radius:50%;display:inline-block}
.dot.paused{background:var(--warn);box-shadow:0 0 12px rgba(245,158,11,.6)}
.dot.running{background:var(--ok);box-shadow:0 0 12px rgba(34,197,94,.6)}
.dot.unknown{background:var(--dim)}
#toast{position:fixed;left:50%;transform:translateX(-50%);bottom:24px;background:#1f2430;border:1px solid var(--line);padding:10px 16px;border-radius:8px;display:none;max-width:80vw;font-size:13px;box-shadow:0 6px 24px rgba(0,0,0,.4)}
.hidden{display:none}
</style>
</head>
<body>
<div class="wrap">
  <h1>雷神加速器管理器</h1>
  <div class="sub" id="now">加载中…</div>

  <div class="card">
    <h2>当前暂停状态</h2>
    <div class="state">
      <span class="dot unknown" id="stateDot"></span>
      <span class="big" id="stateText">查询中…</span>
      <span class="tag dim" id="stateTime"></span>
    </div>
    <div class="muted" id="stateReason" style="margin-top:8px"></div>
    <div class="kv" id="stateExtra" style="margin-top:10px"></div>
  </div>

  <div class="card">
    <h2>定时暂停</h2>
    <div class="kv" style="margin-bottom:12px">
      <div>当前规则</div><div><code id="cronNow">-</code> <span class="muted" id="cronDesc"></span></div>
      <div>任务</div><div class="muted" id="cronTask">-</div>
    </div>
    <div class="row" style="margin-bottom:10px">
      <input id="cronInput" class="mono" placeholder="分 时 日 月 周，例如 0 3 * * 1-5" autocomplete="off" spellcheck="false">
      <button id="btnCron">保存规则</button>
    </div>
    <div class="row" id="presets"></div>
    <div class="muted" style="margin-top:10px">星期：0/7=周日，1-5=工作日，6=周六。支持 <code>*/N</code>、<code>a-b</code>、<code>a,b</code>。</div>
    <pre id="cronOut" class="hidden" style="margin-top:12px"></pre>
  </div>

  <div class="card">
    <h2>更新 Token</h2>
    <div class="row" style="margin-bottom:10px">
      <input id="tokenInput" type="password" placeholder="粘贴 account_token（不会显示明文）" autocomplete="off">
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
      <button id="btnRefresh" class="ghost">刷新状态</button>
    </div>
    <pre id="actionOut" class="hidden" style="margin-top:12px"></pre>
  </div>

  <div class="card">
    <h2>概览</h2>
    <div class="kv" id="overview"></div>
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
function esc(s){ return String(s==null?'':s).replace(/[&<>]/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c])); }
async function api(path, opts){
  const res = await fetch(path, Object.assign({}, opts||{}));
  const data = await res.json().catch(()=>({}));
  return data;
}
async function post(path, body){
  return api(path, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body||{})});
}

const STATE_MAP = {
  paused:  {text:'已暂停（时长停止消耗）', cls:'paused',  tag:'warn'},
  running: {text:'未暂停（时长正在消耗）', cls:'running', tag:'ok'},
  unknown: {text:'未知',                    cls:'unknown', tag:'dim'},
};

function renderState(ps){
  ps = ps || {state:'unknown'};
  const meta = STATE_MAP[ps.state] || STATE_MAP.unknown;
  $('stateDot').className = 'dot ' + meta.cls;
  $('stateText').textContent = meta.text;
  $('stateTime').textContent = ps.checked_at ? ('查询于 ' + ps.checked_at) : '';
  $('stateReason').textContent = ps.reason ? ('原因：' + ps.reason) : '';
  const extra = ps.extra || {};
  const rows = [];
  if (ps.pause_status_id !== undefined) rows.push(['pause_status_id', ps.pause_status_id]);
  for (const [k,v] of Object.entries(extra)) rows.push([k, String(v)]);
  $('stateExtra').innerHTML = rows.map(([k,v])=>`<div>${esc(k)}</div><div>${esc(v)}</div>`).join('');
}

function renderSchedule(sc){
  sc = sc || {};
  if (!sc.ok) {
    $('cronNow').textContent = '-';
    $('cronDesc').textContent = sc.error || '读取失败';
    $('cronTask').textContent = '未找到任务';
    return;
  }
  $('cronNow').textContent = sc.cron;
  $('cronDesc').textContent = sc.desc || '';
  $('cronTask').textContent = `#${sc.id} ${sc.name} · ${sc.command}`;
  if (!$('cronInput').value) $('cronInput').value = sc.cron;
  const box = $('presets');
  if (box.dataset.done) return;
  box.dataset.done = '1';
  (sc.presets||[]).forEach(p => {
    const b = document.createElement('button');
    b.className = 'chip'; b.textContent = p.label + '  ' + p.cron;
    b.onclick = () => { $('cronInput').value = p.cron; };
    box.appendChild(b);
  });
}

async function loadSummary(){
  const d = await api('/api/summary');
  $('now').textContent = '当前时间 ' + (d.now||'') + ' · 时区 ' + ((d.config||{})['时区']||'');
  renderState(d.pause_state);
  renderSchedule(d.schedule);

  const token = d.token||{};
  const lu = d.last_token_update;
  const lj = d.last_job_result;
  const ll = d.last_log_query;
  const rows = [
    ['Token', token.configured ? '<span class="tag ok">已配置</span> 长度 ' + token.length : '<span class="tag err">未配置</span>'],
    ['Token 变量', esc(d.token_env)],
    ['最近更新', lu ? esc(lu.time) + ' · ' + esc(lu.result) : '<span class="tag dim">无记录</span>'],
    ['最近定时任务', lj ? esc(lj.time) + ' · ' + esc(lj.result) : '<span class="tag dim">无记录</span>'],
    ['最近日志查询', ll ? esc(ll.time) + ' · ' + esc(ll.result) : '<span class="tag dim">无记录</span>'],
    ['事件条数', d.event_count],
  ];
  if (d.errors && d.errors.length) rows.push(['最近错误', d.errors.map(e=>esc(e.time+' '+e.detail)).join('<br>')]);
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

$('btnCron').onclick = async () => {
  const cron = $('cronInput').value.trim();
  if (!cron) { toast('请输入 cron 表达式'); return; }
  $('btnCron').disabled = true;
  try {
    const d = await post('/api/schedule', {cron});
    $('cronOut').classList.remove('hidden');
    $('cronOut').textContent = d.text || '';
    toast(d.ok ? '定时规则已保存' : '保存失败');
    if (d.ok) await loadSummary();
  } finally { $('btnCron').disabled = false; }
};

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
    if (d.state) renderState(d.state);
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
    await loadHistory();
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


# --------------------------------------------------------------------------
# HTTP
# --------------------------------------------------------------------------


class Handler(BaseHTTPRequestHandler):
    server_version = "LeigodPanel/1.1"

    def log_message(self, fmt, *args):
        print(f"[{self.log_date_time_string()}] {fmt % args}", flush=True)

    def _send(self, code: int, body: bytes, ctype: str):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, data, code: int = 200):
        self._send(code, json.dumps(data, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except Exception:  # noqa: BLE001
            return {}

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path, query = parsed.path, urllib.parse.parse_qs(parsed.query)
        try:
            if path == "/healthz":
                self._json({"ok": True, "time": fmt_ts(Config())})
            elif path in ("/", "/index.html"):
                self._send(200, PAGE.encode("utf-8"), "text/html; charset=utf-8")
            elif path == "/api/summary":
                self._json(summary())
            elif path == "/api/schedule":
                _cfg, ql, _store = clients()
                self._json(_schedule_block(ql))
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
        try:
            if path == "/api/token":
                self._json(save_token(str(body.get("token") or "")))
            elif path == "/api/pause":
                self._json(run_pause())
            elif path == "/api/schedule":
                self._json(set_schedule(str(body.get("cron") or "")))
            else:
                self._json({"error": "not found"}, 404)
        except Exception as exc:  # noqa: BLE001
            self._json({"ok": False, "error": str(exc)}, 500)


def main() -> int:
    cfg = Config()
    server = ThreadingHTTPServer(("0.0.0.0", PANEL_PORT), Handler)
    print(f"雷神管理器面板已启动 http://0.0.0.0:{PANEL_PORT}", flush=True)
    print(f"青龙地址 {cfg.ql_base} · Token 变量 {cfg.token_env} · 时区 {cfg.tz_name}", flush=True)
    print(f"暂停任务名 {PAUSE_TASK_NAME}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
