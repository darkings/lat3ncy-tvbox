#!/usr/bin/env python3
"""统一分类字典与归一化：单一真相源，取代散落在各模块的分类规则。

分类流程：
1. 成人/无效黑名单直接剔除；
2. 站点白名单（按 host）优先；
3. 别名/关键词按优先级映射到标准分类；
4. 去重并按字典顺序输出，未识别名称进入 unmapped 供审计。
"""
from __future__ import annotations

import json
import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ponyo_source_manager.core.common import CONFIG_DIR

DEFAULT_TAXONOMY_PATH = CONFIG_DIR / "categories.json"
DEFAULT_WHITELIST_PATH = CONFIG_DIR / "category-host-whitelist.json"


@dataclass
class CategoryResult:
    categories: list[str] = field(default_factory=list)
    unmapped: list[str] = field(default_factory=list)
    denied: list[str] = field(default_factory=list)


def load_taxonomy(path: str | Path | None = None) -> dict[str, Any]:
    p = Path(path) if path else DEFAULT_TAXONOMY_PATH
    return json.loads(p.read_text(encoding="utf-8"))


def load_host_whitelist(path: str | Path | None = None) -> dict[str, list[str]]:
    p = Path(path) if path else DEFAULT_WHITELIST_PATH
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def _deny_tokens(taxonomy: dict[str, Any]) -> list[str]:
    return [str(k) for k in taxonomy.get("adult_deny", [])]


def _match_entries(taxonomy: dict[str, Any]) -> list[tuple[str, list[str]]]:
    return [
        (str(c["name"]), [str(k) for k in c.get("match", [])])
        for c in taxonomy.get("categories", [])
        if isinstance(c, dict)
    ]


def normalize_category_name(
    name: str, taxonomy: dict[str, Any]
) -> str | None:
    """单个原始分类名 → 标准分类；成人/无效返回 None，未识别返回 ''。"""
    n = (name or "").strip()
    if not n:
        return ""
    lowered = n.lower()
    if any(k.lower() in lowered for k in _deny_tokens(taxonomy)):
        return None
    for canonical, tokens in _match_entries(taxonomy):
        if any(t.lower() in lowered for t in tokens):
            return canonical
    return ""


def is_top_name(name: str, taxonomy: dict[str, Any]) -> bool:
    """无 type_pid 时判断一个分类名是否是顶级（连续剧等同义词也算顶级）。"""
    n = (name or "").strip()
    return n in {str(k) for k in taxonomy.get("top_synonyms", [])}


def raw_signature(raw: list[Any]) -> str:
    """原始分类列表的稳定签名，用于缓存失效和漂移检测。"""
    names = []
    for item in raw:
        if isinstance(item, dict):
            names.append(str(item.get("type_name", "") or "").strip())
        elif isinstance(item, str):
            names.append(item.strip())
    return hashlib.sha256("\n".join(sorted(names)).encode("utf-8")).hexdigest()


def normalize_categories(
    raw: list[Any],
    taxonomy: dict[str, Any] | None = None,
    *,
    host: str | None = None,
    host_whitelist: dict[str, list[str]] | None = None,
) -> CategoryResult:
    """原始分类列表 → 标准分类。host 命中白名单时优先使用白名单。"""
    tx = taxonomy or load_taxonomy()
    whitelist = host_whitelist if host_whitelist is not None else load_host_whitelist()
    if host:
        h = host.lower().removeprefix("www.")
        for key, names in whitelist.items():
            if h.endswith(key):
                raw = list(names)
                break

    order = [c["name"] for c in tx.get("categories", [])]
    found: list[str] = []
    unmapped: list[str] = []
    denied: list[str] = []
    for item in raw:
        if not isinstance(item, (str, dict)):
            continue
        name = (
            str(item.get("type_name", "") or "")
            if isinstance(item, dict)
            else str(item)
        ).strip()
        if not name:
            continue
        canonical = normalize_category_name(name, tx)
        if canonical is None:
            denied.append(name)
        elif canonical:
            if canonical not in found:
                found.append(canonical)
        elif name not in unmapped:
            unmapped.append(name)

    found.sort(key=lambda c: order.index(c) if c in order else len(order))
    return CategoryResult(categories=found, unmapped=unmapped, denied=denied)


