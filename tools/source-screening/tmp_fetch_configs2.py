#!/usr/bin/env python3
"""v3：BOM 处理 + 多仓展开 + 老刘备 maccms 去重。"""

import json
import os
import re
import sys
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

OUT = "/tmp/tvbox_configs"
os.makedirs(OUT, exist_ok=True)
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}


def to_ascii(url: str) -> str:
    from urllib.parse import urlsplit, urlunsplit

    parts = urlsplit(url)
    try:
        host = parts.hostname.encode("idna").decode("ascii")
    except Exception:
        return url
    port = f":{parts.port}" if parts.port else ""
    return urlunsplit(
        (parts.scheme, host + port, parts.path, parts.query, parts.fragment)
    )


def fetch(url: str, timeout: int = 25) -> bytes:
    req = urllib.request.Request(to_ascii(url), headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def strip_json_comments(text: str) -> str:
    lines = []
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("//") or stripped.startswith("/*"):
            continue
        lines.append(line)
    return "\n".join(lines)


def parse(body: bytes):
    for enc in ("utf-8-sig", "utf-8", "gbk"):
        try:
            text = body.decode(enc)
            return text, json.loads(strip_json_comments(text))
        except Exception:
            continue
    return None, None


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


def save_maccms(tag: str, maccms: list):
    if not maccms:
        return
    fn = f"{OUT}/{re.sub(r'[^a-zA-Z0-9]', '_', tag)}_maccms.json"
    with open(fn, "w", encoding="utf-8") as f:
        json.dump(maccms, f, ensure_ascii=False, indent=1)
    print(f"  保存 {len(maccms)} 个 -> {fn}")


# 1. 重新解析小马 / 小盒子4K（BOM）
for name, url in [
    ("小马", "https://szyyds.cn/tv/x.json"),
    ("小盒子4K", "http://xhztv.top/4k.json"),
]:
    try:
        body = fetch(url)
        text, j = parse(body)
        if j:
            sites = j.get("sites") or []
            m = extract_maccms(sites)
            print(f"[{name}] JSON sites={len(sites)} maccms={len(m)}")
            for x in m[:30]:
                print(f"  {x['name']:<18} {x['api'][:85]}")
            save_maccms(name, m)
        else:
            print(f"[{name}] 解析失败 head={text[:100] if text else ''}")
    except Exception as e:
        print(f"[{name}] ERR {e}")

# 2. 多仓展开
print()
MULTI = [
    ("小盒子多仓", "http://xhztv.top/dc"),
    ("拾光多仓", "http://xmbjm.fh4u.org/dc.txt"),
]
all_maccms = {}
for name, url in MULTI:
    try:
        body = fetch(url)
        text, j = parse(body)
        if not j or not isinstance(j.get("urls"), list):
            print(f"[{name}] 无 urls 字段 {text[:120] if text else ''}")
            continue
        subs = j["urls"]
        print(f"[{name}] {len(subs)} 个子配置")
        for sub in subs:
            subname = sub.get("name", "?") if isinstance(sub, dict) else str(sub)[:30]
            suburl = sub.get("url") if isinstance(sub, dict) else str(sub)
            if not suburl or "禁止" in str(subname) or "禁售" in str(subname):
                continue
            try:
                sbody = fetch(suburl)
                stext, sj = parse(sbody)
                if sj:
                    ssites = sj.get("sites") or []
                    m = extract_maccms(ssites)
                    if m:
                        print(f"  [{subname}] sites={len(ssites)} maccms={len(m)}")
                        for x in m[:8]:
                            print(f"      {x['name']:<16} {x['api'][:80]}")
                        all_maccms.setdefault(subname, []).extend(m)
                    else:
                        print(f"  [{subname}] sites={len(ssites)} maccms=0")
                else:
                    print(
                        f"  [{subname}] 非JSON {len(sbody)}B head={stext[:80] if stext else ''}"
                    )
            except Exception as e:
                print(f"  [{subname}] ERR {type(e).__name__} {e}")
    except Exception as e:
        print(f"[{name}] ERR {e}")

if all_maccms:
    save_maccms("multi_all", [s for v in all_maccms.values() for s in v])
