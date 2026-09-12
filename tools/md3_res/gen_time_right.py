# -*- coding: utf-8 -*-
"""Time display: transparent background, right aligned."""

import os

OUT = r"C:/Users/Jie/Projects/lat3ncy-tvbox/tools/md3_res"

# ---- Time pill: fully transparent (text only) ----
MD3_TIME_PILL = """<?xml version="1.0" encoding="utf-8"?>
<shape xmlns:android="http://schemas.android.com/apk/res/android">
    <corners android:radius="@dimen/md3_corner_full" />
    <solid android:color="@android:color/transparent" />
</shape>
"""

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

        <!-- Ponyo app icon (brand) -->
        <ImageView
            android:layout_width="@dimen/vs_36"
            android:layout_height="@dimen/vs_36"
            android:contentDescription="@string/app_name"
            android:src="@drawable/app_icon" />

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

files = {
    "md3_time_pill.xml": MD3_TIME_PILL,
    "activity_home.xml": ACTIVITY_HOME,
}
for name, content in files.items():
    with open(os.path.join(OUT, name), "w", encoding="utf-8") as f:
        f.write(content)
    print("written", name)
