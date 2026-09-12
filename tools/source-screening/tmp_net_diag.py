#!/usr/bin/env python3
"""Python 连接诊断：20.205.243.166 与域名解析差异。"""

import socket
import sys
import time
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

# 1. DNS 解析
for host in [
    "raw.githubusercontent.com",
    "api.github.com",
    "codeload.github.com",
    "objects.githubusercontent.com",
]:
    try:
        infos = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        ips = [i[4][0] for i in infos[:6]]
        print(f"{host}: {ips}")
    except Exception as e:
        print(f"{host}: ERR {e}")

# 2. 用 Python socket 直连 20.205.243.166（带 timeout）
print()
t0 = time.time()
try:
    s = socket.create_connection(("20.205.243.166", 443), timeout=5)
    print(f"create_connection 20.205.243.166: OK {time.time() - t0:.2f}s")
    s.close()
except Exception as e:
    print(
        f"create_connection 20.205.243.166: {type(e).__name__} {time.time() - t0:.2f}s {e}"
    )

# 3. urllib 连 raw.githubusercontent.com（带 timeout）
t0 = time.time()
try:
    r = urllib.request.urlopen(
        urllib.request.Request(
            "https://raw.githubusercontent.com/qist/tvbox/master/README.md",
            headers={"User-Agent": "Mozilla/5.0"},
        ),
        timeout=8,
    )
    print(f"urllib raw.githubusercontent: OK {time.time() - t0:.2f}s {r.status}")
    r.close()
except Exception as e:
    print(
        f"urllib raw.githubusercontent: {type(e).__name__} {time.time() - t0:.2f}s {str(e)[:80]}"
    )
