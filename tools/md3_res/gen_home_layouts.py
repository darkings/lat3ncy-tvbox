# -*- coding: utf-8 -*-
"""Rewrite home-related layouts with MD3 styling."""

import os

OUT = r"C:/Users/Jie/Projects/lat3ncy-tvbox/tools/md3_res"

# ---- activity_home.xml: top bar with brand mark + time pill ----
ACTIVITY_HOME = """<?xml version="1.0" encoding="utf-8"?>
<androidx.constraintlayout.widget.ConstraintLayout xmlns:android="http://schemas.android.com/apk/res/android"
    xmlns:app="http://schemas.android.com/apk/res-auto"
    xmlns:tools="http://schemas.android.com/tools"
    android:layout_width="match_parent"
    android:layout_height="match_parent">

    <LinearLayout
        android:id="@+id/topLayout"
        android:layout_width="match_parent"
        android:layout_height="@dimen/vs_48"
        android:layout_marginLeft="@dimen/vs_35"
        android:layout_marginTop="@dimen/vs_12"
        android:layout_marginRight="@dimen/vs_35"
        android:background="@drawable/ponyo_top_bar"
        android:gravity="center_vertical"
        android:orientation="horizontal"
        android:paddingLeft="@dimen/vs_20"
        android:paddingRight="@dimen/vs_16"
        app:layout_constraintLeft_toLeftOf="parent"
        app:layout_constraintRight_toRightOf="parent"
        app:layout_constraintTop_toTopOf="parent">

        <!-- Brand mark: MD3 primary-container tile + waves -->
        <LinearLayout
            android:layout_width="@dimen/vs_38"
            android:layout_height="@dimen/vs_38"
            android:background="@drawable/md3_brand_mark"
            android:gravity="center"
            android:orientation="horizontal">

            <ImageView
                android:layout_width="@dimen/vs_28"
                android:layout_height="@dimen/vs_28"
                android:contentDescription="@string/app_name"
                android:src="@drawable/icon_brand_waves"
                app:tint="@color/md3_on_primary" />
        </LinearLayout>

        <TextView
            android:id="@+id/tvName"
            android:layout_width="wrap_content"
            android:layout_height="match_parent"
            android:layout_marginLeft="@dimen/vs_14"
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
            android:gravity="center"
            android:includeFontPadding="false"
            android:layout_marginLeft="@dimen/vs_12"
            android:layout_marginTop="@dimen/vs_4"
            android:layout_marginRight="@dimen/vs_8"
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

# ---- item_home_sort.xml: MD3 pill tab ----
ITEM_HOME_SORT = """<?xml version="1.0" encoding="utf-8"?>
<LinearLayout xmlns:android="http://schemas.android.com/apk/res/android"
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
        android:layout_width="@dimen/vs_24"
        android:layout_height="@dimen/vs_24"
        android:layout_gravity="center"
        android:layout_marginStart="@dimen/vs_3"
        android:layout_marginLeft="@dimen/vs_3"
        android:src="@drawable/icon_filter"
        app:tint="@color/md3_icon_tint"
        android:visibility="gone" />

    <ImageView
        android:id="@+id/tvFilterColor"
        android:layout_width="@dimen/vs_24"
        android:layout_height="@dimen/vs_24"
        android:layout_gravity="center"
        android:layout_marginStart="@dimen/vs_3"
        android:layout_marginLeft="@dimen/vs_3"
        android:src="@drawable/icon_filter"
        app:tint="@color/md3_primary"
        android:visibility="gone" />

</LinearLayout>
"""


# ---- fragment_user.xml: MD3 tonal action buttons ----
def action_button(btn_id, icon_res, label, next_focus_left=None, next_focus_right=None):
    extra = ""
    if next_focus_left:
        extra += ' android:nextFocusLeft="@+id/%s"' % next_focus_left
    if next_focus_right:
        extra += ' android:nextFocusRight="@+id/%s"' % next_focus_right
    return f'''            <LinearLayout
                android:id="@+id/{btn_id}"
                android:layout_width="wrap_content"
                android:layout_height="@dimen/vs_56"
                android:layout_gravity="center"
                android:layout_margin="@dimen/vs_5"
                android:background="@drawable/shape_home_action_focus"
                android:clipChildren="false"
                android:clipToPadding="false"
                android:focusable="true"{extra}
                android:orientation="horizontal"
                android:paddingLeft="@dimen/vs_16"
                android:paddingTop="@dimen/vs_8"
                android:paddingRight="@dimen/vs_16"
                android:paddingBottom="@dimen/vs_8">

                <androidx.appcompat.widget.AppCompatImageView
                    android:layout_width="@dimen/vs_28"
                    android:layout_height="@dimen/vs_28"
                    android:layout_gravity="center"
                    android:src="@drawable/{icon_res}"
                    app:tint="@color/md3_icon_tint" />

                <TextView
                    android:layout_width="wrap_content"
                    android:layout_height="wrap_content"
                    android:layout_gravity="center"
                    android:layout_marginLeft="@dimen/vs_10"
                    android:focusable="false"
                    android:focusableInTouchMode="false"
                    android:gravity="center"
                    android:text="{label}"
                    android:textAlignment="gravity"
                    android:textColor="@color/md3_action_text"
                    android:textSize="@dimen/ts_22" />

            </LinearLayout>
'''


BUTTONS = [
    ("tvHistory", "icon_history", "历史", None, None),
    ("tvLive", "icon_live", "直播", None, None),
    ("tvSearch", "icon_search", "搜索", None, None),
    ("tvPush", "icon_push", "推送", None, None),
    ("tvFavorite", "icon_collect", "收藏", None, None),
    ("tvSetting", "icon_setting", "设置", "tvHistory", None),
]

buttons_xml = "\n".join(action_button(*b) for b in BUTTONS)

FRAGMENT_USER = f"""<?xml version="1.0" encoding="utf-8"?>
<RelativeLayout xmlns:android="http://schemas.android.com/apk/res/android"
    xmlns:app="http://schemas.android.com/apk/res-auto"
    android:layout_width="match_parent"
    android:layout_height="match_parent"
    android:orientation="vertical"
    android:paddingLeft="@dimen/vs_40"
    android:paddingRight="@dimen/vs_40">

    <RelativeLayout
        android:layout_width="wrap_content"
        android:layout_height="wrap_content">

        <LinearLayout
            android:id="@+id/tvUserHome"
            android:layout_width="wrap_content"
            android:layout_height="wrap_content"
            android:focusable="false"
            android:focusableInTouchMode="false"
            android:orientation="horizontal">

{buttons_xml}
        </LinearLayout>
        <com.owen.tvrecyclerview.widget.TvRecyclerView
            android:id="@+id/tvHotList"
            android:layout_width="match_parent"
            android:layout_height="wrap_content"
            android:clipChildren="true"
            android:clipToPadding="false"
            android:layout_below="@+id/tvUserHome"
            app:tv_horizontalSpacingWithMargins="@dimen/vs_10"
            app:tv_selectedItemIsCentered="true"
            app:tv_verticalSpacingWithMargins="@dimen/vs_10"
            android:visibility="gone" />
    </RelativeLayout>

</RelativeLayout>
"""

files = {
    "activity_home.xml": ACTIVITY_HOME,
    "item_home_sort.xml": ITEM_HOME_SORT,
    "fragment_user.xml": FRAGMENT_USER,
}
for name, content in files.items():
    with open(os.path.join(OUT, name), "w", encoding="utf-8") as f:
        f.write(content)
    print("written", name)
