"""Deterministic, origin-aware resolution of TVBox relative asset paths.

This module is intentionally pure: it constructs effective URLs for audit and
probing but never rewrites a collected source or its list_state row.
"""
from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit


HTTP_RE = re.compile(r"^https?://", re.I)
RELATIVE_RE = re.compile(r"^(?:\.{1,2}/|libs?/|js/|py/|jar/|json/)", re.I)
ASSET_SUFFIXES = (".js", ".py", ".jar", ".json", ".txt", ".m3u", ".m3u8")
LOCAL_HOSTS = {"127.0.0.1", "localhost"}
MD5_MARKER_RE = re.compile(r";md5;([^;\s]+)", re.I)


def is_relative_asset(value: str) -> bool:
    value = value.strip()
    if not value or HTTP_RE.match(value) or value.startswith(("csp_", "file://")):
        return False
    # Scheme-relative URLs are not source-relative and must never inherit the
    # trusted origin implicitly.
    if value.startswith("//"):
        return True
    path = value.split("?", 1)[0].lower()
    return bool(RELATIVE_RE.match(value)) or path.endswith(ASSET_SUFFIXES)


def _inherit_local_auth(origin: str, resolved: str) -> str:
    """Keep local drpyS query credentials on its relative child assets."""
    source, target = urlsplit(origin), urlsplit(resolved)
    if (source.hostname or "").lower() not in LOCAL_HOSTS:
        return resolved
    if (target.hostname or "").lower() != (source.hostname or "").lower():
        return resolved
    source_query = dict(parse_qsl(source.query, keep_blank_values=True))
    target_query = dict(parse_qsl(target.query, keep_blank_values=True))
    if "pwd" in source_query and "pwd" not in target_query:
        target_query["pwd"] = source_query["pwd"]
        return urlunsplit(target._replace(query=urlencode(target_query)))
    return resolved


def resolve_asset_url(origin: str, value: str) -> tuple[str | None, str]:
    """Return ``(effective_url, status)`` for one source-relative asset."""
    value = value.strip()
    if not is_relative_asset(value):
        return value, "not_relative"
    if value.startswith("//"):
        return None, "rejected_scheme_relative"
    base = urlsplit(origin or "")
    if base.scheme not in {"http", "https"} or not base.hostname:
        return None, "invalid_origin"
    resolved = _inherit_local_auth(origin, urljoin(origin, value))
    target = urlsplit(resolved)
    # urljoin on a relative path must stay on the exact source origin.
    if target.scheme != base.scheme or target.netloc != base.netloc:
        return None, "origin_escape_rejected"
    return resolved, "resolved"


def _resolve_value(origin: str, value: Any, field: str, records: list[dict]) -> Any:
    if isinstance(value, str):
        if not is_relative_asset(value):
            return value
        resolved, status = resolve_asset_url(origin, value)
        records.append({
            "field": field, "original": value, "resolved": resolved, "status": status,
        })
        return resolved if resolved is not None else value
    if isinstance(value, dict):
        return {
            key: _resolve_value(origin, item, f"{field}.{key}", records)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [
            _resolve_value(origin, item, f"{field}[{index}]", records)
            for index, item in enumerate(value)
        ]
    return value


def resolve_source_assets(origin: str, api: Any, ext: Any, jar: Any) -> dict:
    records: list[dict] = []
    effective_api = _resolve_value(origin, api, "api", records)
    effective_ext = _resolve_value(origin, ext, "ext", records)
    effective_jar = _resolve_value(origin, jar, "jar", records)
    unresolved = sorted({r["field"] for r in records if r["status"] != "resolved"})
    resolved = sorted({r["field"] for r in records if r["status"] == "resolved"})
    if not records:
        status = "not_required"
    elif unresolved:
        status = "partial" if resolved else "unresolved"
    else:
        status = "resolved"
    return {
        "status": status,
        "records": records,
        "resolved_fields": resolved,
        "unresolved_fields": unresolved,
        "effective_api": effective_api,
        "effective_ext": effective_ext,
        "effective_jar": effective_jar,
    }


def _strip_md5_marker(value: str) -> str:
    match = re.search(r";md5;", value, flags=re.I)
    return value[:match.start()].strip() if match else value.strip()


def _declared_md5(value: str) -> str:
    match = MD5_MARKER_RE.search(value)
    return match.group(1).strip().lower() if match else ""


def _iter_dependency_strings(value: Any, field: str):
    if isinstance(value, dict):
        for key, item in value.items():
            yield from _iter_dependency_strings(item, f"{field}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _iter_dependency_strings(item, f"{field}[{index}]")
    elif isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith(("{", "[")):
            try:
                parsed = json.loads(stripped)
            except json.JSONDecodeError:
                parsed = None
            if parsed is not None:
                yield from _iter_dependency_strings(parsed, field)
                return
        yield field, stripped


def _asset_type(value: str) -> str | None:
    path = urlsplit(_strip_md5_marker(value)).path.lower()
    for suffix in ASSET_SUFFIXES:
        if path.endswith(suffix):
            return suffix.lstrip(".")
    return None


def collect_dependency_assets(
    origin: str,
    site: dict[str, Any],
    config_root: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Resolve executable/config assets without executing or rewriting a site.

    TVBox commonly declares one root-level ``spider`` JAR shared by every site.
    Keeping that inheritance as explicit evidence prevents it being lost when
    only entries from ``sites`` are normalized.
    """
    config_root = config_root if isinstance(config_root, dict) else {}
    values = (
        ("config.spider", config_root.get("spider"), True),
        ("config.jar", config_root.get("jar"), True),
        ("site.jar", site.get("jar"), False),
        ("site.ext", site.get("ext"), False),
        ("site.api", site.get("api"), False),
    )
    records: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for base_field, value, inherited in values:
        for field, original in _iter_dependency_strings(value, base_field):
            asset_type = _asset_type(original)
            if not asset_type:
                continue
            clean_value = _strip_md5_marker(original)
            if is_relative_asset(clean_value):
                effective, status = resolve_asset_url(origin, clean_value)
            elif HTTP_RE.match(clean_value):
                effective, status = clean_value, "absolute"
            elif clean_value.startswith("file://"):
                effective, status = None, "local_only"
            else:
                effective, status = None, "unresolved"
            key = (field, effective or clean_value, asset_type)
            if key in seen:
                continue
            seen.add(key)
            records.append({
                "source_field": field,
                "effective_url": effective or "",
                "asset_type": asset_type,
                "declared_md5": _declared_md5(original) if asset_type == "jar" else "",
                "resolution_status": status,
                "inherited_from_root": bool(inherited),
            })
    return records
