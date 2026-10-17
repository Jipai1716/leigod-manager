#!/bin/bash
PW="${NAS_SUDO_PW:?需要设置 NAS_SUDO_PW}"
S() { echo "$PW" | sudo -S -p '' "$@" 2>/dev/null; }
echo "=== cron.ts 路由 ==="
S docker exec qinglong sh -c 'grep -n "route\.\(get\|post\|put\)(\|app.use(" /ql/back/api/cron.ts | head -12'
echo
echo "=== cron.ts 创建任务 body 校验 ==="
S docker exec qinglong sh -c 'sed -n "/route.post(/,/async/p" /ql/back/api/cron.ts | head -40'
