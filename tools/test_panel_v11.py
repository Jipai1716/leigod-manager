#!/usr/bin/env python3
"""面板 v1.1 自测：无密码访问、暂停状态、定时规则增改、无效规则拒绝、官网日志。"""
import json
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:5788"


def call(method, path, body=None):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(BASE + path, data=data, method=method)
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


fails = 0


def check(label, ok, extra=""):
    global fails
    if not ok:
        fails += 1
    print(f"[{'OK  ' if ok else 'FAIL'}] {label}{(' · ' + extra) if extra else ''}")


# 1) 无密码直接访问
code, body = call("GET", "/api/summary")
data = json.loads(body) if code == 200 else {}
check("无需登录访问 /api/summary", code == 200, f"code={code}")

# 2) 暂停状态展示
ps = data.get("pause_state") or {}
check("返回暂停状态", ps.get("state") in ("paused", "running", "unknown"),
      f"state={ps.get('state')} pid={ps.get('pause_status_id')}")
print("       extra:", json.dumps(ps.get("extra") or {}, ensure_ascii=False))

# 3) 定时规则读取
sc = data.get("schedule") or {}
check("读取当前 cron", bool(sc.get("cron")), f"{sc.get('cron')} | {sc.get('desc')}")

# 4) 无效 cron 应被拒
code, body = call("POST", "/api/schedule", {"cron": "0 99 * * *"})
d = json.loads(body)
check("非法 cron 被拒绝", d.get("ok") is False, (d.get("text") or "")[:60])

code, body = call("POST", "/api/schedule", {"cron": "0 3 * *"})
d = json.loads(body)
check("段数不足被拒绝", d.get("ok") is False, (d.get("text") or "")[:60])

code, body = call("POST", "/api/schedule", {"cron": "0 3 * * ?"})
d = json.loads(body)
check("问号被拒绝", d.get("ok") is False, (d.get("text") or "")[:60])

# 5) 工作日规则
code, body = call("POST", "/api/schedule", {"cron": "0 3 * * 1-5"})
d = json.loads(body)
check("保存工作日规则", d.get("ok") is True, d.get("text", "").replace("\n", " | ")[:80])

code, body = call("GET", "/api/schedule")
sc = json.loads(body)
check("复核规则已落库", sc.get("cron") == "0 3 * * 1-5", f"cron={sc.get('cron')} desc={sc.get('desc')}")

# 6) 恢复默认
code, body = call("POST", "/api/schedule", {"cron": "0 */6 * * *"})
d = json.loads(body)
check("恢复默认规则", d.get("ok") is True, d.get("text", "").replace("\n", " | ")[:60])

# 7) 官网日志（真实 Token）
code, body = call("GET", "/api/logs?n=3")
d = json.loads(body)
text = d.get("text") or ""
check("官网时长日志查询", code == 200 and bool(text), text.replace("\n", " | ")[:220])

# 8) 历史
code, body = call("GET", "/api/history?n=5")
check("历史记录", code == 200 and isinstance(json.loads(body).get("rows"), list),
      f"rows={len(json.loads(body).get('rows') or [])}")

print(f"\n{'全部通过' if fails == 0 else str(fails) + ' 项失败'}")
