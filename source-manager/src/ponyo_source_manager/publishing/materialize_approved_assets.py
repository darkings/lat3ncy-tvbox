#!/usr/bin/env python3
"""Materialize approved immutable dependency assets without executing them."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from ponyo_source_manager.core import net
from ponyo_source_manager.core.common import DATA_DIR

MAX_GITHUB_BLOB_RESPONSE = 48 * 1024 * 1024
# 无代理环境下 api.github.com 下载 2.5MB jar 的 base64 blob 实测需 ~111s
# （2026-08-01），30s 超时会导致 materialize 整批失败。
GITHUB_BLOB_TIMEOUT = 180.0


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json_with_retry(fetch_text, url: str) -> dict:
    last_error: Exception | None = None
    for _attempt in range(3):
        try:
            return json.loads(
                fetch_text(
                    url,
                    timeout=GITHUB_BLOB_TIMEOUT,
                    max_bytes=MAX_GITHUB_BLOB_RESPONSE,
                )
            )
        except Exception as exc:  # pragma: no cover - exercised by integration
            last_error = exc
    raise RuntimeError(
        "GitHub blob API failed after 3 attempts: "
        f"{type(last_error).__name__}: {str(last_error)[:160]}"
    ) from last_error


def _fetch_immutable_blob(fetch_text, repo: str, blob_sha: str) -> bytes:
    payload = _load_json_with_retry(
        fetch_text,
        f"https://api.github.com/repos/{repo}/git/blobs/{blob_sha}",
    )
    if payload.get("encoding") != "base64" or not payload.get("content"):
        raise RuntimeError("GitHub blob response did not contain base64 content")
    try:
        return base64.b64decode(payload["content"], validate=False)
    except Exception as exc:
        raise RuntimeError("GitHub blob base64 content is invalid") from exc


def materialize_approved_assets(
    db_path: str | Path,
    output_dir: str | Path,
    *,
    fetch_text=net.fetch_text,
    now: str | None = None,
) -> dict:
    """Write only currently approved JAR blobs whose bytes match the approved SHA."""
    now = now or _now_iso()
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    approvals = con.execute(
        "SELECT content_sha256,upstream_repo,git_blob_sha,expires_at "
        "FROM dependency_asset_approval "
        "WHERE asset_type='jar' AND status='approved' "
        "AND expires_at IS NOT NULL AND expires_at>? "
        "AND git_blob_sha IS NOT NULL",
        (now,),
    ).fetchall()
    con.close()

    materialized: list[dict] = []
    failures: list[dict] = []
    for approval in approvals:
        sha256 = approval["content_sha256"].lower()
        target = output / f"{sha256}.jar"
        try:
            if target.is_file():
                existing = target.read_bytes()
                if hashlib.sha256(existing).hexdigest() == sha256:
                    materialized.append(
                        {"sha256": sha256, "size": len(existing), "cached": True}
                    )
                    continue

            blob = _fetch_immutable_blob(
                fetch_text,
                approval["upstream_repo"],
                approval["git_blob_sha"],
            )
            actual_sha256 = hashlib.sha256(blob).hexdigest()
            if actual_sha256 != sha256:
                raise RuntimeError(
                    f"approved SHA mismatch: expected={sha256} actual={actual_sha256}"
                )
            temporary = output / f".{sha256}.tmp"
            temporary.write_bytes(blob)
            temporary.replace(target)
            materialized.append({"sha256": sha256, "size": len(blob), "cached": False})
        except Exception as exc:
            failures.append(
                {
                    "sha256": sha256,
                    "error": f"{type(exc).__name__}: {str(exc)[:240]}",
                }
            )

    manifest = {
        "generated_at": now,
        "approved": len(approvals),
        "materialized": materialized,
        "failures": failures,
    }
    manifest_path = output / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="缓存已批准的固定SHA依赖资产")
    parser.add_argument("--db", default=str(DATA_DIR / "sources.db"))
    parser.add_argument(
        "--output",
        default=str(DATA_DIR / "approved-assets" / "jar"),
    )
    args = parser.parse_args()
    result = materialize_approved_assets(args.db, args.output)
    print(json.dumps(result, ensure_ascii=False))
    if result["failures"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
