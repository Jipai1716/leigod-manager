import json
import shutil
import time

CFG = "/AstrBot/data/cmd_config.json"
OPENID = "240D98E4641A656E85DCBF578A1AAC96"

backup = CFG + ".bak." + time.strftime("%Y%m%d-%H%M%S")
shutil.copy2(CFG, backup)
print("backup ->", backup)

with open(CFG, encoding="utf-8-sig") as fh:
    d = json.load(fh)

for entry in d.get("platform", []):
    if entry.get("id") == "Hex":
        entry["enable"] = False
        print("Hex.enable -> False")

ps = d.setdefault("platform_settings", {})
wl = ps.get("id_whitelist") or []
if OPENID in wl:
    wl.remove(OPENID)
    ps["id_whitelist"] = wl
print("id_whitelist ->", ps.get("id_whitelist"))

with open(CFG, "w", encoding="utf-8") as fh:
    json.dump(d, fh, ensure_ascii=False, indent=2)
print("已恢复：平台适配器全部关闭，白名单清空")
