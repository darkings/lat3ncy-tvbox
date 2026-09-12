#!/usr/bin/env python3
"""直播源自动发现：扫描 GitHub 仓库，提取直播列表，测速后写入候选池。

对应 PLAN §十五 电视直播 - 自动发现机制。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from ponyo_source_manager.core import net
from ponyo_source_manager.core.common import CONFIG_DIR, DATA_DIR
from ponyo_source_manager.probes.live import (
    evaluate_live_source,
    load_test_channels,
    parse_live_channels,
    parse_live_channel_routes,
    _classify_live_source,
    _normalize_channel_name,
)


# 已知 TVBox 直播源仓库（GitHub）
# 格式: (repo, branch, path, name, key_prefix)
LIVE_SOURCE_REPOS = [
    # IPTV 官方/社区源
    ("iptv-org/iptv", "master", "streams/cn.m3u", "IPTV-Org 中国", "iptv_org_cn"),
    ("iptv-org/iptv", "master", "streams/cn_cctv.m3u", "IPTV-Org CCTV", "iptv_org_cctv"),
    ("iptv-org/iptv", "master", "streams/cn_satellite.m3u", "IPTV-Org 卫视", "iptv_org_sat"),
    # 国内聚合
    ("kimwang1978/collect-tv-txt", "main", "assets/txt/txt_all.txt", "收集天下TXT", "collect_tv_txt"),
    ("kimwang1978/collect-tv-txt", "main", "assets/m3u/m3u_all.m3u", "收集天下M3U", "collect_tv_m3u"),
    # 其他可用源
    ("fanmingming/live", "main", "tv/m3u/ipv6.m3u", "范明明IPv6", "fanmingming_ipv6"),
    ("YanG-1989/m3u", "main", "Gather.m3u", "YanG Gather", "yang_gather"),
    ("YueChan/Live", "main", "IPTV.m3u", "YueChan IPTV", "yuechan_iptv"),
    ("Meroser/IPTV", "main", "IPTV.m3u", "Meroser IPTV", "meroser_iptv"),
]


@dataclass
class LiveCandidate:
    """直播候选源"""
    key: str
    name: str
    url: str
    enabled: bool = True
    source: str = "discovery"  # discovery / configured


def _now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def fetch_live_list(repo: str, branch: str, path: str) -> str | None:
    """从 GitHub 拉取直播列表内容。"""
    # 优先 jsDelivr CDN（国内可访问）
    urls = [
        f"https://cdn.jsdelivr.net/gh/{repo}@{branch}/{path}",
        f"https://raw.githubusercontent.com/{repo}/{branch}/{path}",
        f"https://ghproxy.com/https://raw.githubusercontent.com/{repo}/{branch}/{path}",
    ]
    for url in urls:
        try:
            content = net.fetch_text(url, timeout=15, limiter=None)
            if content and len(content) > 100:  # 有效内容
                return content
        except Exception:
            continue
    return None


def analyze_live_content(content: str, name: str) -> dict:
    """分析直播列表内容，返回统计信息。"""
    mapping = parse_live_channels(content)
    routes = parse_live_channel_routes(content)
    
    # 统计中国频道数量
    china_keywords = ["CCTV", "卫视", "湖南", "浙江", "江苏", "东方", "北京", "广东", "深圳"]
    china_count = sum(
        1 for ch in mapping.keys()
        if any(kw in ch for kw in china_keywords)
    )
    
    # 检查是否被预检拒绝
    reject_reason = _classify_live_source(name, "", content)
    
    return {
        "total_channels": len(routes),
        "unique_channels": len(set(_normalize_channel_name(k) for k in mapping.keys())),
        "china_channels": china_count,
        "reject_reason": reject_reason,
    }


def evaluate_candidate(candidate: LiveCandidate, test_channels: list[str]) -> dict:
    """评估单个候选源。"""
    content = fetch_live_list(*candidate.key.split("|"))
    if not content:
        return {
            "key": candidate.key,
            "name": candidate.name,
            "url": candidate.url,
            "enabled": False,
            "error": "fetch_failed",
        }
    
    stats = analyze_live_content(content, candidate.name)
    
    # 如果预检拒绝，直接返回
    if stats["reject_reason"]:
        return {
            "key": candidate.key,
            "name": candidate.name,
            "url": candidate.url,
            "enabled": False,
            "reject_reason": stats["reject_reason"],
            "stats": stats,
        }
    
    # 测速评估
    eval_result = evaluate_live_source(
        candidate.key,
        candidate.url,
        test_channels,
    )
    
    return {
        "key": candidate.key,
        "name": candidate.name,
        "url": candidate.url,
        "enabled": eval_result["hard_pass"],
        "score": eval_result["total_score"],
        "validity_rate": eval_result["validity_rate"],
        "stats": stats,
    }


def discover_live_sources() -> list[dict]:
    """扫描所有已知仓库，返回评估后的候选列表。"""
    test_channels = load_test_channels()
    results = []
    
    for repo, branch, path, name, key_prefix in LIVE_SOURCE_REPOS:
        key = f"{key_prefix}"
        url = f"https://cdn.jsdelivr.net/gh/{repo}@{branch}/{path}"
        
        print(f"扫描 {name} ({repo}/{path})...")
        
        try:
            content = fetch_live_list(repo, branch, path)
            if not content:
                print(f"  ❌ 拉取失败")
                continue
            
            stats = analyze_live_content(content, name)
            print(f"  📺 频道: {stats['total_channels']} 总数, {stats['unique_channels']} 去重, {stats['china_channels']} 中国")
            
            if stats["reject_reason"]:
                print(f"  ❌ 预检拒绝: {stats['reject_reason']}")
                continue
            
            # 测速评估
            eval_result = evaluate_live_source(key, url, test_channels)
            print(f"  📊 得分: {eval_result['total_score']}, 有效率: {eval_result['validity_rate']:.2%}, hard_pass: {eval_result['hard_pass']}")
            
            if eval_result["hard_pass"]:
                results.append({
                    "key": key,
                    "name": name,
                    "url": url,
                    "enabled": True,
                    "source": "discovery",
                    "score": eval_result["total_score"],
                    "validity_rate": eval_result["validity_rate"],
                    "stats": stats,
                })
                print(f"  ✅ 通过")
            else:
                print(f"  ❌ 未通过 hard_pass")
                
        except Exception as e:
            print(f"  ❌ 错误: {e}")
            continue
    
    return results


def update_live_candidates(new_candidates: list[dict], config_path: str | Path | None = None) -> None:
    """将新发现的候选写入 live_candidates.json。"""
    path = Path(config_path) if config_path else CONFIG_DIR / "live_candidates.json"
    
    # 读取现有配置
    existing = []
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
    
    # 合并：保留现有 configured 源，添加新发现的源
    existing_keys = {c["key"] for c in existing}
    for nc in new_candidates:
        if nc["key"] not in existing_keys:
            existing.append({
                "key": nc["key"],
                "name": nc["name"],
                "url": nc["url"],
                "enabled": nc["enabled"],
            })
    
    # 按 score 排序（如果有）
    existing.sort(key=lambda x: x.get("score", 0), reverse=True)
    
    path.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n已更新 {path}: {len(existing)} 个候选")


def main() -> None:
    print("=== 直播源自动发现 ===\n")
    candidates = discover_live_sources()
    
    if candidates:
        print(f"\n=== 发现 {len(candidates)} 个可用源 ===")
        for c in candidates:
            print(f"  {c['name']}: score={c['score']}, validity={c['validity_rate']:.2%}")
        
        update_live_candidates(candidates)
    else:
        print("\n未发现可用的新直播源")


if __name__ == "__main__":
    main()
