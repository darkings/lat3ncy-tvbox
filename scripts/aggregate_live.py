#!/usr/bin/env python3
"""聚合直播源构建器：全量测速 + 分辨率优选 + verified/candidate 双态 + 生成自有 m3u。

流程：
1. 从 live_candidates.json 的 enabled 源收集全部频道线路
2. 按归一化频道名聚合多源线路
3. 目标频道逐线路测速：
   - 服务器可达 -> verified（带延迟 + 分辨率）
   - 服务器 403/超时但 URL 可信 -> candidate（客户端兜底）
4. 排序：verified高清 > verified标清 > candidate高清 > candidate标清，同级按延迟
5. 生成 subscription/aggregated-live.m3u，写报告
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from ponyo_source_manager.core import net
from ponyo_source_manager.core.common import CODE_DIR, CONFIG_DIR, REPORT_DIR
from ponyo_source_manager.probes import playback
from ponyo_source_manager.probes.live import (
    _classify_live_source,
    _normalize_channel_name,
    load_configured_live_candidates,
)

# 默认聚合目标频道（归一化后的名字，覆盖央视 17 台 + 主流省级卫视 + 少儿/体育/纪实/凤凰/新闻/电影/教育）
DEFAULT_CHANNELS = [
    "CCTV1", "CCTV2", "CCTV3", "CCTV4", "CCTV5", "CCTV5P", "CCTV6", "CCTV7",
    "CCTV8", "CCTV9", "CCTV10", "CCTV11", "CCTV12", "CCTV13", "CCTV14",
    "CCTV15", "CCTV16", "CCTV17",
    "湖南卫视", "浙江卫视", "江苏卫视", "东方卫视", "北京卫视", "广东卫视",
    "深圳卫视", "安徽卫视", "四川卫视", "湖北卫视", "山东卫视", "天津卫视",
    "重庆卫视", "辽宁卫视", "黑龙江卫视", "吉林卫视", "云南卫视", "贵州卫视",
    "广西卫视", "海南卫视", "河北卫视", "河南卫视", "山西卫视", "陕西卫视",
    "甘肃卫视", "东南卫视", "江西卫视", "凤凰卫视",
    # 少儿
    "金鹰卡通", "卡酷少儿", "哈哈炫动", "优漫卡通", "嘉佳卡通", "嘉佳卡通卫视",
    # 体育
    "五星体育", "广东体育", "山东体育", "劲爆体育", "天元围棋",
    # 纪实
    "上海纪实", "上海纪实人文", "纪实人文", "金鹰纪实", "北京纪实",
    "北京纪实科教", "重庆纪实",
    # 凤凰系（凤凰卫视已在上方卫视组）
    "凤凰中文", "凤凰资讯", "凤凰香港",
    # 新闻/都市
    "广东新闻", "四川新闻", "深圳都市", "上海都市",
    # 电影（CHC 付费频道，公开源少，有则收）
    "CHC家庭影院", "CHC动作电影", "CHC高清电影",
    # 教育
    "CETV1", "CETV01", "CETV4", "CETV04",
]

LOGO_NAME = {}
for _i in range(1, 18):
    LOGO_NAME[f"CCTV{_i}"] = f"cctv{_i}"
LOGO_NAME["CCTV5P"] = "cctv5p"

# 收录策略（无永久黑名单，全由测速裁决）：
# - 本轮有实测可播(verified/sniffed)线路 -> 收录
# - 本轮无实测线路但上轮已收录且仍有候选线路 -> 保留（测速波动，避免频道抖动消失）
# - 从未实测通过、仅候选/推测的频道 -> 不收录（播放不了不添加）

RES_TIER = {"4K": 4000, "1080": 3000, "720": 2000, "576": 1000, "SD": 500}

PRIVATE_HOST_RE = re.compile(
    r"https?://(10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.|100\.(6[4-9]|[7-9]\d|1[01]\d|12[0-7])\."
    r"|169\.254\.|222\.214\.)"
)
IPV6_HOST_RE = re.compile(r"https?://\[[0-9a-fA-F:]+\]")

# 可信域名白名单：服务器 403 不直接丢弃，标记为 candidate
TRUSTED_HOSTS = {
    # CCTV 官方/央视频
    "liveop.cctv.cn",
    "mobilelive-ds.ysp.cctv.cn",
    "hlspull.ysp.cctv.cn",
    # 中国移动视频
    "cmvideo.cn",
    # 湖南卫视公开流
    "liveplay-srs.voc.com.cn",
    # 中国大陆运营商 CDN（服务器境外不可达，客户端可播）
    "39.134.115.163",     # 中国移动 IPTV
    "39.134.24.166",      # 中国移动 IPTV
    "39.134.39.37",       # 中国移动 IPTV
    "125.210.152.18",     # 中国联通 IPTV
    "183.207.248.71",     # 中国移动贵州
    # 云平台直播
    "yunshicloud.com",    # 云南卫视
    "hwapi.yunshicloud.com",
    # 百视通 CDN（东方卫视等官方源）
    "bestv.cn",
    "bp-resource-dfl.bestv.cn",
    # 教育网 IPTV（限制大陆访问，但客户端可通）
    "huuc.edu.cn",
    "iptv.huuc.edu.cn",
    # 其他可信公开流
    "xykt-fix.github.io", # 已知公开镜像
    "go.bkpcp.top",       # 已知公开代理
    "74.91.26.218",       # iptv-org 镜像节点
    "69.30.245.50",       # iptv-org 镜像节点
    "t.061899.xyz",       # 实测可通的个人代理
    # 大陆个人/自建转发（少儿/体育/新闻/CHC 频道线路，境外服务器不可达，客户端可播）
    "zby.130519.xyz",
    "itv.iptv1688.top",
    "tvbox6.icu",
    "wouu.net",
    "119.32.12.17",
    "122.228.73.138",
    "148.135.93.213",
    "58.19.38.162",
    "101.35.240.114",
    "111.22.153.159",
    "8.138.7.223",
}

# 内置补充源：live_candidates.json 之外的公开直播列表
EXTRA_SOURCES = [
    {
        "key": "iptv_org_cn",
        "name": "IPTV-Org China",
        "url": "https://iptv-org.github.io/iptv/countries/cn.m3u",
    },
    {
        "key": "iptv_org_zho",
        "name": "IPTV-Org Chinese",
        "url": "https://iptv-org.github.io/iptv/languages/zho.m3u",
    },
    {
        "key": "suxuang_ipv4",
        "name": "suxuang IPv4",
        "url": "https://cdn.jsdelivr.net/gh/suxuang/myIPTV@main/ipv4.m3u",
    },
    {
        "key": "zhoujie_ipv4",
        "name": "zhoujie IPv4",
        "url": "https://live.zhoujie218.top/tv/iptv4.m3u",
    },
]



def group_of(norm: str) -> str:
    # 顺序敏感：先匹配更具体的分组，再回落央视/卫视
    if any(m in norm for m in ("卡通", "少儿", "炫动")):
        return "少儿"
    if "纪实" in norm:
        return "纪实"
    if "体育" in norm or norm == "天元围棋":
        return "体育"
    if norm.startswith("CHC"):
        return "电影"
    if "新闻" in norm or norm.endswith("都市"):
        return "新闻"
    if norm.startswith("CETV"):
        return "教育"
    if norm.startswith("凤凰"):
        return "卫视" if norm.endswith("卫视") else "凤凰"
    if norm.startswith(("CCTV", "CGTN")):
        return "央视"
    if norm.endswith("卫视") or norm in ("凤凰卫视", "星空卫视"):
        return "卫视"
    return "其他"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def fetch_source_content(url: str) -> str | None:
    fallbacks = [url]
    m = re.match(r"https://cdn\.jsdelivr\.net/gh/([^@]+)@([^/]+)/(.+)", url)
    if m:
        repo, branch, path = m.groups()
        fallbacks += [
            f"https://gh-proxy.com/https://raw.githubusercontent.com/{repo}/{branch}/{path}",
            f"https://raw.githubusercontent.com/{repo}/{branch}/{path}",
        ]
    for u in fallbacks:
        try:
            content = net.fetch_text(u, timeout=15, limiter=None)
            if content and len(content) > 200:
                return content
        except Exception:
            continue
    return None


def parse_entries(content: str) -> list[tuple[str, str, str]]:
    """解析 M3U/TXT -> [(频道名, URL, EXTINF行原文)]，保留分辨率标记。"""
    entries: list[tuple[str, str, str]] = []
    lines = content.splitlines()
    if content.strip().startswith("#EXTM3U"):
        current_name = None
        current_extinf = ""
        for line in lines:
            line = line.strip()
            if line.startswith("#EXTINF"):
                current_extinf = line
                current_name = line.split(",")[-1].strip()
            elif line.startswith(("http://", "https://")) and current_name:
                entries.append((current_name, line, current_extinf))
            elif line.startswith("#"):
                continue
            elif not line:
                continue
    else:
        for line in lines:
            line = line.strip()
            if not line or line.startswith("#") or ",http" not in line:
                continue
            name, _, url = line.partition(",")
            name, url = name.strip(), url.strip()
            if name and url.startswith(("http://", "https://")):
                entries.append((name, url, line))
    return entries


VOD_PROXY = [
    "https://gh.927223.xyz/", "https://ghfast.top/", "https://gh-proxy.com/",
    "https://github.moeyy.xyz/", "https://ghproxy.net/", "https://mirror.ghproxy.com/",
    "https://raw.kkgithub.com/", "https://down.nigx.cn/", "https://fastgit.cc/",
    "https://gh-proxy.org/", "https://cdn.gh-proxy.org/", "https://gh.tryxd.cn/",
    "https://raw.gitmirror.com/", "https://ghproxy.com/", "https://gh.halonice.com/",
]


def _real_url(u: str) -> str:
    for p in VOD_PROXY:
        if u.startswith(p):
            return u[len(p):]
    return u


def load_vod_sources(path: str, min_china: int = 30) -> list[dict]:
    """从点播挖掘的筛查报告(lives-screened.json)读取有效直播源。

    按真实源URL去重(去掉代理镜像重复)，只保留中国频道数 >= min_china 的。
    返回 collect_routes 可用的 [{key,name,url}] 列表。
    """
    fp = Path(path)
    if not fp.exists():
        print(f"[vod] 挖掘报告不存在: {path}, 跳过")
        return []
    data = json.loads(fp.read_text(encoding="utf-8"))
    entries = data.get("valid_entries", [])
    best: dict[str, dict] = {}
    for r in entries:
        if r.get("china_channels", 0) < min_china:
            continue
        ru = _real_url(str(r.get("url", "")))
        if ru not in best or r.get("china_channels", 0) > best[ru].get("china_channels", 0):
            best[ru] = r
    out = []
    for i, r in enumerate(best.values(), 1):
        out.append({
            "key": f"vod_{i}",
            "name": str(r.get("name", f"vod_{i}")),
            # 用原始(可能是CDN镜像)URL, 保证国内服务器可达
            "url": str(r.get("url", "")),
        })
    print(f"[vod] 从挖掘报告载入 {len(out)} 个新源(中国频道>={min_china})")
    return out


def collect_routes(sources: list[dict]) -> dict[str, list[tuple[str, str, str]]]:
    """汇总所有源线路：{归一化频道名: [(url, 源key, extinf原文)]}。"""
    pool: dict[str, list[tuple[str, str, str]]] = {}
    stats = []
    for src in sources:
        key = src.get("key", "?")
        content = fetch_source_content(str(src.get("url", "")))
        if not content:
            stats.append((key, "fetch_failed", 0))
            continue
        reject = _classify_live_source(str(src.get("name", key)), str(src.get("url", "")), content)
        if reject in ("ipv6_only", "carousel_rooms", "fetch_failed"):
            stats.append((key, f"skipped:{reject}", 0))
            continue
        n = 0
        for name, url, extinf in parse_entries(content):
            if IPV6_HOST_RE.search(url) or PRIVATE_HOST_RE.search(url):
                continue
            norm = _normalize_channel_name(name)
            if norm:
                pool.setdefault(norm, []).append((url, key, extinf))
                n += 1
        stats.append((key, "ok", n))
    for key, status, n in stats:
        print(f"  源 {key}: {status}, 收录线路 {n}")
    return pool


def res_from_text(text: str) -> int | None:
    """从任意文本（EXTINF/URL/频道名）推断分辨率档。"""
    text = text.lower()
    if re.search(r"4k|uhd|2160p", text):
        return RES_TIER["4K"]
    if re.search(r"1080p|fhd|全高清", text):
        return RES_TIER["1080"]
    if re.search(r"720p|\bhd\b", text):
        return RES_TIER["720"]
    if re.search(r"576[ip]|\bsd\b|标清", text):
        return RES_TIER["576"]
    return None


def parse_m3u8_resolution(playlist_text: str) -> int | None:
    """解析 M3U8 master playlist 的 RESOLUTION=WxH，取最高档。"""
    best: int | None = None
    for m in re.finditer(r"RESOLUTION=\d+x(\d+)", playlist_text):
        height = int(m.group(1))
        if height >= 2000:
            tier = RES_TIER["4K"]
        elif height >= 1000:
            tier = RES_TIER["1080"]
        elif height >= 700:
            tier = RES_TIER["720"]
        else:
            tier = RES_TIER["576"]
        if best is None or tier > best:
            best = tier
    return best


def content_fingerprint(playlist_text: str) -> str:
    """从 m3u8 播放列表提取内容指纹，用于识别"同源中转串台"。

    优先取腾讯云 txspiseq（同一后端流该值相同）；
    否则取首个 ts 分片文件名前缀（去掉末尾序号）。
    取不到返回空串（不参与同源判定）。
    """
    if not playlist_text:
        return ""
    m = re.search(r"txspiseq=(\d+)", playlist_text)
    if m:
        return "txs:" + m.group(1)
    for line in playlist_text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        seg = line.split("?")[0].rsplit("/", 1)[-1]
        m2 = re.match(r"([A-Za-z0-9_-]*?)[-.]?\d+\.ts$", seg)
        if m2 and m2.group(1):
            return "ts:" + m2.group(1)
        if seg.endswith(".ts"):
            return "ts:" + seg
    return ""


def is_trusted_host(url: str) -> bool:
    """URL 的主机（域名或IP）是否在可信白名单中。"""
    try:
        host = urlparse(url).hostname or ""
        # 直接匹配 IP，或域名后缀匹配
        return host in TRUSTED_HOSTS or any(host.endswith(d) for d in TRUSTED_HOSTS if "." in d)
    except Exception:
        return False


def is_relay_select_url(url: str) -> bool:
    """识别"参数选台"中转代理：路径以 .php/.asp/.jsp 等动态脚本结尾且带 id= 参数。

    这类入口(如 tl.php?id=cctv8)由后端按 id 转发真实流, 但后端常丢失 id 参数,
    导致所有台返回同一频道内容。服务器端又常 403 拿不到 m3u8 做内容指纹,
    因此按 URL 形态直接识别并降权, 永不作为首选。
    """
    try:
        p = urlparse(url)
        path = (p.path or "").lower()
        query = (p.query or "").lower()
        if re.search(r"\.(php|asp|aspx|jsp|do|action)$", path) and re.search(r"(^|&)id=", query):
            return True
    except Exception:
        pass
    return False


def probe_route(url: str, extinf: str, timeout: int = 8,
                ffprobe_timeout: int = 6) -> dict | None:
    """测单条线路：verified（服务器可播）或 candidate（403但可信域名）。"""
    res = playback.verify_playback(url)
    latency = int(res.get("latency_ms") or 9999)
    ok = res.get("success") == 1

    # 分辨率优先级：M3U8 清单 > EXTINF 标记 > URL 推断 > ffprobe
    tier = None
    playlist_text = ""
    if ok:
        try:
            playlist_text = net.fetch_text(url, timeout=5, limiter=None) or ""
            if playlist_text:
                tier = parse_m3u8_resolution(playlist_text)
        except Exception:
            playlist_text = ""
    if tier is None:
        tier = res_from_text(extinf + " " + url)
    if tier is None and ok:
        tier = ffprobe_resolution(url, ffprobe_timeout)

    if ok:
        # 嗅探型源：入口是网页/跳转，真实流靠 sniff_media_url 提取。
        # 播放器(IJK/Exo)直放入口地址会拿到网页或403，故标 sniffed 单独降权。
        sniffed_url = res.get("sniffed_url") or ""
        status = "sniffed" if sniffed_url else "verified"
        return {
            "url": url,
            "latency_ms": latency,
            "res_tier": tier or RES_TIER["720"],
            "res_label": tier_label(tier),
            "status": status,
            "sniffed_url": sniffed_url,
            "fingerprint": content_fingerprint(playlist_text),
        }

    if is_trusted_host(url):
        # 参数选台中转(如 tl.php?id=xxx): 服务器 403 无法校验内容, 且实测存在
        # 后端丢 id 导致所有台同一画面的串台问题, 单独标 relay 排到 candidate 之后。
        relay = is_relay_select_url(url)
        return {
            "url": url,
            "latency_ms": latency,
            "res_tier": tier or RES_TIER["720"],
            "res_label": tier_label(tier),
            "status": "relay" if relay else "candidate",
            "fingerprint": "",
        }

    return None


def tier_label(tier: int | None) -> str:
    return {4000: "4K", 3000: "1080p", 2000: "720p", 1000: "576p", 500: "SD"}.get(
        tier or 2000, "720p"
    )


def ffprobe_resolution(url: str, timeout: int) -> int | None:
    try:
        r = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=width,height",
                "-of", "csv=p=0",
                url,
            ],
            capture_output=True, text=True, timeout=timeout,
        )
        m = re.search(r"(\d{3,4}),(\d{3,4})", r.stdout or "")
        if not m:
            return None
        height = int(m.group(2))
        if height >= 2000:
            return RES_TIER["4K"]
        if height >= 1000:
            return RES_TIER["1080"]
        if height >= 700:
            return RES_TIER["720"]
        return RES_TIER["576"]
    except (subprocess.TimeoutExpired, OSError, ValueError):
        return None


def sample_routes(
    routes: list[tuple[str, str, str]],
    max_probe: int,
    per_source: int = 2,
) -> list[tuple[str, str, str]]:
    """对一个频道的线路做来源多样化采样。

    routes 按 collect_routes 的顺序是“按源分组”的，若直接取前 N 条，
    会被线路最多的巨型源霸占。这里按来源轮询采样，每个源最多 per_source 条，
    直到凑够 max_probe；不足时再用原始顺序补齐。
    """
    if max_probe <= 0:
        return routes

    by_src: dict[str, list[tuple[str, str]]] = {}
    order: list[str] = []
    for u, k, e in routes:
        if k not in by_src:
            by_src[k] = []
            order.append(k)
        by_src[k].append((u, e))

    picked: list[tuple[str, str, str]] = []
    seen: set[tuple[str, str]] = set()

    # 轮询采样：每个源每次取 1 条，共 per_source 轮
    for round_i in range(per_source):
        for k in order:
            if len(picked) >= max_probe:
                return picked
            lst = by_src[k]
            if round_i < len(lst):
                u, e = lst[round_i]
                if (u, e) not in seen:
                    seen.add((u, e))
                    picked.append((u, k, e))

    # 还没凑够，用原始顺序补齐
    for u, k, e in routes:
        if len(picked) >= max_probe:
            break
        if (u, e) not in seen:
            seen.add((u, e))
            picked.append((u, k, e))
    return picked


def build_channel(norm: str, routes: list[tuple[str, str, str]],
                  max_keep: int, workers: int,
                  max_probe: int = 40, per_source: int = 2,
                  global_fp: dict | None = None,
                  prev_included: set | frozenset = frozenset()) -> dict | None:
    """测一个频道的采样线路。

    收录裁决（无永久黑名单）：
    - 有实测可播(verified/sniffed)线路 -> 收录，候选线路可作备用；
    - 无实测线路但上轮已收录且仍有候选线路 -> 保留（防测速波动抖动）；
    - 其余（从未实测通过）-> 不收录。
    """
    sampled = sample_routes(routes, max_probe=max_probe, per_source=per_source)
    uniq = list(dict.fromkeys((u, e) for u, _k, e in sampled))
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(probe_route, u, e): u for u, e in uniq}
        for fut in concurrent.futures.as_completed(futures):
            r = fut.result()
            if r:
                results.append(r)
    if not results:
        return None

    verified = [r for r in results if r["status"] in ("verified", "sniffed")]
    if not verified:
        cands = [r for r in results if r["status"] in ("candidate", "relay")]
        if norm in prev_included and cands:
            print(f"    [{norm}] 本轮无实测可播线路，沿用上轮收录（候选线路）")
            results = cands
        else:
            print(f"    [{norm}] 无实测可播线路（仅候选/推测），不收录")
            return None

    def sort_key(r: dict) -> tuple:
        # verified 直连最优先；sniffed(网页嗅探,播放器直放易失败)其次；candidate 最后
        status_rank = {"verified": 0, "sniffed": 1, "candidate": 2, "relay": 3}.get(r["status"], 2)
        return (status_rank, -r["res_tier"], r["latency_ms"])

    results.sort(key=sort_key)

    # 同源中转串台去重：同一频道内, 若多条线路内容指纹相同但入口 URL 不同,
    # 说明是"一个后端套多个台名"的中转代理(如 tl.php?id=xxx 全部返回同一频道),
    # 只保留排序最优的一条, 其余降权丢弃, 避免占满 max_keep 名额。
    seen_fp: set[str] = set()
    fp_deduped = []
    dropped_same_origin = 0
    for r in results:
        fp = r.get("fingerprint") or ""
        if fp and fp in seen_fp:
            dropped_same_origin += 1
            continue
        if fp:
            seen_fp.add(fp)
        fp_deduped.append(r)
    if dropped_same_origin:
        print(f"    [同源去重] {norm}: 丢弃 {dropped_same_origin} 条串台中转线路")

    # 跨频道串台判定：同一内容指纹若已被其它频道占用(典型: tl.php?id=xxx
    # 无论 id 传什么都返回同一频道), 则本频道里这些线路全是串台, 全部丢弃。
    if global_fp is not None:
        cross_ok = []
        dropped_cross = 0
        for r in fp_deduped:
            fp = r.get("fingerprint") or ""
            if fp:
                owner = global_fp.get(fp)
                if owner is not None and owner != norm:
                    dropped_cross += 1
                    continue
                # 首次占用该指纹：登记归属(verified 优先登记, 避免被 candidate 抢注)
                if owner is None or r["status"] == "verified":
                    global_fp[fp] = norm
            cross_ok.append(r)
        if dropped_cross:
            print(f"    [跨台串台] {norm}: 丢弃 {dropped_cross} 条与他台同指纹线路")
        results = cross_ok
    else:
        results = fp_deduped

    if not results:
        return None

    # relay(参数选台中转)兜底过滤：若该频道已没有任何 verified/candidate 真实源,
    # 剩下的全是 relay, 说明此台只能靠"丢 id 的串台中转"播出, 画面必然是错的,
    # 与其输出错误画面, 不如不产出该频道(返回 None), 避免误导用户。
    has_real = any(r["status"] in ("verified", "sniffed", "candidate") for r in results)
    if not has_real:
        relay_only = [r for r in results if r["status"] == "relay"]
        if relay_only and len(relay_only) == len(results):
            print(f"    [中转兜底] {norm}: 仅剩 {len(relay_only)} 条串台中转, 无真实源, 放弃本频道")
            return None

    # 最终保留前按 URL 去重(同一直流地址不同 extinf 会重复, 只留最优的一条)
    seen_url: set[str] = set()
    deduped = []
    for r in results:
        if r["url"] in seen_url:
            continue
        seen_url.add(r["url"])
        deduped.append(r)
        if len(deduped) >= max_keep:
            break
    kept = deduped
    best = kept[0]
    verified_count = sum(1 for r in results if r["status"] == "verified")
    relay_count = sum(1 for r in results if r["status"] == "relay")
    return {
        "channel": norm,
        "group": group_of(norm),
        "logo_name": LOGO_NAME.get(norm, norm.lower()),
        "routes": kept,
        "best_res": best["res_label"],
        "best_latency_ms": best["latency_ms"],
        "best_status": best["status"],
        "tested": len(uniq),
        "total_routes": len(routes),
        "playable": len(results),
        "verified": verified_count,
        "candidate": len(results) - verified_count - relay_count,
        "relay": relay_count,
    }


def render_m3u(channels: list[dict], epg_url: str) -> str:
    lines = [f'#EXTM3U x-tvg-url="{epg_url}"']
    for ch in channels:
        logo = f"https://logo.wyfc.qzz.io/{ch['logo_name']}.png"
        attr = (
            f'#EXTINF:-1 tvg-name="{ch["channel"]}" tvg-logo="{logo}" '
            f'group-title="{ch["group"]}",{ch["channel"]}'
        )
        lines.append(attr)
        lines.extend(r["url"] for r in ch["routes"])
    return "\n".join(lines) + "\n"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--output", default=str(CODE_DIR.parent / "subscription" / "aggregated-live.m3u"))
    p.add_argument("--report", default=str(REPORT_DIR / "live-aggregate-report.json"))
    p.add_argument("--channels-file", default=None)
    p.add_argument("--max-keep", type=int, default=3)
    p.add_argument("--workers", type=int, default=12)
    p.add_argument("--max-probe", type=int, default=40,
                   help="每频道最多测速多少条线路(0=全部)")
    p.add_argument("--per-source", type=int, default=2,
                   help="采样时每个源最多贡献几条线路")
    p.add_argument("--epg", default="http://epg.51zmt.top:8000/api/diyp/")
    p.add_argument("--extra-sources", default=None,
                   help="点播挖掘的 lives-screened.json, 作为额外线路来源")
    p.add_argument("--min-china", type=int, default=30,
                   help="挖掘源仅采用中国频道>=N 的")
    args = p.parse_args()

    t0 = time.time()
    targets = (
        json.loads(Path(args.channels_file).read_text(encoding="utf-8"))
        if args.channels_file
        else DEFAULT_CHANNELS
    )
    target_set = {_normalize_channel_name(c) for c in targets}

    print("=== 收集候选源线路 ===")
    sources = load_configured_live_candidates()
    # 追加内置补充源（iptv-org 等公开列表）
    sources.extend(EXTRA_SOURCES)
    # 追加点播挖掘出的新直播源(线路级, 参与每频道前3优选)
    if args.extra_sources:
        sources.extend(load_vod_sources(args.extra_sources, args.min_china))
    pool = collect_routes(sources)
    print(f"线路池: {len(pool)} 个去重频道")

    print(f"\n=== 测速 {len(target_set)} 个目标频道 ===")
    built = []
    # 上轮已收录频道（防测速波动抖动：本轮无实测线路但上轮有 -> 候选线路仍保留）
    prev_included: set[str] = set()
    out_path = Path(args.output)
    if out_path.is_file():
        try:
            prev_included = set(re.findall(
                r'tvg-name="([^"]+)"', out_path.read_text(encoding="utf-8")))
        except Exception:
            prev_included = set()
    print(f"上轮收录频道: {len(prev_included)} 个")

    # 全局内容指纹表 {指纹: 首个占用频道名}, 用于跨频道串台识别
    global_fp: dict = {}
    for i, norm in enumerate(sorted(target_set), 1):
        routes = pool.get(norm)
        if not routes:
            print(f"  [{i}/{len(target_set)}] {norm}: 无线路")
            continue
        ch = build_channel(norm, routes, args.max_keep, args.workers,
                           max_probe=args.max_probe, per_source=args.per_source,
                           global_fp=global_fp, prev_included=prev_included)
        if ch:
            built.append(ch)
            status_mark = "V" if ch["best_status"] == "verified" else "~"
            print(
                f"  [{i}/{len(target_set)}] {norm}: {ch['playable']}/{ch['tested']} 可用 "
                f"(verified={ch['verified']} candidate={ch['candidate']}), "
                f"首选 {status_mark}{ch['best_res']} {ch['best_latency_ms']}ms"
            )
        else:
            print(f"  [{i}/{len(target_set)}] {norm}: 全部不可用")

    order = {name: idx for idx, name in enumerate(DEFAULT_CHANNELS)}
    built.sort(key=lambda c: order.get(c["channel"], 999))

    m3u_text = render_m3u(built, args.epg)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(m3u_text, encoding="utf-8")

    report = {
        "generated_at": _now(),
        "elapsed_s": round(time.time() - t0, 1),
        "target_channels": len(target_set),
        "built_channels": len(built),
        "channels": built,
        "missing": sorted(target_set - {c["channel"] for c in built}),
    }
    Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    Path(args.report).write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n完成: {len(built)}/{len(target_set)} 频道, 耗时 {report['elapsed_s']}s")
    print(f"m3u: {out_path} ({len(m3u_text)}B), 报告: {args.report}")


if __name__ == "__main__":
    main()
