#!/usr/bin/env python3
"""无损云直连解析（VIP 解析替换方案）

原理与 88lin/video_vip 的"无损云直连"相同：
按片名搜索上游苹果 CMS 采集站 -> 命中条目 -> 拉详情解析 vod_play_url
-> 按集数选出对应 m3u8 -> 返回给 App 直接播放（parse:0，无需 WebView）。

与旧 Playwright VIP 解析的区别：
- 不碰官方页面/不模拟浏览器，只调采集站 JSON API（稳定得多）
- 输入是"片名+集数"（App 端 mVodInfo 已持有），不是官方 URL
- 多源并发 + 候选排序，单源故障不影响整体可用性

实测基线（2026-09-10）：
- 量子采集 lziapi 搜"狂飙" 67 条候选，精确命中 id=47131，77 集 vod_play_url
- share 链接（HTML 播放页）内嵌带 sign 的 m3u8 相对路径，拼接后可直接播放
- 子索引 -> ts 分片首字节 0x47（合法 MPEG-TS），全链路真实出流
"""

import asyncio
import re
from typing import Optional
from urllib.parse import urljoin

import httpx

# ---------------------------------------------------------------------------
# 上游采集源白名单
# ---------------------------------------------------------------------------
# 精选 TVBox 生态最主流、实测可用的苹果 CMS 采集源。
# 顺序即优先级：命中多个候选时，先按"片名匹配度"排序，同分再按源顺序。
# 后续可从 sources.db 按 conn_probe 健康度动态扩展（阶段 2）。
DIRECT_SOURCES: list = [
    # 量子采集：实测搜索"狂飙"67 条结果，精确命中，77 集全量 vod_play_url
    {"name": "lzm3u8", "api": "https://cj.lziapi.com/api.php/provide/vod"},
    # 非凡采集：老牌源，片库大
    {"name": "ffm3u8", "api": "http://ffzy.tv/api.php/provide/vod"},
    # 暴风采集
    {"name": "bfm3u8", "api": "https://bfzyapi.com/api.php/provide/vod"},
    # 卧龙采集
    {"name": "wlm3u8", "api": "https://wolongzyw.com/api.php/provide/vod"},
]

# 单源搜索/详情超时（秒）。并发场景下不宜过长，慢源直接放弃。
SOURCE_TIMEOUT = 8.0
# share 播放页解析超时（秒）
SHARE_TIMEOUT = 10.0
# 通用 UA（部分采集站校验 UA，空 UA 会被拒）
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ponyo-direct/1.0"}

# 集名归一化：提取"第01集"/"01"/"EP1"/"第1回"里的数字 -> int
_EP_NUM_RE = re.compile(r"(\d+)")
# share 页内嵌 m3u8 引用：匹配 /path/index.m3u8?sign=xxx 这类相对/绝对地址
_M3U8_REF_RE = re.compile(r"""["']([^"']*?\.m3u8[^"']*)["']""")


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------
def norm_ep_number(ep_name):
    """集名 -> 集号。"第01集"->1，"EP12"->12，"01"->1，无数字->None。"""
    if not ep_name:
        return None
    m = _EP_NUM_RE.search(ep_name)
    return int(m.group(1)) if m else None



