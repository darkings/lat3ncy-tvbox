#!/usr/bin/env python3
"""儿童聚合服务 (FastAPI)
提供标准 TVBox/MacCMS JSON 接口。
数据库只保存源内 ID 和集数映射，不长期保存过期的播放 URL。
在收到请求时，实时解析（或借助缓存）分发到各子源。
"""
import sqlite3
import json
import re
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import FileResponse, JSONResponse
import httpx
import uvicorn
from ponyo_source_manager.core.common import DATA_DIR, CODE_DIR

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

@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


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
async def provide_vod(ac: Optional[str] = Query(None),
                      t: Optional[str] = Query(None),
                      pg: Optional[str] = Query("1"),
                      wd: Optional[str] = Query(None),
                      ids: Optional[str] = Query(None)):
    
    if ac == "list":
        return JSONResponse({"class": CATEGORIES, "list": []})
        
    con = _get_db()
    try:
        if ac == "detail" or ids:
            if not ids:
                return JSONResponse({"list": []})
            id_list = ids.split(",")
            placeholders = ",".join("?" * len(id_list))
            rows = con.execute(f"SELECT * FROM videos WHERE id IN ({placeholders})", id_list).fetchall()
            
            result_list = []
            for r in rows:
                from ponyo_source_manager.probes.drpy_runner import run_drpy_detail, run_drpy_episode
                
                row_dict = dict(r)
                rule_path = row_dict.get("api") or row_dict.get("ext") or ""
                if not rule_path: continue
                
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
                                episodes_str_list.append(f"{title}${playurl_res['play_url']}")
                            else:
                                episodes_str_list.append(f"{title}${flag}") # Fallback
                    if episodes_str_list:
                        vod_play_url = "#".join(episodes_str_list)
                        
                vod = {
                    "vod_id": r["id"],
                    "vod_name": r["name"],
                    "vod_pic": r["pic"],
                    "type_name": "儿童",
                    "vod_remarks": r["latest"],
                    "vod_play_from": vod_play_from,
                    "vod_play_url": vod_play_url
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
                    "vod_remarks": r["latest"]
                }
                for r in rows
            ]
            return JSONResponse({
                "page": int(pg),
                "pagecount": 1,
                "limit": 20,
                "total": len(result_list),
                "list": result_list
            })
            
    finally:
        con.close()
        
    return JSONResponse({"list": []})


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)
