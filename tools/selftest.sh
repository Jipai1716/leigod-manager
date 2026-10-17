#!/bin/bash
# 青龙容器内自检：语法 + 青龙 API 连通性
PW="${NAS_SUDO_PW:?需要设置 NAS_SUDO_PW}"
S() { echo "$PW" | sudo -S -p '' "$@"; }

echo "=== py_compile（青龙侧脚本）==="
S docker exec qinglong sh -c 'cd /ql/data/scripts/leigod && python3 -m py_compile *.py && echo COMPILE_OK'

echo "=== py_compile（插件侧）==="
S docker exec astrbot sh -c 'cd /AstrBot/data/plugins/astrbot_plugin_leigod_manager/lib && python3 -m py_compile *.py && echo COMPILE_OK'

cat > /tmp/ql_selftest.py <<'PY'
import json, sqlite3, sys
sys.path.insert(0, "/ql/data/scripts/leigod")
from leigod_common import QinglongClient, Config

db = sqlite3.connect("/ql/data/db/database.sqlite")
row = db.execute("select name, client_id, client_secret from Apps limit 1").fetchone()
print("app:", row[0], "client_id:", row[1], "secret_len:", len(row[2] or ""))
secret = row[2]

cli = QinglongClient("http://127.0.0.1:5700", row[1], secret)
envs = cli.list_envs()
print("env count:", len(envs))
for e in envs:
    print("  -", e.get("name"), "| remarks:", e.get("remarks"))
cfg = Config()
print("config:", json.dumps(cfg.describe(), ensure_ascii=False))
PY
S docker cp /tmp/ql_selftest.py qinglong:/tmp/ >/dev/null
echo "=== 青龙 API 自检 ==="
S docker exec qinglong python3 /tmp/ql_selftest.py
