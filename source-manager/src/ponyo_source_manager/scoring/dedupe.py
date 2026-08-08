#!/usr/bin/env python3
"""指纹分组去重：每组选 primary，写 dedup_group + reports/dedupe-report.json。"""
from __future__ import annotations

import argparse
import json
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from ponyo_source_manager.core.common import PONYO_HOME as HERE


def _load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def run_dedupe(db_path, policy_path, report_path) -> dict:
    policy = _load(policy_path)
    vrank = policy.get("verdict_rank", {})
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute("""
            SELECT n.id AS norm_id, n.fingerprint AS fp, n.required_urls AS req,
                   r.id AS raw_id, r.name AS name, r.site_key AS site_key,
                   h.verdict AS verdict, nm.new_name AS new_name
            FROM norm_source n
            JOIN raw_source r ON n.raw_id = r.id
            LEFT JOIN health_snapshot h ON h.site_key = r.site_key
            LEFT JOIN name_map nm ON nm.site_key = r.site_key
        """).fetchall()

        groups = defaultdict(list)
        for row in rows:
            groups[row["fp"]].append(row)

        def sort_key(row):
            rank = vrank.get(row["verdict"], 99)
            try:
                req_len = len(json.loads(row["req"] or "[]"))
            except json.JSONDecodeError:
                req_len = 999
            has_new = 0 if (row["new_name"]) else 1
            return (rank, req_len, has_new, row["raw_id"])

        # 读取旧的 dedup_group 记录用于主源切换审计 (A21)
        old_primaries = {}
        try:
            for r in con.execute("SELECT fingerprint, primary_raw_id FROM dedup_group").fetchall():
                old_primaries[r["fingerprint"]] = r["primary_raw_id"]
        except Exception:
            pass

        con.execute("DELETE FROM dedup_group")
        details = []
        now_str = datetime.now(timezone.utc).isoformat()
        for fp, members in groups.items():
            ordered = sorted(members, key=sort_key)
            primary = ordered[0]
            member_ids = [m["norm_id"] for m in members]

            old_primary_id = old_primaries.get(fp)
            if old_primary_id and old_primary_id != primary["raw_id"]:
                con.execute(
                    "INSERT INTO audit_log (entity_type, entity_id, action, old_value, new_value, reason, acted_at) "
                    "VALUES ('dedup_group', ?, 'primary_switch', ?, ?, ?, ?)",
                    (fp, str(old_primary_id), str(primary["raw_id"]), f"verdict={primary['verdict']} sort_rank_switch", now_str)
                )

            con.execute(
                "INSERT INTO dedup_group(fingerprint,member_count,primary_raw_id,member_ids)"
                " VALUES(?,?,?,?)",
                (fp, len(members), primary["raw_id"], json.dumps(member_ids)))
            details.append({
                "fingerprint": fp,
                "member_count": len(members),
                "primary_raw_id": primary["raw_id"],
                "primary_name": primary["name"],
                "members": [m["name"] for m in members],
                "members_ids": member_ids,
                "reason": f"verdict={primary['verdict']} req={sort_key(primary)[1]}",
            })
        con.commit()

    finally:
        con.close()

    details.sort(key=lambda d: (-d["member_count"], d["primary_name"] or ""))
    total = len(rows)
    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total": total,
        "groups": len(groups),
        "duplicates": total - len(groups),
        "details": details,
    }
    Path(report_path).parent.mkdir(parents=True, exist_ok=True)
    Path(report_path).write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"total": total, "groups": len(groups), "duplicates": total - len(groups)}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--db", default=str(HERE / "data" / "sources.db"))
    p.add_argument("--policy", default=str(HERE / "config" / "policy.json"))
    p.add_argument("--report", default=str(HERE / "reports" / "dedupe-report.json"))
    args = p.parse_args()
    result = run_dedupe(args.db, args.policy, args.report)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
