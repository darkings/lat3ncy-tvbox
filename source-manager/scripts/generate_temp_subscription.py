# -*- coding: utf-8 -*-
"""临时/正式订阅生成：allow/hard_pass/candidate 混合按得分排序（默认上限 95 点播源）。

- 工具源仅保留豆瓣推荐（配置中心/本地视频不可用，剔除）
- 点播源：allow/hard_pass/candidate 全量按 total_score 降序（不分组）
- 源名字统一清洗：去 emoji/注释/数字序号前缀，┃→-；重名时保留原名

发布到与正式版相同的地址，后续源晋级后用正式 30 源版覆盖即可（连接地址不变）。
"""

import argparse
import json
import re
import sqlite3
from pathlib import Path

EXEMPT_KEYS = {"drpy_js_豆瓣"}

_EMOJI_RE = re.compile(
    "[\U0001f000-\U0001faff\U00002600-\U000027bf\U0001f900-\U0001f9ff\U0000fe0f\U00002702-\U000027b0]"
)
_SEQ_RE = re.compile(r"^\d+-")
_TRAIL_NOTE_RE = re.compile(r"<=\S+")


def clean_name(name: str) -> str:
    """统一源名字：去 emoji、去 (vpn) 等前缀注释、去 <= 尾部注释、┃→-、折叠空格。"""
    n = _EMOJI_RE.sub("", name)
    n = n.replace("(vpn)", "")
    n = _TRAIL_NOTE_RE.sub("", n)
    n = re.sub(r"┃", "-", n)
    n = re.sub(r"\s+", " ", n).strip(" -")
    return n


def strip_seq_prefix(name: str) -> str:
    """去掉开头的数字序号前缀（如 40-橘猫采集 → 橘猫采集）。"""
    return _SEQ_RE.sub("", name)


def _load_sites(con, limit: int) -> list:
    """三状态混合按评分降序取源（指纹去重，primary_raw_id 对应 raw_json）。"""
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
        WHERE ls.state IN ('allow', 'hard_pass', 'candidate')
        ORDER BY COALESCE(s.total_score, 0) DESC
        LIMIT ?
        """,
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


def _assign_names(sites: list) -> None:
    """统一命名：清洗 + 去数字前缀；重名项回退为保留前缀的清洗版（保证唯一可辨）。"""
    cleaned = [clean_name(str(s.get("name", ""))) for s in sites]
    stripped = [strip_seq_prefix(c) for c in cleaned]
    counts = {}
    for n in stripped:
        counts[n] = counts.get(n, 0) + 1
    for s, c, st in zip(sites, cleaned, stripped):
        s["name"] = st if counts[st] == 1 else c


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

    # 1. 工具源：仅豆瓣推荐（从模板提取）
    tool_sites = [s for s in template.get("sites", []) if s.get("key") in EXEMPT_KEYS]

    # 2. 点播源：三状态混合按分排序，过滤本机 jar，取前 limit
    vod_sites = [s for s in _load_sites(con, args.limit * 3) if _jar_usable(s)][
        : args.limit
    ]
    _assign_names(vod_sites)

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
