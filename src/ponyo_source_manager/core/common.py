#!/usr/bin/env python3
"""Ponyo 源管理 - 去重指纹、分类与无代理断言（纯函数，标准库 only）。

去重原语内联自 tools/subscription_audit.py，保持 source-manager/ 自包含。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import socket
import sys
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit, quote

_curr = Path(__file__).resolve()
_default_root = _curr.parent.parent
for _p in _curr.parents:
    if (_p / "pyproject.toml").exists():
        _default_root = _p
        break

PONYO_ROOT = Path(os.environ.get("PONYO_ROOT", _default_root)).resolve()
CODE_DIR = Path(os.environ.get("CODE_DIR", _curr.parent.parent)).resolve()
CONFIG_DIR = Path(os.environ.get("CONFIG_DIR", PONYO_ROOT / "config")).resolve()
DATA_DIR = Path(os.environ.get("DATA_DIR", PONYO_ROOT / "data")).resolve()
REPORT_DIR = Path(os.environ.get("REPORT_DIR", PONYO_ROOT / "reports")).resolve()
LOG_DIR = Path(os.environ.get("LOG_DIR", PONYO_ROOT / "logs")).resolve()

# 确保目录存在
for _dir in (CONFIG_DIR, DATA_DIR, REPORT_DIR, LOG_DIR):
    _dir.mkdir(parents=True, exist_ok=True)

# 兼容旧变量
PONYO_HOME = PONYO_ROOT

URL_RE = re.compile(r"^https?://", re.I)
URL_FIND_RE = re.compile(r"https?://[^,\s\"']+", re.I)
ASSET_EXTENSIONS = (".json", ".js", ".py", ".txt", ".jar", ".m3u", ".m3u8")
SPIDER_RE = re.compile(r"csp_[A-Za-z0-9_]+")


def strip_md5(url: str) -> str:
    """去除 URL 结尾的 ;md5; 注解。"""
    return re.sub(r";md5;[a-zA-Z0-9]+$", "", url)


def normalize_url(url: str) -> str:
    """标准化 URL。"""
    url = url.strip()
    if not url.startswith("http"):
        return url
    url = strip_md5(url)
    if url.endswith("/"):
        url = url[:-1]
    return url


def iri_to_uri(url: str) -> str:
    parts = urlsplit(url)
    host = parts.hostname.encode("idna").decode("ascii") if parts.hostname else ""
    if parts.port:
        host = f"{host}:{parts.port}"
    return urlunsplit(
        (parts.scheme, host, quote(parts.path, safe="/%:@+~!$&'()*;,=-._"),
         quote(parts.query, safe="=&?/:@+~!$'()*;,%-._{}"), "")
    )


def collect_urls(value, location="root", out=None):
    if out is None:
        out = {}
    if isinstance(value, dict):
        for key, item in value.items():
            collect_urls(item, f"{location}.{key}", out)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            collect_urls(item, f"{location}[{index}]", out)
    elif isinstance(value, str):
        for candidate in URL_FIND_RE.findall(strip_md5(value.strip())):
            out.setdefault(candidate, set()).add(location)
    return out


def is_critical_asset(url: str) -> bool:
    path = urlsplit(strip_md5(url)).path.lower()
    return path.endswith(ASSET_EXTENSIONS) or "raw.githubusercontent.com" in url


def item_required_urls(item: dict) -> list[str]:
    required: list[str] = []
    for field in ("api", "jar"):
        value = item.get(field)
        if isinstance(value, str) and URL_RE.match(strip_md5(value)):
            required.append(strip_md5(value))
    for url in collect_urls(item.get("ext")):
        if is_critical_asset(url):
            required.append(url)
    return sorted(set(required))


def _jar_md5(ext) -> str:
    if isinstance(ext, str) and ";md5;" in ext:
        return ext.split(";md5;", 1)[1].strip().split(";")[0].split()[0]
    return ""


def _spider_class(item: dict) -> str:
    blob = " ".join(str(item.get(k, "")) for k in ("api", "ext"))
    m = SPIDER_RE.search(blob)
    return m.group(0) if m else ""


def compute_fingerprint(site: dict) -> tuple[str, dict]:
    api = site.get("api") or ""
    normalized_api = strip_md5(api) if isinstance(api, str) else ""
    api_host = urlsplit(normalized_api).netloc.lower() if normalized_api else ""
    required = item_required_urls(site)
    jar_md5 = _jar_md5(site.get("ext"))
    spider = _spider_class(site)
    type_id = str(site.get("type", ""))
    
    ext = site.get("ext", "")
    if isinstance(ext, dict):
        def _recursive_sort_and_strip(d):
            if isinstance(d, dict):
                return {k: _recursive_sort_and_strip(v) for k, v in sorted(d.items())}
            elif isinstance(d, list):
                return [_recursive_sort_and_strip(i) for i in d]
            elif isinstance(d, str):
                return strip_md5(d)
            return d
        ext_str = json.dumps(_recursive_sort_and_strip(ext), sort_keys=True, separators=(',', ':'))
    elif isinstance(ext, list):
        ext_str = json.dumps(ext, sort_keys=True, separators=(',', ':'))
    else:
        ext_str = strip_md5(str(ext))
        
    material = "\n".join([type_id, normalized_api, api_host, "".join(required), spider, ext_str])
    fp = hashlib.sha256(material.encode("utf-8")).hexdigest()
    meta = {"api_host": api_host, "required_urls": required,
            "jar_md5": jar_md5, "spider_class": spider}
    return fp, meta


def classify(name: str, policy: dict) -> str:
    text = (name or "").lower()
    cats = policy["categories"]
    for label in policy["category_order"]:
        for kw in cats.get(label, []):
            if kw.lower() in text:
                return label
    return policy["default_category"]


def assert_no_proxy() -> list[str]:
    return [v for v in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY")
            if os.environ.get(v)]