# ---------------------------------------------------------------------------
# 语言版本归一化（四平台统一处理：腾讯/爱奇艺/优酷/芒果）
# ---------------------------------------------------------------------------
# 各平台多语言版本命名格式（2026-09-11 实测）：
#   腾讯:   "小猪佩奇 第12季[普通话版]"   方括号后缀 + 阿拉伯数字季
#   爱奇艺: "小猪佩奇 第12季 英文版"     空格尾缀（无括号）+ 阿拉伯数字季
#   优酷:   "小猪佩奇 第十二季"          无语言后缀 + 中文数字季
#   芒果:   "小猪佩奇 第十二季"          无语言后缀 + 中文数字季（detail.language 有语言字段）
# 采集站条目是基础名（"小猪佩奇第九季"），无语言后缀、无语言线路。
# 带后缀的 title 比采集站名更长，三档匹配（精确/前缀/包含）全部落空 -> miss。
# 处理策略：先剥离语言后缀再匹配，同时保留语言标记用于感知比对（防串台）。
_LANG_TOKEN = (
    r'普通话版?|国语版?|国语中字|粤语版?|粤语中字|'      # 中文系
    r'英文版?|英语版?|原声版?|原版|'                    # 英文/原声系
    r'日语版?|日语中字|台配版?|台语版?|配音版?|中配版?'
)
# 方括号/圆括号包裹式（腾讯）：[普通话版] 【英文版】 （粤语版）
_LANG_BRACKET_RE = re.compile(r'[\[【（(]\s*(' + _LANG_TOKEN + r')\s*[\]】)）]\s*$')
# 空格尾缀式（爱奇艺）：" 第12季 英文版" 结尾的裸语言词。
# 必须锚定行尾且要求前导分隔符，避免误剥正常片名中部的"国语"字样（如"中国语言大会"）。
_LANG_TAIL_RE = re.compile(r'[\s·\-]+\s*(' + _LANG_TOKEN + r')\s*$')
# 语言标记归一化：把各种写法收敛到语义桶，供感知比对
_LANG_BUCKET = {
    "普通话": "mandarin", "国语": "mandarin", "中配": "mandarin", "配音": "mandarin", "台配": "mandarin", "台语": "mandarin",
    "粤语": "cantonese",
    "英文": "english", "英语": "english", "原声": "english", "原版": "english",
    "日语": "japanese",
}
# 中文数字映射（季数归一化："第九季"->9，"第十二季"->12，"二十一"->21）
_CN_DIGITS = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
_CN_UNITS = {"十": 10, "百": 100}


def _cn_to_int(s):
    """中文数字 -> int。支持 一~九百九十九（"九"->9，"十二"->12，"二十一"->21，"一百零二"->102 的简式）。"""
    if s is None:
        return None
    s = str(s).strip()
    if s.isdigit():
        return int(s)
    total, num = 0, 0
    for ch in s:
        if ch in _CN_DIGITS:
            num = _CN_DIGITS[ch]
        elif ch in _CN_UNITS:
            unit = _CN_UNITS[ch]
            # "十"前无数字（"十二"）按 1 处理；有数字（"二十"）先乘再进位
            total += (num if num else 1) * unit
            num = 0
        elif ch == "零":
            continue
    return total + num


def _strip_lang_suffix(s):
    """剥离语言后缀（方括号式优先，其次空格尾缀式）。返回 (剥离后字符串, 语言桶 or None)。"""
    lang = None
    m = _LANG_BRACKET_RE.search(s)
    if m:
        for kw, bucket in _LANG_BUCKET.items():
            if kw in m.group(1):
                lang = bucket
                break
        s = _LANG_BRACKET_RE.sub("", s)
    else:
        m = _LANG_TAIL_RE.search(s)
        if m:
            for kw, bucket in _LANG_BUCKET.items():
                if kw in m.group(1):
                    lang = bucket
                    break
            s = _LANG_TAIL_RE.sub("", s)
    return s.strip(), lang


def norm_title(title):
    """
    客户端 title 归一化（四平台统一入口）。
    返回 (归一化title, 语言桶 or None, 季数 or None)：
      腾讯:   "小猪佩奇 第12季[普通话版]" -> ("小猪佩奇 第12季", "mandarin", 12)
      爱奇艺: "小猪佩奇 第12季 英文版"    -> ("小猪佩奇 第12季", "english",  12)
      优酷:   "小猪佩奇 第十二季"         -> ("小猪佩奇 第十二季", None,     12)
      芒果:   "小猪佩奇 第十二季"         -> ("小猪佩奇 第十二季", None,     12)
    1) 剥语言后缀（保留语言标记供感知比对）
    2) 提取季数（"第12季"/"第十二季"/"第2部" -> int，供 R2 系列兜底搜索）
    """
    if not title:
        return title, None, None
    t, lang = _strip_lang_suffix(title)
    # 季数提取：兼容 阿拉伯("第12季") 与 中文数字("第十二季"，优酷/芒果格式）
    sm = re.search(r'第([0-9一二三四五六七八九十百零]+)[季部]', t)
    season = _cn_to_int(sm.group(1)) if sm else None
    return t, lang, season


