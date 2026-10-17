import json
import os
import sys

BASE = "/AstrBot/data/plugins/astrbot_plugin_leigod_manager"
sys.path.insert(0, BASE + "/lib")

cfg = json.load(open(BASE + "/config.json", encoding="utf-8"))
os.environ.setdefault("LEIGOD_QL_BASE_URL", cfg["ql_base"])
os.environ.setdefault("LEIGOD_QL_CLIENT_ID", cfg["ql_client_id"])
os.environ.setdefault("LEIGOD_QL_CLIENT_SECRET", cfg["ql_client_secret"])
os.environ.setdefault("LEIGOD_TOKEN_ENV", cfg["token_env"])
os.environ.setdefault("LEIGOD_ALLOWED_IDS", ",".join(cfg["allowed_ids"]))
os.environ.setdefault("LEIGOD_TZ", cfg["tz"])
os.environ.setdefault("LEIGOD_STATE_DIR", cfg["state_dir"])

from leigod_cmd import handle  # noqa: E402

GOOD = cfg["allowed_ids"][0]
BAD = "0000000000000000DEADBEEF00000000"

CASES = [
    ("/l h", GOOD, True, "帮助"),
    ("/l s", GOOD, True, "状态"),
    ("/l nope", GOOD, True, "未知指令"),
    ("/l u", GOOD, True, "缺参数"),
    ("/l s extra", GOOD, True, "多参数"),
    ("/l p", BAD, True, "非白名单"),
    ("/l s", GOOD, False, "群聊拦截"),
]

fails = 0
for text, sender, private, label in CASES:
    out = handle(text, sender_id=sender, is_private=private)
    head = out.splitlines()[0] if out else "(空)"
    ok = bool(out)
    if label == "非白名单":
        ok = "无权限" in out
    elif label == "群聊拦截":
        ok = "私聊" in out
    elif label == "未知指令":
        ok = "未知指令" in out
    elif label == "缺参数":
        ok = "缺少 Token" in out
    elif label == "多参数":
        ok = "不接受参数" in out
    if not ok:
        fails += 1
    print(f"[{'OK ' if ok else 'FAIL'}] {label:8s} {text:14s} -> {head}")

print(f"\n结果：{'全部通过' if fails == 0 else str(fails) + ' 项失败'}")
