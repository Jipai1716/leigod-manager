#!/bin/bash
# 在 NAS 上执行（代码已解压到 /tmp/leigod-deploy）
# 用法: bash deploy.sh [--restart-astrbot]
set -euo pipefail

SRC="$(cd "$(dirname "$0")" && pwd)"
PW="${NAS_SUDO_PW:?需要设置 NAS_SUDO_PW}"
S() { echo "$PW" | sudo -S -p '' "$@"; }

QL_DIR=/vol1/1000/Docker/qinglong/scripts/leigod
PLUGIN_DIR=/vol1/1000/Docker/astrbot/data/plugins/astrbot_plugin_leigod_manager

echo "==> 目标"
echo "    青龙: $QL_DIR  (容器内 /ql/data/scripts/leigod)"
echo "    插件: $PLUGIN_DIR"

S mkdir -p "$QL_DIR/state"
S mkdir -p "$PLUGIN_DIR/lib"

echo "==> 同步青龙脚本"
S rm -rf "$QL_DIR/__pycache__" || true
S cp -f "$SRC"/scripts/leigod_common.py "$QL_DIR"/
S cp -f "$SRC"/scripts/leigod_cmd.py "$QL_DIR"/
S cp -f "$SRC"/scripts/leigod_pause.py "$QL_DIR"/
S cp -f "$SRC"/scripts/leigod_daily_report.py "$QL_DIR"/
S cp -f "$SRC"/scripts/leigod_update_token.py "$QL_DIR"/
S cp -f "$SRC"/scripts/leigod_logs.py "$QL_DIR"/
S cp -f "$SRC"/scripts/leigod_status.py "$QL_DIR"/
S cp -f "$SRC"/scripts/leigod_history.py "$QL_DIR"/
S ls -1 "$QL_DIR"

echo "==> 同步 AstrBot 插件"
S cp -f "$SRC"/astrbot_plugin_leigod_manager/main.py "$PLUGIN_DIR"/
S cp -f "$SRC"/astrbot_plugin_leigod_manager/metadata.yaml "$PLUGIN_DIR"/
S cp -f "$SRC"/scripts/leigod_common.py "$PLUGIN_DIR"/lib/
S cp -f "$SRC"/scripts/leigod_cmd.py "$PLUGIN_DIR"/lib/

echo "==> 修正权限"
S chmod -R a+rX "$QL_DIR" "$PLUGIN_DIR"
S chmod 777 "$QL_DIR/state" || true

echo "==> 容器内可见性检查"
S docker exec qinglong ls -1 /ql/data/scripts/leigod
S docker exec astrbot ls -1 /AstrBot/data/plugins/astrbot_plugin_leigod_manager

if [[ "${1:-}" == "--restart-astrbot" ]]; then
    echo "==> 重启 AstrBot"
    S docker restart astrbot
    sleep 4
    S docker logs --tail 60 astrbot 2>&1 | grep -i "leigod\|error\|Traceback" || echo "    (日志中暂无 leigod 关键字)"
fi

echo "==> 完成"
