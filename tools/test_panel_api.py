#!/usr/bin/env python3
"""面板接口自测：登录、概览、写入 Token、清空 Token、日志查询、历史。"""
import json
import os
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:5788"
PW = os.environ["LEIGOD_PANEL_PASSWORD"]
cookie = ""


def call(method, path, body=None, use_cookie=True):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(BASE + path, data=data, method=method)
    if data:
        req.add_header("Content-Type", "application/json")
    if use_cookie and cookie:
        req.add_header("Cookie", cookie)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.read().decode(), r.headers.get("Set-Cookie", "")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(), e.headers.get("Set-Cookie", "")


def show(label, ok, extra=""):
    print(f"[{'OK  ' if ok else 'FAIL'}] {label}{(' · ' + extra) if extra else ''}")
    return ok


fails = 0

# 1) 未登录访问应被拦截
code, body, _ = call("GET", "/api/summary", use_cookie=False)
fails += 0 if code == 401 else 1
show("未登录访问 /api/summary -> 401", code == 401, f"code={code}")

# 2) 错误密码
code, body, _ = call("POST", "/api/login", {"password": "wrong"}, use_cookie=False)
fails += 0 if code == 401 else 1
show("错误密码 -> 401", code == 401, f"code={code}")

# 3) 正确密码
code, body, setcookie = call("POST", "/api/login", {"password": PW}, use_cookie=False)
cookie = (setcookie or "").split(";")[0]
ok = code == 200 and cookie.startswith("lg_sid=")
fails += 0 if ok else 1
show("正确密码登录", ok, f"code={code}")

# 4) 概览
code, body, _ = call("GET", "/api/summary")
data = json.loads(body) if code == 200 else {}
ok = code == 200 and "token" in data
fails += 0 if ok else 1
show("GET /api/summary", ok, f"token.configured={data.get('token', {}).get('configured')}")

# 5) 写入测试 Token
code, body, _ = call("POST", "/api/token", {"token": "TESTTOKEN_ABC123"})
data = json.loads(body)
ok = data.get("ok") is True and "有效性验证：未执行" in data.get("text", "")
fails += 0 if ok else 1
show("写入 Token 并声明未验证有效性", ok, data.get("text", "").replace("\n", " | ")[:80])

# 6) 概览应显示已配置
code, body, _ = call("GET", "/api/summary")
data = json.loads(body)
tok = data.get("token", {})
ok = tok.get("configured") is True and tok.get("length") == len("TESTTOKEN_ABC123")
fails += 0 if ok else 1
show("概览显示已配置且长度正确", ok, f"length={tok.get('length')}")

# 7) 空 Token 应被拒
code, body, _ = call("POST", "/api/token", {"token": "   "})
data = json.loads(body)
ok = data.get("ok") is False
fails += 0 if ok else 1
show("空 Token 被拒绝", ok, data.get("text", "").replace("\n", " ")[:60])

# 8) 日志查询（Token 是假的，应返回明确的失败信息而不是伪造数据）
code, body, _ = call("GET", "/api/logs?n=3")
data = json.loads(body)
ok = code == 200 and data.get("ok") is False and data.get("text")
fails += 0 if ok else 1
show("假 Token 查日志 -> 明确失败", ok, (data.get("text") or "").replace("\n", " ")[:90])

# 9) 历史
code, body, _ = call("GET", "/api/history?n=10")
data = json.loads(body)
ok = code == 200 and isinstance(data.get("rows"), list) and len(data["rows"]) > 0
fails += 0 if ok else 1
show("GET /api/history", ok, f"rows={len(data.get('rows') or [])}")

# 10) 首页
code, body, _ = call("GET", "/")
ok = code == 200 and "雷神加速器管理器" in body
fails += 0 if ok else 1
show("GET / 页面渲染", ok, f"len={len(body)}")

print(f"\n{'全部通过' if fails == 0 else str(fails) + ' 项失败'}")
