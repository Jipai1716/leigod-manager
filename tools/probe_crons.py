import json
import sqlite3
import sys

sys.path.insert(0, "/ql/data/scripts/leigod")
from leigod_common import QinglongClient  # noqa: E402

db = sqlite3.connect("/ql/data/db/database.sqlite")
cid, secret = db.execute("select client_id, client_secret from Apps where name='system'").fetchone()
cli = QinglongClient("http://127.0.0.1:5700", cid, secret)

resp = cli._call("GET", "/open/crons")
print("type:", type(resp))
print("keys:", list(resp.keys()) if isinstance(resp, dict) else "-")
print("code:", resp.get("code") if isinstance(resp, dict) else "-")
data = resp.get("data") if isinstance(resp, dict) else None
print("data type:", type(data))
print("data preview:", str(data)[:600])
