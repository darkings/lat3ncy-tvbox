# -*- coding: utf-8 -*-
"""Extract Material Symbols Rounded (wght=600, FILL=1) glyphs as Android vector drawables."""

import os
import re

from fontTools.misc.transform import Transform
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont

FONT = r"C:/Users/Jie/Projects/lat3ncy-tvbox/tools/md3_res/MaterialSymbolsRounded.ttf"
OUT = r"C:/Users/Jie/Projects/lat3ncy-tvbox/tools/md3_res"

# 目标图标：文件名 -> glyph 名
TARGETS = {
    "icon_search.xml": "search",
    "icon_history.xml": "history",
    "icon_live.xml": "live_tv",
    "icon_collect.xml": "favorite",
    "icon_setting.xml": "settings",
    "icon_push.xml": "send",
    "icon_back.xml": "keyboard_backspace",
    "icon_clear.xml": "close",
    "icon_delete.xml": "delete",
    "icon_filter.xml": "filter_list",
    "icon_filter_off.xml": "filter_alt_off",
    "icon_lock.xml": "lock",
    "icon_unlock.xml": "lock_open",
    "icon_error.xml": "warning",
    "icon_play.xml": "play_arrow",
    "icon_empty.xml": "movie",
    "icon_loading.xml": "sync",
    "icon_pre.xml": "skip_previous",
    "icon_video.xml": "video_library",
    "icon_img_placeholder.xml": "image",
}

SCALE = 24.0 / 1000.0  # 1000em -> 24 viewport

# 字体坐标 y 轴向上，Android viewport y 轴向下：y' = 24 - y*SCALE
# 注意：不能用 Transform().scale().translate() 链式调用（fontTools 左乘语义会把平移量一起缩放），
# 必须直接构造矩阵 Transform(sx, 0, 0, -sx, 0, 24)
TRANSFORM = Transform(SCALE, 0, 0, -SCALE, 0, 24)


def extract(font, glyph_name):
    glyph_set = font.getGlyphSet()
    if glyph_name not in glyph_set:
        return None
    pen = SVGPathPen(glyph_set)
    tpen = TransformPen(pen, TRANSFORM)
    glyph_set[glyph_name].draw(tpen)
    return pen.getCommands()


def fix_implicit_lineto(path):
    # SVGPathPen 输出 "M x y x2 y2 ..."（moveto 后隐式 lineto），
    # Android PathParser 不支持该语法，拆成显式 L 命令
    def repl(m):
        rest = m.group(2)
        rest = re.sub(r"\s*(-?\d+\.?\d*)\s+(-?\d+\.?\d*)", r" L\1 \2", rest)
        return m.group(1) + rest

    return re.sub(
        r"(M\s*-?\d+\.?\d*\s+-?\d+\.?\d*)((?:\s+-?\d+\.?\d*\s+-?\d+\.?\d*)+)",
        repl,
        path,
    )


def make_xml(path_data):
    path_data = fix_implicit_lineto(path_data)
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<vector xmlns:android="http://schemas.android.com/apk/res/android"\n'
        '    android:width="48dp"\n'
        '    android:height="48dp"\n'
        '    android:viewportWidth="24"\n'
        '    android:viewportHeight="24">\n'
        "  <path\n"
        '      android:pathData="%s"\n'
        '      android:fillColor="#FFFFFFFF"/>\n'
        "</vector>\n"
    ) % path_data


def main():
    # 实例化变量字体为静态实例：Rounded 600、填充风格、opsz 24
    from fontTools.varLib.mutator import instantiateVariableFont

    font = TTFont(FONT)
    font = instantiateVariableFont(
        font, {"wght": 600, "FILL": 1, "GRAD": 0, "opsz": 24}
    )
    missing = []
    for name, glyph in TARGETS.items():
        path = extract(font, glyph)
        if path is None:
            missing.append(glyph)
            print("MISSING:", glyph)
            continue
        with open(os.path.join(OUT, name), "w", encoding="utf-8") as f:
            f.write(make_xml(path))
        print("OK %s <- %s (%d chars)" % (name, glyph, len(path)))
    print("done, missing:", missing)


if __name__ == "__main__":
    main()
