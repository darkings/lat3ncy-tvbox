# -*- coding: utf-8 -*-
"""P2-4：fragment_model.xml 插入"减少动态效果"开关行（llDynamicColor 之后）。"""

from pathlib import Path

path = Path("android/app/src/main/res/layout/fragment_model.xml")
data = path.read_text(encoding="utf-8")

anchor = 'android:id="@+id/llDynamicColor"'
idx = data.find(anchor)
assert idx != -1, "未找到 llDynamicColor"

# 找到该 LinearLayout 的闭合 </LinearLayout>
close = data.find("</LinearLayout>", idx)
assert close != -1

new_block = """
            <LinearLayout
                    android:id="@+id/llReduceMotion"
                    android:layout_width="match_parent"
                    android:layout_height="@dimen/vs_50"
                    android:layout_marginBottom="@dimen/vs_10"
                    android:background="@drawable/shape_setting_model_focus"
                    android:focusable="true"
                    android:gravity="center_vertical"
                    android:orientation="horizontal"
                    android:paddingLeft="@dimen/vs_20"
                    android:paddingRight="@dimen/vs_20">

                <TextView
                        android:layout_width="wrap_content"
                        android:layout_height="wrap_content"
                        android:text="减少动态效果"
                        android:textColor="@color/md3_on_surface"
                        android:textSize="@dimen/ts_24" />

                <Space
                        android:layout_width="0dp"
                        android:layout_height="wrap_content"
                        android:layout_weight="1" />

                <TextView
                        android:id="@+id/tvReduceMotion"
                        android:layout_width="wrap_content"
                        android:layout_height="wrap_content"
                        android:text="关"
                        android:textColor="@color/md3_on_surface"
                        android:textSize="@dimen/ts_24" />
            </LinearLayout>
"""

data = data[:close] + new_block + data[close:]
path.write_text(data, encoding="utf-8")
print("插入完成")
