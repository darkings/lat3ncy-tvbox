#!/usr/bin/env python3
"""儿童聚合服务 (FastAPI)
提供标准 TVBox/MacCMS JSON 接口。
数据库只保存源内 ID 和集数映射，不长期保存过期的播放 URL。
在收到请求时，实时解析（或借助缓存）分发到各子源。
"""

import asyncio
import hashlib
import json
import os
import re
import sqlite3
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse

from ponyo_source_manager.core.common import CODE_DIR, DATA_DIR
from ponyo_source_manager.api.quality_query import query_quality
from ponyo_source_manager.api.direct_parse import direct_resolve
from ponyo_source_manager.publishing.children_aggregate import (
    is_maccms_endpoint,
    is_playable_media_url,
    maccms_play_fields,
    _maccms_request_url,
)

# 详情/播放解析走 drpy2 适配器（容器内通过容器名访问 drpy-node；宿主 127.0.0.1 在容器内不可达）
os.environ.setdefault("DRPY2_ADAPTER", "/app/drpy2/drpys-http-adapter.js")
os.environ.setdefault("DRPY2_BASE_URL", "http://ponyo-drpy-node:5757")
os.environ.setdefault(
    "DRPY2_CONFIG_URL", "http://ponyo-drpy-node:5757/config/1?pwd=ponyo-local-drpy")


# DB 初始化：为 Children API 专门设计映射表
def init_children_db():
    con = sqlite3.connect(str(DATA_DIR / "children_cache.db"))
    # videos: id, type_id, name, pic, latest, source_fp, source_id, api, ext
    con.execute("""
        CREATE TABLE IF NOT EXISTS videos (
            id TEXT PRIMARY KEY,
            type_id TEXT,
            name TEXT,
            pic TEXT,
            latest TEXT,
            source_fp TEXT,
            source_id TEXT,
            api TEXT,
            ext TEXT
        )
    """)
    con.commit()
    con.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_children_db()
    yield


from concurrent.futures import ThreadPoolExecutor

# drpy 子进程解析专用线程池：限制并发，防止批量 detail 拉起过多 node 进程
# 占满 CPU/内存。4 个 worker 足以应付 TV 端详情页加载，又不会拖垮容器。
_DRPY_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="drpy")

app = FastAPI(lifespan=lifespan, title="Ponyo Children API")

SOURCES_DB = DATA_DIR / "sources.db"
APPROVED_JAR_DIR = DATA_DIR / "approved-assets" / "jar"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
SUB_DIR = Path("/app/subscription")
DRPYS_DIR = Path("/app/drpys/js")
# host 上的 VIP 解析服务（Playwright 桌面 Chromium 出流，App 端作为 type=1 解析器接入）
JX_PARSE_UPSTREAM = "http://172.19.0.1:8001"


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


@app.get("/quality")
async def quality(
    src: str = Query(..., max_length=200, description="客户端卡片 sourceKey"),
    title: str = Query(..., max_length=200, description="影片名 vod_name"),
):
    """搜索页海报右上角清晰度：返回该源对该片的实测清晰度（读已探测结果）。

    命中:   {"tier":"fhd","label":"1080P","width":1920,"height":1080,...}
    未命中: {"tier":null}（客户端不显示角标；实时探测回填由阶段2增强）
    """
    result = query_quality(SOURCES_DB, src, title)
    return JSONResponse(result, headers={"Cache-Control": "no-store"})


@app.get("/ponyo.json")
async def ponyo_subscription():
    """TVBox 订阅发布（自有托管，无 CDN 缓存，发布即时生效）。"""
    target = SUB_DIR / "ponyo.json"
    if not target.is_file():
        raise HTTPException(status_code=404, detail="subscription not found")
    return FileResponse(
        target,
        media_type="application/json; charset=utf-8",
        headers={"Cache-Control": "no-store"},
    )



