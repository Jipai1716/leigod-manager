#!/bin/bash
# 清理：卸载 AstrBot 指令插件、删除日报任务、更新暂停任务为「仅失败推送」
PW="${NAS_SUDO_PW:?}"
SO() { echo "$PW" | sudo -S -p '' "$@"; }

echo "=== 1) 卸载 AstrBot 指令插件 ==="
SO rm -rf /vol1/1000/Docker/astrbot/data/plugins/astrbot_plugin_leigod_manager
echo "已删除插件目录"

echo "=== 2) 恢复 AstrBot 平台配置（关闭 Hex、清空白名单）==="
SO docker cp /tmp/revert_astrbot.py astrbot:/tmp/ >/dev/null
SO docker exec astrbot python3 /tmp/revert_astrbot.py

echo "=== 3) 重启 AstrBot 使插件卸载生效 ==="
SO docker restart astrbot >/dev/null 2>&1
echo "已重启"

echo "=== 4) 删除日报任务（id=15），保留暂停任务 ==="
cat > /tmp/del_cron.py <<'PY'
import json, sqlite3, sys, urllib.error, urllib.request
sys.path.insert(0, "/ql/data/scripts/leigod")
from leigod_common import QinglongClient

db = sqlite3.connect("/ql/data/db/database.sqlite")
cid, secret = db.execute("select client_id, client_secret from Apps where name='system'").fetchone()
cli = QinglongClient("http://127.0.0.1:5700", cid, secret)

crons = ((cli._call("GET", "/open/crons").get("data") or {}).get("data") or [])
target = [c["id"] for c in crons if c["name"] == "雷神每日日报"]
print("待删除任务:", target)

if target:
    token = cli._auth()
    req = urllib.request.Request(
        cli.base + "/open/crons", data=json.dumps(target).encode(), method="DELETE"
    )
    req.add_header("Authorization", "Bearer " + token)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            print("删除结果:", r.status, r.read().decode()[:120])
    except urllib.error.HTTPError as e:
        print("删除失败:", e.code, e.read().decode()[:200])

crons = ((cli._call("GET", "/open/crons").get("data") or {}).get("data") or [])
print("\n当前任务：")
for c in crons:
    print(f"  id={c['id']} {c['name']} | {c['schedule']}")
PY
SO docker cp /tmp/del_cron.py qinglong:/tmp/ >/dev/null
SO docker exec qinglong python3 /tmp/del_cron.py

echo "=== 5) 更新青龙侧脚本（去掉指令与日报）==="
SO rm -f /vol1/1000/Docker/qinglong/scripts/leigod/leigod_cmd.py
SO rm -f /vol1/1000/Docker/qinglong/scripts/leigod/leigod_daily_report.py
SO cp -f /tmp/leigod-deploy/scripts/leigod_pause.py /vol1/1000/Docker/qinglong/scripts/leigod/leigod_pause.py
SO chmod -R a+rX /vol1/1000/Docker/qinglong/scripts/leigod
echo "青龙侧剩余脚本："
SO docker exec qinglong ls -1 /ql/data/scripts/leigod
