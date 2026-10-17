import json
import sqlite3
import sys
import urllib.error
import urllib.request

sys.path.insert(0, "/ql/data/scripts/leigod")
from leigod_common import QinglongClient

db = sqlite3.connect("/ql/data/db/database.sqlite")
cid, secret = db.execute("select client_id, client_secret from Apps where name='system'").fetchone()
cli = QinglongClient("http://127.0.0.1:5700", cid, secret)

envs = cli.list_envs()
target = [e for e in envs if e["name"] == "LEIGOD_TOKEN"]
print("待删除测试变量:", [e["id"] for e in target])

if target:
    token = cli._auth()
    req = urllib.request.Request(
        cli.base + "/open/envs",
        data=json.dumps([e["id"] for e in target]).encode(),
        method="DELETE",
    )
    req.add_header("Authorization", "Bearer " + token)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            print("删除结果:", r.status, r.read().decode()[:100])
    except urllib.error.HTTPError as e:
        print("删除失败:", e.code, e.read().decode()[:200])

print("\n清理后环境变量：")
for e in cli.list_envs():
    print("  -", e["name"])
