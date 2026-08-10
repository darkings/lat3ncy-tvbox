# -*- coding: utf-8 -*-
"""fragment_model.xml 插入分组标题（P0-4 设置页分组）。"""

from pathlib import Path

path = Path("android/app/src/main/res/layout/fragment_model.xml")
lines = path.read_text(encoding="utf-8").splitlines(keepends=True)

# (插入行号, 组名) —— 行号按 1 基
groups = [
    (27, "通用"),
    (560, "播放"),
    (1115, "外观"),
    (1349, "数据"),
    (1433, "关于"),
]


def title_block(name: str) -> str:
    return (
        "            <TextView\n"
        '                    android:layout_width="match_parent"\n'
        '                    android:layout_height="wrap_content"\n'
        '                    android:layout_marginTop="@dimen/vs_16"\n'
        '                    android:layout_marginBottom="@dimen/vs_8"\n'
        '                    android:focusable="false"\n'
        '                    android:paddingLeft="@dimen/vs_10"\n'
        f'                    android:text="{name}"\n'
        '                    android:textColor="@color/md3_tertiary"\n'
        '                    android:textSize="@dimen/ts_18" />\n'
        "\n"
    )


# 从后往前插入（避免行号偏移）
for lineno, name in reversed(groups):
    lines.insert(lineno - 1, title_block(name))

path.write_text("".join(lines), encoding="utf-8")
print("插入完成，新行数:", len(lines))
