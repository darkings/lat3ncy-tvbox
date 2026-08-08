#!/usr/bin/env python3
"""批量测试 at/xml 端点是否支持 at=json 转换。"""

import json
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.stdout.reconfigure(encoding="utf-8")
TIMEOUT = 10

con = sqlite3.connect("/opt/ponyo-source-manager/data/sources.db")
rows = con.execute(
    "SELECT DISTINCT api FROM raw_source WHERE api LIKE '%at/xml%' OR api LIKE '%mc10/vod/xml%'"
).fetchall()
con.close()
xml_eps = [r[0] for r in rows if r[0]]
print(f"XML 端点: {len(xml_eps)}")


def probe(api):
    # 尝试 at=json 覆盖
    url = api.replace("at/xml", "at/json").replace("vod/xml", "vod/json")
    sep = "&" if "?" in url else "?"
    url = url + sep + "ac=list"
    t0 = time.time()
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            body = resp.read(100 * 1024)
        text = body.decode("utf-8", errors="replace")
        try:
            j = json.loads(text)
            n = len(j.get("list") or (j.get("data") or {}).get("list") or [])
            return {
                "api": api,
                "ok": n > 0,
                "n": n,
                "ms": int((time.time() - t0) * 1000),
                "note": "json转换成功" if n else "json空",
            }
        except Exception:
            if text.lstrip().startswith("<"):
                return {
                    "api": api,
                    "ok": False,
                    "n": 0,
                    "ms": int((time.time() - t0) * 1000),
                    "note": "仍XML",
                }
            return {
                "api": api,
                "ok": False,
                "n": 0,
                "ms": int((time.time() - t0) * 1000),
                "note": "非JSON",
            }
    except urllib.error.HTTPError as e:
        return {
            "api": api,
            "ok": False,
            "n": 0,
            "ms": int((time.time() - t0) * 1000),
            "note": f"HTTP{e.code}",
        }
    except Exception as e:
        return {
            "api": api,
            "ok": False,
            "n": 0,
            "ms": int((time.time() - t0) * 1000),
            "note": type(e).__name__,
        }


results = []
with ThreadPoolExecutor(max_workers=12) as ex:
    futs = {ex.submit(probe, api): api for api in xml_eps}
    for fut in as_completed(futs):
        results.append(fut.result())

ok_list = [r for r in results if r["ok"]]
print(f"\n== at=json 转换成功 ({len(ok_list)}) ==")
for r in sorted(ok_list, key=lambda x: x["ms"]):
    print(f"  {r['api'][:70]:<73} n={r['n']} {r['ms']}ms")
print(f"\n== 不支持转换 ({len(results) - len(ok_list)}) ==")
for r in sorted([r for r in results if not r["ok"]], key=lambda x: x["ms"]):
    print(f"  {r['api'][:70]:<73} {r['note']} {r['ms']}ms")
