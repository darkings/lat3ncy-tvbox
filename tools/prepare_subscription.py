#!/usr/bin/env python3
"""Prepare the Ponyo TV subscription for reliable remote delivery."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path


RAW_RE = re.compile(
    r"https://raw\.githubusercontent\.com/([^/]+)/([^/]+)/([^/]+)/([^\s\"<>]+)"
)


def to_jsdelivr(value):
    if isinstance(value, str):
        return RAW_RE.sub(
            lambda match: (
                "https://cdn.jsdelivr.net/gh/"
                f"{match.group(1)}/{match.group(2)}@{match.group(3)}/{match.group(4)}"
            ),
            value,
        )
    if isinstance(value, list):
        return [to_jsdelivr(child) for child in value]
    if isinstance(value, dict):
        return {key: to_jsdelivr(child) for key, child in value.items()}
    return value


def tidy_core(value):
    value = re.sub(r"\[(?:js|直连)\]", "", value, flags=re.I)
    value = value.replace("动畫", "动漫").replace("動畫", "动漫")
    value = value.replace("cupfox.in", "").strip()
    value = re.sub(r"\s+", "", value)
    return value


def normalize_name(name):
    original = name.strip()
    exact = {
        "豆瓣推荐": "豆瓣推荐",
        "配置｜中心": "配置中心",
        "本地｜视频": "本地视频",
        "新片｜预告": "新片预告",
        "新闪雷┃MP4": "新闪雷影视（MP4）",
        "飞宇影院": "飞宇影视",
        "茶杯狐┃cupfox.in": "茶杯狐影视",
        "ITalkBB｜外": "ITalkBB影视（海外）",
        "戏曲 • 多多": "多多戏曲",
        "明星┃MV": "明星MV",
        "🎶明星┃MV": "明星MV",
        "修复所有,【太太太硬了】领取嘟嘟盘免费容量": "线路修复",
    }
    if original in exact:
        return exact[original]

    cleaned = re.sub(r"^[^\w\u4e00-\u9fff]+", "", original)
    parts = [tidy_core(part) for part in re.split(r"\s*[｜┃|•]\s*", cleaned) if tidy_core(part)]
    if len(parts) >= 2:
        first, second = parts[0], parts[1]
        generic = {"影视", "官源", "动漫", "音频", "广播", "听书", "聚合", "磁力", "网盘", "直播"}
        if first in generic:
            core = second
            if first == "影视":
                if "直连" in original:
                    core = core.replace("资源", "")
                    return core + "采集（直连）"
                return core if core.endswith("影视") else core + "影视"
            if first == "官源":
                return core + "官源"
            if first == "动漫":
                core = re.sub(r"(?:动漫)+$", "", core)
                return core + "动漫"
            if first == "音频":
                return core if core.endswith(("音乐", "电台")) else core + "音乐"
            if first == "广播":
                core = re.sub(r"FM$", "", core, flags=re.I)
                return core + "电台"
            if first == "听书":
                return core if core.endswith("听书") else core + "听书"
            if first == "磁力":
                return core + "磁力"
            if first == "网盘":
                return core if core.endswith("网盘") else core + "网盘"
            if first == "直播":
                return core if core.endswith("直播") else core + "直播"
            return core

        core, kind = first, second
        kind_map = {
            "APP": "影视", "4K": "影视（4K）", "MP4": "影视（MP4）",
            "影视": "影视", "短剧": "短剧", "动漫": "动漫", "新番社": "动漫",
            "网盘": "网盘", "搜索": "搜索", "看球": "体育", "体育": "体育",
            "DJ": "音乐", "FM": "电台", "听书": "听书", "音乐": "音乐",
            "直播": "直播", "教学": "教学", "知识": "知识", "视频": "视频",
            "磁力": "磁力", "云盘": "网盘", "四盘": "搜索", "弹幕": "视频",
            "启蒙": "教学", "课堂": "教学", "不卡": "影视",
        }
        suffix = kind_map.get(kind)
        if suffix:
            return core if core.endswith(suffix) else core + suffix
        return core + kind

    compact = tidy_core(cleaned)
    compact = re.sub(r"\s*APP$", "影视", compact, flags=re.I)
    compact = re.sub(r"\s*4K$", "影视（4K）", compact, flags=re.I)
    compact = re.sub(r"\s*短剧$", "短剧", compact)
    compact = re.sub(r"\s*影视$", "影视", compact)
    compact = re.sub(r"\s*直播$", "直播", compact)
    return compact


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("config", type=Path)
    parser.add_argument("--health", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--asset-output", type=Path, required=True)
    parser.add_argument("--name-map", type=Path, required=True)
    args = parser.parse_args()

    config = json.loads(args.config.read_text(encoding="utf-8"))
    health = json.loads(args.health.read_text(encoding="utf-8"))
    health_by_key = {site["key"]: site for site in health["sites"]}

    kept = []
    mapping = []
    for index, site in enumerate(config.get("sites", [])):
        health_item = health_by_key.get(site.get("key", ""), {})
        verdict = health_item.get("verdict", "builtin-or-conditional")
        old_name = health_item.get("name", site.get("name", ""))
        if verdict == "unreachable":
            mapping.append({"key": site.get("key", ""), "old": old_name, "new": None, "verdict": verdict})
            continue
        site["name"] = normalize_name(old_name)
        site["_original_index"] = index
        site["_verdict"] = verdict
        mapping.append({"key": site.get("key", ""), "old": old_name, "new": site["name"], "verdict": verdict})
        kept.append(site)

    priority = {"verified": 0, "partial": 1, "builtin-or-conditional": 2}
    system_keys = {"drpy_js_豆瓣": 0, "配置中心": 1, "本地": 2, "py_douban": 3}
    kept.sort(key=lambda site: (
        0 if site.get("key") in system_keys else 1,
        system_keys.get(site.get("key"), 99),
        priority.get(site["_verdict"], 9),
        site["_original_index"],
    ))

    counts = Counter(site["name"] for site in kept)
    seen = Counter()
    for site in kept:
        name = site["name"]
        if counts[name] > 1:
            seen[name] += 1
            site["name"] = f"{name}（线路{seen[name]}）"
        site.pop("_original_index", None)
        site.pop("_verdict", None)

    config["sites"] = kept
    config = to_jsdelivr(config)
    rendered = json.dumps(config, ensure_ascii=False, indent=2) + "\n"
    args.output.write_text(rendered, encoding="utf-8")
    args.asset_output.write_text(rendered, encoding="utf-8")
    args.name_map.write_text(json.dumps(mapping, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "sites_before": len(health["sites"]),
        "sites_after": len(kept),
        "removed": len(health["sites"]) - len(kept),
        "renamed": sum(1 for item in mapping if item["new"] and item["old"] != item["new"]),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