def classify_title(title: str, taxonomy: dict[str, Any] | None = None) -> str:
    """内容抽样推断：标题 → 标准分类，无法判断返回空串。"""
    tx = taxonomy or load_taxonomy()
    text = (title or "").lower()
    if not text:
        return ""
    heuristics = [
        ("电视剧", ("第", "集", "更新", "季")),
        ("电影", ("电影", "大电影", "剧场版")),
        ("动漫", ("动漫", "动画", "番剧")),
        ("综艺", ("综艺", "真人秀", "演唱会")),
        ("纪录片", ("纪录片", "纪实", "探索")),
        ("少儿", ("少儿", "亲子", "儿歌", "动画片")),
        ("短剧", ("短剧", "漫剧")),
        ("体育", ("世界杯", "足球", "篮球", "比赛")),
    ]
    for canonical, words in heuristics:
        if any(w in text for w in words):
            return canonical
    return ""


DEFAULT_SITE_OVERRIDES_PATH = CONFIG_DIR / "site-category-overrides.json"

# 腾讯 / 优酷 / 芒果 / 爱奇艺 四个官源。本地 drpyS 无法 ac=list 探测，
# 生成器只会注入电影/电视剧/综艺/动漫；纪录片必须每次生成都补上。
OFFICIAL_PLATFORM_SITE_KEYS: tuple[str, ...] = (
    "drpyS_腾云驾雾[官]",
    "drpyS_优酷[官]",
    "drpyS_百忙无果[官]",
    "drpyS_奇珍异兽[官]",
)
OFFICIAL_BASE_CATEGORIES: tuple[str, ...] = ("电影", "电视剧", "综艺", "动漫")
OFFICIAL_REQUIRED_CATEGORIES: tuple[str, ...] = ("少儿", "纪录片")


def load_site_category_overrides(
    path: str | Path | None = None,
) -> dict[str, Any]:
    """读取站点级分类覆盖配置（config/site-category-overrides.json）。

    结构:
      {
        "add": {"<site key>": ["少儿", "纪录片", ...]},  # 在现有分类后追加（去重）
        "set": {"<site key>": ["电影", ...]}             # 整体替换
      }
    """
    p = Path(path) if path else DEFAULT_SITE_OVERRIDES_PATH
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def apply_site_category_overrides(
    vod_sites: list[dict[str, Any]],
    path: str | Path | None = None,
) -> int:
    """按站点 key 应用分类覆盖，返回发生变更的站点数。

    覆盖在所有检测/缓存回退完成之后执行，
    保证官源等无法通过 ac=list 检测的源也能带上指定分类。
    """
    overrides = load_site_category_overrides(path)
    add_map = overrides.get("add") or {}
    set_map = overrides.get("set") or {}
    if not isinstance(add_map, dict) or not isinstance(set_map, dict):
        return 0
    if not add_map and not set_map:
        return 0
    changed = 0
    for s in vod_sites:
        key = str(s.get("key") or "")
        if not key:
            continue
        if key in set_map:
            cats = [str(c) for c in set_map[key] if str(c).strip()]
            s["categories"] = cats
            s["category_provenance"] = "site_override"
            changed += 1
            continue
        if key in add_map:
            cats = list(s.get("categories") or [])
            for c in add_map[key]:
                c = str(c).strip()
                if c and c not in cats:
                    cats.append(c)
            s["categories"] = cats
            prov = str(s.get("category_provenance") or "detected")
            s["category_provenance"] = prov + "+site_override"
            changed += 1
    return changed


def ensure_official_platform_categories(
    vod_sites: list[dict[str, Any]],
) -> int:
    """每次生成都保证四个官源带上基础四类 + 少儿、纪录片。

    覆盖文件缺失、旧版默认四类、categories 为空时都会补齐。
    已有分类只追加缺失项，不覆盖探测结果。
    """
    changed = 0
    required = OFFICIAL_BASE_CATEGORIES + OFFICIAL_REQUIRED_CATEGORIES
    for s in vod_sites:
        key = str(s.get("key") or "")
        if key not in OFFICIAL_PLATFORM_SITE_KEYS:
            continue
        before = [str(c).strip() for c in (s.get("categories") or []) if str(c).strip()]
        cats = list(before) if before else list(OFFICIAL_BASE_CATEGORIES)
        for name in required:
            if name not in cats:
                cats.append(name)
        if cats == before:
            continue
        s["categories"] = cats
        prov = str(s.get("category_provenance") or "")
        if "official_required" not in prov:
            s["category_provenance"] = (
                f"{prov}+official_required" if prov else "official_required"
            )
        changed += 1
    return changed
