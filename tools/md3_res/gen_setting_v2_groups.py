# -*- coding: utf-8 -*-
"""V2-P0-1：fragment_model.xml 六分组重构。

- 删除中间分组标题（六组由左侧导航标识）
- 混合行按组拆分（每行最多两列）
- 每个行容器加 android:tag="group_xxx"
"""

import copy
import xml.etree.ElementTree as ET
from pathlib import Path

ET.register_namespace("android", "http://schemas.android.com/apk/res/android")
A = "{http://schemas.android.com/apk/res/android}"
path = Path("android/app/src/main/res/layout/fragment_model.xml")
root = ET.parse(path).getroot()

# 1. 找根 vertical LinearLayout
root_ll = None
for e in root.iter():
    if (
        e.tag.split("}")[-1] == "LinearLayout"
        and e.get(A + "orientation") == "vertical"
    ):
        root_ll = e
        break
assert root_ll is not None

children = list(root_ll)

# 2. 删除标题 TextView（通用/播放/外观/数据/关于）
for child in list(root_ll):
    if child.tag.split("}")[-1] == "TextView" and child.get(A + "text", "") in (
        "通用",
        "播放",
        "外观",
        "数据",
        "关于",
    ):
        root_ll.remove(child)

children = list(root_ll)
print("行数(删标题后):", len(children))
for i, c in enumerate(children):
    ids = [e.get(A + "id", "") for e in c.iter() if "@+id/ll" in e.get(A + "id", "")]
    ids = [x.replace("@+id/", "") for x in ids]
    print(f"  [{i}] {ids}")


def row_template():
    """新行容器（全宽、横向、vs_60、不可聚焦容器）。"""
    ll = ET.Element("LinearLayout")
    ll.set(A + "layout_width", "match_parent")
    ll.set(A + "layout_height", "@dimen/vs_60")
    ll.set(A + "layout_marginBottom", "@dimen/vs_10")
    ll.set(A + "focusable", "false")
    ll.set(A + "orientation", "horizontal")
    return ll


def full_width(item):
    """把 ll 项改为全宽（去掉 weight 半宽）。"""
    item.set(A + "layout_width", "match_parent")
    item.attrib.pop(A + "layout_weight", None)
    item.set(A + "layout_marginEnd", "@dimen/vs_0")
    item.set(A + "layout_marginRight", "@dimen/vs_0")
    return item


def make_row(tag, items):
    row = row_template()
    row.set(A + "tag", tag)
    for it in items:
        row.append(it)
    return row


# 3. 行索引（删标题后重新定位）：按 ll 控件定位
def find_row(pred):
    for i, c in enumerate(list(root_ll)):
        ids = [
            e.get(A + "id", "") for e in c.iter() if "@+id/ll" in e.get(A + "id", "")
        ]
        ids = [x.replace("@+id/", "") for x in ids]
        if pred(ids):
            return c
    raise AssertionError("行未找到")


row_debug = find_row(lambda ids: "llDebug" in ids)
row_dyn = find_row(lambda ids: "llDynamicColor" in ids)
row_api = find_row(lambda ids: "llApi" in ids)
row_homeapi = find_row(lambda ids: "llHomeApi" in ids)
row_homerec = find_row(lambda ids: "llHomeRec" in ids)
row_play = find_row(lambda ids: "llPlay" in ids)
row_danmu = None
for c in list(root_ll):
    if any("danmuOpen" in e.get(A + "id", "") for e in c.iter()):
        row_danmu = c
        break
assert row_danmu is not None
row_render_dns = find_row(lambda ids: "llRender" in ids)
row_parse_search = find_row(lambda ids: "llParseWebVew" in ids)
row_wp_scale = find_row(lambda ids: "llWp" in ids)
row_ijk_cache = find_row(lambda ids: "llIjkCachePlay" in ids)

# 4. 逐行处理


def sub_items(row):
    """行容器的直接子项（ll 项或组合容器）。"""
    return list(row)


