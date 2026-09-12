# -*- coding: utf-8 -*-
"""Top bar: transparent ponyo icon (no mask). Filter button: circular badge."""

import os

OUT = r"C:/Users/Jie/Projects/lat3ncy-tvbox/tools/md3_res"

# ---- Filter icon circular badge ----
MD3_FILTER_CHIP = """<?xml version="1.0" encoding="utf-8"?>
<selector xmlns:android="http://schemas.android.com/apk/res/android">
    <item android:state_focused="true">
        <shape android:shape="oval">
            <solid android:color="@color/md3_focus_fill" />
        </shape>
    </item>
    <item>
        <shape android:shape="oval">
            <solid android:color="@color/md3_surface_container_high" />
        </shape>
    </item>
</selector>
"""

# ---- Filter icon badge with active filter (selected) ----
MD3_FILTER_CHIP_ACTIVE = """<?xml version="1.0" encoding="utf-8"?>
<shape xmlns:android="http://schemas.android.com/apk/res/android" android:shape="oval">
    <solid android:color="@color/md3_primary" />
</shape>
"""

# ---- activity_home.xml: ponyo transparent icon ----
ACTIVITY_HOME = """<?xml version="1.0" encoding="utf-8"?>
<androidx.constraintlayout.widget.ConstraintLayout xmlns:android="http://schemas.android.com/apk/res/android"
    xmlns:app="http://schemas.android.com/apk/res-auto"
    xmlns:tools="http://schemas.android.com/tools"
    android:layout_width="match_parent"
    android:layout_height="match_parent">

    <LinearLayout
        android:id="@+id/topLayout"
        android:layout_width="match_parent"
        android:layout_height="@dimen/vs_44"
        android:layout_marginLeft="@dimen/vs_35"
        android:layout_marginTop="@dimen/vs_12"
        android:layout_marginRight="@dimen/vs_35"
        android:background="@drawable/ponyo_top_bar"
        android:gravity="center_vertical"
        android:orientation="horizontal"
        android:paddingLeft="@dimen/vs_16"
        android:paddingRight="@dimen/vs_16"
        app:layout_constraintLeft_toLeftOf="parent"
        app:layout_constraintRight_toRightOf="parent"
        app:layout_constraintTop_toTopOf="parent">

        <!-- Ponyo transparent icon (no background mask) -->
        <ImageView
            android:layout_width="@dimen/vs_38"
            android:layout_height="@dimen/vs_38"
            android:contentDescription="@string/app_name"
            android:src="@drawable/ponyo_icon" />

        <TextView
            android:id="@+id/tvName"
            android:layout_width="wrap_content"
            android:layout_height="match_parent"
            android:layout_marginLeft="@dimen/vs_12"
            android:focusable="false"
            android:focusableInTouchMode="false"
            android:gravity="left|center_vertical"
            android:ellipsize="end"
            android:maxLines="1"
            android:text="@string/app_name"
            android:textAlignment="gravity"
            android:textColor="@color/md3_on_surface"
            android:textSize="@dimen/ts_22"
            android:textStyle="bold" />

        <TextView
            android:id="@+id/tvDate"
            android:layout_width="@dimen/vs_0"
            android:layout_height="wrap_content"
            android:layout_gravity="center_vertical"
            android:layout_weight="1"
            android:focusable="false"
            android:focusableInTouchMode="false"
            android:background="@drawable/md3_time_pill"
            android:gravity="right|center_vertical"
            android:includeFontPadding="false"
            android:layout_marginLeft="@dimen/vs_12"
            android:layout_marginTop="@dimen/vs_4"
            android:layout_marginRight="@dimen/vs_4"
            android:layout_marginBottom="@dimen/vs_4"
            android:maxLines="1"
            android:textAlignment="gravity"
            android:textColor="@color/md3_primary"
            android:textSize="@dimen/ts_16"
            tools:text="2026/06/16  周二  15:01" />
    </LinearLayout>

    <LinearLayout
        android:id="@+id/contentLayout"
        android:layout_width="@dimen/vs_0"
        android:layout_height="@dimen/vs_0"
        android:clipChildren="false"
        android:clipToPadding="false"
        android:orientation="vertical"
        app:layout_constraintBottom_toBottomOf="parent"
        app:layout_constraintLeft_toLeftOf="parent"
        app:layout_constraintRight_toRightOf="parent"
        app:layout_constraintTop_toBottomOf="@+id/topLayout">

        <com.owen.tvrecyclerview.widget.TvRecyclerView
            android:id="@+id/mGridView"
            android:layout_width="match_parent"
            android:layout_height="wrap_content"
            android:layout_marginTop="@dimen/vs_10"
            android:layout_marginBottom="@dimen/vs_10"
            android:paddingLeft="@dimen/vs_50"
            android:paddingRight="@dimen/vs_50"
            app:tv_selectedItemIsCentered="true" />

        <com.github.tvbox.osc.ui.tv.widget.NoScrollViewPager
            android:id="@+id/mViewPager"
            android:layout_width="match_parent"
            android:layout_height="match_parent" />
    </LinearLayout>

    <com.github.tvbox.osc.ui.tv.widget.PonyoPetView
        android:id="@+id/ponyoPet"
        android:layout_width="@dimen/vs_120"
        android:layout_height="@dimen/vs_130"
        android:layout_marginRight="@dimen/vs_24"
        android:layout_marginBottom="@dimen/vs_12"
        android:alpha="0.88"
        android:clickable="false"
        android:focusable="false"
        app:layout_constraintBottom_toBottomOf="parent"
        app:layout_constraintRight_toRightOf="parent" />
</androidx.constraintlayout.widget.ConstraintLayout>
"""

# ---- item_home_sort.xml: filter icon in circular badge ----
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
        android:background="@drawable/md3_filter_chip"
        android:padding="@dimen/vs_2"
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
        android:background="@drawable/md3_filter_chip_active"
        android:padding="@dimen/vs_2"
        android:src="@drawable/icon_filter"
        app:tint="@color/md3_on_primary"
        android:visibility="gone" />

</LinearLayout>
"""

files = {
    "md3_filter_chip.xml": MD3_FILTER_CHIP,
    "md3_filter_chip_active.xml": MD3_FILTER_CHIP_ACTIVE,
    "activity_home.xml": ACTIVITY_HOME,
    "item_home_sort.xml": ITEM_HOME_SORT,
}
for name, content in files.items():
    with open(os.path.join(OUT, name), "w", encoding="utf-8") as f:
        f.write(content)
    print("written", name)
