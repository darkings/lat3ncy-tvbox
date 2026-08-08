#!/usr/bin/env python3
"""展开拾光ck多仓(56) + 神秘哥哥多仓，并合并所有新配置的 maccms。"""

import json
import os
import re
import sys
import urllib.error
import urllib.request
from urllib.parse import quote, urlsplit, urlunsplit

sys.stdout.reconfigure(encoding="utf-8")
OUT = "/tmp/tvbox_configs2"
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


def fetch(url: str, timeout: int = 20) -> bytes:
    req = urllib.request.Request(to_ascii(url), headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


# 1. 拾光 ck_github 多仓
print("== 拾光 ck 多仓 ==")
try:
    body = fetch("https://xmbjm.github.io/ck.json")
    text = body.decode("utf-8-sig", errors="replace")
    j = json.loads(strip_json_comments(text))
    subs = j.get("urls") or []
    print(f"{len(subs)} 个子配置")
    for sub in subs[:60]:
        name = sub.get("name", "?") if isinstance(sub, dict) else "?"
        url = sub.get("url", "") if isinstance(sub, dict) else str(sub)
        if not url or "禁止" in str(name) or "贩卖" in str(name) or "贩卖" in url:
            continue
        try:
            sbody = fetch(url)
            stext = sbody.decode("utf-8-sig", errors="replace")
            sj = None
            try:
                sj = json.loads(strip_json_comments(stext))
            except Exception:
                pass
            if sj:
                sites = sj.get("sites") or []
                m = extract_maccms(sites)
                if m:
                    print(f"  [{name}] sites={len(sites)} maccms={len(m)}")
                    for x in m[:6]:
                        print(f"      {x['name']:<14} {x['api'][:75]}")
                    with open(
                        f"{OUT}/ck_{re.sub(r'[^a-zA-Z0-9]', '_', name)}_maccms.json",
                        "w",
                        encoding="utf-8",
                    ) as f:
                        json.dump(m, f, ensure_ascii=False, indent=1)
            else:
                print(
                    f"  [{name}] 非JSON {len(sbody)}B {stext[:60].replace(chr(10), ' ')}"
                )
        except urllib.error.HTTPError as e:
            print(f"  [{name}] HTTP {e.code}")
        except Exception as e:
            print(f"  [{name}] {type(e).__name__}")
except Exception as e:
    print(f"ERR {e}")

# 2. 神秘哥哥多仓
print("\n== 神秘哥哥多仓 ==")
try:
    body = fetch("https://play.iptv365.org/tvbox.txt")
    text = body.decode("utf-8-sig", errors="replace")
    j = json.loads(strip_json_comments(text))
    subs = j.get("urls") or []
    print(f"{len(subs)} 个子配置")
    for sub in subs:
        name = sub.get("name", "?") if isinstance(sub, dict) else "?"
        url = sub.get("url", "") if isinstance(sub, dict) else str(sub)
        try:
            sbody = fetch(url)
            stext = sbody.decode("utf-8-sig", errors="replace")
            sj = None
            try:
                sj = json.loads(strip_json_comments(stext))
            except Exception:
                pass
            if sj:
                sites = sj.get("sites") or []
                m = extract_maccms(sites)
                print(f"  [{name}] sites={len(sites)} maccms={len(m)} {url[:60]}")
                if m:
                    with open(
                        f"{OUT}/shenmi_{re.sub(r'[^a-zA-Z0-9]', '_', name)}_maccms.json",
                        "w",
                        encoding="utf-8",
                    ) as f:
                        json.dump(m, f, ensure_ascii=False, indent=1)
            else:
                print(
                    f"  [{name}] 非JSON {len(sbody)}B {stext[:60].replace(chr(10), ' ')}"
                )
        except Exception as e:
            print(f"  [{name}] {type(e).__name__} {url[:50]}")
except Exception as e:
    print(f"ERR {e}")
