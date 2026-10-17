#!/bin/bash
PW="${NAS_SUDO_PW:?需要设置 NAS_SUDO_PW}"
S() { echo "$PW" | sudo -S -p '' "$@" 2>/dev/null; }

cat > /tmp/ql_apps.py <<'PY'
import sqlite3, json
db = sqlite3.connect("/ql/data/db/database.sqlite")
cur = db.execute("select id,name,client_id,scopes,tokens from Apps")
for row in cur:
    print("id:", row[0], "name:", row[1], "client_id:", row[2])
    print("  scopes:", row[3])
    try:
        tokens = json.loads(row[4] or "[]")
        print("  tokens:", [(t.get("value","")[:8]+"...", t.get("expiration")) for t in tokens])
    except Exception as e:
        print("  tokens raw:", (row[4] or "")[:80], e)
PY
S docker cp /tmp/ql_apps.py qinglong:/tmp/ >/dev/null
S docker exec qinglong python3 /tmp/ql_apps.py
echo
echo "=== AppScope 枚举 ==="
S docker exec qinglong sh -c 'cat /ql/back/data/open.ts 2>/dev/null | head -40'
