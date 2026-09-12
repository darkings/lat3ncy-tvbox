#!/usr/bin/env python3
"""VIP 解析服务（server 端 Playwright 桌面 Chromium 出流兜底）。

- 监听 0.0.0.0:8001，提供 GET /jx/parse?url=<vip_url>
- 用无头 Chromium 并行加载多个 type-0 解析器 iframe，拦截真实 m3u8 响应
- 返回 {"url": "<m3u8>"}（App 端作为 type=1 JSON 解析器接入，走 OkHttp 直连，
  绕开 App 内 WebView 的手机 UA / WASM 限制）
- 结果缓存（默认 30min），失败也短缓存避免风暴

独立于 children-api 容器运行（host .venv + host chromium）。
children-api 通过 172.19.0.1:8001 反向代理到本服务。
"""
from __future__ import annotations

import asyncio
import json
import re
import sys
import time
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse

# 独立脚本启动时也要能 import 仓库内的 HLS 时长探测
_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

CHROME_BIN = Path("/opt/ponyo-source-manager/chromium/chrome-linux/chrome")
TOP_PARSERS = Path("/opt/ponyo-source-manager/data/top-parsers.json")

# type-0 解析器（云解析/爱豆/咸鱼/虾米/全看），按出流成功率排序
FALLBACK_PARSERS = [
    "https://jx.yparse.com/index.php?url=",   # 云解析：mgtv/qiyi 稳定
    "https://jx.aidouer.net/?url=",           # 爱豆：qq
    "https://jx.xyflv.cc/?url=",              # 咸鱼：mgtv
    "https://jx.xmflv.com/?url=",             # 虾米
    "https://jx.quankan.app/?url=",           # 全看
]

M3U8_RE = re.compile(r"\.(m3u8|mp4|ts)(\?|$)", re.I)
BAD_RE = re.compile(r"404|not found|error", re.I)

def norm_flag(flag: str) -> str:
    """平台 flag 别名归一化：drpyS 返回中文站名（优酷/腾讯/芒果/爱奇艺，可能带空格/后缀），
    统一回英文 key：qq/mgtv/qiyi/youku（与 top-parsers.json platforms 一致）。"""
    if not flag:
        return ""
    f = flag.strip().lower().replace(" ", "").replace("_", "").replace("-", "")
    if "qq" in f or "腾讯" in f or "tencent" in f:
        return "qq"
    if "mgtv" in f or "芒果" in f or "imgo" in f:
        return "mgtv"
    if "qiyi" in f or "iqiyi" in f or "奇艺" in f or "爱奇艺" in f:
        return "qiyi"
    if "youku" in f or "优酷" in f:
        return "youku"
    return ""


def timeout_for(flag: str) -> float:
    """优酷出流较慢（实测 >12s），单独放宽超时；其余平台默认。"""
    if norm_flag(flag or "") == "youku":
        return 28.0
    return 16.0

# 缓存：vip_url -> (m3u8, ts)；失败 -> (None, ts)
_cache: dict[str, tuple[str | None, float]] = {}
CACHE_TTL_OK = 1800.0      # 成功 30min
CACHE_TTL_FAIL = 60.0      # 失败 60s
MAX_AGE = 3600.0

app = FastAPI(title="Ponyo JX Parse Server")

_browser = None
_browser_pw = None
_browser_lock = asyncio.Lock()


def _load_parsers() -> list[dict]:
    """从 top-parsers.json 读 type-0 解析器（含 name/platforms），失败回退硬编码。"""
    try:
        if TOP_PARSERS.is_file():
            d = json.loads(TOP_PARSERS.read_text(encoding="utf-8"))
            ps = [p for p in d.get("parsers", []) if p.get("type", 0) == 0]
            if ps:
                return ps
    except Exception:
        pass
    return [{"name": u, "url": u, "type": 0} for u in FALLBACK_PARSERS]


def _filter_parsers(parsers: list[dict], names: set[str] | None, flag: str | None) -> list[dict]:
    """按 name（指定时只用这些）和 flag（parser 声明了 platforms 且不含该平台则剔除）过滤。"""
    nf = norm_flag(flag or "")
    out = []
    for p in parsers:
        if names is not None and p.get("name") not in names:
            continue
        plats = p.get("platforms") or []
        if nf and plats and nf not in plats:
            continue
        out.append(p)
    return out


async def _get_browser():
    """懒加载共享 Chromium 浏览器实例。"""
    global _browser, _browser_pw
    async with _browser_lock:
        if _browser is None or not _browser.is_connected():
            from playwright.async_api import async_playwright
            if _browser_pw is None:
                _browser_pw = await async_playwright().start()
            _browser = await _browser_pw.chromium.launch(
                executable_path=str(CHROME_BIN),
                headless=True,
                args=["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"],
            )
        return _browser


