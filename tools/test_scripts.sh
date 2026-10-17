#!/bin/bash
PW="${NAS_SUDO_PW:?需要设置 NAS_SUDO_PW}"
S() { echo "$PW" | sudo -S -p '' "$@" 2>/dev/null; }
SO() { echo "$PW" | sudo -S -p '' "$@"; }

echo "===== 1) 未配置 Token 时的暂停任务（应为 2）====="
S docker exec qinglong sh -c 'cd /ql/data/scripts && task leigod/leigod_pause.py --no-push' 2>&1 | tail -6
echo "exit=${PIPESTATUS[0]}"

echo
echo "===== 2) 状态查询 ====="
S docker exec qinglong sh -c 'cd /ql/data/scripts && task leigod/leigod_status.py' 2>&1 | tail -12

echo
echo "===== 3) 指令帮助（直接跑 cmd 脚本，带环境变量）====="
SO docker exec qinglong sh -c 'cd /ql/data/scripts/leigod && set -a && . /dev/null; python3 leigod_cmd.py "/l h"' 2>&1 | tail -14