# --- 通用组 ---
row_debug.set(A + "tag", "group_general")
row_api.set(A + "tag", "group_general")
row_homeapi.set(A + "tag", "group_general")

# --- 外观组 ---
row_dyn.set(A + "tag", "group_appearance")

# --- 内容组：行[5]（llHomeRec 复合项 | llSearchView，2 列合规）直接归内容 ---
homerec_items = sub_items(row_homerec)
print("DEBUG 行[5] 子项数:", len(homerec_items))
for _i, _it in enumerate(homerec_items):
    _ids = [e.get(A + "id", "") for e in _it.iter() if "@+id/" in e.get(A + "id", "")]
    print(f"  DEBUG 子[{_i}] ids={_ids}")
assert len(homerec_items) == 2, f"行[5] 子项数: {len(homerec_items)}"
row_homerec.set(A + "tag", "group_content")

# --- 播放组：行[6] llPlay/llMediaCodec（2 列原样）、行[7] 弹幕 ---
row_play.set(A + "tag", "group_player")
row_danmu.set(A + "tag", "group_player")

# --- 行[8] llRender | llDns → 播放/网络 ---
render_dns_items = sub_items(row_render_dns)
assert len(render_dns_items) == 2
i_render, i_dns = render_dns_items
root_ll.remove(row_render_dns)
root_ll.append(make_row("group_player", [full_width(copy.deepcopy(i_render))]))
root_ll.append(make_row("group_network", [full_width(copy.deepcopy(i_dns))]))

# --- 行[9] llParseWebVew | [llSearchTv|llHistoryNum] → 播放/内容 ---
parse_items = sub_items(row_parse_search)
assert len(parse_items) == 2
i_parse, i_search = parse_items
root_ll.remove(row_parse_search)
root_ll.append(make_row("group_player", [full_width(copy.deepcopy(i_parse))]))
root_ll.append(make_row("group_content", [copy.deepcopy(i_search)]))

# --- 行[10] [llWp|llWpRecovery] | llScale → 外观/播放 ---
wp_items = sub_items(row_wp_scale)
assert len(wp_items) == 2
i_wp, i_scale = wp_items
root_ll.remove(row_wp_scale)
root_ll.append(make_row("group_appearance", [copy.deepcopy(i_wp)]))
root_ll.append(make_row("group_player", [full_width(copy.deepcopy(i_scale))]))

# --- 行[11] llIjkCachePlay/llClearCache | llBackup/llAbout → 播放/数据 ---
ijk_items = sub_items(row_ijk_cache)
assert len(ijk_items) == 2
i_ijk, i_backup = ijk_items
# i_ijk 内部含 llIjkCachePlay + llClearCache（2 个孙项）
ijk_subs = list(i_ijk)
clear_subs = list(i_backup)
assert len(ijk_subs) == 3, f"i_ijk 孙项: {len(ijk_subs)}"
assert len(clear_subs) == 3, f"i_backup 孙项: {len(clear_subs)}"
i_ijk_play, _, i_clearcache = ijk_subs  # 中间可能为装饰
i_backup2, _, i_about = clear_subs
root_ll.remove(row_ijk_cache)
root_ll.append(make_row("group_player", [full_width(copy.deepcopy(i_ijk_play))]))
root_ll.append(
    make_row(
        "group_data",
        [full_width(copy.deepcopy(i_clearcache)), full_width(copy.deepcopy(i_backup2))],
    )
)
root_ll.append(make_row("group_data", [full_width(copy.deepcopy(i_about))]))

# 5. 序列化输出
ET.indent(root, space="    ")
path.write_text(
    '<?xml version="1.0" encoding="utf-8"?>\n' + ET.tostring(root, encoding="unicode"),
    encoding="utf-8",
)

# 6. 验证
print("\n=== 输出行结构 ===")
for c in list(root_ll):
    ids = [e.get(A + "id", "") for e in c.iter() if "@+id/ll" in e.get(A + "id", "")]
    ids = [x.replace("@+id/", "") for x in ids]
    print(f"  tag={c.get(A + 'tag', ''):18} {ids}")
