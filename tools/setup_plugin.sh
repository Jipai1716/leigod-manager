#!/bin/bash
# 生成 AstrBot 插件配置（含青龙 API 凭据与白名单），并做导入自检
PW="${NAS_SUDO_PW:?需要设置 NAS_SUDO_PW}"
S() { echo "$PW" | sudo -S -p '' "$@" 2>/dev/null; }
SO() { echo "$PW" | sudo -S -p '' "$@"; }

PLUGIN_DIR=/vol1/1000/Docker/astrbot/data/plugins/astrbot_plugin_leigod_manager

cat > /tmp/gen_plugin_cfg.py <<'PY'
import json, sqlite3, sys
sys.path.insert(0, "/ql/data/scripts/leigod")
from leigod_common import QinglongClient

db = sqlite3.connect("/ql/data/db/database.sqlite")
cid, secret = db.execute("select client_id, client_secret from Apps where name='system'").fetchone()
cli = QinglongClient("http://127.0.0.1:5700", cid, secret)
envs = {e["name"]: (e.get("value") or "") for e in cli.list_envs()}

cfg = {
    "ql_base": "http://192.168.10.110:5700",
    "ql_client_id": cid,
    "ql_client_secret": secret,
    "token_env": "LEIGOD_TOKEN",
    "allowed_ids": [x for x in envs.get("LEIGOD_ALLOWED_IDS", "").split(",") if x],
    "tz": envs.get("LEIGOD_TZ", "Asia/Shanghai"),
    "state_dir": "/AstrBot/data/plugins/astrbot_plugin_leigod_manager/state",
}
print(json.dumps(cfg, ensure_ascii=False, indent=2))
open("/tmp/plugin_config.json", "w", encoding="utf-8").write(json.dumps(cfg, ensure_ascii=False, indent=2))
PY
S docker cp /tmp/gen_plugin_cfg.py qinglong:/tmp/ >/dev/null
S docker exec qinglong python3 /tmp/gen_plugin_cfg.py > /tmp/plugin_config_preview.txt
echo "=== 生成的插件配置（密钥已截断显示）==="
sed -E 's/("ql_client_secret": ")([^"]{6})[^"]*(")/\1\2***\3/' /tmp/plugin_config_preview.txt

echo
echo "=== 写入插件目录 ==="
SO cp /tmp/plugin_config.json "$PLUGIN_DIR/config.json"
SO chmod 600 "$PLUGIN_DIR/config.json"
SO mkdir -p "$PLUGIN_DIR/state"
SO chmod 777 "$PLUGIN_DIR/state"
SO chown 0:0 "$PLUGIN_DIR/config.json" || true
SO ls -l "$PLUGIN_DIR"

echo
echo "=== 容器内导入自检 ==="
SO docker exec astrbot python3 -c "
import sys
sys.path.insert(0, '/AstrBot/data/plugins/astrbot_plugin_leigod_manager/lib')
import leigod_cmd, leigod_common
print('parse /l s ->', leigod_cmd.parse('/l s'))
print('parse /leigod update AbC@1 ->', leigod_cmd.parse('/leigod update AbC@1'))
cfg = leigod_common.Config()
print('config ok:', cfg.ql_base, cfg.token_env, len(cfg.allowed_ids))
"
