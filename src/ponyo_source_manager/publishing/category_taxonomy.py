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
