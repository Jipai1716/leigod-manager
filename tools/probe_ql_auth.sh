#!/bin/bash
PW="${NAS_SUDO_PW:?需要设置 NAS_SUDO_PW}"
S() { echo "$PW" | sudo -S -p '' "$@" 2>/dev/null; }

cat > /tmp/ql_auth_test.py <<'PY'
import json, sqlite3, urllib.request, urllib.error

db = sqlite3.connect("/ql/data/db/database.sqlite")
name, cid, secret = db.execute("select name, client_id, client_secret from Apps limit 1").fetchone()
print("app:", name, "client_id:", cid, "secret_len:", len(secret or ""))

body = json.dumps({"appKey": cid, "appSecret": secret}).encode()
for path in ["/open/auth/token", "/api/open/auth/token"]:
    url = "http://127.0.0.1:5700" + path
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            data = r.read().decode()
            print(path, "->", r.status, data[:200])
    except urllib.error.HTTPError as e:
        print(path, "->", e.code, e.read().decode()[:200])
    except Exception as e:
        print(path, "-> ERR", e)
PY
S docker cp /tmp/ql_auth_test.py qinglong:/tmp/ >/dev/null
S docker exec qinglong python3 /tmp/ql_auth_test.py
echo
echo "=== config whitelist context ==="
S docker exec qinglong sh -c 'sed -n "165,195p" /ql/back/config/index.ts'
