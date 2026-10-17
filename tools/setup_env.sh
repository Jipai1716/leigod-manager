#!/bin/bash
PW="${NAS_SUDO_PW:?需要设置 NAS_SUDO_PW}"
S() { echo "$PW" | sudo -S -p '' "$@" 2>/dev/null; }

cat > /tmp/ql_setup_env.py <<'PY'
import json, sqlite3, sys
sys.path.insert(0, "/ql/data/scripts/leigod")
from leigod_common import QinglongClient

db = sqlite3.connect("/ql/data/db/database.sqlite")
cid, secret = db.execute(
    "select client_id, client_secret from Apps where name='system'"
).fetchone()

cli = QinglongClient("http://127.0.0.1:5700", cid, secret)
envs = {e["name"]: e for e in cli.list_envs()}
openid = (envs.get("QQ_OPENID") or {}).get("value", "")

plan = {
    "LEIGOD_QL_BASE_URL": ("http://127.0.0.1:5700", "雷神管理器：青龙地址"),
    "LEIGOD_QL_CLIENT_ID": (cid, "雷神管理器：青龙 API 应用 ID"),
    "LEIGOD_QL_CLIENT_SECRET": (secret, "雷神管理器：青龙 API 应用密钥"),
    "LEIGOD_ALLOWED_IDS": (openid, "雷神管理器：允许执行指令的 QQ openid"),
    "LEIGOD_TZ": ("Asia/Shanghai", "雷神管理器：时区"),
}

for name, (value, remarks) in plan.items():
    if not value:
        print(f"SKIP {name} (empty)")
        continue
    action = cli.upsert_env(name, value, remarks)
    shown = value if name in ("LEIGOD_QL_BASE_URL", "LEIGOD_TZ") else (
        value[:6] + "..." if len(value) > 8 else value
    )
    print(f"{action:8s} {name} = {shown}")

print("\n现有环境变量：")
for e in cli.list_envs():
    print("  -", e["name"])
PY
S docker cp /tmp/ql_setup_env.py qinglong:/tmp/ >/dev/null
S docker exec qinglong python3 /tmp/ql_setup_env.py
