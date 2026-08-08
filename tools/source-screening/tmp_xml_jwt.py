#!/usr/bin/env python3
"""测试 XML 源是否支持 at=json 切换，以及 JWT 跳转源是否可跟随。"""

import json
import time
import urllib.error
import urllib.request

TIMEOUT = 15

TESTS = [
    ("乐多资源 XML->JSON", "http://cj.leduocaiji.com/inc/api.php", "at=json"),
    (
        "快看资源 XML->JSON",
        "https://kuaikan-api.com/api.php/provide/vod/from/kuaikanyun",
        "at=json",
    ),
    ("乐多资源 默认", "http://cj.leduocaiji.com/inc/api.php", ""),
    (
        "快看资源 默认",
        "https://kuaikan-api.com/api.php/provide/vod/from/kuaikanyun",
        "",
    ),
]

for name, api, extra in TESTS:
    sep = "&" if "?" in api else "?"
    url = api + sep + "ac=list" + (("&" + extra) if extra else "")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            body = resp.read(400 * 1024)
        text = body.decode("utf-8", errors="replace")
        head = text[:150].replace("\n", " ")
        try:
            j = json.loads(text)
            lst = j.get("list") or (j.get("data") or {}).get("list") or []
            print(f"{name}: JSON n={len(lst)}  {head}")
        except Exception:
            print(f"{name}: 非JSON  {head}")
    except Exception as e:
        print(f"{name}: ERR {e}")

# JWT 跳转源：跟随 redirect + 试 js 参数
print()
JWT_SOURCES = [
    ("234影视", "https://www.knyu.net/api.php/provide/vod/"),
    ("MBO影视", "https://www.mbomovie.com/api.php/provide/vod/at/xml/"),
    ("FOX资源", "https://api.foxzyapi.com/api.php/provide/vod/"),
]
for name, api in JWT_SOURCES:
    sep = "&" if "?" in api else "?"
    url = api + sep + "ac=list"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            body = resp.read(400 * 1024)
            final = resp.geturl()
        text = body.decode("utf-8", errors="replace")
        # 提取 JS 跳转 URL
        import re

        m = re.search(r"location\.replace\('([^']+)'\)", text)
        if m:
            target = m.group(1)
            print(f"{name}: JS跳转 -> {target[:100]}")
            # 尝试跟随
            try:
                req2 = urllib.request.Request(
                    target, headers={"User-Agent": "Mozilla/5.0"}
                )
                with urllib.request.urlopen(req2, timeout=TIMEOUT) as resp2:
                    body2 = resp2.read(400 * 1024)
                text2 = body2.decode("utf-8", errors="replace")
                head2 = text2[:150].replace("\n", " ")
                try:
                    j = json.loads(text2)
                    lst = j.get("list") or (j.get("data") or {}).get("list") or []
                    print(f"    跟随成功 JSON n={len(lst)}")
                except Exception:
                    print(f"    跟随返回: {head2}")
            except Exception as e:
                print(f"    跟随失败: {e}")
        else:
            print(f"{name}: 无JS跳转 final={final} head={text[:120]}")
    except Exception as e:
        print(f"{name}: ERR {e}")
