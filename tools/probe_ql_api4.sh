#!/bin/bash
PW="${NAS_SUDO_PW:?需要设置 NAS_SUDO_PW}"
S() { echo "$PW" | sudo -S -p '' "$@" 2>/dev/null; }

echo "=== app.ts mounts ==="
S docker exec qinglong sh -c 'grep -n "app.use\|require\|import" /ql/back/app.ts | head -40'
echo
echo "=== search for auth/token across back ==="
S docker exec qinglong sh -c 'grep -rn "auth/token" /ql/back 2>/dev/null | head -10'
echo
echo "=== search for appKey usage ==="
S docker exec qinglong sh -c 'grep -rn "appKey" /ql/back 2>/dev/null | head -10'
