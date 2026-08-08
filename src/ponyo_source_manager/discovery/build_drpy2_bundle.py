#!/usr/bin/env python3
"""Build a reviewed, immutable drpy2 rule bundle without mutating source state."""

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import re
import shutil
import socket
import tempfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urljoin, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from ponyo_source_manager.core.common import assert_no_proxy

DEFAULT_MAX_BYTES = 512 * 1024
DEFAULT_TIMEOUT = 20

DANGEROUS_PATTERNS = (
    ("node-module", re.compile(r"(?:require\s*\(|from\s+|import\s*\()[\"'](?:node:)?(?:child_process|fs|fs/promises|net|dgram|cluster|worker_threads|vm)[\"']", re.I)),
    ("process-access", re.compile(r"\bprocess\s*\.(?:env|exit|kill|binding|mainModule)\b", re.I)),
    ("runtime-spawn", re.compile(r"\b(?:child_process\s*\.|spawnSync\s*\(|execFileSync\s*\(|execFile\s*\()", re.I)),
    ("alternate-runtime", re.compile(r"\b(?:Deno|Bun)\s*\.", re.I)),
    ("filesystem-url", re.compile(r"\bfile://", re.I)),
    ("private-target", re.compile(r"(?:https?://)?(?:localhost|127(?:\.\d{1,3}){3}|0\.0\.0\.0|169\.254(?:\.\d{1,3}){2}|10(?:\.\d{1,3}){3}|192\.168(?:\.\d{1,3}){2}|172\.(?:1[6-9]|2\d|3[01])(?:\.\d{1,3}){2})(?=[:/\s\"'])", re.I)),
    ("cleartext-secret", re.compile(r"(?i)(?:password|authorization|token)\s*[=:]\s*[\"']?(?:basic\s+)?[A-Za-z0-9._-]{12,}")),
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_public_host(hostname: str) -> bool:
    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)}
    except socket.gaierror:
        return False
    if not addresses:
        return False
    return all(ipaddress.ip_address(address).is_global for address in addresses)


def validate_public_url(url: str) -> str:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("rule URL must be absolute HTTP(S)")
    if parsed.username or parsed.password:
        raise ValueError("rule URL credentials rejected")
    if not _is_public_host(parsed.hostname):
        raise ValueError("rule URL does not resolve exclusively to public addresses")
    return url


def request_url(url: str) -> str:
    """Convert a validated IRI to the ASCII URI form required by urllib."""
    parsed = urlsplit(url)
    host = (parsed.hostname or "").encode("idna").decode("ascii")
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    netloc = host if parsed.port is None else f"{host}:{parsed.port}"
    return urlunsplit((
        parsed.scheme,
        netloc,
        quote(parsed.path, safe="/%:@+~!$&'()*;,=-._"),
        quote(parsed.query, safe="=&?/:@%+~!$'()*;,-._"),
        "",
    ))


class PublicRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        validate_public_url(urljoin(req.full_url, newurl))
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def github_mirror_urls(url: str) -> list[str]:
    """Return reviewed URL-level accelerators for a GitHub Raw URL."""
    parsed = urlsplit(url)
    if parsed.hostname != "raw.githubusercontent.com":
        return []
    parts = parsed.path.lstrip("/").split("/", 3)
    if len(parts) != 4 or not all(parts):
        return []
    owner, repository, revision, asset_path = parts
    return [f"https://cdn.jsdelivr.net/gh/{owner}/{repository}@{revision}/{asset_path}"]


