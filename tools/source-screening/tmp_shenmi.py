#!/usr/bin/env python3
"""抓取神秘哥哥多仓 23 个子配置（专题频道）。"""

import json
import re
import sys
import urllib.error
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


SUBS = [
    "饭太硬",
    "小米",
    "肥猫",
    "菜妮丝",
    "王二小",
    "小虎斑",
    "摸鱼儿",
    "PG",
    "欧歌",
    "潇洒",
    "天微",
    "天天开心",
    "香雅情",
    "南风",
    "骚零",
    "白嫖",
    "OK",
    "戏曲音乐",
    "短剧频道",
    "少儿频道",
    "动漫频道",
    "iptv365直播",
]

for name in SUBS:
    url = f"https://play.iptv365.org/{name}/api.json"
    try:
        req = urllib.request.Request(to_ascii(url), headers=UA)
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = resp.read(800 * 1024)
        text = body.decode("utf-8-sig", errors="replace")
        j = None
        try:
            j = json.loads(strip_json_comments(text))
        except Exception:
            pass
        if j:
            sites = j.get("sites") or []
            maccms = extract_maccms(sites)
            t3 = [s for s in sites if s.get("type") == 3]
            print(f"[{name}] sites={len(sites)} maccms={len(maccms)} type3={len(t3)}")
            for m in maccms[:12]:
                print(f"    {m['name']:<16} {m['api'][:78]}")
            if maccms:
                with open(
                    f"/tmp/tvbox_configs2/sm_{re.sub(r'[^a-zA-Z0-9]', '_', name)}_maccms.json",
                    "w",
                    encoding="utf-8",
                ) as f:
                    json.dump(maccms, f, ensure_ascii=False, indent=1)
        else:
            print(f"[{name}] 非JSON size={len(body)} {text[:80].replace(chr(10), ' ')}")
    except urllib.error.HTTPError as e:
        print(f"[{name}] HTTP {e.code}")
    except Exception as e:
        print(f"[{name}] {type(e).__name__}")
