#!/usr/bin/env python3
"""GitHub 特征扫描结果：地址级去重 + 探测。"""

import json
import re
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

sys.stdout.reconfigure(encoding="utf-8")
DB = "/opt/ponyo-source-manager/data/sources.db"
TIMEOUT = 12


def host_of(api):
    u = urlsplit(api if "://" in api else "http://" + api)
    return (u.hostname or "").lower()


def norm_host(h):
    h = h.lower()
    if h.startswith("www."):
        h = h[4:]
    return h.split(":")[0]


def normalize_endpoint(url):
    parts = urlsplit(url.strip())
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return None
    path_lower = parts.path.lower().rstrip("/")
    markers = ("/api.php/provide/vod", "/provide/vod", "/cjapi/", "/inc/api.php")
    if not any(m in path_lower for m in markers):
        return None
    ignored = {"ac", "action", "wd", "ids", "pg", "page", "limit"}
    query = urlencode(
        [(k, v) for k, v in parse_qsl(parts.query) if k.lower() not in ignored]
    )
    return urlunsplit(
        (parts.scheme, parts.netloc, parts.path.rstrip("/") + "/", query, "")
    )


# 读取扫描结果
d = json.load(open("/tmp/gh_feature_maccms.json", encoding="utf-8"))
# 过滤代理包装/示例
SKIP = ("example.com", "dpdns.org", "ccwu.cc", "qzz.io")
cands = {h: v for h, v in d.items() if not any(s in h for s in SKIP)}
print(f"候选（过滤代理/示例后）: {len(cands)}")

# 地址级去重
con = sqlite3.connect(DB)
rows = con.execute("SELECT api FROM raw_source WHERE api IS NOT NULL").fetchall()
db_norm = set()
for (api,) in rows:
    n = normalize_endpoint(api)
    if n:
        db_norm.add(n)
con.close()

new = {}
for h, v in cands.items():
    n = normalize_endpoint(v["api"])
    if n and n not in db_norm:
        new[h] = {"api": v["api"], "repo": v["repo"], "norm": n}

print(f"未入库（地址级）: {len(new)}")
for h, v in sorted(new.items()):
    print(f"  {h:<32} {v['api'][:70]}")

with open("/tmp/gh_new_candidates.json", "w", encoding="utf-8") as f:
    json.dump(new, f, ensure_ascii=False, indent=1)


# 探测
def probe(item):
    h, v = item
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
            "h": h,
            "v": v,
            "ok": n > 0,
            "code": 200,
            "n": n,
            "ms": int((time.time() - t0) * 1000),
        }
    except urllib.error.HTTPError as e:
        return {
            "h": h,
            "v": v,
            "ok": False,
            "code": e.code,
            "n": 0,
            "ms": int((time.time() - t0) * 1000),
        }
    except Exception as e:
        return {
            "h": h,
            "v": v,
            "ok": False,
            "code": type(e).__name__,
            "n": 0,
            "ms": int((time.time() - t0) * 1000),
        }


results = []
with ThreadPoolExecutor(max_workers=12) as ex:
    futs = {ex.submit(probe, item): item for item in new.items()}
    for fut in as_completed(futs):
        results.append(fut.result())

ok_list = sorted([r for r in results if r["ok"]], key=lambda r: r["ms"])
print(f"\n== 可用 ({len(ok_list)}) ==")
for r in ok_list:
    print(f"  {r['h']:<30} {r['v']['api'][:65]} n={r['n']:<5} {r['ms']}ms")
print(f"\n== 不可用 ({len(results) - len(ok_list)}) ==")
for r in sorted([r for r in results if not r["ok"]], key=lambda r: r["ms"]):
    print(f"  {r['h']:<30} {r['v']['api'][:60]} {r['code']} {r['ms']}ms")
