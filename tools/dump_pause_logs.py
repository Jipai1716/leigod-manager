import json
import sys

sys.path.insert(0, "/app")
from leigod_common import Config, LeigodClient, QinglongClient, get_token  # noqa: E402

cfg = Config()
ql = QinglongClient(cfg.ql_base, cfg.ql_client_id, cfg.ql_client_secret, cfg.http_timeout)
token = get_token(cfg, ql)
raw = LeigodClient(token, timeout=cfg.http_timeout).pause_logs(size=5)

print("TOP KEYS:", list(raw.keys()))
data = raw.get("data")
print("DATA TYPE:", type(data).__name__)
if isinstance(data, dict):
    print("DATA KEYS:", list(data.keys()))
    for k, v in data.items():
        if isinstance(v, list):
            print(f"LIST FIELD: {k} len={len(v)}")
            if v:
                print("ITEM KEYS:", list(v[0].keys()))
                print("FIRST ITEM:", json.dumps(v[0], ensure_ascii=False)[:800])
        else:
            print(f"  {k} = {str(v)[:100]}")
elif isinstance(data, list):
    print("ITEMS:", len(data))
    if data:
        print("ITEM KEYS:", list(data[0].keys()))
        print("FIRST ITEM:", json.dumps(data[0], ensure_ascii=False)[:800])
