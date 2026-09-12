# -*- coding: utf-8 -*-
"""Generate Material Symbols style icons + MD3 home resources."""

import os

OUT = r"C:/Users/Jie/Projects/lat3ncy-tvbox/tools/md3_res"


def icon(name, path_data, fill="#FFFFFFFF"):
    return f'''<?xml version="1.0" encoding="utf-8"?>
<vector xmlns:android="http://schemas.android.com/apk/res/android"
    android:width="48dp"
    android:height="48dp"
    android:viewportWidth="24"
    android:viewportHeight="24">
  <path
      android:pathData="{path_data}"
      android:fillColor="{fill}"/>
</vector>
'''


FILES = {}

# Material Symbols (filled, 24dp) — Apache 2.0
FILES["icon_search.xml"] = icon(
    "search",
    "M15.5,14h-0.79l-0.28,-0.27C15.41,12.59 16,11.11 16,9.5 16,5.91 13.09,3 9.5,3S3,5.91 3,9.5 5.91,16 9.5,16c1.61,0 3.09,-0.59 4.23,-1.57l0.27,0.28v0.79l5,4.99L20.49,19l-4.99,-5zM9.5,14C7.01,14 5,11.99 5,9.5S7.01,5 9.5,5 14,7.01 14,9.5 11.99,14 9.5,14z",
)
FILES["icon_history.xml"] = icon(
    "history",
    "M13,3c-4.97,0 -9,4.03 -9,9L1,12l3.89,3.89 0.07,0.14L9,12L6,12c0,-3.87 3.13,-7 7,-7s7,3.13 7,7 -3.13,7 -7,7c-1.93,0 -3.68,-0.79 -4.94,-2.06l-1.42,1.42C8.27,19.99 10.51,21 13,21c4.97,0 9,-4.03 9,-9s-4.03,-9 -9,-9zM12,8v5l4.28,2.54 0.72,-1.21 -3.5,-2.08L13,8L12,8z",
)
FILES["icon_live.xml"] = icon(
    "live_tv",
    "M21,6h-7.59l3.29,-3.29L16,2l-4,4 -4,-4 -0.71,0.71L10.59,6L3,6c-1.1,0 -2,0.9 -2,2v12c0,1.1 0.9,2 2,2h18c1.1,0 2,-0.9 2,-2L23,8c0,-1.1 -0.9,-2 -2,-2zM21,20L3,20L3,8h18v12zM9,10v8l7,-4z",
)
FILES["icon_collect.xml"] = icon(
    "favorite",
    "M12,21.35l-1.45,-1.32C5.4,15.36 2,12.28 2,8.5 2,5.42 4.42,3 7.5,3c1.74,0 3.41,0.81 4.5,2.09C13.09,3.81 14.76,3 16.5,3 19.58,3 22,5.42 22,8.5c0,3.78 -3.4,6.86 -8.55,11.54L12,21.35z",
)
FILES["icon_setting.xml"] = icon(
    "settings",
    "M19.14,12.94c0.04,-0.3 0.06,-0.61 0.06,-0.94 0,-0.32 -0.02,-0.64 -0.07,-0.94l2.03,-1.58c0.18,-0.14 0.23,-0.41 0.12,-0.61l-1.92,-3.32c-0.12,-0.22 -0.37,-0.29 -0.59,-0.22l-2.39,0.96c-0.5,-0.38 -1.03,-0.7 -1.62,-0.94l-0.36,-2.54c-0.04,-0.24 -0.24,-0.41 -0.48,-0.41h-3.84c-0.24,0 -0.43,0.17 -0.47,0.41l-0.36,2.54c-0.59,0.24 -1.13,0.57 -1.62,0.94l-2.39,-0.96c-0.22,-0.08 -0.47,0 -0.59,0.22L2.74,8.87c-0.12,0.21 -0.08,0.47 0.12,0.61l2.03,1.58c-0.05,0.3 -0.09,0.63 -0.09,0.94s0.02,0.64 0.07,0.94l-2.03,1.58c-0.18,0.14 -0.23,0.41 -0.12,0.61l1.92,3.32c0.12,0.22 0.37,0.29 0.59,0.22l2.39,-0.96c0.5,0.38 1.03,0.7 1.62,0.94l0.36,2.54c0.05,0.24 0.24,0.41 0.48,0.41h3.84c0.24,0 0.44,-0.17 0.47,-0.41l0.36,-2.54c0.59,-0.24 1.13,-0.56 1.62,-0.94l2.39,0.96c0.22,0.08 0.47,0 0.59,-0.22l1.92,-3.32c0.12,-0.22 0.07,-0.47 -0.12,-0.61l-2.01,-1.58zM12,15.6c-1.98,0 -3.6,-1.62 -3.6,-3.6s1.62,-3.6 3.6,-3.6 3.6,1.62 3.6,3.6 -1.62,3.6 -3.6,3.6z",
)
FILES["icon_push.xml"] = icon("send", "M2.01,21L23,12 2.01,3 2,10l15,2 -15,2z")
FILES["icon_back.xml"] = icon(
    "keyboard_backspace",
    "M21,11L6.83,11l3.58,-3.59L9,6l-6,6 6,6 1.41,-1.41L6.83,13L21,13z",
)
FILES["icon_clear.xml"] = icon(
    "close",
    "M19,6.41L17.59,5 12,10.59 6.41,5 5,6.41 10.59,12 5,17.59 6.41,19 12,13.41 17.59,19 19,17.59 13.41,12z",
)
FILES["icon_delete.xml"] = icon(
    "delete",
    "M6,19c0,1.1 0.9,2 2,2h8c1.1,0 2,-0.9 2,-2L18,7L6,7v12zM19,4h-3.5l-1,-1h-5l-1,1L5,4v2h14L19,4z",
)
FILES["icon_filter.xml"] = icon(
    "filter_list", "M10,18h4v-2h-4v2zM3,6v2h18L21,6L3,6zM6,13h12v-2L6,11v2z"
)

