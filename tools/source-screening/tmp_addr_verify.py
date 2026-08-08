#!/usr/bin/env python3
"""抽查变体内容质量。"""

import json
import sys
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

for name, api in [
    ("ffm3u8", "http://cj.ffzyapi.com/api.php/provide/vod/from/ffm3u8/"),
    ("snm3u8", "https://suoniapi.com/api.php/provide/vod/from/snm3u8/"),
    ("jyzyapi", "https://jyzyapi.com/provide/vod/"),
    ("gsm3u8", "https://api.guangsuapi.com/api.php/provide/vod/from/gsm3u8/"),
]:
    try:
        j = json.loads(
            urllib.request.urlopen(
                urllib.request.Request(
                    api + "?ac=list", headers={"User-Agent": "Mozilla/5.0"}
                ),
                timeout=15,
            ).read()
        )
        lst = j.get("list") or []
        if lst:
            v = lst[0]
            print(
                f"{name}: {v.get('vod_name')} | {v.get('type_name')} | from={v.get('vod_play_from')} | remarks={v.get('vod_remarks')}"
            )
        else:
            print(f"{name}: 列表空")
    except Exception as e:
        print(f"{name}: ERR {e}")
