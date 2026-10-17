#!/bin/bash
PW="${NAS_SUDO_PW:?}"
SO() { echo "$PW" | sudo -S -p '' "$@"; }

cat > /tmp/read_cfg2.py <<'PY'
import json
p = "/AstrBot/data/cmd_config.json"
d = json.load(open(p, encoding="utf-8-sig"))

def mask(obj):
    out = {}
    for k, v in obj.items():
        if isinstance(v, str) and any(s in k.lower() for s in ("secret", "token", "password", "key")) and v:
            out[k] = v[:4] + "***(" + str(len(v)) + ")"
        else:
            out[k] = v
    return out

for entry in d.get("platform", []):
    print(json.dumps(mask(entry), ensure_ascii=False, indent=2))
    print("---")

ps = d.get("platform_settings", {})
print("enable_id_white_list:", ps.get("enable_id_white_list"))
print("id_whitelist:", ps.get("id_whitelist"))
print("id_whitelist_log:", ps.get("id_whitelist_log"))
print("admins_id:", d.get("admins_id"))
PY
SO docker cp /tmp/read_cfg2.py astrbot:/tmp/ >/dev/null
SO docker exec astrbot python3 /tmp/read_cfg2.py
echo
echo "=== 青龙里的 QQ_APP_ID（与 Hex 的 appid 对比）==="
SO docker exec qinglong sh -c 'python3 -c "
import sqlite3
db=sqlite3.connect(\"/ql/data/db/database.sqlite\")
for n,v in db.execute(\"select name,value from Envs where name in (\x27QQ_APP_ID\x27,\x27QQ_OPENID\x27)\"):
    print(n, \"=\", (v[:6]+\"...\") if len(v)>8 else v)
"'
