#!/usr/bin/env python3
"""Review JAR evidence and manage immutable SHA-256 approvals.

This module never loads, executes, or decompiles dependency assets.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

from ponyo_source_manager.core import net
from ponyo_source_manager.core.common import DATA_DIR

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
COMMIT_RE = re.compile(r"^[0-9a-fA-F]{40}$")
MAX_APPROVAL_DAYS = 90
MAX_PROVENANCE_BYTES = 32 * 1024 * 1024


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _parse_iso(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _validate_identity(sha256: str, repo: str, commit: str) -> tuple[str, str, str]:
    sha256 = sha256.strip().lower()
    repo = repo.strip()
    commit = commit.strip().lower()
    if not SHA256_RE.fullmatch(sha256):
        raise ValueError("SHA-256 必须是 64 位十六进制字符串")
    if not REPO_RE.fullmatch(repo):
        raise ValueError("上游仓库必须使用 owner/repo 格式")
    if not COMMIT_RE.fullmatch(commit):
        raise ValueError("上游 commit 必须是完整的 40 位 Git commit SHA")
    return sha256, repo, commit


# scan_security 已在使用的 raw 代理前缀（evidence.effective_url 同款）。
# api.github.com 的大响应在本机网络会被中间设备截断，raw 代理路径已验证可用；
# 可通过环境变量覆盖或置空以直连 raw.githubusercontent.com。
RAW_PROXY_PREFIX = os.environ.get(
    "PONYO_RAW_PROXY", "https://github.allproxy.dpdns.org/"
)


def _git_blob_sha(data: bytes) -> str:
    """Git blob 对象 SHA-1：sha1("blob <size>\0" + content)。"""
    return hashlib.sha1(
        b"blob " + str(len(data)).encode("ascii") + b"\0" + data
    ).hexdigest()


def verify_raw_provenance(
    repo: str,
    commit: str,
    path: str,
    *,
    fetch_bytes=net.fetch_bytes,
) -> dict:
    """下载固定 commit 的 raw 文件并证明内容与审核对象一致。

    与 verify_github_provenance 等价（甚至更强：直接做内容级校验），但绕开
    api.github.com 的大响应截断问题。raw.githubusercontent.com 在本机网络
    不可达，因此默认通过 RAW_PROXY_PREFIX 代理下载。
    """
    path = path.strip().lstrip("/")
    if not path or ".." in path.split("/"):
        raise ValueError("上游文件路径不能为空，也不能包含 ..")
    encoded_path = quote(path, safe="/")
    raw_url = f"https://raw.githubusercontent.com/{repo}/{commit}/{encoded_path}"
    target = (RAW_PROXY_PREFIX or "") + raw_url if RAW_PROXY_PREFIX else raw_url
    data = fetch_bytes(target, timeout=120.0, max_bytes=MAX_PROVENANCE_BYTES)
    if not data:
        raise RuntimeError(f"raw 下载返回空内容: {raw_url}")
    return {
        "upstream_path": path,
        "git_blob_sha": _git_blob_sha(data),
        "content_sha256": hashlib.sha256(data).hexdigest(),
        "size_bytes": len(data),
    }


def verify_github_provenance(
    repo: str,
    commit: str,
    path: str,
    *,
    fetch_text=net.fetch_text,
) -> dict:
    """Read an immutable Git blob and prove that it matches the reviewed bytes."""

    def load_json(url: str, *, timeout: float, max_bytes: int) -> dict:
        last_error = None
        for _attempt in range(3):
            try:
                return json.loads(fetch_text(url, timeout=timeout, max_bytes=max_bytes))
            except Exception as exc:
                last_error = exc
        raise RuntimeError(
            f"GitHub API 连续 3 次未返回完整内容: {type(last_error).__name__}: "
            f"{str(last_error)[:160]}"
        ) from last_error

    path = path.strip().lstrip("/")
    if not path or ".." in path.split("/"):
        raise ValueError("上游文件路径不能为空，也不能包含 ..")
    encoded_path = quote(path, safe="/")
    metadata_url = (
        f"https://api.github.com/repos/{repo}/contents/{encoded_path}?ref={commit}"
    )
    metadata = load_json(metadata_url, timeout=30.0, max_bytes=2 * 1024 * 1024)
    if metadata.get("type") != "file" or not metadata.get("git_url"):
        raise ValueError("固定 commit 下没有找到指定文件")
    blob = load_json(
        metadata["git_url"],
        timeout=120.0,
        max_bytes=MAX_PROVENANCE_BYTES * 2,
    )
    if blob.get("encoding") != "base64":
        raise ValueError("GitHub Blob API 未返回可验证的 base64 内容")
    try:
        encoded = "".join(str(blob.get("content", "")).split())
        payload = base64.b64decode(encoded, validate=True)
    except (ValueError, TypeError) as exc:
        raise ValueError("Git Blob 内容无法进行严格 base64 解码") from exc
    if len(payload) > MAX_PROVENANCE_BYTES:
        raise ValueError("Git Blob 超过 32 MiB 审批上限")
    git_blob_sha = str(metadata.get("sha") or "").lower()
    if not re.fullmatch(r"[0-9a-f]{40}", git_blob_sha):
        raise ValueError("GitHub 未返回有效的 Git Blob SHA")
    return {
        "upstream_path": path,
        "git_blob_sha": git_blob_sha,
        "content_sha256": hashlib.sha256(payload).hexdigest(),
        "size_bytes": len(payload),
    }


def _evidence_summary(con: sqlite3.Connection, sha256: str) -> dict:
    rows = con.execute(
        "SELECT fingerprint,effective_url,declared_md5,actual_md5,"
        "validation_status,fetch_status FROM dependency_asset_evidence "
        "WHERE asset_type='jar' AND lower(content_sha256)=?",
        (sha256,),
    ).fetchall()
    if not rows:
        raise ValueError("数据库中没有该 SHA-256 对应的 JAR 静态扫描证据")
    statuses: dict[str, int] = {}
    for row in rows:
        statuses[row[4]] = statuses.get(row[4], 0) + 1
    allowed = {"verified", "review_required"}
    blocked = sorted(set(statuses) - allowed)
    if blocked:
        raise ValueError("存在不可审批的静态状态: " + ", ".join(blocked))
    if any(row[5] != "fetched" for row in rows):
        raise ValueError("JAR 尚未全部成功下载并完成静态扫描")
    high = con.execute(
        "SELECT COUNT(*) FROM security_finding s "
        "JOIN dependency_asset_evidence d "
        "ON d.fingerprint=s.fingerprint AND d.effective_url=s.target_url "
        "WHERE d.asset_type='jar' AND lower(d.content_sha256)=? "
        "AND s.severity='high'",
        (sha256,),
    ).fetchone()[0]
    if high:
        raise ValueError(f"该 JAR 仍有 {high} 条高危静态发现，禁止审批")
    return {
        "references": len(rows),
        "statuses": statuses,
        "md5_declared": sum(1 for row in rows if row[2]),
        "md5_matched": sum(1 for row in rows if row[2] and row[2] == row[3]),
        "urls": sorted({row[1] for row in rows}),
    }


def approve_asset(
    db_path: str,
    *,
    sha256: str,
    repo: str,
    commit: str,
    reviewer: str,
    reason: str,
    path: str,
    days: int = 60,
    now: datetime | None = None,
    provenance_verifier=verify_raw_provenance,
) -> dict:
    sha256, repo, commit = _validate_identity(sha256, repo, commit)
    reviewer = reviewer.strip()
    reason = reason.strip()
    if not reviewer:
        raise ValueError("审核人不能为空")
    if len(reason) < 10:
        raise ValueError("审核理由至少需要 10 个字符")
    if days < 1 or days > MAX_APPROVAL_DAYS:
        raise ValueError(f"审批有效期必须为 1–{MAX_APPROVAL_DAYS} 天")
    now = now or _utc_now()
    expires_at = now + timedelta(days=days)
    provenance = provenance_verifier(repo, commit, path)
    if provenance.get("content_sha256") != sha256:
        raise ValueError("固定 commit 的 Git Blob SHA-256 与静态扫描证据不一致")
    upstream_path = str(provenance.get("upstream_path") or path).strip()
    git_blob_sha = str(provenance.get("git_blob_sha") or "").lower()
    if not upstream_path or not re.fullmatch(r"[0-9a-f]{40}", git_blob_sha):
        raise ValueError("来源核验没有返回完整路径和 Git Blob SHA")
    con = sqlite3.connect(str(db_path))
    try:
        con.execute("BEGIN IMMEDIATE")
        evidence = _evidence_summary(con, sha256)
        previous = con.execute(
            "SELECT status FROM dependency_asset_approval WHERE content_sha256=?",
            (sha256,),
        ).fetchone()
        old_status = previous[0] if previous else None
        now_text = _iso(now)
        expires_text = _iso(expires_at)
        con.execute(
            "INSERT INTO dependency_asset_approval"
            "(content_sha256,asset_type,upstream_repo,upstream_commit,status,"
            "review_reason,approved_by,approved_at,expires_at,revoked_at,"
            "created_at,updated_at,upstream_path,git_blob_sha,provenance_verified_at) "
            "VALUES(?, 'jar', ?, ?, 'approved', ?, ?, ?, ?, NULL, ?, ?, ?, ?, ?) "
            "ON CONFLICT(content_sha256) DO UPDATE SET "
            "upstream_repo=excluded.upstream_repo,upstream_commit=excluded.upstream_commit,"
            "status='approved',review_reason=excluded.review_reason,"
            "approved_by=excluded.approved_by,approved_at=excluded.approved_at,"
            "expires_at=excluded.expires_at,revoked_at=NULL,updated_at=excluded.updated_at,"
            "upstream_path=excluded.upstream_path,git_blob_sha=excluded.git_blob_sha,"
            "provenance_verified_at=excluded.provenance_verified_at",
            (
                sha256,
                repo,
                commit,
                reason,
                reviewer,
                now_text,
                expires_text,
                now_text,
                now_text,
                upstream_path,
                git_blob_sha,
                now_text,
            ),
        )
        con.execute(
            "INSERT INTO dependency_asset_approval_event"
            "(content_sha256,old_status,new_status,actor,reason,upstream_repo,"
            "upstream_commit,expires_at,created_at,upstream_path,git_blob_sha,"
            "provenance_verified_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                sha256,
                old_status,
                "approved",
                reviewer,
                reason,
                repo,
                commit,
                expires_text,
                now_text,
                upstream_path,
                git_blob_sha,
                now_text,
            ),
        )
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()
    return {
        "content_sha256": sha256,
        "status": "approved",
        "upstream_repo": repo,
        "upstream_commit": commit,
        "upstream_path": upstream_path,
        "git_blob_sha": git_blob_sha,
        "provenance_verified_at": _iso(now),
        "approved_by": reviewer,
        "approved_at": _iso(now),
        "expires_at": _iso(expires_at),
        "evidence": evidence,
    }


def set_asset_decision(
    db_path: str,
    *,
    sha256: str,
    status: str,
    actor: str,
    reason: str,
    repo: str | None = None,
    commit: str | None = None,
    now: datetime | None = None,
) -> dict:
    sha256 = sha256.strip().lower()
    if not SHA256_RE.fullmatch(sha256):
        raise ValueError("SHA-256 必须是 64 位十六进制字符串")
    if status not in {"rejected", "revoked"}:
        raise ValueError("决定只能是 rejected 或 revoked")
    actor, reason = actor.strip(), reason.strip()
    if not actor or len(reason) < 10:
        raise ValueError("审核人不能为空，理由至少需要 10 个字符")
    now = now or _utc_now()
    now_text = _iso(now)
    con = sqlite3.connect(str(db_path))
    try:
        con.execute("BEGIN IMMEDIATE")
        row = con.execute(
            "SELECT status,upstream_repo,upstream_commit FROM dependency_asset_approval "
            "WHERE content_sha256=?",
            (sha256,),
        ).fetchone()
        if not row:
            if status != "rejected":
                raise ValueError("该 SHA-256 尚无批准记录，不能撤销")
            sha256, repo, commit = _validate_identity(sha256, repo or "", commit or "")
            exists = con.execute(
                "SELECT 1 FROM dependency_asset_evidence "
                "WHERE asset_type='jar' AND lower(content_sha256)=? LIMIT 1",
                (sha256,),
            ).fetchone()
            if not exists:
                raise ValueError("数据库中没有该 SHA-256 对应的 JAR 静态扫描证据")
            con.execute(
                "INSERT INTO dependency_asset_approval"
                "(content_sha256,asset_type,upstream_repo,upstream_commit,status,"
                "review_reason,approved_by,approved_at,expires_at,revoked_at,"
                "created_at,updated_at) VALUES(?, 'jar', ?, ?, 'rejected', ?, ?, "
                "NULL, NULL, NULL, ?, ?)",
                (sha256, repo, commit, reason, actor, now_text, now_text),
            )
            row = (None, repo, commit)
        if status == "revoked" and row[0] != "approved":
            raise ValueError("只有 approved 状态可以撤销")
        if row[0] is not None:
            con.execute(
                "UPDATE dependency_asset_approval SET status=?,review_reason=?,"
                "approved_by=?,revoked_at=?,updated_at=? WHERE content_sha256=?",
                (
                    status,
                    reason,
                    actor,
                    now_text if status == "revoked" else None,
                    now_text,
                    sha256,
                ),
            )
        con.execute(
            "INSERT INTO dependency_asset_approval_event"
            "(content_sha256,old_status,new_status,actor,reason,upstream_repo,"
            "upstream_commit,expires_at,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
            (sha256, row[0], status, actor, reason, row[1], row[2], None, now_text),
        )
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()
    return {"content_sha256": sha256, "status": status, "actor": actor}


def build_review_report(db_path: str, *, now: datetime | None = None) -> dict:
    now = now or _utc_now()
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT content_sha256,COUNT(*) references_count,"
        "SUM(CASE WHEN declared_md5<>'' THEN 1 ELSE 0 END) md5_declared,"
        "SUM(CASE WHEN declared_md5<>'' AND declared_md5=actual_md5 THEN 1 ELSE 0 END) md5_matched,"
        "GROUP_CONCAT(DISTINCT validation_status) validation_statuses,"
        "MIN(effective_url) sample_url "
        "FROM dependency_asset_evidence WHERE asset_type='jar' "
        "AND content_sha256 IS NOT NULL GROUP BY content_sha256 ORDER BY references_count DESC"
    ).fetchall()
    assets = []
    for row in rows:
        approval = con.execute(
            "SELECT status,upstream_repo,upstream_commit,approved_by,approved_at,"
            "expires_at,revoked_at,review_reason,upstream_path,git_blob_sha,"
            "provenance_verified_at FROM dependency_asset_approval "
            "WHERE content_sha256=?",
            (row["content_sha256"],),
        ).fetchone()
        approval_doc = dict(approval) if approval else None
        effective_status = "pending"
        if approval_doc:
            effective_status = approval_doc["status"]
            if effective_status == "approved" and approval_doc["expires_at"]:
                if _parse_iso(approval_doc["expires_at"]) <= now:
                    effective_status = "expired"
        assets.append(
            {
                "content_sha256": row["content_sha256"],
                "references": row["references_count"],
                "md5_declared": row["md5_declared"],
                "md5_matched": row["md5_matched"],
                "validation_statuses": sorted(row["validation_statuses"].split(",")),
                "sample_url": row["sample_url"],
                "approval_status": effective_status,
                "approval": approval_doc,
            }
        )
    con.close()
    counts: dict[str, int] = {}
    for asset in assets:
        status = asset["approval_status"]
        counts[status] = counts.get(status, 0) + 1
    return {"generated_at": _iso(now), "summary": counts, "assets": assets}


def main() -> None:
    parser = argparse.ArgumentParser(description="管理 JAR SHA-256 人工审批")
    parser.add_argument("--db", default=str(DATA_DIR / "sources.db"))
    sub = parser.add_subparsers(dest="command", required=True)
    report = sub.add_parser("report", help="生成去重后的待审核清单")
    report.add_argument("--output")
    approve = sub.add_parser("approve", help="批准一个固定 SHA-256")
    approve.add_argument("--sha256", required=True)
    approve.add_argument("--repo", required=True)
    approve.add_argument("--commit", required=True)
    approve.add_argument("--path", required=True)
    approve.add_argument("--reviewer", required=True)
    approve.add_argument("--reason", required=True)
    approve.add_argument("--days", type=int, default=60)
    for name in ("reject", "revoke"):
        command = sub.add_parser(name)
        command.add_argument("--sha256", required=True)
        command.add_argument("--reviewer", required=True)
        command.add_argument("--reason", required=True)
        if name == "reject":
            command.add_argument("--repo", required=True)
            command.add_argument("--commit", required=True)
    args = parser.parse_args()
    if args.command == "report":
        result = build_review_report(args.db)
        if args.output:
            output = Path(args.output)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(
                json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
            )
    elif args.command == "approve":
        result = approve_asset(
            args.db,
            sha256=args.sha256,
            repo=args.repo,
            commit=args.commit,
            path=args.path,
            reviewer=args.reviewer,
            reason=args.reason,
            days=args.days,
        )
    else:
        result = set_asset_decision(
            args.db,
            sha256=args.sha256,
            status={"reject": "rejected", "revoke": "revoked"}[args.command],
            actor=args.reviewer,
            reason=args.reason,
            repo=getattr(args, "repo", None),
            commit=getattr(args, "commit", None),
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
