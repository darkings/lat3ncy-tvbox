# -*- coding: utf-8 -*-
"""临时：列出 allow/hard_pass 源，支持状态降级/恢复（测试用）。"""

import json
import sqlite3
import sys

con = sqlite3.connect("data/sources.db")
con.row_factory = sqlite3.Row

rows = con.execute(
    """
    WITH LatestScores AS (
        SELECT fingerprint, total_score,
               ROW_NUMBER() OVER(PARTITION BY fingerprint ORDER BY scored_at DESC) as rn
        FROM score_snapshot
    )
    SELECT ls.state, ls.fingerprint, r.raw_json, s.total_score
    FROM list_state ls
    JOIN dedup_group dg ON ls.fingerprint = dg.fingerprint
    JOIN raw_source r ON dg.primary_raw_id = r.id
    LEFT JOIN LatestScores s ON ls.fingerprint = s.fingerprint AND s.rn = 1
    WHERE ls.state IN ('allow', 'hard_pass')
    ORDER BY ls.state, COALESCE(s.total_score, 0) DESC
    """
).fetchall()

for r in rows:
    obj = json.loads(r["raw_json"])
    print(
        r["state"],
        r["fingerprint"][:16],
        r["total_score"],
        obj.get("name"),
        obj.get("key"),
    )

if len(sys.argv) == 3 and sys.argv[1] == "demote":
    con.execute(
        "UPDATE list_state SET state='candidate' WHERE fingerprint LIKE ?",
        (sys.argv[2] + "%",),
    )
    con.commit()
    print("DEMOTED:", sys.argv[2][:16])
elif len(sys.argv) == 3 and sys.argv[1] == "restore":
    con.execute(
        "UPDATE list_state SET state='allow' WHERE fingerprint LIKE ?",
        (sys.argv[2] + "%",),
    )
    con.commit()
    print("RESTORED allow:", sys.argv[2][:16])
