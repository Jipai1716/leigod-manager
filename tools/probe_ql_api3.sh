#!/bin/bash
PW="${NAS_SUDO_PW:?需要设置 NAS_SUDO_PW}"
S() { echo "$PW" | sudo -S -p '' "$@" 2>/dev/null; }
S docker exec qinglong sh -c 'sed -n "1,90p" /ql/back/api/open.ts'
echo "................"
S docker exec qinglong sh -c 'grep -n "open" /ql/back/app.ts | head -20'
