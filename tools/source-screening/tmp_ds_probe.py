#!/usr/bin/env python3
"""定向实测高价值 DS 源（drpy-node 本地 API）。"""

import json
import sys
import urllib.parse
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")
PWD = "ponyo-local-drpy"
BASE = f"http://127.0.0.1:5757/api/{{name}}?pwd={PWD}"

TARGETS = [
    ("哔哩少儿[官]", "小猪佩奇"),
    ("央视大全[官]", "新闻"),
    ("樱花动漫[优]", "海贼王"),
    ("短剧聚合[短]", "逆袭"),
    ("人人影视[优]", "流浪地球"),
    ("剧海影视[优]", "庆余年"),
]


def fetch(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": "okhttp/4.9.2"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


for name, kw in TARGETS:
    print(f"== {name} ==")
    try:
        # 1. 首页/列表
        body = fetch(BASE.format(name=urllib.parse.quote(name)))
        text = body.decode("utf-8", errors="replace")
        try:
            j = json.loads(text)
            lst = j.get("list") or []
            print(f"  [列表] {len(lst)} 条")
            if lst:
                v = lst[0]
                print(
                    f"    样例: {v.get('vod_name')} | {v.get('type_name')} | from={v.get('vod_play_from')}"
                )
        except Exception:
            print(f"  [列表] 非JSON {text[:80]}")
        # 2. 搜索
        body2 = fetch(
            BASE.format(name=urllib.parse.quote(name)) + f"&wd={urllib.parse.quote(kw)}"
        )
        text2 = body2.decode("utf-8", errors="replace")
        try:
            j2 = json.loads(text2)
            lst2 = j2.get("list") or []
            print(f"  [搜索{kw}] {len(lst2)} 条")
            if lst2:
                v2 = lst2[0]
                print(
                    f"    命中: {v2.get('vod_name')} | from={v2.get('vod_play_from')} | remarks={v2.get('vod_remarks')}"
                )
        except Exception:
            print(f"  [搜索] 非JSON {text2[:80]}")
    except Exception as e:
        print(f"  ERR {type(e).__name__}: {str(e)[:80]}")
    print()
