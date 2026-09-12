# -*- coding: utf-8 -*-
"""探测 TVBox jar：检查是否含 Config/LocalFile 类、是否含自杀/环境检测特征。"""

import sys
import urllib.request

CANDIDATES = [
    (
        "liuzhijun347/tvbox(master)",
        "https://raw.githubusercontent.com/liuzhijun347/tvbox/master/tvbox.jar",
    ),
    (
        "takagen99/Box(main)",
        "https://raw.githubusercontent.com/takagen99/Box/main/jar/tvbox.jar",
    ),
    (
        "takagen99/Box(main)/tvbox",
        "https://raw.githubusercontent.com/takagen99/Box/main/tvbox.jar",
    ),
    (
        "mengzhu2/ysc(master)",
        "https://raw.githubusercontent.com/mengzhu2/ysc/master/ysc.jar",
    ),
    (
        "FongMi/TV(main)",
        "https://raw.githubusercontent.com/FongMi/TV/main/jar/tvbox.jar",
    ),
    (
        "qiusang/tvbox(master)",
        "https://raw.githubusercontent.com/qiusang/tvbox/master/tvbox.jar",
    ),
]

# 自杀/环境检测特征（qist spider.jar 的包名检测 + killProcess）
BAD_PATTERNS = [
    b"killProcess",
    b"getPackageName",
    b'equalsIgnoreCase("com.darkings',
    b"android.os.Process",
]


def check(data: bytes, label: str) -> None:
    has_cfg = b"spider/Config" in data
    has_lf = b"spider/LocalFile" in data
    bad = [p.decode() for p in BAD_PATTERNS if p in data]
    print(
        f"{label}: Config={has_cfg} LocalFile={has_lf} 自杀特征={bad if bad else '无'} size={len(data)}"
    )


for label, url in CANDIDATES:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=20) as r:
            data = r.read()
        check(data, label)
    except Exception as e:
        print(f"{label}: ERR {e}")
