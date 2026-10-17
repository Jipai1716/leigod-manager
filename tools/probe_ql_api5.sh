#!/bin/bash
PW="${NAS_SUDO_PW:?需要设置 NAS_SUDO_PW}"
S() { echo "$PW" | sudo -S -p '' "$@" 2>/dev/null; }

echo "=== apiWhiteList 使用处 ==="
S docker exec qinglong sh -c 'grep -rn "apiWhiteList" /ql/back --include=*.ts | grep -v config/index.ts'
echo
echo "=== 路由挂载前缀 ==="
S docker exec qinglong sh -c 'grep -rn "openRoutes\|/open\"\|/open\b\|use(.*open" /ql/back/loaders/*.ts /ql/back/app.ts 2>/dev/null | head -20'
echo
echo "=== loaders/express 里 jwt 配置 ==="
S docker exec qinglong sh -c 'grep -rn "jwt\|unless" /ql/back/loaders/express.ts 2>/dev/null | head -20'