def norm_name_for_cmp(name):
    """
    比较键归一化（请求侧与候选侧共用）：去空白 + 中文数字季->阿拉伯 + 剥语言后缀。
    两侧格式差异（括号/空格/中文数字）全部抹平：
      请求(腾讯):   "小猪佩奇 第12季[普通话版]" -> "小猪佩奇第12季"
      请求(优酷):   "小猪佩奇 第十二季"         -> "小猪佩奇第12季"
      候选(采集站): "小猪佩奇第九季"            -> "小猪佩奇第9季"
      候选(采集站): "小猪佩奇 第12季"           -> "小猪佩奇第12季"
    """
    # 先剥语言后缀再去空白：空格尾缀式（爱奇艺" 英文版"）依赖前导空格做锚点，
    # 若先去空白会把"英文版"紧贴片名导致无法识别（实测踩坑）。
    s, _ = _strip_lang_suffix(name or '')
    s = re.sub(r'\s+', '', s)
    # 中文数字季/部 -> 阿拉伯（"第十二季"->"第12季"，"第二十一部"->"第21部"）
    def _rep(m):
        return '第%d%s' % (_cn_to_int(m.group(1)), m.group(2))
    s = re.sub(r'第([一二三四五六七八九十百零]+)([季部])', _rep, s)
    return s.strip()

def _candidate_score(vod, title, lang_bucket=None):
    """
    单条候选打分（rank_candidates 与 direct_resolve 过滤共用同一套分数）。
    匹配档位（高->低）：
      4.0  精确命中（归一化比较键完全相等）
      3.0  前缀命中（候选键以 title 键开头，"狂飙 第二部"）
      2.0  包含命中（"狂飙223[电影解说]"，最低可信档）
      1.0  系列前缀命中（剥季数后的系列名前缀，"小猪佩奇"系全部命中）
           —— 仅当请求带季数时才有意义，由 direct_resolve 的 R2 轮启用
    语言感知（仅请求带语言标记时启用，普通内容行为与旧版完全一致）：
      候选名带一致语言字样 +0.5（优先）；带冲突语言字样 -2.0（沉底防串台）。
      例：请求 mandarin（普通话版），候选"XX[粤语版]"直接出局。
    """
    name = (vod.get("vod_name") or "").strip()
    if not name:
        return 0
    norm_t, lang_t, season = norm_title(title)
    cmp_t = norm_name_for_cmp(norm_t)
    if not cmp_t:
        return 0
    cmp_n = norm_name_for_cmp(name)
    s = 0
    if cmp_n == cmp_t:
        s = 4.0                                   # 归一化精确命中
    elif cmp_n.startswith(cmp_t):
        s = 3.0                                   # 前缀命中
    elif cmp_t in cmp_n:
        s = 2.0                                   # 包含命中
    else:
        # 系列前缀兜底：请求带季数时，剥掉季数的系列名做前缀比较
        # （"小猪佩奇第12季" vs 候选"小猪佩奇第9季" -> 系列"小猪佩奇"前缀命中）
        if season:
            series = re.sub(r'第\d+[季部]', '', cmp_t)
            if series and cmp_n.startswith(series):
                s = 1.0
    if s <= 0:
        return 0
    # ---- 语言感知 ----
    if lang_t:
        for kw, bucket in _LANG_BUCKET.items():
            if kw in name:
                s += 0.5 if bucket == lang_t else -2.0  # 一致加分 / 冲突沉底
                break
    return s


def rank_candidates(title, items):
    """候选排序：按 _candidate_score 降序（语言感知版，四平台统一）。"""
    return sorted(items, key=lambda v: _candidate_score(v, title), reverse=True)

