import json
import shutil
import time

PATH = "/AstrBot/data/cmd_config.json"
OPENID = "240D98E4641A656E85DCBF578A1AAC96"

backup = PATH + ".bak." + time.strftime("%Y%m%d-%H%M%S")
shutil.copy2(PATH, backup)
print("backup ->", backup)

with open(PATH, encoding="utf-8-sig") as fh:
    d = json.load(fh)

changed = []

# 1) 启用 qq_official 适配器（Hex）
for entry in d.get("platform", []):
    if entry.get("id") == "Hex" and entry.get("type") == "qq_official":
        if not entry.get("enable"):
            entry["enable"] = True
            changed.append("platform.Hex.enable=True")

# 2) AstrBot 自身白名单加入该 openid（空列表 + 开启白名单会导致全部拦截）
ps = d.setdefault("platform_settings", {})
wl = ps.get("id_whitelist") or []
if OPENID not in wl:
    wl.append(OPENID)
    ps["id_whitelist"] = wl
    changed.append("platform_settings.id_whitelist += openid")

with open(PATH, "w", encoding="utf-8") as fh:
    json.dump(d, fh, ensure_ascii=False, indent=2)

print("changed:", changed or "无")
for entry in d.get("platform", []):
    print("  platform:", entry.get("id"), entry.get("type"), "enable =", entry.get("enable"))
print("  id_whitelist:", ps.get("id_whitelist"))
