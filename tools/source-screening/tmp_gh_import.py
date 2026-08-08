#!/usr/bin/env python3
"""导入 GitHub 特征扫描发现的 18 个可用源。"""

import hashlib
import json
import sys

sys.stdout.reconfigure(encoding="utf-8")

OK = [
    ("lbapiby.com", "http://lbapiby.com/api.php/provide/vod"),
    ("api.apibdzy.com", "http://api.apibdzy.com/api.php/provide/vod"),
    ("api.wsyzy.net", "https://api.wsyzy.net/api.php/provide/vod"),
    ("hsckzy.xyz", "https://hsckzy.xyz/api.php/provide/vod"),
    ("tyyszyapi.com", "https://tyyszyapi.com/api.php/provide/vod"),
    ("api.souavzyw.net", "https://api.souavzyw.net/api.php/provide/vod"),
    ("jyzyapi.com", "https://jyzyapi.com/provide/vod/from/jinyingyun/at/json"),
    ("caiji.dbzy5.com", "https://caiji.dbzy5.com/api.php/provide/vod"),
    ("xingba222.com", "https://xingba222.com/api.php/provide/vod"),
    ("xingba111.com", "https://xingba111.com/api.php/provide/vod"),
    ("360zyzz.com", "https://360zyzz.com/api.php/provide/vod"),
    ("huyaapi.com", "https://www.huyaapi.com/api.php/provide/vod/at/json"),
    ("heiliaozyapi.com", "https://www.heiliaozyapi.com/api.php/provide/vod"),
    ("lovedan.net", "http://lovedan.net/api.php/provide/vod"),
    ("api.xiaojizy.live", "https://api.xiaojizy.live/provide/vod"),
    ("thzy1.me", "https://thzy1.me/api.php/provide/vod"),
    ("api.souavzy.vip", "https://api.souavzy.vip/api.php/provide/vod"),
    ("api.douapi.cc", "https://api.douapi.cc/api.php/provide/vod"),
]

NAME_HINT = {
    "wsyzy.net": "网视资源",
    "hsckzy.xyz": "黑山采集",
    "tyyszyapi.com": "天涯API",
    "souavzyw.net": "搜爱资源",
    "souavzy.vip": "搜爱VIP",
    "dbzy5.com": "豆瓣采集5",
    "xingba111.com": "星吧1",
    "xingba222.com": "星吧2",
    "360zyzz.com": "360ZZ",
    "heiliaozyapi.com": "黑料资源",
    "xiaojizy.live": "小鸡资源",
    "thzy1.me": "THZY",
    "douapi.cc": "豆瓣API",
    "wsyzy": "网视",
    "jyzyapi.com": "金鹰线路",
}

sites = []
for host, api in OK:
    hint = NAME_HINT.get(host.split(".")[0] + "." + host.split(".")[1], host)
    key = hashlib.sha256(api.encode()).hexdigest()[:12]
    sites.append(
        {
            "key": key,
            "name": f"{hint}┃GH",
            "type": 0,
            "api": api,
            "ext": "",
            "remark": "github-feature-scan 2026-08-08",
        }
    )

with open("/tmp/gh_ponyo.json", "w", encoding="utf-8") as f:
    json.dump({"sites": sites}, f, ensure_ascii=False, indent=1)
with open("/tmp/gh_health.json", "w", encoding="utf-8") as f:
    json.dump({"sites": []}, f)
with open("/tmp/gh_namemap.json", "w", encoding="utf-8") as f:
    json.dump({"map": []}, f)
print(f"生成 {len(sites)} 个")
for s in sites:
    print(f"  {s['name']:<14} {s['api'][:70]}")
