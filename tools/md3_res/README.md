# Ponyo TV MD3 资源资料包

除本说明外，本目录包含 80 个既有实现或生成文件，以及 1 份随包许可证：Android XML 资源、Material Symbols 提取后的矢量图标、页面/组件样式样例、生成脚本和对应的 Apache-2.0 许可文本。生成图标所需的字体文件体积较大且可重新获取，不纳入版本库，获取方式见下文。

它们是 UI 方案的可复用材料，不表示已经自动应用到 android 工作副本。

## 分类

- 设计 token：colors.xml、dimens.xml、styles.xml。
- 页面/布局样例：activity_home.xml、fragment_user.xml、dialog_grid_filter.xml、item_grid_filter.xml、item_grid_filter_value.xml、item_home_sort.xml。
- 品牌容器：app_bg_layer.xml、ponyo_top_bar.xml、ponyo_panel.xml、ponyo_poster_surface.xml、md3_brand_mark.xml、icon_brand_waves.xml。
- 焦点和控件：shape_home_action_focus.xml、shape_source_series_focus.xml、shape_user_focus.xml、button_home_sort_focus.xml、button_detail_play.xml、button_dialog_main.xml、input_search.xml。
- 播放与直播：seekbar_style.xml、seekbar_thumb_normal.xml、seekbar_thumb_pressed.xml、shape_play_bottom.xml、shape_play_mobile_center.xml、box_controller_top_bg.xml、bg_channel_list.xml、shape_live_channel_num.xml。
- 状态：icon_loading.xml、icon_empty.xml、icon_error.xml、icon_img_placeholder.xml。
- 功能图标：icon_back.xml、icon_history.xml、icon_live.xml、icon_search.xml、icon_push.xml、icon_collect.xml、icon_setting.xml、icon_clear.xml、icon_delete.xml、icon_filter.xml、icon_filter_off.xml、icon_lock.xml、icon_unlock.xml、icon_play.xml、icon_pre.xml、icon_video.xml。
- 生成脚本：gen_drawables.py、gen_home_res.py、gen_home_layouts.py、gen_topbar_fix.py、gen_transparent_topbar.py、gen_time_right.py、gen_ponyo_icon_filter.py、gen_filter_ux.py、gen_pages.py、gen_live.py、extract_symbols.py。
- 生成输入：MaterialSymbolsRounded.ttf（**不入库**，见「字体获取方式」）。
- 许可证：[LICENSE-MATERIAL-SYMBOLS.txt](LICENSE-MATERIAL-SYMBOLS.txt)。

## 字体获取方式

MaterialSymbolsRounded.ttf 体积 14.38 MB，仅用于提取 vector path，不作为 APK 运行时字体，因此不纳入版本库。需要重新生成图标时按以下信息获取：

| 项目 | 值 |
|:---|:---|
| 字体名 | Material Symbols Rounded |
| 来源 | Google Fonts（https://fonts.google.com/icons） |
| 文件大小 | 15080092 字节（14.38 MB） |
| MD5 | `5dfc6ea34d166a439e25574f69c4fad4` |
| SHA256 | `619eaa2f2e270723cf0cd06d2aba126ade66fee94e380c3e6a61e2e496279e0c` |

获取后放置到本目录，文件名必须为 MaterialSymbolsRounded.ttf，并核对上述校验值。xtract_symbols.py 中的 FONT 常量指向该路径。

## 使用规则

- 先以 docs/ui-audit/2026-08-10/materials/design-tokens.json 为最终 token 规范；本目录已有 values 文件是现状材料，不一定覆盖深度改造的全部值。
- 复制或生成资源前先比较目标文件，避免覆盖 android 工作副本中的用户改动。
- 生成脚本必须在临时目录运行并检查输出，再由人工选择性合并。
- MaterialSymbolsRounded.ttf 只用于提取 vector path，不应因为本方案新增为 APK 运行时字体。
- 字体或其衍生资源对外分发前，保留 [LICENSE-MATERIAL-SYMBOLS.txt](LICENSE-MATERIAL-SYMBOLS.txt) 及来源说明。
- 图标使用统一 tint；不要把 emoji 与矢量图标混在同一导航或控制条。
- 详情页旧的绿色、玫红按钮资源不属于最终规范。

## 配套文档

- 主方案：docs/ui-audit/2026-08-10/ponyo-tv-ui-deep-beautification-audit.md。
- 资料索引：docs/ui-audit/2026-08-10/materials/README.md。
- 页面映射：docs/ui-audit/2026-08-10/materials/resource-map.tsv。
- 验收清单：docs/ui-audit/2026-08-10/materials/qa-checklist.md。
