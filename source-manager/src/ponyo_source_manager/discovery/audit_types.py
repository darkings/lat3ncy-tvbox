#!/usr/bin/env python3
"""Read-only runtime/content type audit for collected TVBox sources.

The audit deliberately does not promote, deny, score, or probe a source.  Its
job is to separate entries that the current drpy2/drpyS pipeline can execute
from sources that require path resolution or a different runtime adapter.
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlsplit

from ponyo_source_manager.core.common import DATA_DIR, REPORT_DIR
from ponyo_source_manager.discovery.path_resolver import (
    is_relative_asset,
    resolve_source_assets,
)


HTTP_RE = re.compile(r"^https?://", re.I)
MACCMS_RE = re.compile(
    r"(?:api\.php/)?provide/vod|api\.php/provide|/vod\?ac=|/cjapi/[^?#]*/vod/",
    re.I,
)
DRPYS_RE = re.compile(r"https?://(?:127\.0\.0\.1|localhost)(?::5757)?/api/", re.I)
CATVOD_RE = re.compile(r"https?://(?:127\.0\.0\.1|localhost)(?::5757)?/cat/", re.I)

LIVE_WORDS = ("直播", "live", "电视台", "电视代理", "卫视", "cctv", "虎牙", "斗鱼")
CHILDREN_WORDS = ("儿童", "少儿", "幼儿", "宝宝", "亲子", "早教", "启蒙", "童话")
CLOUD_WORDS = (
    "网盘", "云盘", "夸克", "阿里盘", "阿里云", "uc盘", "百度盘", "天翼盘",
    "迅雷盘", "盘搜", "盘搜索", "push", "wogg", "wogg", "alist", "webdav",
    "[盘]", "┃盘", "(盘)",
)
LOCAL_WORDS = ("本地", "localfile", "csp_local")
SETTINGS_WORDS = ("配置中心", "设置中心", "csp_config")
TOOL_WORDS = ("工具", "市场", "配置接口", "请勿相信", "完全免费", "免责声明")
TOOL_APIS = {
    "csp_config", "csp_localfile", "csp_local", "csp_market", "csp_push",
    "csp_firstaid", "csp_firstaidguard",
}


def _json(value: Any, fallback: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    if not isinstance(value, str) or not value.strip():
        return fallback
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return fallback


def _strings(value: Any, prefix: str) -> Iterable[tuple[str, str]]:
    if isinstance(value, str):
        yield prefix, value.strip()
    elif isinstance(value, dict):
        for key, item in value.items():
            yield from _strings(item, f"{prefix}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _strings(item, f"{prefix}[{index}]")


def _primary_runtime(tags: list[str]) -> str:
    priority = (
        "tool", "live", "python", "catvod", "drpys", "drpy2", "maccms",
        "xbpq", "jar_csp", "unknown",
    )
    return next((name for name in priority if name in tags), "unknown")


def audit_source(row: dict[str, Any]) -> dict[str, Any]:
    """Classify one raw_source row without network or database mutation."""
    raw = _json(row.get("raw_json"), {})
    api = str(row.get("api") or raw.get("api") or "").strip()
    ext = _json(row.get("ext"), row.get("ext"))
    if ext in (None, ""):
        ext = raw.get("ext")
    jar = raw.get("jar")
    name = str(row.get("name") or raw.get("name") or "")
    site_key = str(row.get("site_key") or raw.get("key") or "")
    blob = " ".join((name, site_key, api, json.dumps(ext, ensure_ascii=False, default=str))).lower()
    api_lower = api.lower()

    roles: list[str] = []
    if any(word in blob for word in LIVE_WORDS) or "lives" in raw:
        roles.append("live")
    if any(word in blob for word in CHILDREN_WORDS):
        roles.append("children")
    if any(word in blob for word in CLOUD_WORDS) or re.search(r"csp_(?:pan|wogg|wogg|alist|webdav)", api, re.I):
        roles.append("cloud_drive")
    if any(word in blob for word in LOCAL_WORDS):
        roles.append("local")
    if any(word in blob for word in SETTINGS_WORDS):
        roles.append("settings")
    if api_lower in TOOL_APIS or any(word in blob for word in TOOL_WORDS):
        roles.append("tool")
    if not roles or roles == ["children"]:
        roles.insert(0, "vod")

    tags: list[str] = []
    if "tool" in roles or "settings" in roles or "local" in roles:
        tags.append("tool")
    if "live" in roles:
        tags.append("live")
    if DRPYS_RE.search(api):
        tags.append("drpys")
    if CATVOD_RE.search(api) or site_key.lower().startswith("catvod_") or "(cat)" in name.lower():
        tags.append("catvod")
    if "drpy2" in api_lower or site_key.lower().startswith("drpy_js_") or (
        api_lower.endswith(".js") and any(value.lower().endswith(".js") for _, value in _strings(ext, "ext"))
    ):
        tags.append("drpy2")
    if MACCMS_RE.search(api):
        tags.append("maccms")
    if api_lower == "csp_xbpq" or "csp_xbpq" in blob:
        tags.append("xbpq")
    if api_lower.endswith(".py") or ".py?" in api_lower or api_lower.startswith("py_") or site_key.lower().startswith("py_"):
        tags.extend(("python", "catvod"))
    if (api_lower.startswith("csp_") and "xbpq" not in tags) or jar:
        tags.append("jar_csp")
    if not tags:
        tags.append("unknown")
    tags = list(dict.fromkeys(tags))

    dependencies = [("api", api), *list(_strings(ext, "ext")), *list(_strings(jar, "jar"))]
    original_relative_fields = sorted({field for field, value in dependencies if is_relative_asset(value)})
    resolution = resolve_source_assets(str(row.get("origin") or ""), api, ext, jar)
    relative_fields = resolution["unresolved_fields"]
    local_fields = sorted({
        field for field, value in dependencies
        if value.startswith(("file://", "/"))
        or (HTTP_RE.match(value) and (urlsplit(value).hostname or "").lower() in {"127.0.0.1", "localhost"})
    })
    if relative_fields:
        path_state = "relative_unresolved"
    elif original_relative_fields:
        resolved_values = [
            r["resolved"] for r in resolution["records"]
            if r["status"] == "resolved" and r["resolved"]
        ]
        if any((urlsplit(value).hostname or "").lower() in {"127.0.0.1", "localhost"} for value in resolved_values):
            path_state = "local_only"
        else:
            path_state = "relative_resolved"
    elif local_fields:
        path_state = "local_only"
    else:
        path_state = "absolute"

    reasons: list[str] = []
    if relative_fields:
        reasons.append("relative dependencies require origin-aware resolution: " + ", ".join(relative_fields))
    elif original_relative_fields:
        reasons.append("relative dependencies resolved from collected origin")
    if local_fields:
        reasons.append("dependencies are reachable only inside the configured runtime: " + ", ".join(local_fields))

    excluded_roles = {"tool", "settings", "local"}
    if excluded_roles.intersection(roles):
        testability = "excluded"
        reasons.append("utility/settings/local entry is outside the remote VOD ranking quota")
    elif path_state == "relative_unresolved":
        testability = "needs_resolution"
    elif "live" in roles:
        testability = "needs_adapter"
        reasons.append("live entry must use the dedicated live-channel probe")
    elif "cloud_drive" in roles:
        testability = "needs_adapter"
        reasons.append("cloud-drive entry is maintained outside the 30-source VOD quota")
    elif "drpys" in tags:
        testability = "testable_now"
    elif "drpy2" in tags:
        testability = "needs_adapter"
        reasons.append("installed Node bridge accepts only drpyS/T4 /api endpoints, not drpy2 script pairs")
    elif "maccms" in tags:
        testability = "needs_adapter"
        reasons.append("standard MacCMS semantics are known but no full-chain MacCMS probe is installed")
    elif any(tag in tags for tag in ("xbpq", "jar_csp", "python", "catvod")):
        testability = "needs_adapter"
        reasons.append("current drpy2/drpyS runner cannot execute this runtime")
    else:
        testability = "needs_adapter"
        reasons.append("runtime could not be mapped to an installed probe adapter")

    true_testable_vod = (
        "vod" in roles
        and not excluded_roles.intersection(roles)
        and "live" not in roles
        and "cloud_drive" not in roles
        and testability == "testable_now"
    )
    return {
        "id": row.get("id"),
        "origin": row.get("origin"),
        "site_key": site_key,
        "name": name,
        "declared_type": row.get("type"),
        "api": api,
        "runtime_type": _primary_runtime(tags),
        "runtime_tags": tags,
        "content_role": roles[0],
        "content_roles": roles,
        "path_state": path_state,
        "resolution_status": resolution["status"],
        "original_relative_fields": original_relative_fields,
        "relative_fields": relative_fields,
        "resolved_fields": resolution["resolved_fields"],
        "resolved_dependencies": resolution["records"],
        "effective_api": resolution["effective_api"],
        "effective_ext": resolution["effective_ext"],
        "effective_jar": resolution["effective_jar"],
        "local_fields": local_fields,
        "testability": testability,
        "true_testable_vod": true_testable_vod,
        "reasons": reasons,
    }


def audit_database(db_path: str | Path) -> dict[str, Any]:
    """Read raw_source using SQLite read-only mode and return a complete audit."""
    db_path = Path(db_path).resolve()
    con = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        rows = [dict(row) for row in con.execute(
            "SELECT id, origin, site_key, name, type, api, ext, raw_json FROM raw_source ORDER BY id"
        )]
    finally:
        con.close()
    entries = [audit_source(row) for row in rows]

    def counts(field: str) -> dict[str, int]:
        return dict(sorted(Counter(str(entry[field]) for entry in entries).items()))

    tag_counts = Counter(tag for entry in entries for tag in entry["runtime_tags"])
    role_counts = Counter(role for entry in entries for role in entry["content_roles"])
    summary = {
        "total": len(entries),
        "runtime_primary": counts("runtime_type"),
        "runtime_tags": dict(sorted(tag_counts.items())),
        "content_roles": dict(sorted(role_counts.items())),
        "path_state": counts("path_state"),
        "testability": counts("testability"),
        "true_testable_vod": sum(bool(entry["true_testable_vod"]) for entry in entries),
    }
    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "database": str(db_path),
        "read_only": True,
        "summary": summary,
        "sources": entries,
    }


def render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]

    def table(title: str, values: dict[str, int]) -> list[str]:
        lines = [f"## {title}", "", "| 分类 | 数量 |", "|---|---:|"]
        lines.extend(f"| `{key}` | {value} |" for key, value in values.items())
        return lines + [""]

    lines = [
        "# Ponyo Source Manager 类型审计", "",
        f"- 生成时间：`{report['generated_at']}`",
        f"- 数据库：`{report['database']}`",
        f"- 审计总数：**{summary['total']}**",
        f"- 真正可由当前能力测试的普通点播源：**{summary['true_testable_vod']}**",
        "- 数据库访问模式：只读；本报告不会修改 `list_state`、评分或探测结果。", "",
    ]
    lines += table("主运行类型", summary["runtime_primary"])
    lines += table("运行类型标签（可重叠）", summary["runtime_tags"])
    lines += table("内容角色（可重叠）", summary["content_roles"])
    lines += table("路径状态", summary["path_state"])
    lines += table("可测试性", summary["testability"])
    lines += [
        "## 逐源明细", "",
        "| ID | 名称 | 主类型 | 类型标签 | 内容角色 | 路径 | 可测试性 | 真正点播 | 原因 |",
        "|---:|---|---|---|---|---|---|:---:|---|",
    ]
    for entry in report["sources"]:
        safe_name = entry["name"].replace("|", "\\|").replace("\n", " ")
        reasons = "; ".join(entry["reasons"]).replace("|", "\\|") or "-"
        lines.append(
            f"| {entry['id']} | {safe_name} | `{entry['runtime_type']}` | "
            f"{', '.join(entry['runtime_tags'])} | {', '.join(entry['content_roles'])} | "
            f"`{entry['path_state']}` | `{entry['testability']}` | "
            f"{'是' if entry['true_testable_vod'] else '否'} | {reasons} |"
        )
    return "\n".join(lines) + "\n"


def write_reports(report: dict[str, Any], json_path: str | Path, md_path: str | Path) -> None:
    json_path, md_path = Path(json_path), Path(md_path)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="只读审计 TVBox 候选源类型")
    parser.add_argument("--db", default=str(DATA_DIR / "sources.db"))
    parser.add_argument("--json", default=str(REPORT_DIR / "source-type-audit.json"))
    parser.add_argument("--markdown", default=str(REPORT_DIR / "source-type-audit.md"))
    args = parser.parse_args()
    report = audit_database(args.db)
    write_reports(report, args.json, args.markdown)
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
