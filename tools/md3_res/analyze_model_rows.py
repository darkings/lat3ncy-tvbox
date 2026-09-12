# -*- coding: utf-8 -*-
"""查看混合行 [7][8][9][10][11] 的直接子元素结构。"""

import xml.etree.ElementTree as ET
from pathlib import Path

A = "{http://schemas.android.com/apk/res/android}"
data = Path("android/app/src/main/res/layout/fragment_model.xml").read_text(
    encoding="utf-8"
)
root = ET.fromstring(data)

root_ll = None
for e in root.iter():
    if (
        e.tag.split("}")[-1] == "LinearLayout"
        and e.get(A + "orientation") == "vertical"
    ):
        root_ll = e
        break

children = list(root_ll)
for idx in [7, 8, 9, 10, 11]:
    row = children[idx]
    print(f"=== 行[{idx}] ===")
    for sub in row:
        tag = sub.tag.split("}")[-1]
        ids = [
            e.get(A + "id", "") for e in sub.iter() if "@+id/ll" in e.get(A + "id", "")
        ]
        ids = [x.replace("@+id/", "") for x in ids]
        weight = sub.get(A + "layout_weight", "")
        focusable = sub.get(A + "focusable", "")
        vis = sub.get(A + "visibility", "")
        print(f"  {tag:10} weight={weight:6} focus={focusable:5} vis={vis:5} ll={ids}")
