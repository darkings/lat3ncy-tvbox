#!/usr/bin/env python3
"""导入 11 个 at/xml→at/json 转换成功的端点（JSON 形式）。"""

import json
import sys

sys.stdout.reconfigure(encoding="utf-8")

XML_OK = [
    "http://lbapiby.com/api.php/provide/vod/at/xml",
    "https://lbapi9.com/api.php/provide/vod/at/xml",
    "http://cj.ffzyapi.com/api.php/provide/vod/at/xml/",
    "http://fhapi9.com/api.php/provide/vod/at/xml",
    "https://cj.lziapi.com/api.php/provide/vod/at/xml/",
    "http://api.11bat.com/api.php/provide/vod/at/xml/",
    "https://www.mdzyapi.com/api.php/provide/vod/at/xml/",
    "http://sdzyapi.com/api.php/provide/vod/at/xml",
    "https://155api.com/api.php/provide/vod/at/xml",
    "https://suoniapi.com/api.php/provide/vod/at/xml/",
    "https://api.ddapi.cc/api.php/provide/vod/at/xml",
]

NAME_MAP = {
    "lbapiby.com": "LBAPI-by",
    "lbapi9.com": "LBAPI-9",
    "cj.ffzyapi.com": "非凡XML-JSON",
    "fhapi9.com": "FHAPI-9",
    "cj.lziapi.com": "量子XML-JSON",
    "api.11bat.com": "11BAT",
    "www.mdzyapi.com": "魔都资源",
    "sdzyapi.com": "闪电XML-JSON",
    "155api.com": "155API",
    "suoniapi.com": "索尼XML-JSON",
    "api.ddapi.cc": "DDAPI",
}

import hashlib

sites = []
for api in XML_OK:
    json_api = api.replace("at/xml", "at/json")
    host = json_api.split("/")[2] if "://" in json_api else json_api
    name = NAME_MAP.get(host, host)
    key = hashlib.sha256(json_api.encode()).hexdigest()[:12]
    sites.append(
        {
            "key": key,
            "name": f"{name}┃JSON",
            "type": 0,
            "api": json_api,
            "ext": "",
            "remark": "xml→json 转换 2026-08-08",
        }
    )

with open("/tmp/xmljson_ponyo.json", "w", encoding="utf-8") as f:
    json.dump({"sites": sites}, f, ensure_ascii=False, indent=1)
with open("/tmp/xmljson_health.json", "w", encoding="utf-8") as f:
    json.dump({"sites": []}, f)
with open("/tmp/xmljson_namemap.json", "w", encoding="utf-8") as f:
    json.dump({"map": []}, f)
print(f"生成 {len(sites)} 个")
for s in sites:
    print(f"  {s['api'][:75]}")
