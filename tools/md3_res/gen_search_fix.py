# -*- coding: utf-8 -*-
"""P1-3 搜索页：白色文字统一为 md3_on_surface。"""

from pathlib import Path

targets = [
    Path("android/app/src/main/res/layout/activity_search.xml"),
    Path("android/app/src/main/res/layout/layout_keyborad.xml"),
    Path("android/app/src/main/res/layout/item_search_normal.xml"),
    Path("android/app/src/main/res/layout/item_search_lite.xml"),
    Path("android/app/src/main/res/layout/item_search_word_hot.xml"),
]

for p in targets:
    if not p.exists():
        continue
    data = p.read_text(encoding="utf-8")
    n = data.count('android:textColor="@android:color/white"')
    n += data.count('android:textColor="@color/color_FFFFFF"')
    data = data.replace(
        'android:textColor="@android:color/white"',
        'android:textColor="@color/md3_on_surface"',
    )
    data = data.replace(
        'android:textColor="@color/color_FFFFFF"',
        'android:textColor="@color/md3_on_surface"',
    )
    p.write_text(data, encoding="utf-8")
    print(f"{p.name}: 替换 {n} 处")
