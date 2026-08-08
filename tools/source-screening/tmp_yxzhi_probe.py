#!/usr/bin/env python3
"""yxzhi 32 个未入库 maccms 服务器探测。"""

import json
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse

sys.stdout.reconfigure(encoding="utf-8")
DB = "/opt/ponyo-source-manager/data/sources.db"
TIMEOUT = 12


def host_of(api: str) -> str:
    u = urlparse(api if "://" in api else "http://" + api)
    return (u.hostname or "").lower()


def norm_host(h: str) -> str:
    h = h.lower()
    if h.startswith("www."):
        h = h[4:]
    return h.split(":")[0]


m = json.load(open("/tmp/yxzhi_merged.json", encoding="utf-8"))
con = sqlite3.connect(DB)
rows = con.execute("SELECT api FROM raw_source").fetchall()
db_hosts = {norm_host(host_of(r[0])) for r in rows if r[0]}
con.close()
candidates = [
    {"host": h, "name": v["name"], "api": v["api"]}
    for h, v in m.items()
    if h not in db_hosts
]
print(f"候选: {len(candidates)}")


def probe(c):
    api = c["api"].strip()
    sep = "&" if "?" in api else "?"
    url = api + sep + "ac=list"
    t0 = time.time()
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            body = resp.read(150 * 1024)
        text = body.decode("utf-8", errors="replace")
        n = 0
        try:
            j = json.loads(text)
            lst = j.get("list") or (j.get("data") or {}).get("list") or []
            n = len(lst)
        except Exception:
            pass
        return {
            "c": c,
            "ok": n > 0,
            "code": 200,
            "n": n,
            "ms": int((time.time() - t0) * 1000),
        }
    except urllib.error.HTTPError as e:
        return {
            "c": c,
            "ok": False,
            "code": e.code,
            "n": 0,
            "ms": int((time.time() - t0) * 1000),
        }
    except Exception as e:
        return {
            "c": c,
            "ok": False,
            "code": type(e).__name__,
            "n": 0,
            "ms": int((time.time() - t0) * 1000),
        }


results = []
with ThreadPoolExecutor(max_workers=12) as ex:
    futs = {ex.submit(probe, c): c for c in candidates}
    for fut in as_completed(futs):
        results.append(fut.result())

ok_list = sorted([r for r in results if r["ok"]], key=lambda r: r["ms"])
print(f"\n== 可用 ({len(ok_list)}) ==")
for r in ok_list:
    print(f"  {r['c']['host']:<30} {r['c']['name']:<14} n={r['n']:<5} {r['ms']}ms")
print(f"\n== 不可用 ({len(results) - len(ok_list)}) ==")
for r in sorted([r for r in results if not r["ok"]], key=lambda r: r["ms"]):
    print(f"  {r['c']['host']:<30} {r['c']['name']:<14} {r['code']} {r['ms']}ms")