def pick_episode(play_url, ep_index):
    """从 vod_play_url 选出对应集的播放地址。

    vod_play_url 格式（苹果 CMS 标准）：
        "第01集$URL1#第02集$URL2#...$$$另一线路第01集$URL..."
    - '#' 分隔同一线路的集
    - '$' 分隔 集名 与 地址
    - '$$$' 分隔多线路（只取第一条线路，与 children.py MAX_PLAY_LINES=1 约定一致）

    匹配策略：
    1. ep_index 有效 -> 按"集名归一化数字 == ep_index"匹配
    2. 匹配不到（上游集数命名不规则/总数不一致）-> 集数越界时取最后可用集
    3. 单集影片（电影）-> 直接取第一条
    """
    if not play_url:
        return None
    # 只取第一条线路
    first_line = play_url.split("$$$")[0]
    eps = [e for e in first_line.split("#") if "$" in e]
    if not eps:
        return None

    # 单集（电影/综艺单期）：直接返回第一条
    if len(eps) == 1:
        return eps[0].split("$", 1)[1]

    if ep_index is not None:
        # 先按集名数字精确匹配
        for e in eps:
            name, _, url = e.partition("$")
            if norm_ep_number(name) == ep_index:
                return url
        # 匹配不到：集数越界（上游只有 39 集而客户端要第 40 集）-> 取最后一集兜底
        return eps[-1].partition("$")[2]
    return None


async def resolve_share_link(client, url):
    """share 播放页 -> 真实 m3u8。

    量子采集的 vod_play_url 里，新集是 share 链接（HTML 播放页），
    旧集是直链 m3u8。share 页内嵌带 sign 的 m3u8 相对路径：
        /20251024/2700_ed34a79a/index.m3u8?sign=6557dbc5...
    实测拼接后可直接播放（ts 首字节 0x47）。
    """
    # 已经是 m3u8 直链 -> 原样返回
    if ".m3u8" in url.split("?")[0]:
        return url
    try:
        r = await client.get(url, timeout=SHARE_TIMEOUT, headers=UA,
                             follow_redirects=True)
        m = _M3U8_REF_RE.search(r.text)
        if not m:
            return None
        # 相对路径 -> 拼绝对地址（urljoin 自动处理 / 开头与相对两种情况）
        return urljoin(str(r.url), m.group(1))
    except Exception:
        return None


# ---------------------------------------------------------------------------
# 搜索 / 详情
# ---------------------------------------------------------------------------
async def search_source(client, api, title):
    """单源搜索：ac=videolist&wd=片名。失败返回空列表（不抛异常打断并发）。"""
    try:
        r = await client.get(api, params={"ac": "videolist", "wd": title},
                             timeout=SOURCE_TIMEOUT, headers=UA)
        r.raise_for_status()
        data = r.json()
        return data.get("list") or []
    except Exception:
        return []


async def fetch_detail(client, api, vod_id):
    """单源详情：ac=detail&ids=id -> 返回 vod 条目（含 vod_play_url）。"""
    try:
        r = await client.get(api, params={"ac": "detail", "ids": str(vod_id)},
                             timeout=SOURCE_TIMEOUT, headers=UA)
        r.raise_for_status()
        lst = r.json().get("list") or []
        return lst[0] if lst else None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def _season_of_name(name):
    """候选名 -> 季数（归一化比较键层面提取，"第十二季"/"第12季" -> 12，无季 -> 0）。"""
    m = re.search(r'第(\d+)[季部]', norm_name_for_cmp(name or ""))
    return int(m.group(1)) if m else 0