# Brand mark: Ponyo waves (two wave lines)
FILES["icon_brand_waves.xml"] = """<?xml version="1.0" encoding="utf-8"?>
<vector xmlns:android="http://schemas.android.com/apk/res/android"
    android:width="48dp"
    android:height="48dp"
    android:viewportWidth="24"
    android:viewportHeight="24">
  <path
      android:pathData="M2,9.5c2.1,-2.8 4.2,2.8 6.3,0s4.2,2.8 6.3,0 4.2,2.8 6.3,0"
      android:strokeColor="#FFFFFFFF"
      android:strokeWidth="1.8"
      android:strokeLineCap="round"
      android:fillColor="#00000000"/>
  <path
      android:pathData="M2,15.5c2.1,-2.8 4.2,2.8 6.3,0s4.2,2.8 6.3,0 4.2,2.8 6.3,0"
      android:strokeColor="#FFFFFFFF"
      android:strokeWidth="1.8"
      android:strokeLineCap="round"
      android:fillColor="#00000000"/>
</vector>
"""

# Icon tint selector (normal: on-surface-variant, focused: on-primary-container)
FILES["md3_icon_tint.xml"] = """<?xml version="1.0" encoding="utf-8"?>
<selector xmlns:android="http://schemas.android.com/apk/res/android">
    <item android:state_focused="true" android:color="@color/md3_focus_text" />
    <item android:color="@color/md3_on_surface_variant" />
</selector>
"""

# Action text color selector
FILES["md3_action_text.xml"] = """<?xml version="1.0" encoding="utf-8"?>
<selector xmlns:android="http://schemas.android.com/apk/res/android">
    <item android:state_focused="true" android:color="@color/md3_focus_text" />
    <item android:color="@color/md3_on_surface_variant" />
</selector>
"""

# Home action button (tonal: surface-container / focus primary-container)
FILES["shape_home_action_focus.xml"] = """<?xml version="1.0" encoding="utf-8"?>
<selector xmlns:android="http://schemas.android.com/apk/res/android">
    <item android:state_focused="true">
        <shape>
            <corners android:radius="@dimen/md3_corner_full" />
            <stroke android:width="@dimen/md3_focus_stroke_width" android:color="@color/md3_primary" />
            <solid android:color="@color/md3_focus_fill" />
        </shape>
    </item>
    <item>
        <shape>
            <corners android:radius="@dimen/md3_corner_full" />
            <solid android:color="@color/md3_surface_container" />
            <stroke android:width="@dimen/md3_outline_stroke_width" android:color="@color/md3_outline_variant" />
        </shape>
    </item>
</selector>
"""

# Time pill (date/time display)
FILES["md3_time_pill.xml"] = """<?xml version="1.0" encoding="utf-8"?>
<shape xmlns:android="http://schemas.android.com/apk/res/android">
    <corners android:radius="@dimen/md3_corner_full" />
    <solid android:color="@color/md3_surface_container_high" />
    <stroke android:width="@dimen/md3_outline_stroke_width" android:color="@color/md3_outline_variant" />
    <padding android:left="@dimen/md3_space_3" android:top="@dimen/md3_space_1" android:right="@dimen/md3_space_3" android:bottom="@dimen/md3_space_1" />
</shape>
"""

# Brand mark container (primary-container rounded square)
FILES["md3_brand_mark.xml"] = """<?xml version="1.0" encoding="utf-8"?>
<shape xmlns:android="http://schemas.android.com/apk/res/android">
    <corners android:radius="@dimen/md3_corner_md" />
    <gradient
        android:angle="45"
        android:startColor="@color/md3_primary_container"
        android:endColor="@color/md3_primary" />
</shape>
"""

for name, content in FILES.items():
    with open(os.path.join(OUT, name), "w", encoding="utf-8") as f:
        f.write(content)
    print("written", name)
print("total", len(FILES))
