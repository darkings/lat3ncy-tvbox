#!/usr/bin/env python3
"""抽查剩余 GitHub 新源内容分类（成人/正常）。"""

import json
import sys
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

for name, api in [
    ("lbapiby", "http://lbapiby.com/api.php/provide/vod"),
    ("apibdzy-http", "http://api.apibdzy.com/api.php/provide/vod"),
    ("黑山", "https://hsckzy.xyz/api.php/provide/vod"),
    ("金鹰线路", "https://jyzyapi.com/provide/vod/from/jinyingyun/at/json"),
    ("虎牙atjson", "https://www.huyaapi.com/api.php/provide/vod/at/json"),
    ("艾旦-http", "http://lovedan.net/api.php/provide/vod"),
    ("THZY", "https://thzy1.me/api.php/provide/vod"),
    ("豆瓣API", "https://api.douapi.cc/api.php/provide/vod"),
    ("搜爱VIP", "https://api.souavzy.vip/api.php/provide/vod"),
    ("星吧2", "https://xingba222.com/api.php/provide/vod"),
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
                f"{name}: {str(v.get('vod_name'))[:30]} | {v.get('type_name')} | from={v.get('vod_play_from')}"
            )
        else:
            print(f"{name}: 空")
    except Exception as e:
        print(f"{name}: ERR {type(e).__name__}")
