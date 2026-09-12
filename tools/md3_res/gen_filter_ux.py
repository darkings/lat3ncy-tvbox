# -*- coding: utf-8 -*-
"""Filter UX: no badge bg, dual icons, open/close animation, MD3 value pills."""

import os

OUT = r"C:/Users/Jie/Projects/lat3ncy-tvbox/tools/md3_res"

# ---- item_home_sort.xml: no badge background ----
ITEM_HOME_SORT = """<?xml version="1.0" encoding="utf-8"?>
<LinearLayout xmlns:android="http://schemas.android.com/apk/res/android"
    xmlns:app="http://schemas.android.com/apk/res-auto"
    android:layout_width="wrap_content"
    android:layout_height="@dimen/vs_40"
    android:background="@drawable/button_home_sort_focus"
    android:clickable="true"
    android:focusable="true"
    android:focusableInTouchMode="true"
    android:orientation="horizontal"
    android:paddingLeft="@dimen/vs_16"
    android:paddingRight="@dimen/vs_16">

    <TextView
        android:id="@+id/tvTitle"
        android:layout_width="wrap_content"
        android:layout_height="wrap_content"
        android:layout_gravity="center"
        android:focusable="false"
        android:gravity="center"
        android:textColor="@color/md3_action_text"
        android:textSize="@dimen/ts_22" />

    <ImageView
        android:id="@+id/tvFilter"
        android:layout_width="@dimen/vs_26"
        android:layout_height="@dimen/vs_26"
        android:layout_gravity="center"
        android:layout_marginStart="@dimen/vs_4"
        android:layout_marginLeft="@dimen/vs_4"
        android:src="@drawable/icon_filter"
        app:tint="@color/md3_icon_tint"
        android:visibility="gone" />

    <ImageView
        android:id="@+id/tvFilterColor"
        android:layout_width="@dimen/vs_26"
        android:layout_height="@dimen/vs_26"
        android:layout_gravity="center"
        android:layout_marginStart="@dimen/vs_4"
        android:layout_marginLeft="@dimen/vs_4"
        android:src="@drawable/icon_filter"
        app:tint="@color/md3_primary"
        android:visibility="gone" />

</LinearLayout>
"""

# ---- icon_filter_off.xml: filter_alt_off (panel open state) ----
ICON_FILTER_OFF = """<?xml version="1.0" encoding="utf-8"?>
<vector xmlns:android="http://schemas.android.com/apk/res/android"
    android:width="48dp"
    android:height="48dp"
    android:viewportWidth="24"
    android:viewportHeight="24">
  <path
      android:pathData="M21,1L7,1c-0.26,0 -0.51,0.01 -0.75,0.04L8.27,3.27 21,3.27v-2.27zM10.17,8.41L19,8.41l-6.17,7.64v-6.02l-2.66,-2.61zM2.81,2.81L1.39,4.22 4.18,7.01l-0.15,0.19 3.81,4.72L7.83,19h4v-5.17l5.37,5.37 1.41,-1.41L2.81,2.81z"
      android:fillColor="#FFFFFFFF"/>
</vector>
"""

# ---- md3_filter_value.xml: pill selector (normal / focus / selected) ----
MD3_FILTER_VALUE = """<?xml version="1.0" encoding="utf-8"?>
<selector xmlns:android="http://schemas.android.com/apk/res/android">
    <item android:state_focused="true">
        <shape>
            <corners android:radius="@dimen/md3_corner_full" />
            <solid android:color="@color/md3_primary" />
            <stroke android:width="@dimen/md3_focus_stroke_width" android:color="@color/md3_on_primary" />
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

# ---- md3_filter_value_selected.xml: selected state (primary fill) ----
MD3_FILTER_VALUE_SELECTED = """<?xml version="1.0" encoding="utf-8"?>
<shape xmlns:android="http://schemas.android.com/apk/res/android">
    <corners android:radius="@dimen/md3_corner_full" />
    <solid android:color="@color/md3_primary" />
