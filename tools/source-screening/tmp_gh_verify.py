#!/usr/bin/env python3
"""抽查 GitHub 特征扫描新源的内容。"""

import json
import sys
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

for name, api in [
    ("黑料", "https://www.heiliaozyapi.com/api.php/provide/vod"),
    ("天涯API", "https://tyyszyapi.com/api.php/provide/vod"),
    ("星吧1", "https://xingba111.com/api.php/provide/vod"),
    ("豆瓣5", "https://caiji.dbzy5.com/api.php/provide/vod"),
    ("搜爱", "https://api.souavzyw.net/api.php/provide/vod"),
    ("网视", "https://api.wsyzy.net/api.php/provide/vod"),
    ("小鸡", "https://api.xiaojizy.live/provide/vod"),
    ("360ZZ", "https://360zyzz.com/api.php/provide/vod"),
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
                f"{name}: {v.get('vod_name')} | {v.get('type_name')} | from={v.get('vod_play_from')} | {v.get('vod_remarks')}"
            )
        else:
            print(f"{name}: 空")
    except Exception as e:
        print(f"{name}: ERR {type(e).__name__}")
