#!/bin/bash
# 构建并启动雷神管理器面板容器
set -euo pipefail
PW="${NAS_SUDO_PW:?}"
SO() { echo "$PW" | sudo -S -p '' "$@"; }

SRC=/tmp/leigod-deploy2
CONF_DIR=/vol1/1000/Docker/leigod-panel
ENV_FILE="$CONF_DIR/panel.env"

echo "=== 1) 准备配置目录 ==="
SO mkdir -p "$CONF_DIR"
SO chown 1000:1001 "$CONF_DIR" 2>/dev/null || true

if [[ ! -f "$ENV_FILE" ]]; then
  echo "=== 2) 首次生成访问密码与配置 ==="
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
  PANEL_PW=$(python3 -c "import secrets,string;print(''.join(secrets.choice(string.ascii_letters+string.digits) for _ in range(16)))")
  cat > /tmp/panel.env <<EOF
LEIGOD_PANEL_PASSWORD=$PANEL_PW
LEIGOD_QL_BASE_URL=http://192.168.10.110:5700
LEIGOD_QL_CLIENT_ID=$CID
LEIGOD_QL_CLIENT_SECRET=$SECRET
LEIGOD_TZ=Asia/Shanghai
EOF
  SO cp /tmp/panel.env "$ENV_FILE"
  SO chmod 600 "$ENV_FILE"
  rm -f /tmp/panel.env 2>/dev/null || true
  SO rm -f /tmp/ql_cred.txt || true
  echo "PINNED_PASSWORD:$PANEL_PW"
else
  echo "=== 2) 复用已有配置 $ENV_FILE ==="
  SO grep -c . "$ENV_FILE"
fi

echo "=== 3) 构建镜像 ==="
SO docker build -q -t leigod-panel:1.0.0 -f "$SRC/panel/Dockerfile" "$SRC" 2>&1 | tail -5

echo "=== 4) 启动容器 ==="
SO docker rm -f leigod-panel >/dev/null 2>&1 || true
SO docker run -d --name leigod-panel --restart unless-stopped \
  -p 5788:5788 --env-file "$ENV_FILE" leigod-panel:1.0.0 >/dev/null
sleep 4
SO docker ps --filter name=leigod-panel --format "{{.Names}} | {{.Status}} | {{.Ports}}"

echo "=== 5) 健康检查 ==="
SO docker exec leigod-panel python3 -c "
import urllib.request, json
r = urllib.request.urlopen('http://127.0.0.1:5788/healthz', timeout=5)
print('healthz:', r.status, r.read().decode()[:120])
"
echo "=== 6) 容器日志 ==="
SO docker logs --tail 8 leigod-panel 2>&1 | tail -8
