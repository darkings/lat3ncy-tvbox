# -*- coding: utf-8 -*-
"""Generate MD3-styled drawable resources for Ponyo TV (Warm Sea theme)."""

import os

OUT = r"C:/Users/Jie/Projects/lat3ncy-tvbox/tools/md3_res"

FILES = {
    # 1. Global focus background (tonal highlight: primary-container + primary outline)
    "item_right_bg.xml": """<?xml version="1.0" encoding="utf-8"?>
<shape xmlns:android="http://schemas.android.com/apk/res/android">
    <solid android:color="@color/md3_focus_fill"/>
    <corners android:radius="@dimen/md3_corner_md"/>
    <stroke android:width="@dimen/md3_focus_stroke_width"
        android:color="@color/md3_focus_stroke"/>
</shape>
""",
    # 2. Home category focus (pill)
    "button_home_sort_focus.xml": """<?xml version="1.0" encoding="utf-8"?>
<selector xmlns:android="http://schemas.android.com/apk/res/android">
    <item android:state_focused="true">
        <shape>
            <corners android:radius="@dimen/md3_corner_full"/>
            <solid android:color="@color/md3_focus_fill"/>
            <stroke android:width="@dimen/md3_focus_stroke_width" android:color="@color/md3_focus_stroke" />
        </shape>
    </item>
    <item android:state_focused="false">
        <shape>
            <corners android:radius="@dimen/md3_corner_full"/>
            <solid android:color="@android:color/transparent"/>
        </shape>
    </item>
</selector>
""",
    # 3. Panel (surface-container + outline-variant)
    "ponyo_panel.xml": """<?xml version="1.0" encoding="utf-8"?>
<shape xmlns:android="http://schemas.android.com/apk/res/android" android:shape="rectangle">
    <corners android:radius="@dimen/md3_corner_lg" />
    <solid android:color="@color/md3_surface_container" />
    <stroke android:width="@dimen/md3_outline_stroke_width" android:color="@color/md3_outline_variant" />
    <padding android:left="@dimen/md3_space_3" android:top="@dimen/md3_space_3" android:right="@dimen/md3_space_3" android:bottom="@dimen/md3_space_3" />
</shape>
""",
    # 4. Dialog panel (surface-container-high + extra-large corners)
    "bg_dialog_rounded.xml": """<?xml version="1.0" encoding="utf-8"?>
<shape xmlns:android="http://schemas.android.com/apk/res/android">
    <solid android:color="@color/md3_surface_container_high" />
    <corners android:radius="@dimen/md3_corner_xl"/>
    <stroke android:width="@dimen/md3_outline_stroke_width" android:color="@color/md3_outline_variant"/>
    <padding android:left="@dimen/md3_space_3" android:right="@dimen/md3_space_3" android:top="@dimen/md3_space_3" android:bottom="@dimen/md3_space_3"/>
</shape>
""",
    # 5. Search input (MD3 outlined text field)
    "input_search.xml": """<?xml version="1.0" encoding="utf-8"?>
<selector xmlns:android="http://schemas.android.com/apk/res/android">
    <item android:state_focused="true">
        <shape>
            <corners android:radius="@dimen/md3_corner_sm" />
            <solid android:color="@color/md3_surface_container" />
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
    # 6. Dialog primary button (filled tonal)
    "button_dialog_main.xml": """<?xml version="1.0" encoding="utf-8"?>
<selector xmlns:android="http://schemas.android.com/apk/res/android">
    <item android:state_focused="true">
        <shape>
            <corners android:radius="@dimen/md3_corner_full" />
            <solid android:color="@color/md3_primary" />
            <stroke android:width="@dimen/md3_focus_stroke_width" android:color="@color/md3_on_primary" />
        </shape>
    </item>
    <item android:state_focused="false">
        <shape>
            <corners android:radius="@dimen/md3_corner_full" />
            <solid android:color="@color/md3_primary_container" />
        </shape>
    </item>
</selector>
""",
    # 7. Top bar (surface-container + bottom outline)
    "ponyo_top_bar.xml": """<?xml version="1.0" encoding="utf-8"?>
<shape xmlns:android="http://schemas.android.com/apk/res/android" android:shape="rectangle">
    <corners android:radius="@dimen/md3_corner_lg" />
    <solid android:color="@color/md3_surface_container" />
    <stroke android:width="@dimen/md3_outline_stroke_width" android:color="@color/md3_outline_variant" />
</shape>
""",
    # 8. Fast search status panel
    "bg_fast_search_status.xml": """<?xml version="1.0" encoding="utf-8"?>
<shape xmlns:android="http://schemas.android.com/apk/res/android">
    <solid android:color="@color/md3_surface_container" />
    <corners android:radius="@dimen/md3_corner_md" />
    <padding
        android:left="@dimen/md3_space_2"
        android:top="@dimen/md3_space_1"
        android:right="@dimen/md3_space_2"
        android:bottom="@dimen/md3_space_1" />
</shape>
""",
    # 9. Search word chip (assist/filter chip)
    "bg_fast_search_word.xml": """<?xml version="1.0" encoding="utf-8"?>
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
        </shape>
    </item>
</selector>
""",
    # 10. Site filter word chip (with selected state)
    "bg_fast_site_word.xml": """<?xml version="1.0" encoding="utf-8"?>
<selector xmlns:android="http://schemas.android.com/apk/res/android">
    <item android:state_focused="true">
        <shape>
            <corners android:radius="@dimen/md3_corner_full" />
            <stroke android:width="@dimen/md3_focus_stroke_width" android:color="@color/md3_primary" />
            <solid android:color="@color/md3_focus_fill" />
        </shape>
    </item>
    <item android:state_selected="true">
        <shape>
            <corners android:radius="@dimen/md3_corner_full" />
            <stroke android:width="@dimen/md3_outline_stroke_width" android:color="@color/md3_primary" />
            <solid android:color="@color/md3_primary_container" />
        </shape>
    </item>
    <item>
        <shape>
            <corners android:radius="@dimen/md3_corner_full" />
            <solid android:color="@color/md3_surface_container" />
        </shape>
    </item>
</selector>
""",
    # 11. Progress track (tonal)
    "bg_progress_bar_out.xml": """<?xml version="1.0" encoding="utf-8"?>
<shape xmlns:android="http://schemas.android.com/apk/res/android">
    <solid android:color="@color/md3_surface_container_highest" />
    <corners android:radius="@dimen/md3_corner_full"/>
</shape>
""",
    # 12. Detail play button (primary filled)
    "button_detail_play.xml": """<?xml version="1.0" encoding="utf-8"?>
<selector xmlns:android="http://schemas.android.com/apk/res/android">
    <item android:state_focused="true">
        <shape>
            <corners android:radius="@dimen/md3_corner_full" />
            <solid android:color="@color/md3_primary" />
            <stroke android:width="@dimen/md3_focus_stroke_width" android:color="@color/md3_on_primary" />
        </shape>
    </item>
    <item android:state_focused="false">
        <shape>
            <corners android:radius="@dimen/md3_corner_full" />
            <solid android:color="@color/md3_primary" />
        </shape>
    </item>
</selector>
""",
    # 13. App background layer (brand art + MD3 surface scrim)
    "app_bg_layer.xml": """<?xml version="1.0" encoding="utf-8"?>
<layer-list xmlns:android="http://schemas.android.com/apk/res/android">
    <item android:drawable="@drawable/app_bg" />
    <item>
        <shape android:shape="rectangle">
            <gradient
                android:angle="270"
                android:startColor="@color/md3_brand_gradient_start"
                android:endColor="@color/md3_brand_gradient_end"
                android:centerColor="#B317120F" />
        </shape>
    </item>
</layer-list>
""",
}

for name, content in FILES.items():
    with open(os.path.join(OUT, name), "w", encoding="utf-8") as f:
        f.write(content)
    print("written", name)
print("total", len(FILES))
