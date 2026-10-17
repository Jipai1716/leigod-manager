#!/bin/bash
PW="${NAS_SUDO_PW:?需要设置 NAS_SUDO_PW}"
S() { echo "$PW" | sudo -S -p '' "$@" 2>/dev/null; }

echo "=== 试跑 task 子目录形式（无 Token 应返回退出码 2）==="
S docker exec qinglong sh -c 'cd /ql/data/scripts && task leigod/leigod_pause.py --no-push; echo "exit=$?"'
echo
echo "=== 平台 task 命令实现 ==="
S docker exec qinglong sh -c 'grep -rn "task" /ql/shell/task.sh 2>/dev/null | head -20; ls /ql/shell 2>/dev/null | head'
