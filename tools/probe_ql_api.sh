#!/bin/bash
PW="${NAS_SUDO_PW:?需要设置 NAS_SUDO_PW}"
S() { echo "$PW" | sudo -S -p '' "$@" 2>/dev/null; }

echo "=== open api routers in /ql/back ==="
S docker exec qinglong sh -c 'ls /ql/back/api; grep -rn "auth/token\|/envs\|open/" /ql/back/api/*.js 2>/dev/null | head -30'
echo
echo "=== try common paths ==="
for p in /open/auth/token /api/open/auth/token /open/user/login; do
  code=$(S docker exec qinglong sh -c "curl -s -o /dev/null -w '%{http_code}' -X POST http://127.0.0.1:5700$p -H 'Content-Type: application/json' -d '{}'")
  echo "$p -> $code"
done