def _fetch_rule_candidate(url: str, *, timeout: int,
                          max_bytes: int) -> dict[str, Any]:
    try:
        validate_public_url(url)
    except ValueError as error:
        return {"success": False, "url": url, "error": f"ValueError: {error}"}
    opener = build_opener(ProxyHandler({}), PublicRedirectHandler())
    request = Request(request_url(url), headers={"User-Agent": "ponyo-source-manager/1.0", "Accept": "text/javascript,text/plain,*/*"})
    try:
        with opener.open(request, timeout=timeout) as response:
            final_url = response.geturl()
            validate_public_url(final_url)
            content = response.read(max_bytes + 1)
            content_type = response.headers.get("Content-Type", "")
            status = getattr(response, "status", 200)
    except (HTTPError, URLError, TimeoutError, OSError, ValueError) as error:
        return {"success": False, "url": url, "error": f"{type(error).__name__}: {error}"}
    if len(content) > max_bytes:
        return {"success": False, "url": url, "error": f"rule exceeds {max_bytes} bytes"}
    if b"\x00" in content:
        return {"success": False, "url": url, "error": "binary NUL byte rejected"}
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        return {"success": False, "url": url, "error": f"invalid UTF-8: {error}"}
    findings = scan_rule_text(text)
    if findings:
        return {"success": False, "url": url, "error": "static security rejection", "findings": findings}
    return {
        "success": True,
        "url": url,
        "final_url": final_url,
        "status_code": status,
        "content_type": content_type,
        "bytes": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
        "content": content,
        "text": text,
    }


def fetch_rule(url: str, *, timeout: int = DEFAULT_TIMEOUT,
               max_bytes: int = DEFAULT_MAX_BYTES) -> dict[str, Any]:
    attempts = []
    mirrors = github_mirror_urls(url)
    candidates = [*mirrors, url] if mirrors else [url]
    for candidate in candidates:
        result = _fetch_rule_candidate(candidate, timeout=timeout, max_bytes=max_bytes)
        if result.get("success"):
            result["url"] = url
            result["fetched_url"] = candidate
            result["accelerated"] = candidate != url
            return result
        if result.get("error") == "static security rejection":
            result["url"] = url
            result["fetched_url"] = candidate
            result["accelerated"] = candidate != url
            return result
        attempts.append({"url": candidate, "error": result.get("error")})
    return {"success": False, "url": url, "error": "all download routes failed", "attempts": attempts}


def scan_rule_text(text: str) -> list[dict[str, Any]]:
    findings = []
    for rule_id, pattern in DANGEROUS_PATTERNS:
        match = pattern.search(text)
        if match:
            evidence = text[max(0, match.start() - 40):match.end() + 80].replace("\n", " ")
            if rule_id == "cleartext-secret":
                evidence = "[redacted secret-like assignment]"
            findings.append({"rule_id": rule_id, "offset": match.start(), "evidence": evidence[:180]})
    return findings


def _eligible_sources(audit: dict, asset_health: dict) -> tuple[list[dict], list[dict]]:
    health = {item["url"]: bool(item.get("success")) for item in asset_health.get("assets", [])}
    eligible, rejected = [], []
    for source in audit.get("sources", []):
        if source.get("runtime_type") != "drpy2":
            continue
        if source.get("content_role") not in {"vod", "children"}:
            continue
        rule_url = source.get("effective_ext")
        dependencies = source.get("resolved_dependencies") or []
        failed_dependencies = []
        for dependency in dependencies:
            dependency_url = dependency.get("resolved")
            if not dependency_url or dependency.get("field") == "api":
                continue
            if health.get(dependency_url, False) or github_mirror_urls(dependency_url):
                continue
            failed_dependencies.append(dependency_url)
        reason = None
        if not isinstance(rule_url, str) or not rule_url.startswith(("http://", "https://")):
            reason = "effective_ext is not an HTTP(S) rule"
        elif not rule_url.lower().split("?", 1)[0].endswith(".js"):
            reason = "effective_ext is not JavaScript"
        elif failed_dependencies:
            reason = "asset health failed: " + ", ".join(failed_dependencies)
        if reason:
            rejected.append({"id": source.get("id"), "name": source.get("name"), "url": rule_url, "reason": reason})
        else:
            eligible.append(source)
    return eligible, rejected


