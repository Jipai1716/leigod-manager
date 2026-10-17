#!/bin/bash
PW="${NAS_SUDO_PW:?需要设置 NAS_SUDO_PW}"
S() { echo "$PW" | sudo -S -p '' "$@" 2>/dev/null; }
S docker exec qinglong sh -c 'grep -n "getApps" -A 12 /ql/back/shared/store.ts | head -30'