async def _try_ranked(client, ranked, ep_index, req_season=None):
    """
    逐候选尝试出流：拉详情 -> 选集 -> share 解析，直到成功（最多前 5 个）。
    req_season: 请求季数（R2 系列兜底时传入）。命中候选季数 != 请求季数时
    jxFrom 加"~近似季"标注（App 端 Toast 显示"解析来自: direct:xxx~近似季"，
    用户可感知内容差异）；季数恰好一致（如采集站最新季==请求季）则视为精确命中不标注。
    """
    for vod, src in ranked[:5]:
        detail = await fetch_detail(client, src["api"], vod.get("vod_id"))
        if not detail:
            continue
        raw_url = pick_episode(detail.get("vod_play_url", ""), ep_index)
        if not raw_url:
            continue
        m3u8 = await resolve_share_link(client, raw_url)
        if m3u8:
            approx = req_season is not None and _season_of_name(vod.get("vod_name") or "") != req_season
            tag = "direct:" + src["name"] + ("~近似季" if approx else "")
            return {"url": m3u8, "parse": 0, "jxFrom": tag}
    return None


async def direct_resolve(title, ep_name=None, ep_index=None, lang=None):
    """
    无损云直连主流程（多轮搜索版，四平台统一）。
    R1: 归一化 title（剥语言后缀）直接搜 —— 覆盖"同名不同语言后缀"场景
        （腾讯"[普通话版]" / 爱奇艺" 英文版"）
    R2: R1 无有效候选且请求带季数时，剥季数按系列名搜 ——
        覆盖"腾讯第12季 vs 采集站第九季"的季数错位场景（含优酷/芒果中文数字季），
        命中后取该系列最新季，jxFrom 标注"~近似季"供 UI 提示
    lang: App 端 &lang= 显式参数（可选），与 title 自动提取的语言取并集，显式优先。
    返回 {"url": m3u8, "parse": 0, "jxFrom": "direct:<源名>"} 或 None（miss）。
    """
    if not title:
        return None
    norm_t, lang_bucket, season = norm_title(title)
    # 显式 lang 参数优先（App 端从片名提取，服务器入口透传）
    if lang:
        for kw, bucket in _LANG_BUCKET.items():
            if kw in str(lang):
                lang_bucket = bucket
                break
    if ep_index is None:
        ep_index = norm_ep_number(ep_name)

    # trust_env=False: 忽略系统代理环境变量（服务器环境 ALL_PROXY 为畸形 IPv6，会导致 httpx InvalidURL）
    async with httpx.AsyncClient(follow_redirects=True, trust_env=False) as client:
        # ---------- R1：归一化 title 搜索 ----------
        results = await asyncio.gather(
            *(search_source(client, s["api"], norm_t) for s in DIRECT_SOURCES)
        )
        ranked = []
        for src, items in zip(DIRECT_SOURCES, results):
            for vod in rank_candidates(norm_t, items):
                # 只收包含档(2.0)及以上；系列档(1.0)留给 R2 显式兜底
                if _candidate_score(vod, norm_t, lang_bucket) >= 2.0:
                    ranked.append((vod, src))
        hit = await _try_ranked(client, ranked, ep_index)
        if hit:
            return hit

        # ---------- R2：系列名兜底（仅带季数的请求） ----------
        if season:
            # 剥季数得系列名（比较键层面操作，"小猪佩奇第12季"->"小猪佩奇"）
            series_key = re.sub(r'第\d+[季部]', '', norm_name_for_cmp(norm_t))
            if series_key and series_key != norm_name_for_cmp(norm_t):
                results2 = await asyncio.gather(
                    *(search_source(client, s["api"], series_key) for s in DIRECT_SOURCES)
                )
                ranked2 = []
                for src, items in zip(DIRECT_SOURCES, results2):
                    for vod in rank_candidates(series_key, items):
                        # 系列档(1.0)也收：同系列不同季正是 R2 的目标场景
                        if _candidate_score(vod, series_key, lang_bucket) >= 1.0:
                            ranked2.append((vod, src))
                if ranked2:
                    # 同系列多季时取"最新季"：按候选名里的季数取最大
                    ranked2.sort(key=lambda vs: _season_of_name(vs[0].get("vod_name") or ""), reverse=True)
                    hit = await _try_ranked(client, ranked2, ep_index, req_season=season)
                    if hit:
                        return hit
    return None