# -*- coding: utf-8 -*-
"""MD3 restyle: detail page + player controls + live page resources."""

import os

OUT = r"C:/Users/Jie/Projects/lat3ncy-tvbox/tools/md3_res"

FILES = {}

# ---- Detail page ----
FILES["shape_detail_thumb_bg.xml"] = """<?xml version="1.0" encoding="utf-8"?>
<selector xmlns:android="http://schemas.android.com/apk/res/android">
    <item android:state_focused="true">
        <shape>
            <corners android:radius="@dimen/md3_corner_md" />
            <stroke android:width="@dimen/md3_focus_stroke_width" android:color="@color/md3_primary" />
            <solid android:color="@color/md3_surface_container" />
        </shape>
    </item>
    <item android:state_focused="false">
        <shape>
            <corners android:radius="@dimen/md3_corner_md" />
            <solid android:color="@color/md3_surface_container_low" />
            <stroke android:width="@dimen/md3_outline_stroke_width" android:color="@color/md3_outline_variant" />
        </shape>
    </item>
</selector>
"""

FILES["shape_source_series_focus.xml"] = """<?xml version="1.0" encoding="utf-8"?>
<selector xmlns:android="http://schemas.android.com/apk/res/android">
    <item android:state_focused="true">
        <shape>
            <corners android:radius="@dimen/md3_corner_sm" />
            <stroke android:width="@dimen/md3_focus_stroke_width" android:color="@color/md3_primary" />
            <solid android:color="@color/md3_focus_fill" />
        </shape>
    </item>
    <item android:state_focused="false">
        <shape>
            <corners android:radius="@dimen/md3_corner_sm" />
            <solid android:color="@color/md3_surface_container" />
            <stroke android:width="@dimen/md3_outline_stroke_width" android:color="@color/md3_outline_variant" />
        </shape>
    </item>
</selector>
"""

FILES["ponyo_poster_surface.xml"] = """<?xml version="1.0" encoding="utf-8"?>
<shape xmlns:android="http://schemas.android.com/apk/res/android" android:shape="rectangle">
    <corners android:radius="@dimen/md3_corner_md" />
    <solid android:color="@color/md3_surface_container_low" />
</shape>
"""

# ---- Player controls ----
FILES["box_controller_top_bg.xml"] = """<?xml version="1.0" encoding="utf-8"?>
<shape xmlns:android="http://schemas.android.com/apk/res/android">
    <gradient
        android:angle="270"
        android:endColor="@android:color/transparent"
        android:startColor="@color/md3_scrim_60" />
</shape>
"""

FILES["shape_play_bottom.xml"] = """<?xml version="1.0" encoding="utf-8"?>
<shape xmlns:android="http://schemas.android.com/apk/res/android">
    <corners
        android:topLeftRadius="@dimen/md3_corner_lg"
        android:topRightRadius="@dimen/md3_corner_lg" />
    <solid android:color="@color/md3_surface_container" />
    <stroke android:width="@dimen/md3_outline_stroke_width" android:color="@color/md3_outline_variant" />
</shape>
"""

FILES["shape_play_mobile_center.xml"] = """<?xml version="1.0" encoding="utf-8"?>
<shape xmlns:android="http://schemas.android.com/apk/res/android">
    <corners android:radius="@dimen/md3_corner_full" />
    <solid android:color="@color/md3_scrim_60" />
    <stroke android:width="@dimen/md3_outline_stroke_width" android:color="@color/md3_primary" />
</shape>
"""

FILES["shape_user_focus.xml"] = """<?xml version="1.0" encoding="utf-8"?>
<selector xmlns:android="http://schemas.android.com/apk/res/android">
    <item android:state_focused="true">
        <shape>
            <corners android:radius="@dimen/md3_corner_sm" />
            <stroke android:width="@dimen/md3_focus_stroke_width" android:color="@color/md3_primary" />
            <solid android:color="@color/md3_focus_fill" />
        </shape>
    </item>
    <item android:state_focused="false">
        <shape>
            <corners android:radius="@dimen/md3_corner_sm" />
            <solid android:color="@color/md3_surface_container" />
            <stroke android:width="@dimen/md3_outline_stroke_width" android:color="@color/md3_outline_variant" />
        </shape>
    </item>
</selector>
"""

FILES["seekbar_style.xml"] = """<?xml version="1.0" encoding="utf-8"?>
<layer-list xmlns:android="http://schemas.android.com/apk/res/android">
    <item android:id="@android:id/background">
        <shape>
            <solid android:color="@color/md3_surface_container_highest" />
            <corners android:radius="@dimen/md3_corner_full" />
        </shape>
    </item>
    <item android:id="@android:id/secondaryProgress">
        <clip>
            <shape>
                <solid android:color="@color/md3_tertiary" />
                <corners android:radius="@dimen/md3_corner_full" />
            </shape>
        </clip>
    </item>
    <item android:id="@android:id/progress">
        <clip>
            <shape>
                <solid android:color="@color/md3_primary" />
                <corners android:radius="@dimen/md3_corner_full" />
            </shape>
        </clip>
    </item>
</layer-list>
"""

FILES["seekbar_thumb_normal.xml"] = """<?xml version="1.0" encoding="utf-8"?>
<shape xmlns:android="http://schemas.android.com/apk/res/android" android:shape="oval">
    <solid android:color="@color/md3_primary" />
    <size android:width="14dp" android:height="14dp" />
</shape>
"""

FILES["seekbar_thumb_pressed.xml"] = """<?xml version="1.0" encoding="utf-8"?>
<shape xmlns:android="http://schemas.android.com/apk/res/android" android:shape="oval">
    <solid android:color="@color/md3_primary" />
    <stroke android:width="3dp" android:color="@color/md3_on_primary" />
    <size android:width="18dp" android:height="18dp" />
</shape>
"""

for name, content in FILES.items():
    with open(os.path.join(OUT, name), "w", encoding="utf-8") as f:
        f.write(content)
    print("written", name)
print("total", len(FILES))
