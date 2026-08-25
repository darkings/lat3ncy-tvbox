# -*- coding: utf-8 -*-
"""临时/正式订阅生成：allow/hard_pass/candidate 混合按得分排序（默认上限 95 点播源）。

- 工具源仅保留豆瓣推荐（配置中心/本地视频不可用，剔除）
- 点播源：allow/hard_pass/candidate 全量按 total_score 降序（不分组）
- 源名字统一清洗：去 emoji/注释/数字序号前缀，┃→-；重名时保留原名

发布到与正式版相同的地址，后续源晋级后用正式 30 源版覆盖即可（连接地址不变）。
"""

import argparse
import json
import os
import re
import sqlite3
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any
from ponyo_source_manager.publishing.category_taxonomy import (
    load_host_whitelist,
    load_taxonomy,
    normalize_categories,
)
from ponyo_source_manager.publishing.generate_subscription import (
    _detect_top_categories as _detect_top_categories,
)


# 分类检测结果缓存：接口临时故障时回退到上次成功结果，避免分类栏退回“接口全显示”
_CACHE_FILE = (
    Path(os.environ.get("PONYO_ROOT", str(Path(__file__).resolve().parent.parent)))
    / "data"
    / "category-cache.json"
)


def _load_cache() -> dict[str, list[str]]:
    try:
        if _CACHE_FILE.exists():
            return json.loads(_CACHE_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _save_cache(cache: dict[str, list[str]]) -> None:
    try:
        _CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


# 成人分类名黑名单：无配置源净化分类时过滤（避免接口返回的成人分类出现在分类栏）
def _fetch_json(url: str, timeout: int = 5) -> dict[str, Any] | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8", "replace"))
    except Exception:
        return None


# 两级分类规则（与 App 端 DefaultConfig 保持一致，需同步修改）：
# 类型词 / 地区剧（…剧）/ 综艺地区（…综艺）/ 动漫地区（…动漫）→ 子分类；其余 → 顶级
# 工具源：豆瓣推荐 + 本地视频（配置中心暂时隐藏，不进入订阅）
EXEMPT_KEYS = {"drpy_js_豆瓣", "本地"}

# 暂不收录：央视大全（drpyS WASM 签名规则，App 端 QuickJS 无 WebAssembly，详情/播放不可用）
BLOCKED_KEYS = {"drpyS_央视大全[官]"}

# 官源（VIP 解析源）：腾讯/芒果/爱奇艺/优酷 官方源。它们 play 返回 VIP 页面地址 + jx 标记，
# 必须依赖可用解析器才能出流。策略：只有检测到"能出流的解析器"时才收录，否则不收录
# （避免用户在 App 里点进一个播放不了的源）。是否可用由 refresh_parsers.py 写入 top-parsers.json 的 has_working_parser 决定。
VIP_OFFICIAL_KEYS = {
    "drpyS_腾云驾雾[官]", "drpyS_百忙无果[官]",
    "drpyS_奇珍异兽[官]", "drpyS_优酷[官]",
}

# 官源 key → 平台 flag（用于按平台判断该官源是否有可用解析器）
VIP_OFFICIAL_FLAGS = {
    "drpyS_腾云驾雾[官]": "qq",
    "drpyS_百忙无果[官]": "mgtv",
    "drpyS_奇珍异兽[官]": "qiyi",
    "drpyS_优酷[官]": "youku",
}

# 4 平台视频源：(平台flag, 采集源 key, 官源 key)。官源(type-4,配合解析器)优先，该平台无可用解析器则用采集源(type-1,直链)顶上去。
PLATFORM_VIDEO = [
    ("爱奇艺", "qiyi", "iqiyizyapi.com", "drpyS_奇珍异兽[官]"),
    ("腾讯", "qq", None, "drpyS_腾云驾雾[官]"),
    ("芒果", "mgtv", "芒果资源", "drpyS_百忙无果[官]"),
    ("优酷", "youku", None, "drpyS_优酷[官]"),
]


def _read_parser_state() -> dict:
    """读 refresh_parsers.py 的输出（含 has_working_parser 和 working_platforms）。"""
    try:
        return json.loads(Path("data/top-parsers.json").read_text(encoding="utf-8"))
    except Exception:
        return {}


def _has_working_parser() -> bool:
    """判断是否存在能真实出流的解析器。"""
    return bool(_read_parser_state().get("has_working_parser"))


def _platform_has_parser(flag: str) -> bool:
    """判断某个平台（flag）是否有能出流的解析器。"""
    return bool(_read_parser_state().get("working_platforms", {}).get(flag))


def _source_score(con, key: str) -> float:
    """按 site_key 或 name 查最新评分（无评分为 0）。"""
    row = con.execute(
        "SELECT COALESCE(s.total_score, 0) AS score FROM raw_source r "
        "LEFT JOIN dedup_group dg ON dg.primary_raw_id = r.id "
        "LEFT JOIN score_snapshot s ON s.fingerprint = dg.fingerprint "
        "WHERE r.site_key = ? OR r.name = ? ORDER BY s.scored_at DESC LIMIT 1",
        (key, key),
    ).fetchone()
    return float(row["score"]) if row else 0.0


def _load_platform_video(con) -> list[dict[str, Any]]:
    """4 平台视频源：官源(type-4,配合解析器)优先，该平台无可用解析器则用采集源(type-1,直链)顶上去。"""
    result: list[dict[str, Any]] = []
    for platform, flag, collect_key, official_key in PLATFORM_VIDEO:
        obj = None
        # 官源优先：该平台有可用解析器才收录官源
        if _platform_has_parser(flag):
            row = con.execute(
                "SELECT raw_json FROM raw_source WHERE site_key = ? LIMIT 1", (official_key,)
            ).fetchone()
            if row:
                try:
                    obj = json.loads(row["raw_json"])
                except Exception:
                    obj = None
        # 采集源兜底：该平台无解析器时用采集源(评分>0 表示探测过、直链可用)
        if obj is None and collect_key and _source_score(con, collect_key) > 0:
            row = con.execute(
                "SELECT raw_json FROM raw_source WHERE site_key = ? OR name = ? LIMIT 1",
                (collect_key, collect_key),
            ).fetchone()
            if row:
                try:
                    obj = json.loads(row["raw_json"])
                except Exception:
                    obj = None
        if obj is not None:
            result.append(obj)
    return result

# 类别配额：发布层保证“听歌/短视频”等类别只保留指定数量的最高分源。
# 无论 DB 中多少同类源晋级（candidate/allow），临时版与正式版订阅中每类最多出现 max 个。
CATEGORY_QUOTAS: dict[str, dict[str, Any]] = {
    "music": {
        "max": 1,
        "match": lambda s: (
            ("[听]" in str(s.get("name", "")))
            or ("音乐" in str(s.get("name", "")))
            or ("DJ" in str(s.get("name", "")))
            or ("MV" in str(s.get("name", "")))
            or ("听友" in str(s.get("name", "")))
        ),
    },
    "short_video": {
        "max": 1,
        "match": lambda s: ("短剧" in str(s.get("name", ""))) or ("短视频" in str(s.get("name", ""))),
    },
    # 小说 + 听书 合并为一类，只保留 1 个（按评分降序取最高分）
    "book_audio": {
        "max": 1,
        "match": lambda s: (
            str(s.get("类型", "") or "") in ("小说", "听书")
            or "小说" in str(s.get("name", "") or "")
            or "听书" in str(s.get("name", "") or "")
            or "读书" in str(s.get("name", "") or "")
            or "书坊" in str(s.get("name", "") or "")
        ),
    },
}


def _apply_category_quota(sites: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """按评分降序应用类别配额（调用方保证 sites 已按评分降序）。"""
    used = {key: 0 for key in CATEGORY_QUOTAS}
    kept: list[dict[str, Any]] = []
    for s in sites:
        cat = None
        for key, cfg in CATEGORY_QUOTAS.items():
            if cfg["match"](s):
                cat = key
                break
        if cat is not None:
            if used[cat] >= CATEGORY_QUOTAS[cat]["max"]:
                continue
            used[cat] += 1
        kept.append(s)
    return kept


# 同站点多入口去重：discovery 会从不同配置仓库采集同一站点的多个入口（不同 api 格式/线路），
# 发布层每组只保留评分最高的一个。新增同站别名时在此补充（域名已归一化，去 www. 前缀）。
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
    """同站点多入口去重：SITE_GROUPS 每组只保留评分降序中的第一个（评分高者优先）。"""
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


_EMOJI_RE = re.compile(
    "[\U0001f000-\U0001faff\U00002600-\U000027bf\U0001f900-\U0001f9ff\U0000fe0f\U00002702-\U000027b0]"
)
_SEQ_RE = re.compile(r"^\d+-")
_TRAIL_NOTE_RE = re.compile(r"<=\S+")


def clean_name(name: str) -> str:
    """基础清洗：去 emoji/变体选择符、去 (vpn) 等前缀注释、去 <= 尾部注释、┃→-、折叠空格。"""
    n = _EMOJI_RE.sub("", name)
    n = re.sub(r"[\ufe0e\ufe0f]", "", n)
    n = n.replace("(vpn)", "")
    n = _TRAIL_NOTE_RE.sub("", n)
    n = re.sub(r"┃", "-", n)
    n = re.sub(r"\s+", " ", n).strip(" -")
    return n


def strip_seq_prefix(name: str) -> str:
    """去掉开头的数字序号前缀（如 40-橘猫采集 → 橘猫采集；24-樱花 → 樱花）。"""
    return _SEQ_RE.sub("", name)


# 繁→简 常用字映射（命名规范：统一简体）
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


# 域名 → 中文品牌（已知映射；未收录的域名保留清洗后短名）
_DOMAIN_ALIASES: list[tuple[str, str]] = [
    ("lovedan", "艾旦"),
    ("apibdzy", "百度"),
]


# 冗余词尾（按出现顺序截取第一个命中；去词尾后过短则保留原名）
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
    """命名规范化，返回 (简短名, 回退名)。

    - 工具/内置源：仅基础清洗（保留「品牌-特性」结构）
    - 采集站/drpyS：删方括号标签、去 (DS)、去 -GH/-变体 后缀、去冗余词尾、去序号
    - 回退名用于重名时保留可辨性（去掉词尾后与其它源撞名时回退）
    """
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


# 混合站分类白名单：接口含成人分类但主体正常的站点，注入 categories 只显示正常分类。
# 分类名按各站接口实际返回书写（精确匹配生效，不依赖 App 端归一化）。
def _inject_category_whitelist(obj: dict[str, Any]) -> None:
    """命中白名单域名的源注入 categories（统一字典归一化）。"""
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


def _load_sites(con, limit: int) -> list[dict[str, Any]]:
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
        if key in BLOCKED_KEYS:
            continue
        # 该平台无可用解析器时，官源（VIP 解析源）不收录（按平台逐判，不全局一刀切）
        flag = VIP_OFFICIAL_FLAGS.get(key)
        if flag and not _platform_has_parser(flag):
            continue
        seen.add(key)
        _inject_category_whitelist(obj)
        sites.append(obj)
    return sites


def _jar_usable(obj: dict[str, Any]) -> bool:
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


def _assign_names(sites: list[dict[str, Any]]) -> None:
    """命名规范化 + 重名回退：
    简短名唯一直接用；简短名冲突时回退到保留词尾版；仍冲突用基础清洗名。
    不引入数字序号前缀。
    """
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


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--db", required=True)
    p.add_argument(
        "--template",
        required=True,
        help="顶层结构模板（仓库根 subscription/ponyo.json）",
    )
    p.add_argument("--output", required=True)
    p.add_argument("--limit", type=int, default=100, help="点播源数量上限")
    args = p.parse_args()

    template = json.loads(Path(args.template).read_text(encoding="utf-8"))
    con = sqlite3.connect(args.db)
    con.row_factory = sqlite3.Row

    # 1. 工具源：仅豆瓣推荐（从模板提取）
    tool_sites = [s for s in template.get("sites", []) if s.get("key") in EXEMPT_KEYS]

    # 2. 点播源：三状态混合按分排序，过滤本机 jar，取前 limit
    #    取 limit*5 再配额过滤，保证类别配额后仍能补满 limit
    vod_sites = [s for s in _load_sites(con, args.limit * 5) if _jar_usable(s)][
        : args.limit * 2
    ]
    # 发布层规则：4 平台视频源(官源优先/采集兜底) 置顶 → 按 key 去重 → 同站点去重 → 命名规范化 → 类别配额 → 取前 limit
    vod_sites = _load_platform_video(con) + vod_sites
    _seen_keys: set[str] = set()
    _deduped: list[dict[str, Any]] = []
    for _s in vod_sites:
        _k = str(_s.get("key", ""))
        if _k and _k in _seen_keys:
            continue
        if _k:
            _seen_keys.add(_k)
        _deduped.append(_s)
    vod_sites = _deduped
    vod_sites = _apply_site_dedup(vod_sites)
    _assign_names(vod_sites)
    # 两级分类净化：对所有采集站源检测顶级分类并注入 categories（覆盖旧配置）
    # 顶级分类 + 成人名过滤 + 无子分类顶级的内容检测；检测失败回退缓存，无缓存保持原配置
    # drpy 本地代理 / csp_* 内置类 / 非 http 协议：分类无法通过 ac=list 检测，
    # 直接注入通用分类避免客户端"无分类"显示
    DRPY_DEFAULT_CATS = ["电影", "电视剧", "综艺", "动漫"]
    for s in vod_sites:
        api = str(s.get("api", "") or "")
        if not api.startswith("http") or "127.0.0.1" in api or "localhost" in api:
            if not s.get("categories"):
                s["categories"] = list(DRPY_DEFAULT_CATS)
                s["category_provenance"] = "default_drpy"

    cache = _load_cache()
    with ThreadPoolExecutor(max_workers=4) as ex:
        futs = {
            ex.submit(_detect_top_categories, str(s.get("api", "") or "")): s
            for s in vod_sites
            if str(s.get("api", "") or "").startswith("http")
            and "127.0.0.1" not in str(s.get("api", ""))
            and "localhost" not in str(s.get("api", ""))
        }
        for f in as_completed(futs):
            s = futs[f]
            api = str(s.get("api", "") or "")
            cats = f.result()
            entry = cache.get(api)
            if cats:
                s["categories"] = cats
                s["category_provenance"] = "detected"
                cache[api] = {"sig": "", "at": "", "cats": cats}
            elif isinstance(entry, dict):
                s["categories"] = list(entry.get("cats") or [])
                s["category_provenance"] = "cache"
            elif isinstance(entry, list):
                s["categories"] = list(entry)
                s["category_provenance"] = "cache-legacy"
    _save_cache(cache)
    vod_sites = _apply_category_quota(vod_sites)[: args.limit]

    # 3. 组装：顶层结构沿用模板（spider/lives/parses/hosts/flags/doh/rules/ads/wallpaper）
    result = dict(template)
    result["sites"] = tool_sites + vod_sites

    # 注入直播源：聚合 M3U 优先，其次 live-report.json 的 official_url
    agg_m3u = Path("/opt/ponyo-source-manager/src/subscription/aggregated-live.m3u")
    agg_cdn_url = "https://cdn.jsdelivr.net/gh/darkings/lat3ncy-tvbox@main/subscription/aggregated-live.m3u"
    live_report_path = Path(args.db).resolve().parent.parent / "reports" / "live-report.json"
    if not live_report_path.exists():
        live_report_path = Path("/opt/ponyo-source-manager/reports/live-report.json")

    injected_live = False
    # 优先：聚合直播源
    if agg_m3u.exists() and agg_m3u.stat().st_size > 100:
        live_entry = {
            "name": "聚合直播",
            "type": 0,
            "url": agg_cdn_url,
            "playerType": 1,
            "epg": "http://epg.51zmt.top:8000/api/diyp/",
        }
        existing_lives = template.get("lives", [])
        result["lives"] = [live_entry] + [l for l in existing_lives if l.get("url") != agg_cdn_url]
        injected_live = True
        print(f"Live: injected aggregated m3u ({agg_m3u.stat().st_size}B)")

    # 兜底：live-report.json 的 official_url
    if not injected_live and live_report_path.exists():
        try:
            live_report = json.loads(live_report_path.read_text(encoding="utf-8"))
            summary = live_report.get("summary", {})
            if official_url := summary.get("official_url"):
                official_name = summary.get("official_source") or "四川电信IPTV"
                live_entry = {
                    "name": official_name,
                    "type": 0,
                    "url": official_url,
                    "playerType": 1,
                    "epg": "http://epg.51zmt.top:8000/api/diyp/",
                }
                existing_lives = template.get("lives", [])
                result["lives"] = [live_entry] + [l for l in existing_lives if l.get("url") != official_url]
        except Exception as e:
            print(f"Warning: failed to inject live source: {e}")

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
