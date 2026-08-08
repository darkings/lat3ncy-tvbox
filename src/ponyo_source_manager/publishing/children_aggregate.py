#!/usr/bin/env python3
"""儿童内容聚合：多源去重、统一分类、多线路选择与安全过滤。

对应 PLAN §十一。用户只看到一个「儿童动画」入口，
后台从多个源中汇总、去重、排序，选出最佳播放线路。
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from ponyo_source_manager.core.common import PONYO_HOME as HERE

# PLAN §十一 统一分类
DEFAULT_CATEGORIES = [
    "热门推荐", "学龄前", "国产动画", "经典动画",
    "少儿英语", "动画电影", "科普启蒙",
]

# 分类关键词映射
CATEGORY_KEYWORDS = {
    "学龄前": ["宝宝", "巴士", "贝瓦", "儿歌", "幼儿", "早教", "启蒙",
              "peppa", "佩奇", "汪汪队", "可可", "碰碰狐"],
    "国产动画": ["熊出没", "喜羊羊", "猪猪侠", "超级飞侠", "哪吒",
               "大头儿子", "蜡笔小新", "巴啦啦", "斗罗", "武魂"],
    "经典动画": ["猫和老鼠", "海绵宝宝", "米老鼠", "唐老鸭", "变形金刚",
               "叮当猫", "七龙珠", "机器猫", "哆啦a梦", "蓝精灵"],
    "少儿英语": ["英语", "english", "abc", "phonics", "disney",
               "frozen", "英文"],
    "动画电影": ["电影", "movie", "剧场版", "大电影"],
    "科普启蒙": ["科普", "科学", "恐龙", "太空", "海洋", "动物",
              "nature", "百科"],
}

# 儿童安全屏蔽词
UNSAFE_KEYWORDS = [
    "成人", "伦理", "18禁", "色情", "赌博", "博彩",
    "约炮", "AV", "三级", "情色",
]


def _normalize_title(title: str) -> str:
    """标准化标题用于去重。"""
    t = title.strip()
    t = re.sub(r"[（(].+?[)）]", "", t)  # 去括号内容
    t = re.sub(r"第?\d+季", "", t)        # 去季数
    t = re.sub(r"\s+", "", t)
    return t.lower()


def classify_children_content(title: str) -> str:
    """将儿童内容分到统一分类。"""
    text = title.lower()
    for cat, keywords in CATEGORY_KEYWORDS.items():
        for kw in keywords:
            if kw.lower() in text:
                return cat
    return "热门推荐"


def is_safe_content(title: str, category: str = "") -> bool:
    """检查是否为安全的儿童内容。"""
    text = (title + " " + category).lower()
    return not any(kw.lower() in text for kw in UNSAFE_KEYWORDS)


def dedupe_children_content(items: list[dict]) -> list[dict]:
    """跨源去重：相同标题+年份+季数+语言的内容只保留最佳线路。

    PLAN §十一第4节：不能只按标题合并，避免同名但不同版本混淆。
    """
    groups: dict[str, list[dict]] = {}
    for item in items:
        title = _normalize_title(item.get("title", ""))
        year = item.get("year", "")
        season = item.get("season", "")
        lang = item.get("language", "")
        key = f"{title}|{year}|{season}|{lang}"
        groups.setdefault(key, []).append(item)

    deduped = []
    for key, members in groups.items():
        # 按质量得分排序，保留最佳
        members.sort(key=lambda m: (
            -m.get("quality_score", 0),
            -m.get("play_success_rate", 0),
            -m.get("speed_score", 0),
        ))
        best = members[0].copy()
        # 保留所有来源作为备用线路
        best["routes"] = [
            {"source": m.get("source_fp", ""),
             "play_url": m.get("play_url", ""),
             "quality": m.get("quality_tier", ""),
             "success_rate": m.get("play_success_rate", 0)}
            for m in members
        ]
        deduped.append(best)

    return deduped


def aggregate_children_sources(db_path: str, *,
                               report_path: str | None = None,
                               now: str | None = None) -> dict:
    """从数据库中聚合所有儿童内容。"""
    now = now or datetime.now(timezone.utc).isoformat()
    con = sqlite3.connect(str(db_path))

    # 查找所有儿童/少儿分类的源
    rows = con.execute("""
        SELECT n.fingerprint, n.category, r.name, r.site_key,
               ls.state
        FROM norm_source n
        JOIN raw_source r ON n.raw_id = r.id
        LEFT JOIN list_state ls ON n.fingerprint = ls.fingerprint
        WHERE (
            n.category = '儿童'
            OR EXISTS (
                SELECT 1 FROM capability_sampling cs
                WHERE cs.fingerprint=n.fingerprint
                  AND cs.capability='children'
                  AND cs.hit_count>0
            )
        )
        AND n.category NOT IN ('直播', '网盘', '工具')
        AND ls.state = 'allow'
    """).fetchall()

    # 统计每个源的评分和质量
    sources = []
    for fp, cat, name, key, state in rows:
        score_row = con.execute(
            "SELECT total_score, hard_pass FROM score_snapshot "
            "WHERE fingerprint=? ORDER BY scored_at DESC LIMIT 1",
            (fp,)).fetchone()
        if not score_row or score_row[1] != 1:
            continue
        quality_row = con.execute(
            "SELECT COUNT(*) as total, "
            "SUM(CASE WHEN quality_tier IN ('hd','fhd','uhd') THEN 1 ELSE 0 END) as hd "
            "FROM media_probe WHERE fingerprint=? AND success=1",
            (fp,)).fetchone()

        sources.append({
            "fingerprint": fp, "name": name, "key": key,
            "state": state or "candidate",
            "score": score_row[0] if score_row else 0,
            "hd_count": quality_row[1] if quality_row else 0,
            "total_probes": quality_row[0] if quality_row else 0,
        })

    con.close()

    # 按评分排序，分主力和备用
    sources.sort(key=lambda s: -s.get("score", 0))
    primary = sources[:2] if len(sources) >= 2 else sources
    backup = sources[2:4] if len(sources) > 2 else []
    ready = len(primary) == 2 and len(backup) == 2

    import os
    api_url = os.environ.get("CHILDREN_API_URL", "")
    if not api_url:
        raise ValueError("A12: 环境变量 CHILDREN_API_URL 未设置。正式订阅中儿童API必须使用电视可访问的HTTPS域名，不得使用 127.0.0.1 或 localhost。")
    if "127.0.0.1" in api_url or "localhost" in api_url:
        raise ValueError(f"A12: CHILDREN_API_URL 不得包含 127.0.0.1 或 localhost: {api_url}")
    
    tvbox_site = {
        "key": "Ponyo_Children",
        "name": "儿童动画",
        "type": 1,
        "api": api_url,
        "searchable": 1,
        "quickSearch": 1,
        "filterable": 1,
        "ext": ""
    } if ready else None

    summary = {
        "total_children_sources": len(sources),
        "primary": len(primary),
        "backup": len(backup),
        "ready": ready,
        "primary_names": [s["name"] for s in primary],
        "backup_names": [s["name"] for s in backup],
        "categories": DEFAULT_CATEGORIES,
        "tvbox_site": tvbox_site,
    }

    if report_path:
        report = {
            "summary": summary, "generated_at": now,
            "sources": sources,
        }
        Path(report_path).parent.mkdir(parents=True, exist_ok=True)
        Path(report_path).write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    # [NEW] Populate children_cache.db with search results from primary sources
    if ready:
        _populate_cache_from_sources(db_path, primary)

    return summary

def _populate_cache_from_sources(db_path: str, primary_sources: list[dict]):
    from ponyo_source_manager.core.common import DATA_DIR
    from ponyo_source_manager.probes.drpy_runner import run_drpy_search
    
    cache_db = DATA_DIR / "children_cache.db"
    con = sqlite3.connect(str(cache_db))
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
    con.execute("DELETE FROM videos") # Refresh cache
    
    src_db = sqlite3.connect(db_path)
    # A11: 先收集所有条目，再统一去重和安全过滤
    all_items = []
    for ps in primary_sources:
        fp = ps["fingerprint"]
        row = src_db.execute("SELECT api, ext FROM raw_source r JOIN norm_source n ON r.id = n.raw_id WHERE n.fingerprint=?", (fp,)).fetchone()
        if not row: continue
        api, ext = row
        rule_path = api or ext
        if not rule_path: continue
        
        for type_name, keywords in CATEGORY_KEYWORDS.items():
            type_id = str(list(CATEGORY_KEYWORDS.keys()).index(type_name) + 1)
            for kw in keywords[:1]: # Just first keyword for speed
                res = run_drpy_search(rule_path, kw)
                if res["success"] and res["items"]:
                    for item in res["items"]:
                        vod_name = item.get("vod_name", "")
                        # A11: 安全过滤 - 成人/伦理/博彩等不良内容拦截
                        if not is_safe_content(vod_name, type_name):
                            continue
                        all_items.append({
                            "title": vod_name,
                            "vod_id": item.get("vod_id"),
                            "pic": item.get("vod_pic", ""),
                            "latest": item.get("vod_remarks", ""),
                            "type_id": type_id,
                            "source_fp": fp,
                            "api": api,
                            "ext": ext,
                            "quality_score": ps.get("score", 0),
                            "play_success_rate": 0,
                            "speed_score": 0,
                        })
    src_db.close()

    # A11: 跨源去重 - 相同标题+年份+季数+语言只保留最佳线路
    deduped = dedupe_children_content(all_items)

    inserted = 0
    for item in deduped:
        vid = f"{item.get('source_fp', '')}_{item.get('vod_id', inserted)}"
        con.execute(
            "INSERT OR REPLACE INTO videos (id, type_id, name, pic, latest, source_fp, source_id, api, ext) VALUES (?,?,?,?,?,?,?,?,?)",
            (vid, item.get("type_id", ""), item.get("title", ""), item.get("pic", ""), item.get("latest", ""), item.get("source_fp", ""), item.get("vod_id", ""), item.get("api", ""), item.get("ext", ""))
        )
        inserted += 1
    con.commit()
    con.close()
    print(f"Populated {inserted} videos into children_cache.db (filtered from {len(all_items)} raw items)")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--db", default=str(HERE / "data" / "sources.db"))
    p.add_argument("--report",
                   default=str(HERE / "reports" / "children-report.json"))
    args = p.parse_args()
    result = aggregate_children_sources(args.db, report_path=args.report)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
