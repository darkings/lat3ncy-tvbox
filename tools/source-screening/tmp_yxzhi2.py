#!/usr/bin/env python3
"""yxzhi 页面配置：合并 maccms 去重 + 检查无 maccms 新配置的 type 分布。"""

import json
import os
import re
import sys
import urllib.request
from collections import Counter
from urllib.parse import quote, urlsplit, urlunsplit

sys.stdout.reconfigure(encoding="utf-8")
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}


def to_ascii(url: str) -> str:
    parts = urlsplit(url)
    try:
        host = parts.hostname.encode("idna").decode("ascii")
    except Exception:
        host = parts.hostname
    port = f":{parts.port}" if parts.port else ""
    path = quote(parts.path, safe="/%")
    return urlunsplit((parts.scheme, host + port, path, parts.query, parts.fragment))


def strip_json_comments(text: str) -> str:
    lines = []
    for line in text.splitlines():
        s = line.lstrip()
        if s.startswith("//") or s.startswith("/*"):
            continue
        lines.append(line)
    return "\n".join(lines)


def fetch(url: str, timeout: int = 20) -> bytes:
    req = urllib.request.Request(to_ascii(url), headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


# 1. 无 maccms 新配置的 type 分布
for name, url in [
    ("qist-fty", "https://qist.wyfc.qzz.io/fty.json"),
    ("qist-xiaosa", "https://qist.wyfc.qzz.io/xiaosa/api.json"),
    ("124.223.214.31", "http://124.223.214.31:8/api.json"),
    ("47.96.82.41", "http://47.96.82.41:5188/api.json"),
]:
    try:
        body = fetch(url)
        j = json.loads(strip_json_comments(body.decode("utf-8-sig", errors="replace")))
        sites = j.get("sites") or []
        tc = Counter(s.get("type") for s in sites)
        print(f"[{name}] sites={len(sites)} type分布={dict(tc)}")
        for s in sites[:6]:
            print(
                f"    {s.get('name', '?')[:20]:<22} type={s.get('type')} {(s.get('api') or '')[:60]}"
            )
    except Exception as e:
        print(f"[{name}] ERR {e}")

# 2. 合并 yxzhi_*.json 的 maccms
print()
all_m = {}
for fn in os.listdir("c:/tmp"):
    if fn.startswith("yxzhi_") and fn.endswith(".json"):
        with open(f"c:/tmp/{fn}", encoding="utf-8") as f:
            lst = json.load(f)
        for s in lst:
            api = s.get("api") or ""
            if not api:
                continue
            host = re.sub(r"^https?://", "", api).split("/")[0].lower()
            if host.startswith("www."):
                host = host[4:]
            host = host.split(":")[0]
            all_m.setdefault(host, {"name": s.get("name", "?"), "api": api, "src": fn})
print(f"合并 maccms: {len(all_m)}")
for h, v in sorted(all_m.items()):
    print(f"  {h:<32} {v['name']:<16} {v['api'][:70]}")

with open("c:/tmp/yxzhi_merged.json", "w", encoding="utf-8") as f:
    json.dump(all_m, f, ensure_ascii=False, indent=1)
