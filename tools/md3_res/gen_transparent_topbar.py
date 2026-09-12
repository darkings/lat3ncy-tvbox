# -*- coding: utf-8 -*-
"""Top bar: transparent background; time pill without border."""

import os

OUT = r"C:/Users/Jie/Projects/lat3ncy-tvbox/tools/md3_res"

# ---- Transparent top bar (no background, no border) ----
PONYO_TOP_BAR = """<?xml version="1.0" encoding="utf-8"?>
<shape xmlns:android="http://schemas.android.com/apk/res/android" android:shape="rectangle">
    <corners android:radius="@dimen/md3_corner_lg" />
    <solid android:color="@android:color/transparent" />
</shape>
"""

# ---- Time pill: solid fill only, no stroke ----
MD3_TIME_PILL = """<?xml version="1.0" encoding="utf-8"?>
<shape xmlns:android="http://schemas.android.com/apk/res/android">
    <corners android:radius="@dimen/md3_corner_full" />
    <solid android:color="#B32F2824" />
    <padding android:left="@dimen/md3_space_3" android:top="@dimen/md3_space_1" android:right="@dimen/md3_space_3" android:bottom="@dimen/md3_space_1" />
</shape>
"""

files = {
    "ponyo_top_bar.xml": PONYO_TOP_BAR,
    "md3_time_pill.xml": MD3_TIME_PILL,
}
for name, content in files.items():
    with open(os.path.join(OUT, name), "w", encoding="utf-8") as f:
        f.write(content)
    print("written", name)
