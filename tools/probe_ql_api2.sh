#!/bin/bash
PW="${NAS_SUDO_PW:?需要设置 NAS_SUDO_PW}"
S() { echo "$PW" | sudo -S -p '' "$@" 2>/dev/null; }

echo "=== open.ts routes ==="
S docker exec qinglong sh -c 'grep -n "router\.\(get\|post\|put\|delete\)\|appKey\|appSecret" /ql/back/api/open.ts | head -40'
echo
echo "=== env.ts routes (for env read/write) ==="
S docker exec qinglong sh -c 'grep -n "router\.\(get\|post\|put\|delete\)" /ql/back/api/open.ts /ql/back/api/env.ts 2>/dev/null | head -30'