def _media_usable(url: str) -> bool:
    """拦截到的媒体是否可返回给 App。

    明确过短的点播 m3u8（常见 1～2 分钟试看片）返回 False，让其它解析器继续试。
    拉不到时长、直播窗口、非 m3u8 都放行，避免误杀。
    """
    lowered = str(url or "").lower()
    path = lowered.split("?", 1)[0]
    if not (path.endswith((".m3u8", ".m3u")) or ".m3u8" in lowered):
        return True
    try:
        from ponyo_source_manager.probes.playback import inspect_hls_duration

        info = inspect_hls_duration(url)
    except Exception:
        return True
    if info.get("ok", True):
        return True
    print(f"[jx] skip {info.get('reason')} {url[:160]}", flush=True)
    return False


async def _first_usable(found: list[str], checked: set[str]) -> str | None:
    """对尚未检查过的拦截结果做时长过滤，返回第一条可用媒体。"""
    for u in list(found):
        if u in checked:
            continue
        checked.add(u)
        if await asyncio.to_thread(_media_usable, u):
            return u
    return None


async def _probe(parser_url: str, vip_url: str, timeout: float) -> str | None:
    """单个解析器：加载 parser+vip，拦截 m3u8 响应，返回首个可用命中。"""
    try:
        browser = await _get_browser()
    except Exception:
        return None
    page = None
    found: list[str] = []
    checked: set[str] = set()

    def on_resp(resp):
        try:
            u = resp.url
            if M3U8_RE.search(u) and not BAD_RE.search(u):
                found.append(u)
        except Exception:
            pass

    try:
        page = await browser.new_page()
        page.on("response", on_resp)
        try:
            await page.goto(
                parser_url + vip_url,
                timeout=int(timeout * 1000),
                wait_until="domcontentloaded",
            )
        except Exception:
            pass
        # 轮询等待可用 m3u8：试看片会被丢掉，继续等后续正片或超时
        deadline = time.time() + timeout
        while time.time() < deadline:
            usable = await _first_usable(found, checked)
            if usable:
                return usable
            await asyncio.sleep(0.5)
        return await _first_usable(found, checked)
    except Exception:
        return None
    finally:
        if page is not None:
            try:
                await page.close()
            except Exception:
                pass


async def _parse(vip_url: str, timeout: float = 12.0,
                 names: set[str] | None = None, flag: str | None = None) -> str | None:
    """并行尝试多个解析器，返回第一个出流的 m3u8。names 限定解析器，flag 限定平台。"""
    parsers = _filter_parsers(_load_parsers(), names, flag)
    if not parsers:
        return None
    # 用信号量限制并发 page 数
    sem = asyncio.Semaphore(len(parsers))

    async def run(p: dict) -> str | None:
        async with sem:
            return await _probe(p["url"], vip_url, timeout)

    # FIRST_COMPLETED：第一个非空结果即返回
    tasks = [asyncio.create_task(run(p)) for p in parsers]
    try:
        pending = set(tasks)
        while pending:
            done, pending = await asyncio.wait(
                pending, timeout=timeout, return_when=asyncio.FIRST_COMPLETED
            )
            for t in done:
                try:
                    r = t.result()
                except Exception:
                    r = None
                if r:
                    return r
            if not done:
                break  # 全部超时
        return None
    finally:
        for t in tasks:
            if not t.done():
                t.cancel()


@app.get("/healthz")
async def healthz():
    return {"status": "ok", "chrome": CHROME_BIN.is_file()}


@app.get("/jx/parse")
async def jx_parse(
    url: str = Query(..., max_length=2000),
    name: str = Query("", max_length=200),
    parsers: str = Query("", max_length=2000),
    flag: str = Query("", max_length=32),
):
    """解析 VIP url。

    - name:    指定只用某一个解析器（按 top-parsers.json 里的 name）
    - parsers: 逗号分隔的解析器 name 列表，限定可用范围（name 优先于 parsers）
    - flag:    平台 qq/mgtv/qiyi/youku，解析器声明了 platforms 且不含该平台时跳过
    """
    if not url.startswith("http"):
        return JSONResponse({"url": "", "error": "bad url"}, headers={"Cache-Control": "no-store"})

    names: set[str] | None = None
    if name.strip():
        names = {name.strip()}
    elif parsers.strip():
        names = {n.strip() for n in parsers.split(",") if n.strip()}
    flag = flag.strip() or None

    now = time.time()
    cache_key = f"{url}|{name}|{parsers}|{flag or ''}"
    # 缓存命中
    hit = _cache.get(cache_key)
    if hit and now - hit[1] < (CACHE_TTL_OK if hit[0] else CACHE_TTL_FAIL):
        m3u8, _ = hit
        if m3u8:
            return JSONResponse({"url": m3u8}, headers={"Cache-Control": "no-store"})
        return JSONResponse({"url": "", "error": "cached-fail"}, headers={"Cache-Control": "no-store"})

    m3u8 = await _parse(url, timeout=timeout_for(flag), names=names, flag=flag)
    # 缓存
    if len(_cache) > 500:
        _cache.clear()
    _cache[cache_key] = (m3u8, now)

    if m3u8:
        return JSONResponse({"url": m3u8}, headers={"Cache-Control": "no-store"})
    return JSONResponse({"url": "", "error": "parse-failed"}, headers={"Cache-Control": "no-store"})


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001, log_level="info")
