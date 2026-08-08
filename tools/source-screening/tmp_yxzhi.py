#!/usr/bin/env python3
"""提取 yxzhi.com/tvbox 页面全部配置 URL 并批量探测。"""

import json
import re
import sys
import urllib.error
import urllib.request
from urllib.parse import quote, urlsplit, urlunsplit

sys.stdout.reconfigure(encoding="utf-8")
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

text = open(r"c:/tmp/yxzhi.html", encoding="utf-8", errors="replace").read()

# 提取所有 URL
urls = re.findall(r"https?://[a-zA-Z0-9._~:/?#@!$&()*+,;=%-]+", text)
# 过滤配置类
CONFIG_HINTS = (
    ".json",
    ".txt",
    "/tv",
    "/dc",
    "api",
    "tvbox",
    "/m/",
    "/wex",
    "fish",
    "box",
)
candidates = []
seen = set()
for u in urls:
    u2 = u.rstrip(".,;")
    if any(k in u2 for k in CONFIG_HINTS) and u2 not in seen:
        # 排除站内资源
        if "yxzhi.com" in u2 or u2.endswith(
            (".png", ".webp", ".jpg", ".jpeg", ".css", ".js")
        ):
            continue
        seen.add(u2)
        candidates.append(u2)
print(f"配置候选: {len(candidates)}")


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


def extract_maccms(sites: list) -> list:
    out = []
    for s in sites:
        api = s.get("api") or ""
        if not api:
            continue
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
            out.append({"name": s.get("name", "?"), "api": api, "type": s.get("type")})
    return out


for name_idx, url in enumerate(candidates):
    try:
        req = urllib.request.Request(to_ascii(url), headers=UA)
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = resp.read(600 * 1024)
        text_b = body.decode("utf-8-sig", errors="replace")
        j = None
        try:
            j = json.loads(strip_json_comments(text_b))
        except Exception:
            pass
        if j:
            sites = j.get("sites") or []
            maccms = extract_maccms(sites)
            urls_field = j.get("urls") or []
            tag = f"JSON sites={len(sites)} maccms={len(maccms)} urls={len(urls_field)}"
            print(f"[{name_idx}] {url[:60]:<62} {tag}")
            for m in maccms[:6]:
                print(f"      {m['name']:<16} {m['api'][:70]}")
            if maccms:
                with open(f"c:/tmp/yxzhi_{name_idx}.json", "w", encoding="utf-8") as f:
                    json.dump(maccms, f, ensure_ascii=False, indent=1)
        else:
            lines = [
                l.strip()
                for l in text_b.splitlines()
                if l.strip() and not l.strip().startswith("#")
            ]
            if lines and all(l.startswith("http") for l in lines[:5]):
                print(f"[{name_idx}] {url[:60]:<62} 多仓文本 {len(lines)} 行")
            else:
                print(
                    f"[{name_idx}] {url[:60]:<62} 非JSON {len(body)}B {text_b[:60].replace(chr(10), ' ')}"
                )
    except urllib.error.HTTPError as e:
        print(f"[{name_idx}] {url[:60]:<62} HTTP {e.code}")
    except Exception as e:
        print(f"[{name_idx}] {url[:60]:<62} {type(e).__name__}")