# ---------------------------------------------------------------------------
# 本地测试订阅：拉取线上 ponyo.json，把 "Ponyo解析" 的 URL 替换为本地
# /jx/parse，其余保持不变。用于 adb reverse 环境下验证直连解析链路，
# 避免线上订阅静默刷新把解析地址覆盖回 api.ponyo.fun。
# ---------------------------------------------------------------------------
_LOCAL_JX_URL = "http://127.0.0.1:8000/jx/parse?url="
_UPSTREAM_SUBSCRIPTION = "https://api.ponyo.fun/ponyo.json"


@app.get("/ponyo-local.json")
async def ponyo_local_subscription():
    """本地测试订阅：线上配置 + 本地解析器地址。"""
    async with httpx.AsyncClient(timeout=15.0, trust_env=False) as client:
        resp = await client.get(_UPSTREAM_SUBSCRIPTION)
        resp.raise_for_status()
        data = resp.json()
    replaced = 0
    for p in data.get("parses", []):
        # 只替换 type=1 的 Ponyo 官方解析器（JSON 解析），第三方网页解析器不动
        if p.get("type") == 1 and "api.ponyo.fun" in str(p.get("url", "")):
            p["url"] = _LOCAL_JX_URL
            replaced += 1
    return JSONResponse(
        data,
        headers={"Cache-Control": "no-store"},
    )
@app.get("/aggregated-live.m3u")
async def aggregated_live_m3u():
    """聚合直播 M3U（自有托管，无 CDN 缓存，发布即时生效）。"""
    target = SUB_DIR / "aggregated-live.m3u"
    if not target.is_file():
        raise HTTPException(status_code=404, detail="m3u not found")
    return FileResponse(
        target,
        media_type="application/vnd.apple.mpegurl; charset=utf-8",
        headers={"Cache-Control": "no-store"},
    )


# 静态文件路由：serve subscription/libs/ 下的依赖文件（js/json 等）
@app.get("/libs/{file_path:path}")
async def serve_lib_file(file_path: str):
    """Serve static dependency files under subscription/libs/."""
    # 安全校验：禁止路径穿越
    if ".." in file_path or file_path.startswith("/"):
        raise HTTPException(status_code=400, detail="invalid path")
    target = SUB_DIR / "libs" / file_path
    if not target.is_file():
        raise HTTPException(status_code=404, detail="file not found")
    # 根据扩展名设置 media_type
    suffix = target.suffix.lower()
    media_types = {
        ".js": "application/javascript; charset=utf-8",
        ".json": "application/json; charset=utf-8",
        ".py": "text/plain; charset=utf-8",
        ".txt": "text/plain; charset=utf-8",
    }
    media_type = media_types.get(suffix, "application/octet-stream")
    return FileResponse(
        target,
        media_type=media_type,
        headers={"Cache-Control": "public, max-age=300"},
    )

def _safe_module(name: str) -> str:
    """drpy 规则模块名校验：仅允许普通文件名，禁止路径穿越/隐藏名。"""
    if not isinstance(name, str):
        return ""
    name = name.strip()
    if not name or "/" in name or "\\" in name or ".." in name or name.startswith("."):
        return ""
    return name


@app.get("/drpys/manifest")
async def drpys_manifest():
    """drpy 规则清单：{module: sha256}，供 App 检查需要更新的规则。"""
    manifest = {}
    if DRPYS_DIR.is_dir():
        for f in sorted(DRPYS_DIR.glob("*.js")):
            manifest[f.stem] = hashlib.sha256(f.read_bytes()).hexdigest()
    return JSONResponse(manifest, headers={"Cache-Control": "no-store"})


@app.get("/drpys/rule")
async def drpys_rule(name: str = Query(...)):
    """返回单个 drpy 规则 JS 源文件。"""
    module = _safe_module(name)
    if not module:
        raise HTTPException(status_code=404, detail="rule not found")
    target = DRPYS_DIR / f"{module}.js"
    if not target.is_file():
        raise HTTPException(status_code=404, detail="rule not found")
    return FileResponse(
        target,
        media_type="application/javascript; charset=utf-8",
        headers={
            "Cache-Control": "public, max-age=300",
            "ETag": f'"{hashlib.sha256(target.read_bytes()).hexdigest()}"',
        },
    )


