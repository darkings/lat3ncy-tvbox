import json
import re

with open("/tmp/tv.json", encoding="utf-8") as f:
    data = json.load(f)

EXCLUDE_HOSTS = ["127.0.0.1", "localhost", "m1839732.ca.caoni.ru"]
EXCLUDE_GROUP = {"18+"}
SEEN = set()

print("== maccms type sources ==")
for s in data.get("sites", []):
    api = s.get("api") or ""
    if (
        "provide/vod" not in api
        and "inc/api.php" not in api
        and "seacmsapi" not in api
        and "api_mac10" not in api
    ):
        continue
    if s.get("group") in EXCLUDE_GROUP:
        continue
    host = re.sub(r"^https?://", "", api).split("/")[0]
    if any(x in host for x in EXCLUDE_HOSTS):
        continue
    key = host
    if key in SEEN:
        continue
    SEEN.add(key)
    cats = s.get("categories") or []
    print(f"{s.get('name', '?'):<16} {api[:90]}")
    if cats:
        # 标记分类配额相关
        joined = ",".join(cats)
        flags = []
        if any("纪录" in c or "记录" in c or "documentary" in c.lower() for c in cats):
            flags.append("纪录片")
        if any("综艺" in c for c in cats):
            flags.append("综艺")
        if any("动漫" in c or "动画" in c for c in cats):
            flags.append("动漫")
        if flags:
            print(f"    -> 含: {'/'.join(flags)}")
