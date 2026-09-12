#!/usr/bin/env python3
"""儿童聚合服务 (FastAPI)
提供标准 TVBox/MacCMS JSON 接口。
数据库只保存源内 ID 和集数映射，不长期保存过期的播放 URL。
在收到请求时，实时解析（或借助缓存）分发到各子源。
"""

import hashlib
import json
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
async def jx_parse_proxy(url: str = Query(..., max_length=2000)):
    """VIP 解析代理：转发到 host 的 Playwright 出流服务（返回 {"url": m3u8}）。"""
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


CATEGORIES = [
    {"type_id": "1", "type_name": "经典动画"},
    {"type_id": "2", "type_name": "早教益智"},
    {"type_id": "3", "type_name": "儿歌童谣"},
]


def _get_db():
    con = sqlite3.connect(str(DATA_DIR / "children_cache.db"))
    con.row_factory = sqlite3.Row
    return con


@app.get("/api.php/provide/vod/")
async def provide_vod(
    ac: Optional[str] = Query(None),
    t: Optional[str] = Query(None),
    pg: Optional[str] = Query("1"),
    wd: Optional[str] = Query(None),
    ids: Optional[str] = Query(None),
):

    if ac == "list":
        return JSONResponse({"class": CATEGORIES, "list": []})

    con = _get_db()
    try:
        if ac == "detail" or ids:
            if not ids:
                return JSONResponse({"list": []})
            id_list = ids.split(",")
            placeholders = ",".join("?" * len(id_list))
            rows = con.execute(
                f"SELECT * FROM videos WHERE id IN ({placeholders})", id_list
            ).fetchall()

            result_list = []
            for r in rows:
                from ponyo_source_manager.probes.drpy_runner import (
                    run_drpy_detail,
                    run_drpy_episode,
                )

                row_dict = dict(r)
                rule_path = row_dict.get("api") or row_dict.get("ext") or ""
                if not rule_path:
                    continue

                detail_res = run_drpy_detail(rule_path, r["source_id"])
                ep_res = run_drpy_episode(rule_path, r["source_id"])

                vod_play_from = "儿童专线"
                vod_play_url = ""

                if ep_res["success"] and ep_res["episodes"]:
                    from ponyo_source_manager.probes.drpy_runner import run_drpy_playurl

                    episodes_str_list = []
                    for ep in ep_res["episodes"]:
                        title = ep.get("name", ep.get("title", ""))
                        flag = ep.get("url", ep.get("flag", ""))
                        if title and flag:
                            playurl_res = run_drpy_playurl(rule_path, flag)
                            if playurl_res["success"] and playurl_res["play_url"]:
                                episodes_str_list.append(
                                    f"{title}${playurl_res['play_url']}"
                                )
                            else:
                                episodes_str_list.append(f"{title}${flag}")  # Fallback
                    if episodes_str_list:
                        vod_play_url = "#".join(episodes_str_list)

                vod = {
                    "vod_id": r["id"],
                    "vod_name": r["name"],
                    "vod_pic": r["pic"],
                    "type_name": "儿童",
                    "vod_remarks": r["latest"],
                    "vod_play_from": vod_play_from,
                    "vod_play_url": vod_play_url,
                }
                result_list.append(vod)
            return JSONResponse({"list": result_list})

        elif ac == "videolist" or wd or t:
            # 返回视频列表
            query = "SELECT * FROM videos WHERE 1=1"
            params = []
            if t:
                query += " AND type_id=?"
                params.append(t)
            if wd:
                query += " AND name LIKE ?"
                params.append(f"%{wd}%")

            query += " LIMIT 20"
            rows = con.execute(query, params).fetchall()
            result_list = [
                {
                    "vod_id": r["id"],
                    "vod_name": r["name"],
                    "vod_pic": r["pic"],
                    "vod_remarks": r["latest"],
                }
                for r in rows
            ]
            return JSONResponse(
                {
                    "page": int(pg),
                    "pagecount": 1,
                    "limit": 20,
                    "total": len(result_list),
                    "list": result_list,
                }
            )

    finally:
        con.close()

    return JSONResponse({"list": []})


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)
