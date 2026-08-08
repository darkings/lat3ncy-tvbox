#!/usr/bin/env python3
"""对比 tv.json 中的 maccms 源与数据库 raw_source，列出未入库的新源。"""

import json
import re
import sqlite3
from urllib.parse import urlparse

DB = "/opt/ponyo-source-manager/data/sources.db"

with open("/tmp/tv.json", encoding="utf-8") as f:
    data = json.load(f)

EXCLUDE_HOSTS = ["127.0.0.1", "localhost", "m1839732.ca.caoni.ru"]
EXCLUDE_GROUP = {"18+"}


def host_of(api: str) -> str:
    u = urlparse(api if "://" in api else "http://" + api)
    return (u.hostname or "").lower()


def norm_host(h: str) -> str:
    """归一化 host：去 www. 前缀、去端口。"""
    h = h.lower()
    if h.startswith("www."):
        h = h[4:]
    return h.split(":")[0]


# 1. 收集 tv.json 中所有 maccms 源
tv_sources = []
seen = set()
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
    host = host_of(api)
    if not host or any(x in host for x in EXCLUDE_HOSTS):
        continue
    key = norm_host(host)
    if key in seen:
        continue
    seen.add(key)
    tv_sources.append(
        {
            "name": s.get("name", "?"),
            "api": api,
            "host": key,
            "cats": s.get("categories") or [],
        }
    )

print(f"tv.json maccms 源(去重后): {len(tv_sources)}")

# 2. 读数据库 raw_source
con = sqlite3.connect(DB)
rows = con.execute("SELECT id, name, api FROM raw_source").fetchall()
db_hosts = set()
db_apis = set()
for rid, rname, rapi in rows:
    if rapi:
        db_apis.add(rapi)
        db_hosts.add(norm_host(host_of(rapi)))
print(f"数据库 raw_source: {len(rows)}")

# 3. 比对：按 host 归一化
new_by_host = [s for s in tv_sources if s["host"] not in db_hosts]
print(f"host 未入库: {len(new_by_host)}")
for s in sorted(new_by_host, key=lambda x: x["host"]):
    flags = []
    joined = ",".join(s["cats"])
    if any("纪录" in c or "记录" in c or "documentary" in c.lower() for c in s["cats"]):
        flags.append("纪录片")
    if any("综艺" in c for c in s["cats"]):
        flags.append("综艺")
    if any("动漫" in c or "动画" in c for c in s["cats"]):
        flags.append("动漫")
    tag = (" [" + "/".join(flags) + "]") if flags else ""
    print(f"  {s['host']:<32} {s['name']:<14} {s['api'][:70]}{tag}")

# 4. 已有入库但可能以其他形式存在的
print()
print("== host 已入库的 tv.json 源（参考，不再导入）==")
existing = [s for s in tv_sources if s["host"] in db_hosts]
for s in sorted(existing, key=lambda x: x["host"]):
    print(f"  {s['host']:<32} {s['name']:<14}")

con.close()
