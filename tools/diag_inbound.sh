#!/bin/bash
PW="${NAS_SUDO_PW:?需要设置 NAS_SUDO_PW}"
SO() { echo "$PW" | sudo -S -p '' "$@"; }

echo "=== AstrBot 平台适配器初始化日志 ==="
SO docker logs --since 60m astrbot 2>&1 | grep -aiE "platform|adapter|aiocqhttp|qqofficial|websocket|connected" | tail -30
echo
echo "=== AstrBot 配置里的平台列表 ==="
SO docker exec astrbot sh -c 'ls /AstrBot/data; python3 -c "
import json
p=\"/AstrBot/data/cmd_config.json\"
d=json.load(open(p))
print(\"platform:\", json.dumps(d.get(\"platform\"), ensure_ascii=False)[:800])
print(\"provider_settings.enable:\", d.get(\"provider_settings\",{}).get(\"enable\"))
" 2>&1 | head -20'
echo
echo "=== napcat 容器状态 ==="
SO docker ps -a --filter "name=napcat" --format "{{.Names}} | {{.Status}} | {{.Ports}}"
