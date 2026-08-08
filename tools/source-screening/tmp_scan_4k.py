#!/usr/bin/env python3
"""正则扫描小盒子4K 配置中的 maccms API URL。"""

import json
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")

raw = open("/tmp/tvbox_configs/___4K.bin", "rb").read()
text = raw.decode("utf-8-sig", errors="replace")

# 找 "name": "xxx", "type": N, "api": "URL" 结构（TVBox sites 格式）
pat = re.compile(
    r'"name"\s*:\s*"([^"]+)"[^{}]*?"type"\s*:\s*(\d)[^{}]*?"api"\s*:\s*"([^"]+)"', re.S
)
hits = []
for m in pat.finditer(text):
    name, typ, api = m.group(1), m.group(2), m.group(3)
    if any(k in api for k in ("provide/vod", "inc/api.php", "seacmsapi", "api_mac10")):
        hits.append({"name": name, "type": int(typ), "api": api})

# 去重
seen = set()
uniq = []
for h in hits:
    if h["api"] not in seen:
        seen.add(h["api"])
        uniq.append(h)

print(f"正则命中 maccms: {len(uniq)}")
for h in uniq[:40]:
    print(f"  {h['name']:<18} type={h['type']} {h['api'][:85]}")

with open("/tmp/tvbox_configs/4k_maccms.json", "w", encoding="utf-8") as f:
    json.dump(uniq, f, ensure_ascii=False, indent=1)
print("已保存 /tmp/tvbox_configs/4k_maccms.json")
