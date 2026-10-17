#!/bin/bash
PW="${NAS_SUDO_PW:?需要设置 NAS_SUDO_PW}"
S() { echo "$PW" | sudo -S -p '' "$@" 2>/dev/null; }

echo "=== 找到 routes() 定义 ==="
S docker exec qinglong sh -c 'grep -rn "export default.*routes\|const routes" /ql/back --include=*.ts | head'
echo
echo "=== app router 文件 ==="
S docker exec qinglong sh -c 'sed -n "1,60p" /ql/back/loaders/app.ts 2>/dev/null || sed -n "1,60p" /ql/back/app.ts'
echo
echo "=== 包含 open 挂载的文件 ==="
S docker exec qinglong sh -c 'grep -rln "api/open" /ql/back --include=*.ts | head'
