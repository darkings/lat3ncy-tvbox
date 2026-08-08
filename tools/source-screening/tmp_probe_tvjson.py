#!/usr/bin/env python3
"""批量连通性测试：对 tv.json 未入库的 maccms 候选源做 API 探测。"""

import json
import re
import sqlite3
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse

DB = "/opt/ponyo-source-manager/data/sources.db"
EXCLUDE_HOSTS = ["127.0.0.1", "localhost", "m1839732.ca.caoni.ru"]
EXCLUDE_GROUP = {"18+"}
TIMEOUT = 10


def host_of(api: str) -> str:
    u = urlparse(api if "://" in api else "http://" + api)
    return (u.hostname or "").lower()


def norm_host(h: str) -> str:
    h = h.lower()
    if h.startswith("www."):
        h = h[4:]
    return h.split(":")[0]


with open("/tmp/tv.json", encoding="utf-8") as f:
    data = json.load(f)

tv_sources = []
seen = set()
for s in data.get("sites", []):
    api = s.get("api") or ""
    if (
        "provide/vod" not in api
        and "inc/api.php" not in api
        and "seacmsapi" not in api
        and "api_mac10" not in api
    ):
        continue
    if s.get("group") in EXCLUDE_GROUP:
        continue
    host = host_of(api)
    if not host or any(x in host for x in EXCLUDE_HOSTS):
        continue
    key = norm_host(host)
    if key in seen:
        continue
    seen.add(key)
    tv_sources.append({"name": s.get("name", "?"), "api": api, "host": key})

con = sqlite3.connect(DB)
rows = con.execute("SELECT api FROM raw_source").fetchall()
db_hosts = {norm_host(host_of(r[0])) for r in rows if r[0]}
con.close()

candidates = [s for s in tv_sources if s["host"] not in db_hosts]
print(f"候选源: {len(candidates)}")

# 分类关键词（与 policy.json 一致）
KEYWORDS = {
    "动漫": ["动漫", "动画", "番剧", "anime", "追番"],
    "纪录": ["纪录", "纪实", "documentary"],
    "综艺": ["综艺", "娱乐", "show"],
    "听书短剧": ["听", "有声", "音乐", "ktv", "mv", "dj", "短剧", "短视频"],
    "影视": ["影视", "电影", "电视剧", "剧场", "vip", "港剧", "美剧"],
}


def cat_of(name: str) -> str:
    for cat, kws in KEYWORDS.items():
        for kw in kws:
            if kw.lower() in name.lower():
                return cat
    return "-"


def probe(src):
    api = src["api"].strip()
    # maccms 标准探测：?ac=list（兼容 ac=detail）
    sep = "&" if "?" in api else "?"
    url = api + sep + "ac=list"
    t0 = time.time()
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            body = resp.read(200 * 1024)
            code = resp.status
        text = body.decode("utf-8", errors="replace")
        n = 0
        try:
            j = json.loads(text)
            lst = (j.get("data") or {}).get("list") or []
            n = len(lst)
        except Exception:
            if '"list"' in text:
                n = -1  # 有 list 字段但解析失败
        return {
            "src": src,
            "ok": code == 200 and n != 0,
            "code": code,
            "n": n,
            "ms": int((time.time() - t0) * 1000),
        }
    except urllib.error.HTTPError as e:
        return {
            "src": src,
            "ok": False,
            "code": e.code,
            "n": 0,
            "ms": int((time.time() - t0) * 1000),
        }
    except Exception as e:
        return {
            "src": src,
            "ok": False,
            "code": str(type(e).__name__),
            "n": 0,
            "ms": int((time.time() - t0) * 1000),
        }


results = []
with ThreadPoolExecutor(max_workers=16) as ex:
    futs = {ex.submit(probe, s): s for s in candidates}
    for fut in as_completed(futs):
        results.append(fut.result())

ok_list = sorted([r for r in results if r["ok"]], key=lambda r: r["ms"])
fail_list = sorted([r for r in results if not r["ok"]], key=lambda r: r["ms"])

print(f"\n== 可用 ({len(ok_list)}) ==")
for r in ok_list:
    cat = cat_of(r["src"]["name"])
    print(
        f"  {r['src']['host']:<32} {r['src']['name']:<14} n={r['n']:<6} {r['ms']}ms  [{cat}]"
    )

print(f"\n== 不可用 ({len(fail_list)}) ==")
for r in fail_list:
    print(f"  {r['src']['host']:<32} {r['src']['name']:<14} {r['code']} {r['ms']}ms")

# 保存结果供下一步
with open("/tmp/tvjson_probe_result.json", "w", encoding="utf-8") as f:
    json.dump({"ok": ok_list, "fail": fail_list}, f, ensure_ascii=False, indent=1)
print("\n结果已保存 /tmp/tvjson_probe_result.json")
