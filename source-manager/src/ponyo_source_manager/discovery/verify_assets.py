"""Reachability verification for origin-resolved drpy2 assets (read-only)."""
from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
from urllib.parse import urlsplit

import requests

from ponyo_source_manager.core.common import REPORT_DIR


def collect_assets(type_audit: dict) -> list[dict]:
    """Deduplicate required resolved drpy2 api/ext assets with provenance."""
    assets: dict[str, dict] = {}
    for source in type_audit.get("sources", []):
        roles = set(source.get("content_roles", []))
        if source.get("runtime_type") != "drpy2" or not source.get("resolved_dependencies"):
            continue
        if "vod" not in roles or roles.intersection({"live", "cloud_drive", "tool", "settings", "local"}):
            continue
        for record in source.get("resolved_dependencies", []):
            if record.get("status") != "resolved" or not record.get("resolved"):
                continue
            if not str(record.get("field", "")).startswith(("api", "ext")):
                continue
            url = record["resolved"]
            item = assets.setdefault(url, {"url": url, "sources": [], "fields": []})
            if source["id"] not in item["sources"]:
                item["sources"].append(source["id"])
            if record["field"] not in item["fields"]:
                item["fields"].append(record["field"])
    return sorted(assets.values(), key=lambda item: item["url"])


def fetch_asset(url: str, timeout: float = 12.0) -> dict:
    session = requests.Session()
    session.trust_env = False
    started = time.monotonic()
    try:
        response = session.get(
            url,
            headers={"Range": "bytes=0-4095", "User-Agent": "PonyoSourceManager/1.0"},
            timeout=timeout,
            allow_redirects=True,
            stream=True,
        )
        body = response.raw.read(4096, decode_content=True)
        latency_ms = int((time.monotonic() - started) * 1000)
        content_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
        path = urlsplit(response.url).path.lower()
        looks_html = body.lstrip().lower().startswith((b"<!doctype html", b"<html"))
        ok = response.status_code in {200, 206} and bool(body)
        reason = None
        if response.status_code not in {200, 206}:
            reason = f"http_{response.status_code}"
        elif not body:
            reason = "empty_body"
        elif looks_html and path.endswith((".js", ".json", ".jar", ".py")):
            ok, reason = False, "unexpected_html"
        return {
            "success": bool(ok), "status_code": response.status_code,
            "final_url": response.url, "content_type": content_type,
            "bytes_sampled": len(body), "latency_ms": latency_ms, "error": reason,
        }
    except requests.RequestException as exc:
        return {
            "success": False, "status_code": None, "final_url": None,
            "content_type": "", "bytes_sampled": 0,
            "latency_ms": int((time.monotonic() - started) * 1000),
            "error": str(exc)[:300],
        }
    finally:
        session.close()


def verify_assets(
    type_audit: dict,
    *,
    fetcher: Callable[[str], dict] = fetch_asset,
    workers: int = 12,
) -> dict:
    assets = collect_assets(type_audit)
    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        pending = {executor.submit(fetcher, item["url"]): item for item in assets}
        for future in as_completed(pending):
            item = pending[future]
            try:
                probe = future.result()
            except Exception as exc:  # injected/custom fetcher containment
                probe = {"success": False, "error": str(exc)[:300]}
            results.append({**item, **probe})
    results.sort(key=lambda item: item["url"])
    passed = sum(bool(item.get("success")) for item in results)
    source_pass: dict[int, bool] = {}
    for item in results:
        for source_id in item["sources"]:
            source_pass[source_id] = source_pass.get(source_id, True) and bool(item.get("success"))
    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "read_only": True,
        "summary": {
            "unique_assets": len(results),
            "assets_passed": passed,
            "assets_failed": len(results) - passed,
            "asset_pass_rate": round(passed / len(results), 4) if results else 0.0,
            "sources_with_resolved_assets": len(source_pass),
            "sources_all_assets_reachable": sum(source_pass.values()),
            "failure_reasons": dict(sorted(Counter(
                str(item.get("error") or "unknown") for item in results if not item.get("success")
            ).items())),
        },
        "assets": results,
    }


def render_markdown(report: dict) -> str:
    s = report["summary"]
    lines = [
        "# 已解析 drpy2 资源可达性报告", "",
        f"- 唯一资源：**{s['unique_assets']}**",
        f"- 可达：**{s['assets_passed']}**",
        f"- 不可达：**{s['assets_failed']}**",
        f"- 资源成功率：**{s['asset_pass_rate']:.2%}**",
        f"- 涉及源：**{s['sources_with_resolved_assets']}**",
        f"- 所有已解析资源均可达的源：**{s['sources_all_assets_reachable']}**", "",
        "本报告只读取类型审计结果并发起资源请求，不修改候选、评分或发布状态。", "",
        "| URL | 状态 | HTTP | 延迟(ms) | 来源ID | 错误 |", "|---|:---:|---:|---:|---|---|",
    ]
    for item in report["assets"]:
        url = item["url"].replace("|", "%7C")
        error = str(item.get("error") or "-").replace("|", "\\|")
        lines.append(
            f"| {url} | {'通过' if item.get('success') else '失败'} | "
            f"{item.get('status_code') or '-'} | {item.get('latency_ms', '-')} | "
            f"{', '.join(map(str, item['sources']))} | {error} |"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="验证类型审计中已解析的 drpy2 资源")
    parser.add_argument("--audit", default=str(REPORT_DIR / "source-type-audit.json"))
    parser.add_argument("--json", default=str(REPORT_DIR / "resolved-asset-health.json"))
    parser.add_argument("--markdown", default=str(REPORT_DIR / "resolved-asset-health.md"))
    parser.add_argument("--workers", type=int, default=12)
    args = parser.parse_args()
    audit = json.loads(Path(args.audit).read_text(encoding="utf-8"))
    report = verify_assets(audit, workers=args.workers)
    json_path, md_path = Path(args.json), Path(args.markdown)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
