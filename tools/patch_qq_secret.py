import json
import shutil
import time

CFG = "/AstrBot/data/cmd_config.json"
SECRET_FILE = "/tmp/qq_secret.txt"

with open(SECRET_FILE, encoding="utf-8") as fh:
    secret = fh.read().strip()

if not secret:
    raise SystemExit("QQ_APP_SECRET 为空")
print("取到 secret 长度:", len(secret))

backup = CFG + ".bak." + time.strftime("%Y%m%d-%H%M%S")
shutil.copy2(CFG, backup)
print("backup ->", backup)

with open(CFG, encoding="utf-8-sig") as fh:
    d = json.load(fh)

for entry in d.get("platform", []):
    if entry.get("id") == "Hex" and entry.get("type") == "qq_official":
        old = entry.get("secret") or ""
        entry["secret"] = secret
        print("Hex.secret 已更新：旧长度", len(old), "-> 新长度", len(secret))

with open(CFG, "w", encoding="utf-8") as fh:
    json.dump(d, fh, ensure_ascii=False, indent=2)
print("写入完成")
