# -*- coding: utf-8 -*-
"""临时放宽订阅生成：allow/hard_pass 全部 + 高分 candidate 补足（默认上限 95 点播源）。
发布到与正式版相同的地址，后续源晋级后用正式 30 源版覆盖即可（连接地址不变）。
"""

import argparse
import json
import sqlite3
from pathlib import Path

EXEMPT_KEYS = {"drpy_js_豆瓣", "配置中心", "本地"}


def _load_sites(con, state_filter: str, limit: int) -> list:
    """按状态+评分取源（指纹去重，primary_raw_id 对应 raw_json）。"""
    rows = con.execute(
        """
        WITH LatestScores AS (
            SELECT fingerprint, total_score,
                   ROW_NUMBER() OVER(PARTITION BY fingerprint ORDER BY scored_at DESC) as rn
            FROM score_snapshot
        )
        SELECT ls.state, r.raw_json, s.total_score
        FROM list_state ls
        JOIN dedup_group dg ON ls.fingerprint = dg.fingerprint
        JOIN raw_source r ON dg.primary_raw_id = r.id
        LEFT JOIN LatestScores s ON ls.fingerprint = s.fingerprint AND s.rn = 1
        WHERE ls.state IN (%s)
        ORDER BY COALESCE(s.total_score, 0) DESC
        LIMIT ?
        """
        % state_filter,
        (limit,),
    ).fetchall()
    sites = []
    seen = set()
    for r in rows:
        try:
            obj = json.loads(r["raw_json"])
        except Exception:
            continue
        key = str(obj.get("key", ""))
        if not key or key in seen:
            continue
        seen.add(key)
        sites.append(obj)
    return sites


def _jar_usable(obj: dict) -> bool:
    """过滤不可访问的 jar（本机地址）。纯 API 源（无 jar）直接可用。"""
    jar = str(obj.get("jar", "") or "")
    if not jar:
        return True
    low = jar.lower()
    if "127.0.0.1" in low or "localhost" in low:
        return False
    if not jar.startswith("http"):
        return False
    return True


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--db", required=True)
    p.add_argument(
        "--template",
        required=True,
        help="顶层结构模板（仓库根 subscription/ponyo.json）",
    )
    p.add_argument("--output", required=True)
    p.add_argument("--limit", type=int, default=95, help="点播源数量上限")
    args = p.parse_args()

    template = json.loads(Path(args.template).read_text(encoding="utf-8"))
    con = sqlite3.connect(args.db)
    con.row_factory = sqlite3.Row

    # 1. 工具源（豆瓣推荐/配置中心/本地）——从模板提取
    tool_sites = []
    for s in template.get("sites", []):
        k = str(s.get("key", ""))
        api = str(s.get("api", ""))
        if k in EXEMPT_KEYS or "csp_Config" in api or "csp_LocalFile" in api:
            tool_sites.append(s)

    # 2. 点播源：allow/hard_pass 优先，candidate 高分补足
    vod_sites = []
    for state in ("'allow'", "'hard_pass'"):
        for s in _load_sites(con, state, args.limit):
            if _jar_usable(s):
                vod_sites.append(s)
        if len(vod_sites) >= args.limit:
            break

    if len(vod_sites) < args.limit:
        fill = args.limit - len(vod_sites)
        for s in _load_sites(con, "'candidate'", fill * 3):
            if _jar_usable(s):
                vod_sites.append(s)
            if len(vod_sites) >= args.limit:
                break

    # 3. 组装：顶层结构沿用模板（spider/lives/parses/hosts/flags/doh/rules/ads/wallpaper）
    result = dict(template)
    result["sites"] = tool_sites + vod_sites

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(
        json.dumps(
            {
                "tool_sites": len(tool_sites),
                "vod_sites": len(vod_sites),
                "total_sites": len(result["sites"]),
                "vod_names": [s.get("name", "") for s in vod_sites],
                "output": args.output,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