def build_bundle(audit_path: str, asset_health_path: str, output_dir: str, report_path: str,
                 *, timeout: int = DEFAULT_TIMEOUT, max_bytes: int = DEFAULT_MAX_BYTES,
                 workers: int = 6, fetcher=fetch_rule) -> dict[str, Any]:
    if assert_no_proxy():
        raise SystemExit("代理环境变量非空，drpy2 规则包构建中止（需无代理）。")
    audit = json.loads(Path(audit_path).read_text(encoding="utf-8"))
    asset_health = json.loads(Path(asset_health_path).read_text(encoding="utf-8"))
    eligible, rejected = _eligible_sources(audit, asset_health)
    by_url: dict[str, list[dict]] = {}
    for source in eligible:
        by_url.setdefault(source["effective_ext"], []).append(source)

    def download(url: str) -> dict:
        return fetcher(url, timeout=timeout, max_bytes=max_bytes)

    with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        downloaded = list(executor.map(download, sorted(by_url)))

    accepted: list[dict] = []
    for result in downloaded:
        sources = by_url[result["url"]]
        if not result.get("success"):
            rejected.extend({
                "id": source.get("id"), "name": source.get("name"), "url": result["url"],
                "reason": result.get("error"), "findings": result.get("findings", []),
                "attempts": result.get("attempts", []),
            } for source in sources)
            continue
        accepted.append({**result, "sources": sources})

    output = Path(output_dir)
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{output.name}.", dir=output.parent))
    try:
        rules_dir = staging / "rules"
        rules_dir.mkdir()
        registry: dict[str, dict] = {}
        manifest_rules = []
        for item in sorted(accepted, key=lambda value: value["url"]):
            first_id = min(int(source["id"]) for source in item["sources"])
            module = f"r{first_id:04d}-{item['sha256'][:12]}"
            rule_content = item.get("content", item["text"].encode("utf-8"))
            (rules_dir / f"{module}.js").write_bytes(rule_content)
            source_ids = sorted(int(source["id"]) for source in item["sources"])
            registry[item["url"]] = {"module": module, "sha256": item["sha256"], "source_ids": source_ids}
            manifest_rules.append({
                "url": item["url"], "fetched_url": item.get("fetched_url", item["url"]),
                "accelerated": bool(item.get("accelerated")), "final_url": item["final_url"], "module": module,
                "sha256": item["sha256"], "bytes": item["bytes"], "source_ids": source_ids,
                "names": [source.get("name") for source in item["sources"]],
            })
        (staging / "rule-map.json").write_text(
            json.dumps({"schema_version": 1, "generated_at": utc_now(), "rules": registry}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        (staging / "manifest.json").write_text(
            json.dumps({"schema_version": 1, "generated_at": utc_now(), "rules": manifest_rules}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        if output.exists():
            shutil.rmtree(output)
        staging.replace(output)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise

    report = {
        "schema_version": 1,
        "generated_at": utc_now(),
        "read_only": True,
        "summary": {
            "audited_drpy2_sources": sum(source.get("runtime_type") == "drpy2" for source in audit.get("sources", [])),
            "eligible_sources": len(eligible),
            "unique_rule_urls": len(by_url),
            "accepted_rules": len(accepted),
            "accepted_sources": sum(len(item["sources"]) for item in accepted),
            "rejected_sources": len(rejected),
        },
        "rejected": rejected,
    }
    report_file = Path(report_path)
    report_file.parent.mkdir(parents=True, exist_ok=True)
    report_file.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="构建只读审查的 drpy2 规则包")
    parser.add_argument("--audit", default="reports/source-type-audit.json")
    parser.add_argument("--asset-health", default="reports/resolved-asset-health.json")
    parser.add_argument("--output", default="data/drpy2-runtime")
    parser.add_argument("--report", default="reports/drpy2-bundle-report.json")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    parser.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES)
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args()
    report = build_bundle(args.audit, args.asset_health, args.output, args.report,
                          timeout=args.timeout, max_bytes=args.max_bytes, workers=args.workers)
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
