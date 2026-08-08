#!/usr/bin/env python3
"""下载 qist/tvbox 核心配置 + 江江站配置，解析 maccms。"""
import json
import re
import sys
import urllib.request
import urllib.error
from urllib.parse import urlsplit, urlunsplit, quote

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


def fetch(url: str, timeout: int = 25) -> bytes:
    req = urllib.request.Request(to_ascii(url), headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def extract_maccms(sites: list) -> list:
    out = []
    for s in sites:
        api = s.get("api") or ""
        if not api:
            continue
        if any(m in api for m in ("/api.php/provide/vod", "/provide/vod", "/inc/api.php", "seacmsapi", "api_mac10")):
            out.append({"name": s.get("name", "?"), "api": api, "type": s.get("type")})
    return out


CONFIGS = [
    ("qist-jsm", "https://qist.wyfc.qzz.io/jsm.json"),
    ("qist-jsm-raw", "https://raw.githubusercontent.com/qist/tvbox/master/jsm.json"),
    ("qist-0821", "https://raw.githubusercontent.com/qist/tvbox/master/0821.json"),
    ("jiangjiang", "http://8.129.22.85/Jiang.json"),
    ("jiangjiang-tv", "http://tv.江江.com/18.json"),
]

merged = []
for name, url in CONFIGS:
    try:
        body = fetch(url)
        text = body.decode("utf-8-sig", errors="replace")
        j = None
        try:
            j = json.loads(strip_json_comments(text))
        except Exception:
            pass
        if j:
            sites = j.get("sites") or []
            maccms = extract_maccms(sites)
            urls_field = j.get("urls") or []
            print(f"[{name}] sites={len(sites)} maccms={len(maccms)} urls={len(urls_field)}")
            for m in maccms[:20]:
                print(f"    {m['name']:<16} {m['api'][:75]}")
            merged.extend(maccms)
            if maccms:
                with open(f"c:/tmp/{name}_maccms.json", "w", encoding="utf-8") as f:
                    json.dump(maccms, f, ensure_ascii=False, indent=1)
        else:
            print(f"[{name}] 非JSON {len(body)}B {text[:80].replace(chr(10),' ')}")
    except urllib.error.HTTPError as e:
        print(f"[{name}] HTTP {e.code}")
    except Exception as e:
        print(f"[{name}] {type(e).__name__}: {str(e)[:60]}")

# 去重
seen = set()
uniq = []
for m in merged:
    host = re.sub(r"^https?://", "", m["api"]).split("/")[0].lower()
    if host.startswith("www."):
        host = host[4:]
    host = host.split(":")[0]
    if host in seen:
        continue
    seen.add(host)
    m["host"] = host
    uniq.append(m)

with open("c:/tmp/qist_merged.json", "w", encoding="utf-8") as f:
    json.dump(uniq, f, ensure_ascii=False, indent=1)
print(f"\n合并去重: {len(uniq)}")
for m in uniq:
    print(f"  {m['host']:<30} {m['name']:<16} {m['api'][:70]}")
