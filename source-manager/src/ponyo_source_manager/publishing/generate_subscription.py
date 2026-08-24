#!/usr/bin/env python3
"""生成订阅文件与裁决精选 30 入口。

对应 PLAN §十七 与 §十八。
输出文件：
- subscription/ponyo-lite.json (精选 30 + 工具)
- subscription/ponyo-full.json (全量候选)
- subscription/ponyo-live.json (唯一正式直播源)
- subscription/ponyo-children.json (儿童聚合源)
- subscription/manifest.json (版本/哈希/清单)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ponyo_source_manager.core.common import CODE_DIR, DATA_DIR, PONYO_ROOT
from ponyo_source_manager.publishing.category_taxonomy import (
    is_top_name,
    load_host_whitelist,
    load_taxonomy,
    normalize_categories,
    normalize_category_name,
    raw_signature,
)

PROJECT_ROOT = PONYO_ROOT
SUB_DIR = PROJECT_ROOT / "subscription"
APPROVED_ASSET_BASE_URL = os.getenv(
    "APPROVED_ASSET_BASE_URL",
    "https://api.ponyo.fun/assets/jar",
).rstrip("/")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---- 命名规范化（与 scripts/generate_temp_subscription.py 保持一致，需同步修改） ----
_EMOJI_RE = re.compile(
    "[\U0001f000-\U0001faff\U00002600-\U000027bf\U0001f900-\U0001f9ff\U0000fe0f\U00002702-\U000027b0]"
)
_SEQ_RE = re.compile(r"^\d+-")
_TRAIL_NOTE_RE = re.compile(r"<=\S+")


def clean_name(name: str) -> str:
    """基础清洗：去 emoji/变体选择符、去 (vpn) 前缀、去 <= 注释、┃→-、折叠空格。"""
    n = _EMOJI_RE.sub("", name)
    n = re.sub(r"[\ufe0e\ufe0f]", "", n)
    n = n.replace("(vpn)", "")
    n = _TRAIL_NOTE_RE.sub("", n)
    n = re.sub(r"┃", "-", n)
    n = re.sub(r"\s+", " ", n).strip(" -")
    return n


def strip_seq_prefix(name: str) -> str:
    return _SEQ_RE.sub("", name)


_TRAD_SIMPLE = {
    "風": "风",
    "資": "资",
    "無": "无",
    "盡": "尽",
    "雲": "云",
    "動": "动",
    "畫": "画",
    "書": "书",
    "聽": "听",
    "樂": "乐",
    "優": "优",
    "劇": "剧",
    "獨": "独",
    "臥": "卧",
    "網": "网",
    "點": "点",
    "歡": "欢",
    "騰": "腾",
    "駕": "驾",
    "異": "异",
    "獸": "兽",
    "櫻": "樱",
    "遠": "远",
    "欄": "栏",
    "寶": "宝",
    "讀": "读",
    "愛": "爱",
    "華": "华",
    "廣": "广",
    "體": "体",
    "導": "导",
    "載": "载",
    "連": "连",
    "線": "线",
    "數": "数",
    "據": "据",
    "庫": "库",
    "樓": "楼",
    "鳥": "鸟",
    "蘭": "兰",
    "龍": "龙",
    "貓": "猫",
    "鳳": "凤",
    "鵬": "鹏",
    "顆": "颗",
    "葉": "叶",
    "們": "们",
    "個": "个",
    "種": "种",
    "還": "还",
    "這": "这",
    "來": "来",
    "開": "开",
    "關": "关",
    "門": "门",
    "問": "问",
    "間": "间",
    "話": "话",
    "說": "说",
    "請": "请",
    "讓": "让",
    "將": "将",
    "樣": "样",
    "塊": "块",
    "條": "条",
    "裡": "里",
    "麵": "面",
    "飯": "饭",
    "飲": "饮",
    "館": "馆",
    "馬": "马",
    "車": "车",
    "魚": "鱼",
    "雞": "鸡",
    "鴨": "鸭",
    "視": "视",
    "頻": "频",
    "採": "采",
    "麼": "么",
    "務": "务",
    "業": "业",
    "國": "国",
    "長": "长",
    "東": "东",
    "臺": "台",
    "灣": "湾",
    "場": "场",
    "區": "区",
    "時": "时",
    "對": "对",
    "錯": "错",
    "實": "实",
    "現": "现",
    "發": "发",
    "後": "后",
    "進": "进",
    "過": "过",
    "達": "达",
    "應": "应",
    "當": "当",
    "會": "会",
    "沒": "没",
}


def _to_simple(name: str) -> str:
    return "".join(_TRAD_SIMPLE.get(c, c) for c in name)


_DOMAIN_ALIASES: list[tuple[str, str]] = [
    ("lovedan", "艾旦"),
    ("apibdzy", "百度"),
]

_WORD_TAILS = [
    "资源站",
    "资源网",
    "资源",
    "影视站",
    "影视",
    "视频",
    "影院",
    "在线",
    "点播",
    "采集",
]


def normalize_name(name: str, is_builtin: bool) -> tuple[str, str]:
    """命名规范化，返回 (简短名, 回退名)。"""
    n = clean_name(name)
    n = _to_simple(n)
    if is_builtin:
        return n, n
    fallback = strip_seq_prefix(n)
    fallback = re.sub(r"\[[^\]]*\]", "", fallback).replace("(DS)", "").strip(" -")
    fallback = re.sub(r"-(GH|变体)$", "", fallback, flags=re.I).strip(" -")
    for alias_key, alias_name in _DOMAIN_ALIASES:
        if alias_key in fallback.lower():
            return alias_name, alias_name
    short = fallback
    for tail in _WORD_TAILS:
        if short.endswith(tail):
            remaining = short[: -len(tail)]
            # 去词尾后保留：至少 2 字符且（含汉字 或 至少 3 个 ASCII 字符，如 360）
            if len(remaining) >= 2 and (not remaining.isascii() or len(remaining) >= 3):
                short = remaining
            break
    short = short.strip(" -")
    return (short or fallback), (fallback or n)


def _assign_names(sites: list[dict[str, Any]]) -> None:
    """命名规范化 + 重名回退（不引入数字序号前缀）。"""
    normalized = []
    for s in sites:
        api = str(s.get("api", "") or "")
        is_builtin = api.startswith("csp_") or api.startswith("./")
        normalized.append(normalize_name(str(s.get("name", "") or ""), is_builtin))
    short_counts: dict[str, int] = {}
    fallback_counts: dict[str, int] = {}
    for short, fallback in normalized:
        short_counts[short] = short_counts.get(short, 0) + 1
        fallback_counts[fallback] = fallback_counts.get(fallback, 0) + 1
    used_short: set[str] = set()
    for s, (short, fallback) in zip(sites, normalized):
        # 评分降序：第一个使用简短名（最高分源优先），其余回退到保留词尾版
        if short not in used_short:
            used_short.add(short)
            s["name"] = short
        elif fallback_counts[fallback] == 1:
            s["name"] = fallback
        else:
            s["name"] = clean_name(str(s.get("name", "") or ""))


# 分类检测结果缓存（与 scripts/generate_temp_subscription.py 共用 data/category-cache.json）
_CACHE_FILE = PONYO_ROOT / "data" / "category-cache.json"


def _load_cache() -> dict[str, Any]:
    try:
        if _CACHE_FILE.exists():
            return json.loads(_CACHE_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _save_cache(cache: dict[str, Any]) -> None:
    try:
        _CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


# 统一分类字典：categories.json 是唯一真相源（与 scripts/generate_temp_subscription.py 共用）。


def _fetch_json(url: str, timeout: int = 5) -> dict[str, Any] | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8", "replace"))
    except Exception:
        return None


def _is_sub_name(name: str, tx: dict[str, Any]) -> bool:
    """无 type_pid 时判断分类是否为二级（动作片/地区剧/地区综艺等）。"""
    if is_top_name(name, tx):
        return False
    canonical = normalize_category_name(name, tx)
    if canonical == "电影":
        return True  # 动作片/喜剧片等二级类型
    return name.endswith(("剧", "综艺", "动漫", "动画"))


def _detect_top_categories(api: str) -> list[str] | None:
    """检测源顶级分类：成人/无效剔除、父子折叠、空壳剔除、统一归一化。"""
    tx = load_taxonomy()
    base = api.rstrip("/") + ("&" if "?" in api else "?")
    data = _fetch_json(base + "ac=list")
    if not data or not data.get("class"):
        return None
    classes = [
        c
        for c in data["class"]
        if isinstance(c, dict) and c.get("type_id") is not None and c.get("type_name")
    ]
    if not classes:
        return None
    has_pid = any(c.get("type_pid") is not None for c in classes)
    tops: list[dict[str, Any]] = []
    subs: list[dict[str, Any]] = []
    for c in classes:
        name = str(c["type_name"]).strip()
        if not name or normalize_category_name(name, tx) is None:
            continue  # 空名或成人/无效
        if has_pid:
            (tops if str(c.get("type_pid") or "0") == "0" else subs).append(c)
        else:
            (subs if _is_sub_name(name, tx) else tops).append(c)
    if not tops:
        return None

    parents_with_sub: set[str] = set()
    if has_pid:
        pid_names = {
            str(c["type_id"]): normalize_category_name(
                str(c["type_name"]).strip(), tx
            )
            or str(c["type_name"]).strip()
            for c in tops
        }
        for c in subs:
            pid = str(c.get("type_pid") or "0")
            if pid in pid_names:
                parents_with_sub.add(pid_names[pid])
    else:
        top_canon = {
            normalize_category_name(str(c["type_name"]).strip(), tx)
            or str(c["type_name"]).strip()
            for c in tops
        }
        for c in subs:
            p = normalize_category_name(str(c["type_name"]).strip(), tx)
            if p and p in top_canon:
                parents_with_sub.add(p)

    def has_content(c: dict[str, Any]) -> bool:
        page = _fetch_json(base + f"ac=detail&t={c['type_id']}&pg=1", timeout=4)
        if page is None:
            time.sleep(0.3)
            page = _fetch_json(base + f"ac=detail&t={c['type_id']}&pg=1", timeout=6)
        return bool(page and (page.get("list") or []))

    result: list[str] = []
    for c in tops:
        raw_name = str(c["type_name"]).strip()
        canonical = normalize_category_name(raw_name, tx) or raw_name
        if canonical in parents_with_sub or has_content(c):
            if canonical not in result:
                result.append(canonical)
    return result or None


# 类别配额：正式版同样保证“听歌/短视频”等类别只保留指定数量的最高分源。
# 与 scripts/generate_temp_subscription.py 的 CATEGORY_QUOTAS 保持一致，两处需同步修改。
CATEGORY_QUOTAS: dict[str, dict[str, Any]] = {
    "music": {
        "max": 1,
        "match": lambda n: (
            ("[听]" in n)
            or ("音乐" in n)
            or ("DJ" in n)
            or ("MV" in n)
            or ("听友" in n)
        ),
    },
    "short_video": {"max": 1, "match": lambda n: ("短剧" in n) or ("短视频" in n)},
}


def _apply_category_quota(sites: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """按评分降序应用类别配额（调用方保证 sites 已按评分降序）。"""
    used = {key: 0 for key in CATEGORY_QUOTAS}
    kept: list[dict[str, Any]] = []
    for s in sites:
        name = str(s.get("name", "") or "")
        cat = None
        for key, cfg in CATEGORY_QUOTAS.items():
            if cfg["match"](name):
                cat = key
                break
        if cat is not None:
            if used[cat] >= CATEGORY_QUOTAS[cat]["max"]:
                continue
            used[cat] += 1
        kept.append(s)
    return kept


def _inject_category_whitelist(obj: dict[str, Any]) -> None:
    host = _host_of(str(obj.get("api", "") or ""))
    if not host:
        return
    tx = load_taxonomy()
    lowered = host.lower()
    for key, cats in load_host_whitelist().items():
        if lowered.endswith(key):
            obj["categories"] = normalize_categories(cats, tx).categories
            obj["category_provenance"] = "whitelist"
            return


# 同站点多入口去重（与 scripts/generate_temp_subscription.py 的 SITE_GROUPS 保持一致，需同步修改）
SITE_GROUPS: list[list[str]] = [
    ["360zyzz.com", "360zy.com", "360zy.tv"],
    [
        "cj.ffzyapi.com",
        "api.ffzyapi.com",
        "ffzyapi.com",
        "ffzy5.tv",
        "ffzy.tv",
        "ffzy3.tv",
        "ffzy4.tv",
    ],
    ["cj.lziapi.com", "lziapi.com", "cj.lzcaiji.com"],
    ["api.apibdzy.com", "apibdzy.com"],
    ["mdzyapi.com", "caiji.moduapi.cc", "moduapi.cc"],
    ["api.zuidapi.com", "zuidapi.com", "zuidazy.me", "zuidazy.co"],
    ["p2100.net"],
    ["bfzyapi.com"],
    ["caiji.dyttzyapi.com", "dyttzyapi.com"],
    ["jszyapi.com"],
    ["lovedan.net"],
    ["api.maoyanapi.top", "maoyanapi.top"],
    ["iqiyizyapi.com"],
    ["jyzyapi.com", "jinyingzy.com"],
    ["huyaapi.com"],
    ["api.ddapi.cc", "ddapi.cc"],
    ["api.guangsuapi.com", "guangsuapi.com"],
    ["cj.rycjapi.com", "rycjapi.com"],
    ["hhzyapi.com", "haohuazy.com"],
    ["apiyhzy.com", "m3u8.apiyhzy.com", "api.apiyhzy.com", "yhzy.cc"],
    ["subocaiji.com", "suboziyuan.net"],
    ["hongniuzy2.com", "hongniuzy3.com"],
    ["taopianapi.com"],
    ["api.niuniuzy.me", "niuniuzy.me"],
    ["sdzyapi.com"],
    ["api.xinlangapi.com", "xinlangapi.com"],
    ["api.ukuapi88.com", "api.ukuapi.com", "ukuapi.com"],
    ["api.1080zyku.com", "1080zyku.com"],
    ["caiji.maotaizy.cc", "maotaizy.cc"],
    ["api.wujinapi.me", "wujinapi.com"],
    ["feisuzyapi.com"],
    ["haiwaikan.com"],
    ["caiji.kuaichezy.org", "kuaichezy.org", "caiji.kczyapi.com", "kczyapi.com"],
    ["cj.yayazy.net", "yayazy.net"],
    ["wolongzyw.com", "collect.wolongzyw.com", "collect.wolongzy.cc"],
    ["mozhuazy.com"],
    ["tyyszy.com"],
    ["apiyutu.com"],
    ["api.wwzy.tv", "wwzy.tv"],
    ["apilj.com"],
    ["apittzy.com"],
    ["hanjuzy.com"],
    ["ahjiuman.com"],
]


def _host_of(api: str) -> str | None:
    m = re.search(r"https?://([^/]+)", api or "")
    return m.group(1).lower().removeprefix("www.") if m else None


def _apply_site_dedup(sites: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """同站点多入口去重：SITE_GROUPS 每组只保留评分降序中的第一个。"""
    seen: set[tuple[str, ...]] = set()
    kept: list[dict[str, Any]] = []
    for s in sites:
        h = _host_of(str(s.get("api", "") or ""))
        group = None
        if h:
            for g in SITE_GROUPS:
                if h in g:
                    group = tuple(g)
                    break
        if group is None:
            kept.append(s)
        elif group not in seen:
            seen.add(group)
            kept.append(s)
    return kept


def _calc_sha256(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _load_approved_jar_urls(
    con: sqlite3.Connection,
    *,
    now: str,
    base_url: str = APPROVED_ASSET_BASE_URL,
) -> dict[str, str]:
    """Map source fingerprints to immutable, currently approved JAR URLs."""
    rows = con.execute(
        "SELECT d.fingerprint,d.content_sha256,d.actual_md5,d.source_field "
        "FROM dependency_asset_evidence d "
        "JOIN dependency_asset_approval a "
        "ON lower(a.content_sha256)=lower(d.content_sha256) "
        "WHERE d.asset_type='jar' AND d.content_sha256 IS NOT NULL "
        "AND a.asset_type='jar' AND a.status='approved' "
        "AND a.expires_at IS NOT NULL AND a.expires_at>? "
        "ORDER BY d.fingerprint, CASE d.source_field "
        "WHEN 'site.jar' THEN 0 WHEN 'config.jar' THEN 1 "
        "WHEN 'config.spider' THEN 2 ELSE 3 END",
        (now,),
    ).fetchall()
    result: dict[str, str] = {}
    for row in rows:
        fingerprint = row["fingerprint"]
        if fingerprint in result:
            continue
        sha256 = row["content_sha256"].lower()
        url = f"{base_url.rstrip('/')}/{sha256}.jar"
        actual_md5 = (row["actual_md5"] or "").lower()
        if actual_md5:
            url = f"{url};md5;{actual_md5}"
        result[fingerprint] = url
    return result


def _attach_approved_jar(
    site: dict[str, Any],
    fingerprint: str,
    approved_jar_urls: dict[str, str],
) -> dict[str, Any]:
    approved_url = approved_jar_urls.get(fingerprint)
    if not approved_url:
        return site
    rewritten = dict(site)
    rewritten["jar"] = approved_url
    return rewritten


def generate_all_subscriptions(
    db_path: str, *, output_dir: str | Path | None = None, now: str | None = None
) -> dict[str, Any]:
    now = now or _now()
    out_path = Path(output_dir) if output_dir else SUB_DIR
    out_path.mkdir(parents=True, exist_ok=True)

    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    approved_jar_urls = _load_approved_jar_urls(con, now=now)

    from ponyo_source_manager.probes import live as live_manager
    from ponyo_source_manager.publishing import children_aggregate

    # 1. 精选 29 源提取 (按评分排序取前29，且指纹互异)
    rows_allow = con.execute("""
        WITH LatestScores AS (
            SELECT fingerprint, total_score,
                   ROW_NUMBER() OVER(PARTITION BY fingerprint ORDER BY scored_at DESC) as rn
            FROM score_snapshot
        )
        SELECT r.raw_json, s.total_score, dg.fingerprint
        FROM list_state ls
        JOIN dedup_group dg ON ls.fingerprint = dg.fingerprint
        JOIN raw_source r ON dg.primary_raw_id = r.id
        LEFT JOIN LatestScores s ON ls.fingerprint = s.fingerprint AND s.rn = 1
        WHERE ls.state = 'allow'
        ORDER BY COALESCE(s.total_score, 0) DESC
    """).fetchall()

    vod_sites = []
    for r in rows_allow:
        try:
            site_obj = json.loads(r["raw_json"])
            _inject_category_whitelist(site_obj)
            vod_sites.append(
                _attach_approved_jar(site_obj, r["fingerprint"], approved_jar_urls)
            )
        except Exception:
            pass
    # 暂不收录：央视大全（drpyS WASM 签名规则，详情/播放依赖 WebAssembly，App 端 QuickJS 不支持）
    BLOCKED_KEYS = {"drpyS_央视大全[官]"}
    vod_sites = [s for s in vod_sites if s.get("key") not in BLOCKED_KEYS]
    # 命名规范化（纯短名；重名回退，无序号）
    _assign_names(vod_sites)
    # 分类归一化（所有采集站源）：检测成功写入签名缓存，失败按签名回退；
    # 源分类发生变动时缓存自动过期并标记 stale，随下一次探测自动刷新。
    cache = _load_cache()
    with ThreadPoolExecutor(max_workers=4) as ex:
        futs = {
            ex.submit(_detect_top_categories, str(s.get("api", "") or "")): s
            for s in vod_sites
            if str(s.get("api", "") or "").startswith("http")
        }
        for f in as_completed(futs):
            s = futs[f]
            api = str(s.get("api", "") or "")
            cats = f.result()
            declared = s.get("class") or []
            sig = raw_signature(declared)
            entry = cache.get(api)
            if cats:
                s["categories"] = cats
                s["category_provenance"] = "detected"
                cache[api] = {"sig": sig, "at": now, "cats": cats}
            elif isinstance(entry, dict):
                s["categories"] = list(entry.get("cats") or [])
                try:
                    age = datetime.fromisoformat(str(entry.get("at") or ""))
                    elapsed = (datetime.now(timezone.utc) - age).total_seconds()
                    stale = elapsed > 6 * 3600
                except Exception:
                    stale = True
                s["category_provenance"] = "stale" if stale else "cache"
            elif isinstance(entry, list):
                s["categories"] = list(entry)
                s["category_provenance"] = "cache-legacy"
    _save_cache(cache)
    # 类别配额：每类只保留最高分源（正式版同样生效）
    vod_sites = _apply_category_quota(vod_sites)[:29]
    # 同站点去重：每站只保留最高分入口（正式版同样生效）
    vod_sites = _apply_site_dedup(vod_sites)[:29]

    # 获取儿童聚合源 (1 个)
    children_res = children_aggregate.aggregate_children_sources(db_path, now=now)
    children_site = children_res.get("tvbox_site")

    # 29 个精选点播源 + 1 个儿童聚合源 = 30 个计数源
    counted_sites = []
    if children_site:
        counted_sites.append(children_site)
    counted_sites.extend(vod_sites)

    # 获取唯一正式直播源
    live_res = live_manager.select_official_live_source(db_path, now=now)
    official_live_key = live_res.get("official_key")

    # 2. 读取基础配置模板（如豆瓣推荐、设置、本地播放等）
    base_config_file = SUB_DIR / "ponyo.json"
    base_config = {}
    if base_config_file.exists():
        try:
            base_config = json.loads(base_config_file.read_text(encoding="utf-8"))
        except Exception:
            base_config = {}

    # 提取豁免的工具源（豆瓣推荐、配置中心、本地播放等，不计入 30 名额）
    EXEMPT_KEYS = {"drpy_js_豆瓣", "本地"}
    tool_sites = []
    for s in base_config.get("sites", []):
        k = s.get("key", "")
        api = str(s.get("api", ""))
        if k in EXEMPT_KEYS or "csp_LocalFile" in api:
            tool_sites.append(s)

    # 构建 ponyo-lite.json: 工具源 + 30个计数点播源
    lite_config = base_config.copy()
    lite_config["sites"] = tool_sites + counted_sites

    lives_list = []
    if official_live_url := live_res.get("official_url"):
        lives_list = [
            {
                "name": "Live",
                "type": 0,
                "url": official_live_url,
                "playerType": 1,
                "epg": "http://epg.51zmt.top:8000/api/diyp/",
            }
        ]
    elif base_config.get("lives"):
        lives_list = [base_config["lives"][0]]

    lite_config["lives"] = lives_list

    lite_str = json.dumps(lite_config, ensure_ascii=False, indent=2) + "\n"
    lite_bytes = lite_str.encode("utf-8")
    (out_path / "ponyo-lite.json").write_bytes(lite_bytes)

    # 构建 ponyo-live.json
    live_config = base_config.copy()
    live_config["sites"] = []
    live_config["lives"] = lives_list
    live_str = json.dumps(live_config, ensure_ascii=False, indent=2) + "\n"
    live_bytes = live_str.encode("utf-8")
    (out_path / "ponyo-live.json").write_bytes(live_bytes)

    # 构建 ponyo-children.json
    children_config = base_config.copy()
    children_config["sites"] = [children_site] if children_site else []
    children_config["lives"] = []
    children_str = json.dumps(children_config, ensure_ascii=False, indent=2) + "\n"
    children_bytes = children_str.encode("utf-8")
    (out_path / "ponyo-children.json").write_bytes(children_bytes)

    # 3. 生成 ponyo-full.json (所有未被 deny 的源)
    rows_full = con.execute("""
        SELECT r.raw_json, dg.fingerprint
        FROM dedup_group dg
        JOIN raw_source r ON dg.primary_raw_id = r.id
        LEFT JOIN list_state ls ON dg.fingerprint = ls.fingerprint
        WHERE COALESCE(ls.state, 'candidate') != 'deny'
    """).fetchall()

    full_sites = []
    for r in rows_full:
        try:
            full_sites.append(
                _attach_approved_jar(
                    json.loads(r["raw_json"]),
                    r["fingerprint"],
                    approved_jar_urls,
                )
            )
        except Exception:
            pass

    full_config = base_config.copy()
    full_config["sites"] = full_sites
    full_str = json.dumps(full_config, ensure_ascii=False, indent=2) + "\n"
    full_bytes = full_str.encode("utf-8")
    (out_path / "ponyo-full.json").write_bytes(full_bytes)

    # 生成内部候选文件 ponyo-candidates.json (不入 manifest)
    rows_cand = con.execute("""
        SELECT r.raw_json, dg.fingerprint
        FROM dedup_group dg
        JOIN raw_source r ON dg.primary_raw_id = r.id
        LEFT JOIN list_state ls ON dg.fingerprint = ls.fingerprint
        WHERE ls.state = 'candidate'
    """).fetchall()

    cand_sites = []
    for r in rows_cand:
        try:
            cand_sites.append(
                _attach_approved_jar(
                    json.loads(r["raw_json"]),
                    r["fingerprint"],
                    approved_jar_urls,
                )
            )
        except Exception:
            pass
    cand_config = base_config.copy()
    cand_config["sites"] = cand_sites
    cand_str = json.dumps(cand_config, ensure_ascii=False, indent=2) + "\n"
    (out_path / "ponyo-candidates.json").write_bytes(cand_str.encode("utf-8"))

    # 4. 生成 manifest.json
    version_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    manifest = {
        "version": version_id,
        "generated_at": now,
        "source_count": len(lite_config["sites"]),
        "files": {
            "ponyo-lite.json": {
                "sha256": _calc_sha256(lite_str),
                "size": len(lite_bytes),
            },
            "ponyo-full.json": {
                "sha256": _calc_sha256(full_str),
                "size": len(full_bytes),
            },
            "ponyo-live.json": {
                "sha256": _calc_sha256(live_str),
                "size": len(live_bytes),
            },
            "ponyo-children.json": {
                "sha256": _calc_sha256(children_str),
                "size": len(children_bytes),
            },
        },
    }
    manifest_str = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    (out_path / "manifest.json").write_bytes(manifest_str.encode("utf-8"))

    con.close()

    return {
        "version": version_id,
        "lite_sources": len(lite_config["sites"]),
        "full_sources": len(full_sites),
        "output_dir": str(out_path),
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--db", default=str(DATA_DIR / "sources.db"))
    p.add_argument("--output", default=str(SUB_DIR))
    args = p.parse_args()
    result = generate_all_subscriptions(args.db, output_dir=args.output)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()

