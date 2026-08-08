#!/usr/bin/env python3
"""生成 tvbox-suite 导入所需的 ponyo.json / health.json / namemap.json。"""

import json

SOURCES = [
    {
        "key": "yhzy.cc",
        "name": "樱花资源2",
        "type": 0,
        "api": "https://yhzy.cc/api.php/provide/vod/",
        "ext": "",
        "remark": "tvbox-suite: 直链m3u8 total=101526",
    },
    {
        "key": "suboziyuan.net",
        "name": "速播",
        "type": 0,
        "api": "http://suboziyuan.net/api.php/provide/vod/",
        "ext": "",
        "remark": "tvbox-suite: 直链m3u8 total=110045",
    },
    {
        "key": "zy.xiaomaomi.cc",
        "name": "小猫咪",
        "type": 0,
        "api": "https://zy.xiaomaomi.cc/api.php/provide/vod/",
        "ext": "",
        "remark": "tvbox-suite: total=68463 需解析",
    },
    {
        "key": "api.maoyanapi.top",
        "name": "分享猫眼",
        "type": 0,
        "api": "https://api.maoyanapi.top/api.php/provide/vod/at/json",
        "ext": "",
        "remark": "tvbox-suite: 直链m3u8 total=33715 响应慢",
    },
]

ponyo = {"sites": SOURCES}
health = {"sites": []}
namemap = {"map": []}

with open("/tmp/tvbox_ponyo.json", "w", encoding="utf-8") as f:
    json.dump(ponyo, f, ensure_ascii=False, indent=2)
with open("/tmp/tvbox_health.json", "w", encoding="utf-8") as f:
    json.dump(health, f, ensure_ascii=False)
with open("/tmp/tvbox_namemap.json", "w", encoding="utf-8") as f:
    json.dump(namemap, f, ensure_ascii=False)
print("生成完成")
