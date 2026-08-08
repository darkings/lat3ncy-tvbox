#!/usr/bin/env python3
"""下载 awesome-zhuiju-free 的 15 个 TVBox 配置并解析 maccms 源（v2）。"""

import json
import os
import re
import sys
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

OUT = "/tmp/tvbox_configs"
os.makedirs(OUT, exist_ok=True)

CONFIGS = [
    ("饭太硬", "http://www.饭太硬.net/tv"),
    ("肥猫", "http://肥猫.net/"),
    ("老刘备", "https://raw.liucn.cc/box/m.json"),
    ("小马", "https://szyyds.cn/tv/x.json"),
    ("摸鱼儿", "http://摸鱼儿.cc"),
    ("王二小", "http://new.王二小放牛娃.top"),
    ("小盒子4K", "http://xhztv.top/4k.json"),
    ("小盒子单仓", "http://xhztv.top/xhz"),
    ("VOX", "http://rihou.cc:88/demo.php"),
    ("嗷呜", "http://itv666.cc/aowu/config.webp"),
    ("无名", "https://6800.kstore.vip/fish.json"),
    ("小盒子多仓", "http://xhztv.top/dc"),
    ("拾光多仓", "http://xmbjm.fh4u.org/dc.txt"),
    ("挺好分享多仓", "http://ztha.top/TVBox/GYCK.json"),
]


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
    req = urllib.request.Request(
        to_ascii(url),
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def strip_json_comments(text: str) -> str:
    """去掉 TVBox 配置常见的行首 // 注释。"""
    lines = []
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("//") or stripped.startswith("/*"):
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


def analyze(name: str, url: str, body: bytes, depth: int = 0):
    indent = "  " * depth
    text = body.decode("utf-8", errors="replace")
    stripped = strip_json_comments(text)
    j = None
    try:
        j = json.loads(stripped)
    except Exception:
        pass
    if j is not None:
        sites = j.get("sites") or []
        maccms = extract_maccms(sites)
        print(f"{indent}[{name}] JSON sites={len(sites)} maccms={len(maccms)}")
        for m in maccms[:20]:
            print(f"{indent}  {m['name']:<18} {m['api'][:85]}")
        fn = f"{OUT}/{re.sub(r'[^a-zA-Z0-9]', '_', name)}_maccms.json"
        with open(fn, "w", encoding="utf-8") as f:
            json.dump(maccms, f, ensure_ascii=False, indent=1)
        # 多仓：内部引用其他配置
        for k in ("urls", "subscriptions", "stores"):
            v = j.get(k)
            if isinstance(v, list) and v and isinstance(v[0], str):
                print(f"{indent}  多仓字段 {k}: {len(v)} 个子配置")
        return
    # 非 JSON：多仓文本？
    lines = [
        l.strip()
        for l in text.splitlines()
        if l.strip() and not l.strip().startswith("#")
    ]
    if lines and all(l.startswith("http") for l in lines[:5]):
        print(f"{indent}[{name}] 多仓文本 {len(lines)} 个子配置")
        for l in lines[:25]:
            print(f"{indent}  - {l[:90]}")
        return
    # HTML/其他
    head = text[:120].replace("\n", " ")
    print(f"{indent}[{name}] 非JSON size={len(body)} head={head}")


for name, url in CONFIGS:
    try:
        body = fetch(url)
        analyze(name, url, body)
    except Exception as e:
        print(f"[{name}] ERR {type(e).__name__}: {e}")
