# -*- coding: utf-8 -*-
"""修复 fragment_model.xml：标题块移到 LinearLayout 开标签之后。"""

from pathlib import Path

path = Path("android/app/src/main/res/layout/fragment_model.xml")
data = path.read_text(encoding="utf-8")

# 1. 去掉误插在开标签和标题块之间的 <LinearLayout
data = data.replace("<LinearLayout\n            <TextView", "            <TextView")

# 2. 在标题块结束后补回 <LinearLayout 开标签（llXxx 属性行前）
for lid in ("llDebug", "llPlay", "llWp", "llClearCache", "llAbout"):
    anchor = f'                    android:id="@+id/{lid}"'
    idx = data.find(anchor)
    assert idx != -1, lid
    data = data[:idx] + "            <LinearLayout\n" + data[idx:]

path.write_text(data, encoding="utf-8")
print("修复完成")
