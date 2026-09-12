# -*- coding: utf-8 -*-
"""临时：查看 candidate 高分源，并执行状态升降级（测试用）。"""

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
    WHERE ls.state = 'candidate'
    ORDER BY COALESCE(s.total_score, 0) DESC
    LIMIT 5
    """
).fetchall()

for r in rows:
    obj = json.loads(r["raw_json"])
    print(r["fingerprint"][:16], r["total_score"], obj.get("name"), obj.get("key"))

if len(sys.argv) > 2 and sys.argv[1] == "set":
    fp = sys.argv[2]
    con.execute(
        "UPDATE list_state SET state=? WHERE fingerprint LIKE ?",
        ("hard_pass", fp + "%"),
    )
    con.commit()
    print("SET hard_pass:", fp[:16])
elif len(sys.argv) > 2 and sys.argv[1] == "reset":
    fp = sys.argv[2]
    con.execute(
        "UPDATE list_state SET state=? WHERE fingerprint LIKE ?",
        ("candidate", fp + "%"),
    )
    con.commit()
    print("RESET candidate:", fp[:16])
