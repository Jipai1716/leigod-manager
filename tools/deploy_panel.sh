#!/bin/bash
# 构建并启动雷神管理器面板容器（无密码，局域网直连）
# 用法: NAS_SUDO_PW=xxx bash deploy_panel.sh
set -uo pipefail
PW="${NAS_SUDO_PW:?需要设置 NAS_SUDO_PW}"
SO() { echo "$PW" | sudo -S -p '' "$@"; }

SRC="${SRC_DIR:-/tmp/leigod-deploy2}"
CONF_DIR=/vol1/1000/Docker/leigod-panel
ENV_FILE="$CONF_DIR/panel.env"
TASK_NAME="${LEIGOD_PAUSE_TASK_NAME:-雷神定时暂停}"

echo "=== 1) 准备配置目录 ==="
SO mkdir -p "$CONF_DIR"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "=== 2) 生成配置（首次）==="
  cat > /tmp/dump_ql_cred.py <<'PY'
import sqlite3
db = sqlite3.connect("/ql/data/db/database.sqlite")
cid, secret = db.execute("select client_id, client_secret from Apps where name='system'").fetchone()
open("/tmp/ql_cred.txt", "w").write(cid + "\n" + secret)
print("ok")
PY
  SO docker cp /tmp/dump_ql_cred.py qinglong:/tmp/ >/dev/null
  SO docker exec qinglong python3 /tmp/dump_ql_cred.py >/dev/null
  SO docker cp qinglong:/tmp/ql_cred.txt /tmp/ql_cred.txt
  CID=$(sed -n 1p /tmp/ql_cred.txt)
  SECRET=$(sed -n 2p /tmp/ql_cred.txt)

  # 面板在容器里，访问青龙必须用宿主局域网 IP
  NAS_IP=$(ip -4 -o addr show scope global | awk '{print $4}' | cut -d/ -f1 | grep -v '^172\.' | head -1)
  echo "检测到 NAS 局域网 IP: $NAS_IP"

  cat > /tmp/panel.env <<EOF
LEIGOD_QL_BASE_URL=http://$NAS_IP:5700
LEIGOD_QL_CLIENT_ID=$CID
LEIGOD_QL_CLIENT_SECRET=$SECRET
LEIGOD_TZ=Asia/Shanghai
LEIGOD_PAUSE_TASK_NAME=$TASK_NAME
EOF
  SO cp /tmp/panel.env "$ENV_FILE"
  SO chmod 600 "$ENV_FILE"
  rm -f /tmp/panel.env 2>/dev/null || true
  SO rm -f /tmp/ql_cred.txt || true
else
  echo "=== 2) 复用已有配置 $ENV_FILE ==="
  SO grep -E '^LEIGOD_QL_BASE_URL' "$ENV_FILE" || true
fi

echo "=== 3) 构建镜像 ==="
SO docker build -q -t leigod-panel:1.1.0 -f "$SRC/panel/Dockerfile" "$SRC" 2>&1 | tail -3

echo "=== 4) 启动容器 ==="
SO docker rm -f leigod-panel >/dev/null 2>&1 || true
SO docker run -d --name leigod-panel --restart unless-stopped \
  -p 5788:5788 --env-file "$ENV_FILE" leigod-panel:1.1.0 >/dev/null
sleep 4
SO docker ps --filter name=leigod-panel --format "{{.Names}} | {{.Status}} | {{.Ports}}"

echo "=== 5) 健康检查 ==="
SO docker exec leigod-panel python3 -c "
import urllib.request
r = urllib.request.urlopen('http://127.0.0.1:5788/healthz', timeout=5)
print('healthz:', r.status, r.read().decode()[:120])
"

echo "=== 6) 概览接口自检 ==="
SO docker exec leigod-panel python3 -c "
import json, urllib.request
d = json.load(urllib.request.urlopen('http://127.0.0.1:5788/api/summary', timeout=20))
print('token.configured =', d['token']['configured'])
print('pause_state =', d['pause_state'].get('state'), '/', d['pause_state'].get('reason', ''))
s = d.get('schedule') or {}
print('schedule =', s.get('cron'), '|', s.get('desc'))
"
