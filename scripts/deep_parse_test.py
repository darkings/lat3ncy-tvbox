# -*- coding: utf-8 -*-
"""深度出流测试：对新增配置里的全部 type-0/1 解析器，无头 Chromium 逐平台真实出流。

与 refresh_parsers 的区别：不经过 HTTP 预筛选，凡是配置里出现的解析器都实测；
特别关注 youku（当前冗余不足）。输出每解析器可用平台。
"""
import asyncio
import json
import re
import ssl
import sys
import urllib.request
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

CONFIGS = [
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
    "https://raw.liucn.cc/box/m.json",      # 已知大配置，也纳入对比
    "https://clun.top/box.json",
]
# 已收录/已知出流的解析器（跳过，不重复测）
KNOWN = {
    "https://api.ponyo.fun/jx/parse?url=",
    "https://im1907.top/?jx=",        # 纯净/B站
    "https://yparse.ik9.cc/index.php?url=",  # 广告
    "https://jx.yparse.com/index.php?url=",  # 云解析
    "https://jx.xyflv.cc/?url=",      # 咸鱼
    "https://jx.aidouer.net/?url=",   # 爱豆
}
VIPS = [
    ("qq", "https://v.qq.com/x/cover/mzc00200si5bhp6/x4102q9n46a.html"),
    ("mgtv", "https://www.mgtv.com/b/756916/24476835.html"),
    ("qiyi", "http://www.iqiyi.com/v_h6q7qxb5b0.html"),
    ("youku", "https://v.youku.com/v_show/id_XNjU0MjIxOTc4NA==.html"),
]
CHROME_BIN = "/opt/ponyo-source-manager/chromium/chrome-linux/chrome"
MAX_PARSERS = 300

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
M3U8_RE = re.compile(r"\.(m3u8|mp4|ts)(\?|$)", re.I)

def fetch(url, timeout=12):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
            return r.read().decode("utf-8", "replace")
    except Exception:
        return None

def collect_parsers():
    found = {}
    for cfg in CONFIGS:
        d = fetch(cfg)
        if not d:
            continue
        try:
            data = json.loads(d.lstrip("\ufeff"))
        except Exception:
            continue
        for p in data.get("parses") or []:
            if not isinstance(p, dict):
                continue
            url = str(p.get("url", "")).strip()
            typ = p.get("type", 0)
            if not url or url in ("Demo", "Web", "Parallel", "Sequence") or typ not in (0, 1):
                continue
            if url in KNOWN:
                continue
            if url in found:
                continue
            found[url] = {"name": str(p.get("name", url[:20])).strip("- "), "type": typ, "url": url}
    return list(found.values())[:MAX_PARSERS]

async def main():
    parsers = collect_parsers()
    print(f"[1] 新解析器(去重,不含已知): {len(parsers)}")
    if not parsers:
        return
    import playwright.async_api
    working = {}  # url -> set(flags)
    with open("/opt/ponyo-source-manager/data/deep-parser-test.json", "w") as f:
        pass
    async with playwright.async_api.async_playwright() as pw:
        browser = await pw.chromium.launch(executable_path=CHROME_BIN, headless=True,
                                           args=["--no-sandbox", "--disable-gpu"])
        sem = asyncio.Semaphore(4)
        results = {}

        async def probe(p):
            async with sem:
                per_flag = {}
                page = await browser.new_page()
                def make_on_resp(found):
                    def on_resp(resp):
                        try:
                            u = resp.url
                            if M3U8_RE.search(u) and "404" not in u and "player" not in u and "styles" not in u:
                                found.append(u)
                            try:
                                ct = (resp.headers.get("content-type", "") or "").lower()
                                if "json" in ct or "text" in ct or ct == "":
                                    async def grab():
                                        try:
                                            bod = await resp.text()
                                            for m in re.finditer(r"https?://[^\s\"'<>\\]+?\.m3u8[^\s\"'<>\\]*", bod):
                                                if m.group(0) not in found:
                                                    found.append(m.group(0))
                                        except Exception:
                                            pass
                                    asyncio.get_event_loop().create_task(grab())
                            except Exception:
                                pass
                        except Exception:
                            pass
                    return on_resp
                for flag, vip in VIPS:
                    found = []
                    page.on("response", make_on_resp(found))
                    try:
                        await page.goto(p["url"] + vip, timeout=30000, wait_until="domcontentloaded")
                        for _ in range(20):
                            if found:
                                break
                            await asyncio.sleep(1)
                    except Exception:
                        pass
                    if found:
                        per_flag[flag] = True
                await page.close()
                results[p["url"]] = per_flag
                n = len(results)
                print(f"  进度 {n}/{len(parsers)} {p['name'][:12]:<12} -> {sorted(per_flag.keys())}", flush=True)

        await asyncio.gather(*[probe(p) for p in parsers])
        await browser.close()
    # 汇总
    out = {}
    for p in parsers:
        flags = sorted(results.get(p["url"], {}).keys())
        out[p["url"]] = {"name": p["name"], "type": p["type"], "platforms": flags}
    Path("/opt/ponyo-source-manager/data/deep-parser-test.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    youku = [(v, k) for k, v in out.items() if "youku" in v["platforms"]]
    print("\n[2] youku 可用的新解析器:", len(youku))
    for v, k in youku:
        print("   ", v["name"], v["type"], k[:80], "platforms=", v["platforms"])
    qq = [(v, k) for k, v in out.items() if "qq" in v["platforms"] and "youku" not in v["platforms"]]
    print("\n[3] qq 可用(非youku) 新解析器:", len(qq))
    for v, k in qq[:20]:
        print("   ", v["name"], v["type"], k[:80], "platforms=", v["platforms"])

if __name__ == "__main__":
    asyncio.run(main())