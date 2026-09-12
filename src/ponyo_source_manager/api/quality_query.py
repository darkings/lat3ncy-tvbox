#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""清晰度查询服务（Ponyo Quality API）。

供 TVBox 客户端在搜索页海报右上角显示「当前源对该片的实际清晰度」。

数据流：
  客户端搜索到影片卡片（带 sourceKey + vod_name）
    → GET /quality?src=<sourceKey>&title=<片名>
    → 本模块按 sourceKey 解析出 fingerprint，查 media_probe 取该 (源,片名) 最高清晰度
    → 命中返回 {"tier","width","height","label"}；未命中返回 {"tier":null}

关联链：
  sourceKey = raw_source.site_key = raw_json.key（客户端卡片上的源标识）
  raw_source.id = dedup_group.primary_raw_id → dedup_group.fingerprint
  dedup_group.fingerprint = media_probe.fingerprint（清晰度探测记录）

设计说明：
  - 只读已有探测结果，不在请求路径上做 ffprobe（避免 4.5s 阻塞 + drpy 本地代理
    地址 127.0.0.1:5757 重启失效的问题）。实时探测回填由独立的阶段2增强处理。
  - quality_tier 取值：sd|hd|fhd|uhd → label 标清|720P|1080P|4K。
  - 同一片在同一源可能有多条探测（多集/多线路），取最高一档作为该片可达清晰度。
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Any

# tier → 客户端角标文案
TIER_LABEL = {
    "uhd": "4K",
    "fhd": "1080P",
    "hd": "720P",
    "sd": "标清",
}
# tier 优先级（取最高一档）
TIER_RANK = {"sd": 0, "hd": 1, "fhd": 2, "uhd": 3}

# 标题归一化：客户端 vod_name 与服务器 content_title 可能存在的差异
# （全角空格、首尾空白、季/集后缀差异）。只做空格/大小写归一，保持宽松匹配。
_WS_RE = re.compile(r"\s+")


def _norm_title(title: str) -> str:
    """标题归一化：去首尾空白、折叠连续空白、全角空格转半角。"""
    if not title:
        return ""
    t = title.replace("　", " ").strip()
    return _WS_RE.sub(" ", t)


def _fingerprint_for_source(con: sqlite3.Connection, source_key: str) -> str | None:
    """按 sourceKey 解析出清晰度探测用的 fingerprint。

    sourceKey 可能命中 raw_source.site_key 或 raw_json 内的 key。
    经 dedup_group 取该源的主 fingerprint（媒体探测按主指纹归档）。
    """
    if not source_key:
        return None
    # 优先精确匹配 site_key
    row = con.execute(
        "SELECT dg.fingerprint FROM raw_source r "
        "JOIN dedup_group dg ON dg.primary_raw_id = r.id "
        "WHERE r.site_key = ? LIMIT 1",
        (source_key,),
    ).fetchone()
    if row:
        return row[0]
    # 兜底：匹配 raw_json 里的 "key" 字段（部分源 site_key 与对外 key 不同名）
    row = con.execute(
        "SELECT dg.fingerprint FROM raw_source r "
        "JOIN dedup_group dg ON dg.primary_raw_id = r.id "
        "WHERE json_extract(r.raw_json, '$.key') = ? LIMIT 1",
        (source_key,),
    ).fetchone()
    return row[0] if row else None


def query_quality(
    db_path: str | Path,
    source_key: str,
    title: str,
) -> dict[str, Any]:
    """查询某源下某影片的最高实测清晰度。

    返回字典：
      命中:  {"tier": "fhd", "label": "1080P", "width": 1920, "height": 1080,
              "codec": "h264", "probes": 12}
      未命中:{"tier": None}
      源未知:{"tier": None, "reason": "unknown_source"}
    """
    title_n = _norm_title(title)
    if not source_key or not title_n:
        return {"tier": None}

    try:
        con = sqlite3.connect(f"file:{Path(db_path)}?mode=ro", uri=True)
    except sqlite3.Error:
        return {"tier": None, "reason": "db_unavailable"}
    try:
        fp = _fingerprint_for_source(con, source_key)
        if not fp:
            return {"tier": None, "reason": "unknown_source"}

        # 取该 (源, 片名) 所有成功探测，按 tier 优先级选最高一档
        rows = con.execute(
            "SELECT quality_tier, width, height, video_codec, COUNT(*) AS cnt "
            "FROM media_probe "
            "WHERE fingerprint=? AND ffprobe_success=1 AND content_title=? "
            "GROUP BY quality_tier, width, height, video_codec",
            (fp, title_n),
        ).fetchall()
        if not rows:
            # 宽松重试：标题含季/集等后缀时，尝试前缀匹配（content_title LIKE 'title%'）
            rows = con.execute(
                "SELECT quality_tier, width, height, video_codec, COUNT(*) AS cnt "
                "FROM media_probe "
                "WHERE fingerprint=? AND ffprobe_success=1 AND content_title LIKE ? "
                "GROUP BY quality_tier, width, height, video_codec",
                (fp, title_n + "%"),
            ).fetchall()
        if not rows:
            return {"tier": None}

        # 选最高 tier；同 tier 内取探测数最多的一组（更可信）
        best = max(
            rows,
            key=lambda r: (TIER_RANK.get(r[0], -1), r[4]),
        )
        tier = best[0]
        return {
            "tier": tier,
            "label": TIER_LABEL.get(tier, ""),
            "width": best[1],
            "height": best[2],
            "codec": best[3],
            "probes": int(best[4]),
        }
    except sqlite3.Error:
        return {"tier": None, "reason": "query_error"}
    finally:
        con.close()
