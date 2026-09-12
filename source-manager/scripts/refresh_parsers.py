#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""解析器自动发现 + 真实速度测试 + 排序，输出最快 3 个。

流程：
1. 从多个 TVBox 配置地址（含 parses）发现解析器，去重；
2. 从 4 个官源（腾讯/芒果/爱奇艺/优酷）动态取真实 VIP 页面地址；
3. 用真实 VIP 地址逐解析器测速（响应时间 + 有效性）；
4. 按"可达且有效 + 平均耗时"排序，取最快 3 个；
5. 写入 ponyo-template.json 的 parses（生成订阅时只保留这 3 个）。

用法：
    python scripts/refresh_parsers.py [--template ponyo-template.json] [--out data/top-parsers.json]
"""
from __future__ import annotations

import argparse
import json
import re
import ssl
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

UA_DESKTOP = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/139.0.0.0 Safari/537.36"
UA_MOBILE = "Mozilla/5.0 (Linux; Android 13; V2049A Build/TP1A.220624.014; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/116.0.0.0 Mobile Safari/537.36"

# 解析器发现源（TVBox 配置，含 parses 数组）
DISCOVERY_CONFIGS = [
    "https://jihulab.com/mengzhu2/ysc/-/raw/main/YSC.json",
    "https://cdn.jsdelivr.net/gh/gaotianliuyun/gao@master/0821.json",
    "https://cdn.jsdelivr.net/gh/FongMi/CatVodSpider@main/json/config.json",
    "https://cdn.jsdelivr.net/gh/q215613905/TVBoxOS@main/tv.json",
    "http://cdn.qiaoji8.com/tvbox.json",
    "https://gitee.com/blssss/jk/raw/api/bls.json",
    "https://raw.liucn.cc/box/m.json",
    # 2026-08-17 新增（来源：Telegram Xfyjr69 帖子 345/346/347 里的可达配置）
    "https://pastebin.com/raw/sbPpDm9G",
    "https://9280.kstore.space/wex.json",
    "https://dxawi.github.io/0/0.json",
    "https://9280.kstore.vip/newwex.json",
    "https://raw.giteeusercontent.com/hulanlu/04/raw/master/lanlu.json",
    "https://clun.top/box.json",
    "https://raw.githubusercontent.com/maoystv/6/main/001.json",
    "https://17264.kstore.space/%E5%93%88%E5%9F%BA%E7%B1%B3.png",
    "https://11405.kstore.space/xiaye/qk4k.json",
    "http://home.jundie.top:81/top98.json",
    "http://tv.nxog.top/m/",
    "https://www.cttv.vip/ys/json/ctys.json",
    "https://www.yingm.cc/dm/dm.json",
    # 2026-08-17 第二批新增（来源：Telegram Xfyjr69 频道历史与帖子 326-347 里的可达配置）
    "http://xhztv.top/xhz",
    "https://bitbucket.org/xduo/duoapi/raw/master/xpg.json",
    "https://cccimg.com/down.php/7d1f30263b3f2bf3deda2d7faeef4844.zhen6",
    "https://gh-proxy.com/raw.githubusercontent.com/yw88075/tvbox/main/yw.json",
    "https://jihulab.com/jyqhkd/kd/-/raw/main/kai.json",
    "https://jihulab.com/xuanzhuapp/xzys/-/raw/main/xzvip.json",
    "https://jsd.cdn.zzko.cn/gh/1771245847/TvBox/tvbox.json",
    "https://php.doube.eu.org/spider/php/config.php",
    "https://play.iptv365.org/%E5%A4%A9%E5%A4%A9%E5%BC%80%E5%BF%83/api.json",
    "https://play.iptv365.org/%E9%A6%99%E9%9B%85%E6%83%85/api.json",
    "https://szyyds.cn/tv/x.json",
]

# 深度实测白名单：客户端真实出流确认可用、但会被 HTTP 预筛/单轮波动漏掉的解析器。
# 由 deep_parse_test.py 无头 Chromium 全量实测得出（此条目：jx.xymp4.cc 对优酷真实出流）。
# 心愿：保证优酷始终有多于 1 个兜底。格式：name/type/url/ext/platforms。
EXTRA_PARSERS = [
    {
        "name": "咸鱼优酷",
        "type": 0,
        "url": "https://jx.xymp4.cc/?url=",
        "ext": {},
        "platforms": ["youku"],
    },
]

# 官源 → (module, 分类 tid)，用于动态取真实 VIP 地址
GUAN_SOURCES = [
    ("腾云驾雾[官]", "movie", "qq"),
    ("百忙无果[官]", "2", "mgtv"),
    ("奇珍异兽[官]", "1", "qiyi"),
    ("优酷[官]", "电视剧", "youku"),
]

DRPY_BASE = "http://127.0.0.1:5757"

# 无头 Chromium（用于真实出流测试：跑解析器 JS 抓 m3u8）
CHROME_BIN = "/opt/ponyo-source-manager/chromium/chrome-linux/chrome"

# 自建 VIP 解析器（type=1，server 端 Playwright 出流，App 走 OkHttp 直连绕开 WebView 限制）
# 固定置于 parses 首位，作为 web 解析器(iframe)的首选兜底。
SELF_JX = {
    "name": "Ponyo解析",
    "type": 1,
    "url": "https://api.ponyo.fun/jx/parse?url=",
    "ext": {
        "flag": [
            "qq", "腾讯", "腾讯视频",
            "mgtv", "芒果", "芒果TV",
            "qiyi", "爱奇艺", "奇艺",
            "youku", "优酷", "优酷视频",
        ],
        "header": {"User-Agent": "okhttp/4.9.1"},
    },
}


def _ctx():
    c = ssl.create_default_context()
    c.check_hostname = False
    c.verify_mode = ssl.CERT_NONE
    return c


def fetch(url: str, timeout: float = 12.0) -> tuple[int, str, str]:
    """返回 (status, body, final_url)；异常返回 (-1, '', err)。"""
    req = urllib.request.Request(url, headers={"User-Agent": UA_DESKTOP})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_ctx()) as r:
            return r.status, r.read().decode("utf-8", "replace"), r.geturl()
    except Exception as e:
        return -1, "", str(e)[:80]


def fetch_json(url: str, timeout: float = 12.0):
    st, body, _ = fetch(url, timeout)
    if st != 200:
        return None
    try:
        return json.loads(body)
    except Exception:
        return None


# ---------- 1. 发现解析器 ----------
def discover_parsers() -> dict[str, dict]:
    found: dict[str, dict] = {}
    for cfg in DISCOVERY_CONFIGS:
        d = fetch_json(cfg)
        if not d:
            continue
        for p in d.get("parses") or []:
            if not isinstance(p, dict):
                continue
            url = str(p.get("url", "")).strip()
            typ = p.get("type", 0)
            if not url or url in ("Demo", "Web") or typ not in (0, 1):
                continue
            if url not in found:
                found[url] = {
                    "name": str(p.get("name", url[:20])).strip("- "),
                    "type": typ,
                    "url": url,
                    "ext": p.get("ext") or {},
                }
    return found


# ---------- 2. 从官源取真实 VIP 地址 ----------
def fetch_vip_urls() -> list[tuple[str, str]]:
    """返回 [(平台 flag, VIP 地址)]，用于逐平台判定解析器是否可用。"""
    vips: list[tuple[str, str]] = []
    for module, tid, flag in GUAN_SOURCES:
        m = urllib.parse.quote(module)
        # 分类 → 第一个 vod
        d = fetch_json(f"{DRPY_BASE}/api/{m}?pwd=ponyo-local-drpy&ac=detail&t={urllib.parse.quote(tid)}&pg=1", timeout=20)
        lst = (d or {}).get("list") or []
        if not lst:
            continue
        vid = lst[0].get("vod_id")
        # 详情 → play_url 里的第一个 http 地址
        d2 = fetch_json(f"{DRPY_BASE}/api/{m}?pwd=ponyo-local-drpy&ac=detail&ids={urllib.parse.quote(str(vid))}", timeout=20)
        vod = ((d2 or {}).get("list") or [{}])[0]
        pu = str(vod.get("vod_play_url", ""))
        # 兼容明文 URL 与整段 urlencode 的 URL（优酷等 play_url 形如 http%3A%2F%2F...）
        mch = re.search(r"https?://[^#$\s]+", pu) or re.search(
            r"https?%3A%2F%2F[^#$\s]+", pu, re.I
        )
        if mch:
            url = urllib.parse.unquote(mch.group(0))  # 解一次 urlencode（优酷等）
            vips.append((flag, url))
    return vips


# ---------- 3. 测速 ----------
def test_parser(item: tuple[str, dict], vips: list[tuple[str, str]]) -> dict:
    url, meta = item
    name = meta["name"]
    typ = meta["type"]
    times = []
    statuses = []
    valid = 0
    for _flag, vip in vips:
        st, body, final = fetch(url + vip, timeout=12)
        t0_status = st
        # 有效性：200 且返回体不是空/错误页
        is_ok = st == 200 and len(body) > 800 and not re.search(r"404|Not Found|解析失败|接口失效|参数错误", body)
        if is_ok:
            valid += 1
        # 测速（重复 2 次取 min，降低抖动）
        best = 999.0
        for _ in range(2):
            t1 = time.time()
            st2, _, _ = fetch(url + vip, timeout=12)
            dt = time.time() - t1
            if st2 == 200 and dt < best:
                best = dt
        if best < 999.0:
            times.append(best)
        statuses.append(t0_status)
    avg = round(sum(times) / len(times), 2) if times else 999.0
    reachable = sum(1 for s in statuses if s == 200)
    return {
        "name": name,
        "type": typ,
        "url": url,
        "ext": meta["ext"],
        "avg_seconds": avg,
        "reachable": reachable,
        "valid": valid,
        "tested": len(vips),
    }


def pw_m3u8_test(parsers: list[dict], vips: list[str]) -> dict[str, list[str]] | None:
    """用无头 Chromium 真实跑解析器 JS，返回 {平台flag: [能出流的解析器url]}。

    这是"是否真能出流"的权威测试（比 HTTP 可达性/响应时间更准）。
    无法使用浏览器时（未安装 Chromium / playwright）返回 None（区别于"测试了但全失败"的空字典）。
    """
    if not Path(CHROME_BIN).exists():
        print("[4] 跳过真实出流测试（无 Chromium）")
        return None
    import asyncio
    try:
        from playwright.async_api import async_playwright
    except Exception as e:
        print(f"[4] 跳过真实出流测试（无 playwright）: {e}")
        return None

    async def _run():
        working: dict[str, list[str]] = {}
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(
                executable_path=CHROME_BIN, headless=True,
                args=["--no-sandbox", "--disable-gpu"])
            sem = asyncio.Semaphore(4)

            async def probe(p):
                async with sem:
                    for flag, vip in vips:
                        found = []
                        page = await browser.new_page()
                        async def on_resp(resp):
                            u = resp.url
                            if re.search(r"\.(m3u8|mp4|ts)(\?|$)", u, re.I) and "404" not in u and "player" not in u and "styles" not in u:
                                found.append(u)
                            try:
                                ct = (resp.headers.get("content-type", "") or "").lower()
                                if "json" in ct or "text" in ct:
                                    body = await resp.text()
                                    for m in re.finditer(r"https?://[^\s\"'<>\\]+?\.m3u8[^\s\"'<>\\]*", body):
                                        found.append(m.group(0))
                            except Exception:
                                pass
                        page.on("response", on_resp)
                        try:
                            await page.goto(p["url"] + vip, timeout=35000, wait_until="domcontentloaded")
                            for _ in range(25):
                                if found:
                                    break
                                await asyncio.sleep(1)
                        except Exception:
                            pass
                        await page.close()
                        if found:
                            working.setdefault(flag, []).append(p["url"])
            await asyncio.gather(*[probe(p) for p in parsers])
            await browser.close()
        return working

    return asyncio.run(_run())


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--template", default="ponyo-template.json")
    p.add_argument("--out", default="data/top-parsers.json")
    p.add_argument("--top", type=int, default=0, help="保留前 N 个最快；0=全部测试通过的解析器")
    args = p.parse_args()

    print("[1] 发现解析器 ...")
    parsers = discover_parsers()
    print(f"    去重后 {len(parsers)} 个")

    print("[2] 取真实 VIP 地址 ...")
    vips = fetch_vip_urls()
    print(f"    VIP 地址 {len(vips)} 个: {[v[:40] for v in vips]}")

    print("[3] 测速 ...")
    results = []
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(test_parser, item, vips): item for item in parsers.items()}
        for f in as_completed(futs):
            try:
                results.append(f.result())
            except Exception as e:
                pass

    # 排序：可达且有效优先，然后平均耗时升序
    results.sort(key=lambda r: (0 if (r["reachable"] > 0 and r["valid"] > 0) else 1, r["avg_seconds"]))

    print(f"\n{'解析器':12} {'类型':4} {'可达':4} {'有效':4} {'平均耗时':8}")
    for r in results[:15]:
        mark = "✓" if r["reachable"] > 0 and r["valid"] > 0 else "✗"
        print(f"{r['name']:12} {r['type']:<4} {r['reachable']:>3}/{r['tested']} {r['valid']:>3} {r['avg_seconds']:>7.2f}s {mark}  {r['url'][:40]}")

    passing = [r for r in results if r["reachable"] > 0 and r["valid"] > 0]
    top = passing if args.top <= 0 else passing[: args.top]
    print(f"\n[4] 保留 {len(top)} 个: {[r['name'] for r in top]}")

    # [5] 真实出流测试（无头 Chromium），逐平台判断每个解析器能否出流。
    # Ponyo解析 也参与测试（它是 App 端唯一的解析入口，服务器内部再跑下面的 type-0 解析器）。
    test_list = [dict(SELF_JX)] + top
    working = pw_m3u8_test(test_list, vips) if test_list else None
    working_platforms = {flag: bool(urls) for flag, urls in (working or {}).items()}
    has_working = any(working_platforms.values())
    print(f"[5] 真实出流: {'有' if has_working else '无'}")
    for flag, urls in sorted((working or {}).items()):
        print(f"    {flag}: {len(urls)} 个解析器可用 {[u[:40] for u in urls[:3]]}")

    # 每个解析器 → 可用平台 {parser_url: [flag...]}；测试没跑（None）时全部不限制
    url_flags: dict[str, list[str]] = {}
    if working is not None:
        for flag, urls in working.items():
            for u in urls:
                url_flags.setdefault(u, []).append(flag)
    for p in test_list:
        p["platforms"] = url_flags.get(p["url"], [])
    # Ponyo解析 能用的平台 = 它自己测出的 ∪ 任一 type-0 解析器能用的（服务器内部会跑它们）
    self_jx_platforms = sorted(set(url_flags.get(SELF_JX["url"], []) + list(working_platforms.keys())))
    print(f"    Ponyo解析 可用平台: {self_jx_platforms or '无'}")

    # 测试跑过：全平台出流失败的解析器直接剔除（服务器与订阅都不用再试）
    if working is not None:
        dropped = [r["name"] for r in top if not url_flags.get(r["url"])]
        top = [r for r in top if url_flags.get(r["url"])]
        if dropped:
            print(f"    全平台出流失败的解析器已剔除: {dropped}")

    # 深度实测白名单兜底：深度出流测试确认可用、但 HTTP 预筛/单轮波动可能漏掉的解析器强制保留
    top_urls = {r["url"] for r in top}
    for ex in EXTRA_PARSERS:
        if ex["url"] not in top_urls:
            ex_copy = dict(ex)
            top.append(ex_copy)
            top_urls.add(ex_copy["url"])
            print(f"    白名单兜底解析器已并入: {ex_copy['name']} platforms={ex_copy.get('platforms')}")

    # 写 out（供订阅生成读取；working_platforms 决定每个平台收录官源还是采集源）
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps({
            "parsers": top,
            "self_jx_platforms": self_jx_platforms,
            "flow_tested": working is not None,
            "has_working_parser": has_working,
            "working_platforms": working_platforms,
        }, ensure_ascii=False, indent=2),
        encoding="utf-8")

    # 写模板 parses（真实出流测试跑过时，只收录至少 1 个平台能出流的解析器 + 深度实测白名单）
    tpl = Path(args.template)
    if tpl.is_file():
        tpl_data = json.loads(tpl.read_text(encoding="utf-8"))
        extra_by_url = {ex["url"]: ex for ex in EXTRA_PARSERS}
        if working is not None:
            top_keep = [r for r in top if url_flags.get(r["url"]) or r["url"] in extra_by_url]
            skipped = [r["name"] for r in top if not url_flags.get(r["url"]) and r["url"] not in extra_by_url]
            if skipped:
                print(f"    真实出流全平台失败的解析器已剔除: {skipped}")
        else:
            top_keep = top
        tpl_data["parses"] = [dict(SELF_JX)] + [
            {
                "name": r["name"],
                "type": r["type"],
                "url": r["url"],
                "ext": r["ext"] if r["ext"] else None,
            }
            for r in top_keep
        ]
        # 去掉 ext=None 的字段
        for pr in tpl_data["parses"]:
            if not pr.get("ext"):
                pr.pop("ext", None)
        # 附上每解析器可用平台（Ponyo解析 用 self_jx_platforms（服务器内部多解析器并集），
        # 不用单次自测直连结果——自测受瞬时波动影响会漏掉可通过内部解析器覆盖的平台）
        extra_by_url = {ex["url"]: ex for ex in EXTRA_PARSERS}
        for pr in tpl_data["parses"]:
            if pr["url"] == SELF_JX["url"]:
                fl = self_jx_platforms
            elif pr["url"] in extra_by_url:
                fl = extra_by_url[pr["url"]].get("platforms", [])
            else:
                fl = url_flags.get(pr["url"], [])
            if fl:
                pr["platforms"] = fl
        tpl.write_text(json.dumps(tpl_data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"    已写入模板 parses: {[r['name'] for r in tpl_data['parses']]}")


if __name__ == "__main__":
    main()
