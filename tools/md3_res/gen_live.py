# -*- coding: utf-8 -*-
"""MD3 restyle: live page backgrounds."""

import os

OUT = r"C:/Users/Jie/Projects/lat3ncy-tvbox/tools/md3_res"

FILES = {
    # 频道列表容器
    "bg_channel_list.xml": """<?xml version="1.0" encoding="utf-8"?>
<shape android:shape="rectangle"
    xmlns:android="http://schemas.android.com/apk/res/android">
    <solid android:color="@color/md3_surface_container" />
    <corners android:radius="@dimen/md3_corner_lg" />
    <stroke android:width="@dimen/md3_outline_stroke_width" android:color="@color/md3_outline_variant" />
</shape>
""",
    # 频道号角标
    "shape_live_channel_num.xml": """<?xml version="1.0" encoding="utf-8"?>
<shape xmlns:android="http://schemas.android.com/apk/res/android">
    <corners android:radius="@dimen/md3_corner_sm" />
    <solid android:color="@color/md3_surface_container_high" />
    <stroke android:width="@dimen/md3_outline_stroke_width" android:color="@color/md3_outline_variant" />
</shape>
""",
    # 缩略图底部名称条
    "shape_thumb_bottom_name.xml": """<?xml version="1.0" encoding="utf-8"?>
<shape xmlns:android="http://schemas.android.com/apk/res/android">
    <corners
        android:bottomLeftRadius="@dimen/md3_corner_sm"
        android:bottomRightRadius="@dimen/md3_corner_sm" />
    <solid android:color="@color/md3_scrim_60" />
</shape>
""",
    # 直播搜索按钮（pressed 态粉色 → MD3 primary）
    "shape_user_search.xml": """<?xml version="1.0" encoding="utf-8"?>
<selector xmlns:android="http://schemas.android.com/apk/res/android">
    <item android:state_focused="true" android:state_pressed="true">
        <shape>
            <corners android:radius="@dimen/md3_corner_sm" />
            <solid android:color="@color/md3_primary" />
        </shape>
    </item>
    <item android:state_focused="false" android:state_pressed="true">
        <shape>
            <corners android:radius="@dimen/md3_corner_sm" />
            <solid android:color="@color/md3_primary_container" />
        </shape>
    </item>
    <item android:state_focused="true">
        <shape>
            <corners android:radius="@dimen/md3_corner_sm" />
            <solid android:color="@color/md3_focus_fill" />
            <stroke android:width="@dimen/md3_focus_stroke_width" android:color="@color/md3_primary" />
        </shape>
    </item>
    <item>
        <shape>
            <corners android:radius="@dimen/md3_corner_sm" />
            <solid android:color="@color/md3_surface_container" />
            <stroke android:width="@dimen/md3_outline_stroke_width" android:color="@color/md3_outline_variant" />
        </shape>
    </item>
</selector>
""",
}

for name, content in FILES.items():
    with open(os.path.join(OUT, name), "w", encoding="utf-8") as f:
        f.write(content)
    print("written", name)
