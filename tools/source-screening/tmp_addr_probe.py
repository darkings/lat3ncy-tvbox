#!/usr/bin/env python3
"""探测 24 个地址级变体。"""

import json
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.stdout.reconfigure(encoding="utf-8")
TIMEOUT = 12

variants = json.load(open("/tmp/address_variants.json", encoding="utf-8"))
print(f"变体: {len(variants)}")


def probe(v):
    api = v["api"].strip()
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
            "v": v,
            "ok": n > 0,
            "code": 200,
            "n": n,
            "ms": int((time.time() - t0) * 1000),
        }
    except urllib.error.HTTPError as e:
        return {
            "v": v,
            "ok": False,
            "code": e.code,
            "n": 0,
            "ms": int((time.time() - t0) * 1000),
        }
    except Exception as e:
        return {
            "v": v,
            "ok": False,
            "code": type(e).__name__,
            "n": 0,
            "ms": int((time.time() - t0) * 1000),
        }


results = []
with ThreadPoolExecutor(max_workers=12) as ex:
    futs = {ex.submit(probe, v): v for v in variants}
    for fut in as_completed(futs):
        results.append(fut.result())

ok_list = sorted([r for r in results if r["ok"]], key=lambda r: r["ms"])
print(f"\n== 可用 ({len(ok_list)}) ==")
for r in ok_list:
    print(f"  {r['v']['norm'][:70]:<73} n={r['n']:<5} {r['ms']}ms")
print(f"\n== 不可用 ({len(results) - len(ok_list)}) ==")
for r in sorted([r for r in results if not r["ok"]], key=lambda r: r["ms"]):
    print(f"  {r['v']['norm'][:70]:<73} {r['code']} {r['ms']}ms")

with open("/tmp/address_variants_probe.json", "w", encoding="utf-8") as f:
    json.dump(
        {"ok": ok_list, "fail": [r for r in results if not r["ok"]]},
        f,
        ensure_ascii=False,
        indent=1,
    )
