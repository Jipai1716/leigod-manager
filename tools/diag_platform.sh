#!/bin/bash
PW="${NAS_SUDO_PW:?}"
SO() { echo "$PW" | sudo -S -p '' "$@"; }

cat > /tmp/read_cfg.py <<'PY'
import json
p = "/AstrBot/data/cmd_config.json"
d = json.load(open(p, encoding="utf-8-sig"))
print("top-level keys:", list(d.keys())[:20])
plat = d.get("platform", [])
print("\nplatform entries:", len(plat))
for entry in plat:
    safe = {k: v for k, v in entry.items() if k not in ("app_secret", "token", "password", "secret")}
    print("  -", json.dumps(safe, ensure_ascii=False)[:300])
print("\nprovider_settings:", json.dumps(d.get("provider_settings", {}), ensure_ascii=False)[:400])
print("\nplatform_settings:", json.dumps(d.get("platform_settings", {}), ensure_ascii=False)[:300])
PY
SO docker cp /tmp/read_cfg.py astrbot:/tmp/ >/dev/null
SO docker exec astrbot python3 /tmp/read_cfg.py

echo
echo "=== 全部容器（确认有没有别的 QQ 接入端）==="
SO docker ps --format "{{.Names}} | {{.Image}} | {{.Status}}"