@app.get("/jx/parse")
async def jx_parse_proxy(
    url: str = Query(..., max_length=2000),
    # ---- 无损云直连新增参数（旧版 App 不传 -> 自动走旧路径，向后兼容）----
    title: str = Query(None, max_length=200, description="片名 mVodInfo.name"),
    ep: str = Query(None, max_length=100, description="集名 vs.name，如 第01集"),
    ep_index: int = Query(None, ge=0, le=9999, description="集序号，从 1 开始"),
    lang: str = Query(None, max_length=20, description="语言标记（App 端从片名提取，如 普通话/英文/粤语）"),
):
    """VIP 解析入口（双模式）：
    1. 带 title -> 无损云直连：搜采集站拿 m3u8（主力，稳定）
    2. 直连 miss / 未带 title -> 回退 host:8001 Playwright 出流（兜底）
    """
    # ---- 模式 1：无损云直连 ----
    if title:
        direct = await direct_resolve(title, ep, ep_index, lang=lang)
        if direct:
            return JSONResponse(direct, headers={"Cache-Control": "no-store"})
        # 直连 miss：继续往下走 Playwright 兜底（日志留痕便于排查命中率）
        print(f"[jx/direct] miss: title={title!r} ep={ep!r} ep_index={ep_index}")

    # ---- 模式 2：旧 Playwright 路径（原逻辑原样保留）----
    if not url.startswith("http"):
        raise HTTPException(status_code=400, detail="bad url")
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.get(f"{JX_PARSE_UPSTREAM}/jx/parse", params={"url": url})
        return JSONResponse(r.json(), headers={"Cache-Control": "no-store"})
    except Exception:
        return JSONResponse(
            {"url": "", "error": "upstream-unavailable"},
            headers={"Cache-Control": "no-store"},
        )


def resolve_approved_jar(
    sha256: str,
    *,
    db_path: str | Path | None = None,
    asset_dir: str | Path | None = None,
    now: str | None = None,
) -> Path | None:
    """Return a materialized JAR only while its exact SHA remains approved."""
    sha256 = sha256.lower()
    if not SHA256_RE.fullmatch(sha256):
        return None
    db_path = Path(db_path) if db_path is not None else SOURCES_DB
    asset_dir = Path(asset_dir) if asset_dir is not None else APPROVED_JAR_DIR
    now = now or datetime.now(timezone.utc).isoformat()
    try:
        con = sqlite3.connect(f"file:{Path(db_path)}?mode=ro", uri=True)
        row = con.execute(
            "SELECT 1 FROM dependency_asset_approval "
            "WHERE content_sha256=? AND asset_type='jar' AND status='approved' "
            "AND expires_at IS NOT NULL AND expires_at>?",
            (sha256, now),
        ).fetchone()
        con.close()
    except sqlite3.Error:
        return None
    if row is None:
        return None
    target = Path(asset_dir) / f"{sha256}.jar"
    return target if target.is_file() else None


@app.get("/assets/jar/{sha256}.jar")
async def approved_jar(sha256: str):
    target = resolve_approved_jar(sha256)
    if target is None:
        raise HTTPException(status_code=404, detail="approved asset not found")
    return FileResponse(
        target,
        media_type="application/java-archive",
        filename=f"{sha256}.jar",
        headers={
            "Cache-Control": "public, max-age=300",
            "CDN-Cache-Control": "public, max-age=300",
            "Cloudflare-CDN-Cache-Control": "public, max-age=300",
            "ETag": f'"{sha256}"',
            "X-Content-Type-Options": "nosniff",
        },
    )


# 点播时最多把多少集解析成直链（m3u8/mp4）。
# 动漫豆单部可达 50+ 集 × 5 条线路；全量 playurl 会再次把详情拖到 40s+。
MAX_PLAYURL_RESOLVE = 24
# 只解析第一条线路，避免多线路把次数打满
MAX_PLAY_LINES = 1


def _is_media_url(url: str) -> bool:
    """判断是否已经是播放器可直接打开的媒体地址。网页站不算可播。"""
    return is_playable_media_url(url)


