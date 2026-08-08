#!/usr/bin/env python3
"""标记成人内容源为 deny。"""

import sqlite3
import sys
from datetime import datetime, timezone

sys.stdout.reconfigure(encoding="utf-8")
DB = "/opt/ponyo-source-manager/data/sources.db"

ADULT_HOSTS = [
    "lbapiby.com",
    "hsckzy.xyz",
    "api.douapi.cc",
    "api.souavzy.vip",
    "xingba222.com",
    "heiliaozyapi.com",
    "xingba111.com",
    "api.souavzyw.net",
    "api.xiaojizy.live",
]

con = sqlite3.connect(DB, timeout=60)
now = datetime.now(timezone.utc).isoformat()
denied = 0
for h in ADULT_HOSTS:
    rows = con.execute(
        "SELECT n.fingerprint, r.name, r.api FROM norm_source n "
        "JOIN raw_source r ON n.raw_id = r.id WHERE r.api LIKE ? AND r.import_batch='gh-feature-20260808'",
        (f"%{h}%",),
    ).fetchall()
    for fp, name, api in rows:
        con.execute(
            "INSERT OR REPLACE INTO list_state(fingerprint, state, reason, updated_at) "
            "VALUES (?, 'deny', 'adult content detected (内容审核 2026-08-08)', ?)",
            (fp, now),
        )
        denied += 1
        print(f"  deny: {name} {api[:60]}")
con.commit()
print(f"已 deny {denied} 个成人源")
con.close()
