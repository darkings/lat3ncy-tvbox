#!/usr/bin/env python3
"""地址级复查：外部配置的 maccms 完整地址 vs 库（normalize 后比对）。

找出"host 已在库但完整地址（含路径/线路）不在库"的变体并探测。
"""

import json
import re
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import parse_qsl, urlencode, urlparse, urlsplit, urlunsplit

sys.stdout.reconfigure(encoding="utf-8")
DB = "/opt/ponyo-source-manager/data/sources.db"
TIMEOUT = 12


def host_of(api: str) -> str:
    u = urlparse(api if "://" in api else "http://" + api)
    return (u.hostname or "").lower()


def norm_host(h: str) -> str:
    h = h.lower()
    if h.startswith("www."):
        h = h[4:]
    return h.split(":")[0]


def normalize_endpoint(url: str) -> str | None:
    """与 maccms_collector.normalize_endpoint 一致。"""
    parts = urlsplit(url.strip())
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return None
    path_lower = parts.path.lower().rstrip("/")
    markers = ("/api.php/provide/vod", "/provide/vod", "/cjapi/", "/inc/api.php")
    if not any(m in path_lower for m in markers):
        return None
    ignored = {"ac", "action", "wd", "ids", "pg", "page", "limit"}
    query = urlencode(
        [(k, v) for k, v in parse_qsl(parts.query) if k.lower() not in ignored]
    )
    return urlunsplit(
        (parts.scheme, parts.netloc, parts.path.rstrip("/") + "/", query, "")
    )


# 1. 收集外部配置的 maccms 完整地址
external = {}  # normalized -> {name, api, src}


def add(api, name, src):
    if not api:
        return
    n = normalize_endpoint(api)
    if n:
        external.setdefault(n, {"name": name, "api": api, "src": src})


# tv.json（TVBox-Suite 全量）
data = json.load(open("/tmp/tv.json", encoding="utf-8"))
for s in data.get("sites", []):
    api = s.get("api") or ""
    if any(m in api for m in ("provide/vod", "inc/api.php", "seacmsapi", "api_mac10")):
        add(api, s.get("name", "?"), "tvbox-suite")

# 服务器 maccms 提取文件
import os

for d in ("/tmp/tvbox_configs", "/tmp/tvbox_configs2"):
    for fn in os.listdir(d):
        if fn.endswith("_maccms.json"):
            try:
                lst = json.load(open(f"{d}/{fn}", encoding="utf-8"))
                for s in lst:
                    add(
                        s.get("api", ""), s.get("name", "?"), f"{d.split('/')[-1]}/{fn}"
                    )
            except Exception:
                pass

# yxzhi / qist
for fn, tag in (("/tmp/yxzhi_merged.json", "yxzhi"), ("/tmp/qist_merged.json", "qist")):
    try:
        m = json.load(open(fn, encoding="utf-8"))
        for h, v in m.items():
            add(v.get("api", ""), v.get("name", "?"), tag)
    except Exception:
        pass

print(f"外部规范化地址总数: {len(external)}")

# 2. 库：normalize 所有 raw_source api
con = sqlite3.connect(DB)
rows = con.execute(
    "SELECT id, name, api FROM raw_source WHERE api IS NOT NULL AND api <> ''"
).fetchall()
con.close()
db_norm = {}  # normalized -> raw_id
db_hosts = set()
for rid, rname, rapi in rows:
    n = normalize_endpoint(rapi)
    if n:
        db_norm.setdefault(n, rid)
        db_hosts.add(norm_host(host_of(n)))

print(f"库规范化地址: {len(db_norm)}")

# 3. 找出变体：host 在库但完整地址不在库
variants = []
for n, v in external.items():
    if n in db_norm:
        continue
    if norm_host(host_of(n)) in db_hosts:
        variants.append(
            {"norm": n, "name": v["name"], "api": v["api"], "src": v["src"]}
        )

print(f"\n== host 在库但地址不在库的变体: {len(variants)} ==")
for v in sorted(variants, key=lambda x: x["norm"]):
    print(f"  {v['norm'][:75]:<78} [{v['src']}]")

with open("/tmp/address_variants.json", "w", encoding="utf-8") as f:
    json.dump(variants, f, ensure_ascii=False, indent=1)
