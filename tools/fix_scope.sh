#!/bin/bash
PW="${NAS_SUDO_PW:?需要设置 NAS_SUDO_PW}"
S() { echo "$PW" | sudo -S -p '' "$@" 2>/dev/null; }

cat > /tmp/ql_fix_scope.py <<'PY'
import json, sqlite3

# 1) 数据库里的 Apps.scopes 加上 envs
db = sqlite3.connect("/ql/data/db/database.sqlite")
row = db.execute("select id, scopes from Apps where name='system'").fetchone()
print("before:", row)
scopes = json.loads(row[1] or "[]")
if "envs" not in scopes:
    scopes.append("envs")
    db.execute("update Apps set scopes=? where id=?", (json.dumps(scopes), row[0]))
    db.commit()
    print("db updated ->", scopes)
else:
    print("db already has envs")

# 2) keyv 缓存里的 apps 也同步一份，避免重启
kv = sqlite3.connect("/ql/data/db/keyv.sqlite")
print("keyv tables:", [r[0] for r in kv.execute("select name from sqlite_master where type='table'")])
for table, in kv.execute("select name from sqlite_master where type='table'"):
    cols = [r[1] for r in kv.execute(f"PRAGMA table_info({table})")]
    print(table, "cols:", cols)
    for r in kv.execute(f"select * from {table} limit 5"):
        print("   ", str(r)[:200])
PY
S docker cp /tmp/ql_fix_scope.py qinglong:/tmp/ >/dev/null
S docker exec qinglong python3 /tmp/ql_fix_scope.py