async def _fetch_maccms_json(url: str) -> dict | None:
    """异步拉取 MacCMS JSON。失败返回 None，不抛到点播主循环外。"""
    try:
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
            r = await client.get(url, headers={"User-Agent": "ponyo-children"})
            r.raise_for_status()
            data = r.json()
            return data if isinstance(data, dict) else None
    except Exception:
        return None


async def _resolve_maccms_detail(endpoint: str, source_id: str) -> dict:
    """点播 MacCMS：直接请求 ac=detail&ids=，不走 drpy。

    只把真实 m3u8/mp4/flv 交给 App；网页、空地址、整条线路无效时
    vod_play_url 为空，不生成假线路。
    """
    empty = {"vod_play_from": "儿童专线", "vod_play_url": ""}
    if not endpoint or not source_id:
        return empty
    url = _maccms_request_url(endpoint, ac="detail", ids=str(source_id))
    doc = await _fetch_maccms_json(url)
    if not isinstance(doc, dict):
        return empty
    lst = doc.get("list") or []
    if not lst or not isinstance(lst[0], dict):
        return empty
    play_from, play_url = maccms_play_fields(
        lst[0], max_lines=MAX_PLAY_LINES, max_eps=MAX_PLAYURL_RESOLVE
    )
    return {
        "vod_play_from": play_from if play_url else "儿童专线",
        "vod_play_url": play_url,
    }


def _episodes_from_detail(detail: dict) -> list[dict]:
    """从 MacCMS 详情的 vod_play_from / vod_play_url 拆出选集。"""
    if not isinstance(detail, dict):
        return []
    play_from = str(detail.get("vod_play_from") or "")
    play_url = str(detail.get("vod_play_url") or "")
    if not play_url:
        return []
    line_names = [x for x in play_from.split("$$$") if x] or ["儿童专线"]
    url_lines = play_url.split("$$$")
    episodes: list[dict] = []
    for idx, url_line in enumerate(url_lines):
        line_name = line_names[idx] if idx < len(line_names) else f"线路{idx + 1}"
        for ep in url_line.split("#"):
            if "$" not in ep:
                continue
            name, url = ep.split("$", 1)
            name, url = name.strip(), url.strip()
            if name and url:
                episodes.append({
                    "name": name,
                    "line": line_name,
                    "url": url,
                    "flag": url,
                })
    return episodes


def _pick_line_episodes(episodes: list[dict]) -> tuple[str, list[dict]]:
    """只保留前 MAX_PLAY_LINES 条线路，并截断到 MAX_PLAYURL_RESOLVE 集。"""
    if not episodes:
        return "儿童专线", []
    lines: list[str] = []
    grouped: dict[str, list[dict]] = {}
    for ep in episodes:
        line = str(ep.get("line") or "").strip() or "儿童专线"
        if line not in grouped:
            lines.append(line)
            grouped[line] = []
        grouped[line].append(ep)
    chosen_lines = lines[:MAX_PLAY_LINES] or ["儿童专线"]
    picked: list[dict] = []
    for line in chosen_lines:
        picked.extend(grouped.get(line, []))
    return chosen_lines[0], picked[:MAX_PLAYURL_RESOLVE]


# 分类必须与 children_aggregate.CATEGORY_KEYWORDS 的顺序一致（type_id 1..6），
# 「热门推荐」= t=0，表示全量列表（不按分类过滤）。
CATEGORIES = [
    {"type_id": "0", "type_name": "热门推荐"},
    {"type_id": "1", "type_name": "学龄前"},
    {"type_id": "2", "type_name": "国产动画"},
    {"type_id": "3", "type_name": "经典动画"},
    {"type_id": "4", "type_name": "少儿英语"},
    {"type_id": "5", "type_name": "动画电影"},
    {"type_id": "6", "type_name": "科普启蒙"},
]
# App 分类页每次拉 20 条；必须按 pg 翻页，否则缓存再多也只显示第一页。
PAGE_SIZE = 20


def _get_db():
    con = sqlite3.connect(str(DATA_DIR / "children_cache.db"))
    con.row_factory = sqlite3.Row
    return con


