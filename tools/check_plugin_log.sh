#!/bin/bash
PW="${NAS_SUDO_PW:?需要设置 NAS_SUDO_PW}"
SO() { echo "$PW" | sudo -S -p '' "$@"; }
echo "=== 最近 5 分钟日志中的插件相关行 ==="
SO docker logs --since 5m astrbot 2>&1 | grep -iE "leigod|插件|plugin" | tail -40
echo
echo "=== 最近 20 行原始日志 ==="
SO docker logs --tail 20 astrbot 2>&1 | tail -20
