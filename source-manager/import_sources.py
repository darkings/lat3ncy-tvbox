#!/usr/bin/env python3
"""导入 ponyo.json + health + name-map 到 SQLite（幂等；单事务）。"""
from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from common import assert_no_proxy, classify, compute_fingerprint

HERE = Path(__file__).resolve().parent


def _load(path: str):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _asstr(v):
    return v if isinstance(v, str) else (json.dumps(v, ensure_ascii=False) if v is not None else None)


def import_all(db_path, ponyo_path, health_path, namemap_path, policy_path,
               batch, origin="ponyo.json") -> dict:
    proxies = assert_no_proxy()
    if proxies:
        print(f"[warn] proxy env set: {proxies}")

    policy = _load(policy_path)
    ponyo = _load(ponyo_path)
    sites = ponyo.get("sites") or []
    if not sites:
        raise ValueError("ponyo.json has no sites")

    health_doc = _load(health_path)
    health_sites = health_doc.get("sites") if isinstance(health_doc, dict) else health_doc
    namemap = _load(namemap_path)
    now = datetime.now(timezone.utc).isoformat()

    con = sqlite3.connect(str(db_path))
    counts = {"raw": 0, "norm": 0, "health": 0, "name_map": 0, "list_state": 0}
    try:
        con.execute("BEGIN")
        for site in sites:
            cur = con.execute(
                "INSERT OR IGNORE INTO raw_source"
                "(import_batch,origin,site_key,name,type,api,ext,raw_json)"
                " VALUES(?,?,?,?,?,?,?,?)",
                (batch, origin, str(site.get("key", "")), site.get("name"),
                 site.get("type"), _asstr(site.get("api")), _asstr(site.get("ext")),
                 json.dumps(site, ensure_ascii=False)))
            if cur.rowcount == 0:
                continue  # 同 batch 已存在，跳过（幂等）
            raw_id = cur.lastrowid
            counts["raw"] += 1
            fp, meta = compute_fingerprint(site)
            con.execute(
                "INSERT INTO norm_source"
                "(raw_id,fingerprint,api_host,required_urls,jar_md5,spider_class,category,capabilities)"
                " VALUES(?,?,?,?,?,?,?,?)",
                (raw_id, fp, meta["api_host"], json.dumps(meta["required_urls"], ensure_ascii=False),
                 meta["jar_md5"], meta["spider_class"], classify(site.get("name", ""), policy),
                 json.dumps([], ensure_ascii=False)))
            counts["norm"] += 1
            con.execute(
                "INSERT OR IGNORE INTO list_state(fingerprint,state,reason,updated_at)"
                " VALUES(?,?,?,?)", (fp, "candidate", "", now))

        for h in (health_sites or []):
            con.execute(
                "INSERT INTO health_snapshot(site_key,verdict,urls,captured_at)"
                " VALUES(?,?,?,?)",
                (str(h.get("key", "")), h.get("verdict"),
                 json.dumps(h.get("urls", []), ensure_ascii=False), now))
            counts["health"] += 1

        for m in namemap:
            con.execute(
                "INSERT OR REPLACE INTO name_map(site_key,old_name,new_name,verdict)"
                " VALUES(?,?,?,?)",
                (str(m.get("key", "")), m.get("old"), m.get("new"), m.get("verdict")))
            counts["name_map"] += 1

        counts["list_state"] = con.execute("SELECT count(*) FROM list_state").fetchone()[0]
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()
    return counts


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--db", default=str(HERE / "data" / "sources.db"))
    p.add_argument("--ponyo", required=True)
    p.add_argument("--health", required=True)
    p.add_argument("--namemap", required=True)
    p.add_argument("--policy", default=str(HERE / "config" / "policy.json"))
    p.add_argument("--batch", required=True)
    args = p.parse_args()
    counts = import_all(args.db, args.ponyo, args.health, args.namemap, args.policy, args.batch)
    print(json.dumps(counts, ensure_ascii=False))


if __name__ == "__main__":
    main()
