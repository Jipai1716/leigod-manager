#!/bin/bash
PW="${NAS_SUDO_PW:?需要设置 NAS_SUDO_PW}"
S() { echo "$PW" | sudo -S -p '' "$@" 2>/dev/null; }

cat > /tmp/ql_fix_keyv.py <<'PY'
import json, sqlite3

kv = sqlite3.connect("/ql/data/db/keyv.sqlite")
row = kv.execute("select value from keyv where key='keyv:apps'").fetchone()
doc = json.loads(row[0])
apps = doc.get("value") or []
changed = False
for app in apps:
    if app.get("name") == "system":
        scopes = app.get("scopes") or []
        if "envs" not in scopes:
            scopes.append("envs")
            app["scopes"] = scopes
            changed = True
        print("system scopes now:", app["scopes"])
if changed:
    kv.execute("update keyv set value=? where key='keyv:apps'", (json.dumps(doc),))
    kv.commit()
    print("keyv updated")
else:
    print("keyv unchanged")
PY
S docker cp /tmp/ql_fix_keyv.py qinglong:/tmp/ >/dev/null
S docker exec qinglong python3 /tmp/ql_fix_keyv.py
echo "=== 重新验证 /open/envs ==="
S docker exec qinglong python3 /tmp/ql_selftest.py 2>&1 | tail -15