def _page_int(pg: Optional[str]) -> int:
    """把 App 传来的 pg 转成从 1 开始的页码。"""
    try:
        n = int(pg or "1")
    except (TypeError, ValueError):
        n = 1
    return n if n >= 1 else 1


def _query_video_page(con, t: Optional[str], wd: Optional[str], pg: Optional[str]) -> dict:
    """按分类/搜索词分页返回列表。pagecount 按总数计算，App 才能继续翻页。"""
    page = _page_int(pg)
    where = "WHERE 1=1"
    params: list = []
    if t and t != "0":
        where += " AND type_id=?"
        params.append(t)
    if wd:
        where += " AND name LIKE ?"
        params.append(f"%{wd}%")
    total = con.execute(f"SELECT COUNT(*) FROM videos {where}", params).fetchone()[0]
    offset = (page - 1) * PAGE_SIZE
    rows = con.execute(
        f"SELECT * FROM videos {where} ORDER BY rowid LIMIT ? OFFSET ?",
        [*params, PAGE_SIZE, offset],
    ).fetchall()
    result_list = [
        {
            "vod_id": r["id"],
            "vod_name": r["name"],
            "vod_pic": r["pic"],
            "vod_remarks": r["latest"],
        }
        for r in rows
    ]
    pagecount = max(1, (int(total) + PAGE_SIZE - 1) // PAGE_SIZE)
    return {
        "page": page,
        "pagecount": pagecount,
        "limit": PAGE_SIZE,
        "total": int(total),
        "list": result_list,
    }


@app.get("/api.php/provide/vod/")
async def provide_vod(
    ac: Optional[str] = Query(None),
    t: Optional[str] = Query(None),
    pg: Optional[str] = Query("1"),
    wd: Optional[str] = Query(None),
    ids: Optional[str] = Query(None),
):

    if ac == "list":
        # App 端 macCMS 首页推荐从 ac=list 的 list 字段读取；返回全量列表前 20 条
        con = _get_db()
        try:
            rows = con.execute(
                "SELECT id, name, pic, latest FROM videos ORDER BY rowid LIMIT 20"
            ).fetchall()
            home_list = [
                {
                    "vod_id": r["id"],
                    "vod_name": r["name"],
                    "vod_pic": r["pic"],
                    "vod_remarks": r["latest"],
                }
                for r in rows
            ]
        finally:
            con.close()
        return JSONResponse({"class": CATEGORIES, "list": home_list})

    con = _get_db()
    try:
        if ac == "detail" or ids:
            # 修复: TVBox type=1 源点分类发的是 ac=detail&t=N&pg=N (无 ids)
            # 原先直接返回空 list 导致 App 显示"暂无内容"
            # 无 ids 但有 t 时, 按分类返回列表 (等价 videolist 逻辑)
            if not ids and t:
                # App 点分类发 ac=detail&t=N&pg=N，按分类分页返回列表
                return JSONResponse(_query_video_page(con, t, None, pg))
            if not ids:
                return JSONResponse({"list": []})
            id_list = ids.split(",")

            # 主页推荐批量详情(ids 多个): 只返回基本信息, 不解析 drpy 播放地址。
            # 否则 14 个视频 x (detail+episode+每集 playurl) 个 drpy 子进程会超时,
            # 导致 App 端 homeSourceRec 为 null 回退到豆瓣热播综合剧。
            # 主页列表展示只需 vod_id/name/pic; 播放地址在用户点播单个视频时
            # 由 DetailActivity 用单个 id 重新请求(走下方单条 drpy 解析分支)。
            if len(id_list) > 1:
                placeholders = ",".join("?" * len(id_list))
                rows = con.execute(
                    f"SELECT * FROM videos WHERE id IN ({placeholders})", id_list
                ).fetchall()
                batch_list = [
                    {
                        "vod_id": r["id"],
                        "vod_name": r["name"],
                        "vod_pic": r["pic"],
                        "type_name": "儿童",
                        "vod_remarks": r["latest"],
                        "vod_play_from": "儿童专线",
                        "vod_play_url": "",
                    }
                    for r in rows
                ]
                return JSONResponse({"list": batch_list})

            # 点播详情(ids 单个): 解析 drpy 播放地址。
            # 只解析第一条线路、最多 MAX_PLAYURL_RESOLVE 集；已是 m3u8/mp4 的直链不再二次 playurl。
            # 网页 URL（v.qq.com / iqiyi / youku）不算可播，避免 App 显示假线路后播不了。
            loop = asyncio.get_event_loop()
            placeholders = ",".join("?" * len(id_list))
            rows = con.execute(
                f"SELECT * FROM videos WHERE id IN ({placeholders})", id_list
            ).fetchall()

            result_list = []
            for r in rows:
                from ponyo_source_manager.probes.drpy_runner import (
                    run_drpy_detail,
                    run_drpy_episode,
                    run_drpy_playurl,
                )

                row_dict = dict(r)
                rule_path = row_dict.get("api") or row_dict.get("ext") or ""
                if not rule_path:
                    continue

                # MacCMS 采集源：直接请求 ac=detail&ids=原始 vod_id，不走 drpy
                if is_maccms_endpoint(row_dict.get("api") or "", row_dict.get("ext") or ""):
                    play = await _resolve_maccms_detail(
                        row_dict.get("api") or "", r["source_id"]
                    )
                    result_list.append({
                        "vod_id": r["id"],
                        "vod_name": r["name"],
                        "vod_pic": r["pic"],
                        "type_name": "儿童",
                        "vod_remarks": r["latest"],
                        "vod_play_from": play["vod_play_from"],
                        "vod_play_url": play["vod_play_url"],
                    })
                    continue

                # 阻塞的 drpy 子进程调用移入线程池，避免卡死 event loop
                detail_res, ep_res = await asyncio.gather(
                    loop.run_in_executor(
                        _DRPY_EXECUTOR, run_drpy_detail, rule_path, r["source_id"]
                    ),
                    loop.run_in_executor(
                        _DRPY_EXECUTOR, run_drpy_episode, rule_path, r["source_id"]
                    ),
                )

                episodes = []
                if ep_res.get("success") and ep_res.get("episodes"):
                    episodes = ep_res["episodes"]
                if not episodes:
                    episodes = _episodes_from_detail(
                        (detail_res or {}).get("detail") or {}
                    )

                vod_play_from, picked = _pick_line_episodes(episodes)
                vod_play_url = ""

                async def _resolve_episode(ep):
                    title = ep.get("name", ep.get("title", ""))
                    flag = ep.get("url", ep.get("flag", ""))
                    if not (title and flag):
                        return None
                    # 详情里已经是直链：不再打 playurl
                    if _is_media_url(str(flag)):
                        return f"{title}${flag}"
                    playurl_res = await loop.run_in_executor(
                        _DRPY_EXECUTOR, run_drpy_playurl, rule_path, flag
                    )
                    play_url = ""
                    if playurl_res.get("success"):
                        play_url = str(playurl_res.get("play_url") or "")
                    if _is_media_url(play_url):
                        return f"{title}${play_url}"
                    # 网页/空地址一律丢弃，不把假线路交给 App
                    return None

                if picked:
                    ep_results = await asyncio.gather(
                        *(_resolve_episode(ep) for ep in picked)
                    )
                    episodes_str_list = [e for e in ep_results if e]
                    if episodes_str_list:
                        vod_play_url = "#".join(episodes_str_list)
                    else:
                        vod_play_from = "儿童专线"

                vod = {
                    "vod_id": r["id"],
                    "vod_name": r["name"],
                    "vod_pic": r["pic"],
                    "type_name": "儿童",
                    "vod_remarks": r["latest"],
                    "vod_play_from": vod_play_from if vod_play_url else "儿童专线",
                    "vod_play_url": vod_play_url,
                }
                result_list.append(vod)
            return JSONResponse({"list": result_list})

        elif ac == "videolist" or wd or t:
            return JSONResponse(_query_video_page(con, t, wd, pg))

    finally:
        con.close()

    return JSONResponse({"list": []})


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)
