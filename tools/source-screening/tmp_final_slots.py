#!/usr/bin/env python3
"""最终验证：高分源 4 时段覆盖。"""

import sqlite3
import sys

sys.stdout.reconfigure(encoding="utf-8")
con = sqlite3.connect("/opt/ponyo-source-manager/data/sources.db")

fps = [
    ("奶子", "c2f638574ccc361c14ab5d7d295dca5f40bc857ae7000f18c91925003ea9207f"),
    ("爱坤", "04228f4770bde3e9b4c6ee0b4fb1220ffd8128c45b5c3cfcde1da8fc8821becb"),
    ("10-如意", "bb468429cd63ab2ea92964495ab83281aaf0dc2aa50d843aa5847ce8d65b720c"),
    ("66-360", "6728cc8ee3d1b53c57469173664a6ed8221bddff099ed42741a5693742ee721c"),
    ("360┃", "a5643b7ad6979516589f6e3dd59a5e3c7905cadb13cab78fbcc9db924e00cd08"),
]
for name, fp in fps:
    slots = con.execute(
        "SELECT DISTINCT timeslot FROM conn_probe WHERE fingerprint=? AND ok=1 ORDER BY timeslot",
        (fp,),
    ).fetchall()
    ok4 = len(slots) == 4
    mark = "✅ 4时段全" if ok4 else "❌"
    print(f"  {name:<8} {mark} {[s[0] for s in slots]}")

# 最新评分（补测后 scorer 未跑，评分看下轮）
print("\n注：评分在下一轮 scoring 时用最新时段数据重算")
con.close()
