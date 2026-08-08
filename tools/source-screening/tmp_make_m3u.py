#!/usr/bin/env python3
"""从 ls660 iptv.txt 提取四川电信 56 频道，生成干净 M3U。"""

import re
import sys
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

text = (
    urllib.request.urlopen(
        urllib.request.Request(
            "https://www.ls660.com/TV/iptv.txt", headers={"User-Agent": "Mozilla/5.0"}
        ),
        timeout=20,
    )
    .read()
    .decode("utf-8", errors="replace")
)

lines = text.splitlines()
names = [
    re.sub(r"^#EXTINF[^,]*,", "", l).strip() for l in lines if l.startswith("#EXTINF")
]
urls = [l.strip() for l in lines if l.startswith("http")]

# 只看四川电信
pairs = [(n, u) for n, u in zip(names, urls) if "222.214.208.34" in u]
print(f"四川电信频道: {len(pairs)}")

m3u = ["#EXTM3U"]
for n, u in pairs:
    m3u.append(f'#EXTINF:-1 group-title="四川电信",{n}')
    m3u.append(u)

content = "\n".join(m3u) + "\n"
with open(
    r"C:\Users\Jie\Projects\lat3ncy-tvbox\subscription\sctv.m3u", "w", encoding="utf-8"
) as f:
    f.write(content)
print(f"已写入 subscription/sctv.m3u ({len(content)}B, {len(pairs)} 频道)")
