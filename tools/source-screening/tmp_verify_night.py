#!/usr/bin/env python3
"""验证 night 补测结果。"""

import sqlite3
import sys

sys.stdout.reconfigure(encoding="utf-8")
con = sqlite3.connect("/opt/ponyo-source-manager/data/sources.db")

fps = [
    "c2f638574ccc360c14ab5d7d295dca5f40bc857ae7000f18c91925003ea9207f",
    "04228f4770bde3e9b4c6ee0b4fb1220ffd8128c45b5c3cfcde1da8fc8821becb",
    "bb468429cd63ab2ea92964495ab83281aaf0dc2aa50d843aa5847ce8d65b720c",
    "6728cc8ee3d1b53c57469173664a6ed8221bddff099ed42741a5693742ee721c",
    "a5643b7ad6979516589f6e3dd59a5e3c7905cadb13cab78fbcc9db924e00cd08",
]
for fp in fps:
    row = con.execute(
        "SELECT r.name FROM norm_source n JOIN raw_source r ON n.raw_id=r.id WHERE n.fingerprint=?",
        (fp,),
    ).fetchone()
    name = row[0] if row else "?"
    slots = con.execute(
        "SELECT DISTINCT timeslot FROM conn_probe WHERE fingerprint=? AND ok=1 ORDER BY timeslot",
        (fp,),
    ).fetchall()
    nrow = con.execute(
        "SELECT ok, latency_ms, probed_at FROM conn_probe WHERE fingerprint=? AND timeslot='night' ORDER BY id DESC LIMIT 1",
        (fp,),
    ).fetchone()
    print(f"{name[:14]:<16} {[s[0] for s in slots]}  night最近={nrow}")
con.close()
