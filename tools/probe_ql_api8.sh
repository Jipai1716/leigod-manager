#!/bin/bash
PW="${NAS_SUDO_PW:?需要设置 NAS_SUDO_PW}"
S() { echo "$PW" | sudo -S -p '' "$@" 2>/dev/null; }

echo "=== express.ts head ==="
S docker exec qinglong sh -c 'sed -n "1,19p" /ql/back/loaders/express.ts'
echo
echo "=== api/index.ts ==="
S docker exec qinglong sh -c 'cat /ql/back/api/index.ts'
echo
echo "=== open.ts line 95..130 ==="
S docker exec qinglong sh -c 'sed -n "95,130p" /ql/back/api/open.ts'