</shape>
"""

# ---- item_grid_filter.xml: MD3 label row ----
ITEM_GRID_FILTER = """<?xml version="1.0" encoding="utf-8"?>
<LinearLayout xmlns:android="http://schemas.android.com/apk/res/android"
    xmlns:app="http://schemas.android.com/apk/res-auto"
    xmlns:tools="http://schemas.android.com/tools"
    android:layout_width="match_parent"
    android:layout_height="wrap_content"
    android:focusable="false"
    android:orientation="horizontal"
    android:padding="@dimen/vs_1">

    <TextView
        android:id="@+id/filterName"
        android:layout_width="wrap_content"
        android:layout_height="match_parent"
        android:layout_gravity="center"
        android:layout_marginEnd="@dimen/vs_10"
        android:layout_marginRight="@dimen/vs_10"
        android:gravity="center"
        android:textAlignment="gravity"
        android:textColor="@color/md3_on_surface_variant"
        android:textSize="@dimen/ts_22"
        android:textStyle="bold"
        tools:text="类型" />

    <com.owen.tvrecyclerview.widget.TvRecyclerView
        android:id="@+id/mFilterKv"
        android:layout_width="match_parent"
        android:layout_height="wrap_content"
        android:clipChildren="false"
        android:clipToPadding="false"
        app:tv_horizontalSpacingWithMargins="@dimen/vs_5"
        app:tv_selectedItemIsCentered="true"
        app:tv_verticalSpacingWithMargins="@dimen/vs_5" />

</LinearLayout>
"""

# ---- item_grid_filter_value.xml: MD3 pill value ----
ITEM_GRID_FILTER_VALUE = """<?xml version="1.0" encoding="utf-8"?>
<TextView xmlns:android="http://schemas.android.com/apk/res/android"
    android:id="@+id/filterValue"
    android:layout_width="wrap_content"
    android:layout_height="wrap_content"
    android:layout_margin="@dimen/vs_5"
    android:background="@drawable/md3_filter_value"
    android:ellipsize="end"
    android:focusable="true"
    android:gravity="center_vertical"
    android:paddingLeft="@dimen/vs_10"
    android:paddingRight="@dimen/vs_10"
    android:paddingTop="@dimen/vs_6"
    android:paddingBottom="@dimen/vs_6"
    android:singleLine="true"
    android:textColor="@color/md3_on_surface"
    android:textSize="@dimen/ts_20" />
"""

# ---- animations ----
FILTER_IN = """<?xml version="1.0" encoding="utf-8"?>
<set xmlns:android="http://schemas.android.com/apk/res/android"
    android:interpolator="@android:interpolator/decelerate_cubic">
    <translate
        android:fromYDelta="-12%"
        android:toYDelta="0%"
        android:duration="250" />
    <alpha
        android:fromAlpha="0"
        android:toAlpha="1"
        android:duration="250" />
</set>
"""

FILTER_OUT = """<?xml version="1.0" encoding="utf-8"?>
<set xmlns:android="http://schemas.android.com/apk/res/android"
    android:interpolator="@android:interpolator/accelerate_cubic">
    <translate
        android:fromYDelta="0%"
        android:toYDelta="-8%"
        android:duration="180" />
    <alpha
        android:fromAlpha="1"
        android:toAlpha="0"
        android:duration="180" />
</set>
"""

files = {
    "item_home_sort.xml": ITEM_HOME_SORT,
    "icon_filter_off.xml": ICON_FILTER_OFF,
    "md3_filter_value.xml": MD3_FILTER_VALUE,
    "md3_filter_value_selected.xml": MD3_FILTER_VALUE_SELECTED,
    "item_grid_filter.xml": ITEM_GRID_FILTER,
    "item_grid_filter_value.xml": ITEM_GRID_FILTER_VALUE,
    "filter_dialog_in.xml": FILTER_IN,
    "filter_dialog_out.xml": FILTER_OUT,
}
for name, content in files.items():
    with open(os.path.join(OUT, name), "w", encoding="utf-8") as f:
        f.write(content)
    print("written", name)
