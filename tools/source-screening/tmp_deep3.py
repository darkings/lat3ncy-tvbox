#!/usr/bin/env python3
"""正则提取 heroaku spider 配置 + 神秘哥哥多仓 URL。"""

import json
import re
import sys
import urllib.request
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


def fetch(url: str, timeout: int = 25) -> bytes:
    req = urllib.request.Request(to_ascii(url), headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


# 1. heroaku
print("== heroaku 正则提取 ==")
body = fetch(
    "https://cdn.githubraw.com/xuexuguang/tvbox_spider/main/tv/kk/heroaku_dtes.json"
)
text = body.decode("utf-8-sig", errors="replace")

# sites 条目
pat = re.compile(
    r'"name"\s*:\s*"([^"]+)"[^{}]*?"type"\s*:\s*(\d)[^{}]*?"api"\s*:\s*"([^"]+)"', re.S
)
hits = pat.findall(text)
print(f"sites 正则命中: {len(hits)}")
maccms = []
t3 = []
for name, typ, api in hits:
    if any(
        m in api
        for m in (
            "/api.php/provide/vod",
            "/provide/vod",
            "/inc/api.php",
            "seacmsapi",
            "api_mac10",
        )
    ):
        maccms.append((name, typ, api))
    elif typ == "3":
        t3.append((name, api))
seen = set()
uniq_m = []
for m in maccms:
    if m[2] not in seen:
        seen.add(m[2])
        uniq_m.append(m)
print(f"maccms: {len(uniq_m)}")
for n, t, a in uniq_m:
    print(f"  {n:<18} {a[:80]}")
print(f"type3 示例: {len(t3)}")
for n, a in t3[:8]:
    print(f"  {n:<18} {a[:75]}")

# spider/jar
for m in re.finditer(r'"(spider|jar)"\s*:\s*"([^"]+)"', text):
    print(f"  {m.group(1)}: {m.group(2)[:130]}")

with open("/tmp/tvbox_configs2/heroaku_maccms.json", "w", encoding="utf-8") as f:
    json.dump(
        [{"name": n, "api": a, "type": int(t)} for n, t, a in uniq_m],
        f,
        ensure_ascii=False,
        indent=1,
    )

# 2. 神秘哥哥
print("\n== 神秘哥哥多仓 URL 提取 ==")
body = fetch("https://play.iptv365.org/tvbox.txt")
text = body.decode("utf-8-sig", errors="replace")
urls = re.findall(r'"url"\s*:\s*"([^"]+)"', text)
names = re.findall(r'"name"\s*:\s*"([^"]+)"', text)
print(f"urls={len(urls)}")
for i, u in enumerate(urls[:25]):
    n = names[i] if i < len(names) else "?"
    print(f"  [{n}] {u[:80]}")
