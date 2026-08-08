#!/usr/bin/env python3
"""导入 9 个可用地址级变体。"""

import json
import sys

sys.stdout.reconfigure(encoding="utf-8")

data = json.load(open("/tmp/address_variants_probe.json", encoding="utf-8"))
ok = data["ok"]
print(f"可用变体: {len(ok)}")

sites = []
for r in ok:
    v = r["v"]
    api = v["api"]
    host = api.split("/")[2] if "://" in api else api
    # key 用完整地址哈希尾部避免冲突
    import hashlib

    key = hashlib.sha256(api.encode()).hexdigest()[:12]
    sites.append(
        {
            "key": key,
            "name": f"{v['name']}┃变体",
            "type": 0,
            "api": api,
            "ext": "",
            "remark": f"addr-audit 2026-08-08 [{v['src']}]",
        }
    )

ponyo = {"sites": sites}
with open("/tmp/addr_ponyo.json", "w", encoding="utf-8") as f:
    json.dump(ponyo, f, ensure_ascii=False, indent=1)
with open("/tmp/addr_health.json", "w", encoding="utf-8") as f:
    json.dump({"sites": []}, f)
with open("/tmp/addr_namemap.json", "w", encoding="utf-8") as f:
    json.dump({"map": []}, f)
print(f"生成 {len(sites)} 个导入文件")
for s in sites:
    print(f"  {s['api'][:75]}")
