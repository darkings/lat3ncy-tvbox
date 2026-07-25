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

HERE = Path(__file__).resolve().parent

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
        WHERE n.category = '儿童'
        AND COALESCE(ls.state, 'candidate') != 'deny'
    """).fetchall()

    # 统计每个源的评分和质量
    sources = []
    for fp, cat, name, key, state in rows:
        score_row = con.execute(
            "SELECT total_score FROM score_snapshot "
            "WHERE fingerprint=? ORDER BY scored_at DESC LIMIT 1",
            (fp,)).fetchone()
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

    summary = {
        "total_children_sources": len(sources),
        "primary": len(primary),
        "backup": len(backup),
        "primary_names": [s["name"] for s in primary],
        "backup_names": [s["name"] for s in backup],
        "categories": DEFAULT_CATEGORIES,
    }

    if report_path:
        report = {
            "summary": summary, "generated_at": now,
            "sources": sources,
        }
        Path(report_path).parent.mkdir(parents=True, exist_ok=True)
        Path(report_path).write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    return summary


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
