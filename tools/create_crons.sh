#!/bin/bash
PW="${NAS_SUDO_PW:?需要设置 NAS_SUDO_PW}"
S() { echo "$PW" | sudo -S -p '' "$@" 2>/dev/null; }

cat > /tmp/ql_create_crons.py <<'PY'
import json, sqlite3, sys, urllib.error, urllib.request
sys.path.insert(0, "/ql/data/scripts/leigod")
from leigod_common import QinglongClient

db = sqlite3.connect("/ql/data/db/database.sqlite")
cid, secret = db.execute(
    "select client_id, client_secret from Apps where name='system'"
).fetchone()
cli = QinglongClient("http://127.0.0.1:5700", cid, secret)

def post(path, body):
    token = cli._auth()
    req = urllib.request.Request(
        cli.base + path, data=json.dumps(body).encode(), method="POST"
    )
    req.add_header("Authorization", "Bearer " + token)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return {"http": e.code, "body": e.read().decode()[:300]}

existing = {c["name"] for c in ((cli._call("GET", "/open/crons").get("data") or {}).get("data") or [])}

tasks = [
    {
        "name": "雷神定时暂停",
        "command": "task leigod/leigod_pause.py",
        "schedule": "0 */6 * * *",
    },
    {
        "name": "雷神每日日报",
        "command": "task leigod/leigod_daily_report.py",
        "schedule": "59 23 * * *",
    },
]

for t in tasks:
    if t["name"] in existing:
        print("EXISTS", t["name"])
        continue
    res = post("/open/crons", t)
    print("CREATE", t["name"], "->", str(res)[:200])

print("\n当前任务列表：")
for c in ((cli._call("GET", "/open/crons").get("data") or {}).get("data") or []):
    print(f"  id={c.get('id')} {c.get('name')} | {c.get('command')} | {c.get('schedule')}")
PY
S docker cp /tmp/ql_create_crons.py qinglong:/tmp/ >/dev/null
S docker exec qinglong python3 /tmp/ql_create_crons.py
