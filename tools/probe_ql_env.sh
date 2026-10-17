#!/bin/bash
PW="${NAS_SUDO_PW:?需要设置 NAS_SUDO_PW}"
S() { echo "$PW" | sudo -S -p '' "$@" 2>/dev/null; }

echo "=== env.ts 路由 ==="
S docker exec qinglong sh -c 'grep -n "route\.\(get\|post\|put\|delete\)(\|^    .\x27/" /ql/back/api/env.ts | head -20'
echo
echo "=== env.ts 前 40 行 ==="
S docker exec qinglong sh -c 'sed -n "1,40p" /ql/back/api/env.ts'
echo
echo "=== openService.authToken ==="
S docker exec qinglong sh -c 'grep -n "authToken" -A 25 /ql/back/services/open.ts | head -40'
