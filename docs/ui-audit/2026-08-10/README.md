# Ponyo TV UI 审计交付入口

本目录是 2026-08-10 全页面视觉审计、深度美化规范、证据截图和实施资料的统一入口。本轮只交付分析、设计规范和可复用资料，没有修改 Android App 实现。

## 实施基线

实施时按以下优先级取值：

1. [全页面视觉审计与深度美化方案](ponyo-tv-ui-deep-beautification-audit.md)：最终页面方案、组件规则、实施顺序和验收标准。
2. [资料包](materials/README.md)：可直接使用的 token、文案、动效、视觉板、资源映射和 QA 清单。
3. [PONYO_TV_DEEP_VISUAL_REDESIGN.md](PONYO_TV_DEEP_VISUAL_REDESIGN.md)：保留的补充分析稿，用于查看更细的现状描述和页面论证。

若两份长文在颜色、尺寸、单位、文案或动效上不一致，以主方案和 `materials` 中的机器可读文件为准。补充分析稿中的 `dp/sp` 与旧色值不作为最终实现参数。

## 交付完整性

| 方案需要 | 已交付资料 |
| --- | --- |
| 颜色、字体、栅格、焦点、组件尺寸 | [design-tokens.json](materials/design-tokens.json) |
| 可视化样式基准 | [style-board.svg](materials/style-board.svg) 与 [style-board.png](materials/style-board.png) |
| 全页面、状态与 20 个 Dialog 文案 | [copy-deck.json](materials/copy-deck.json) |
| 焦点、页面、加载、Dialog、角色动效 | [motion-spec.json](materials/motion-spec.json) |
| 44 张截图逐张识别与证据限制 | [screen-coverage.csv](materials/screen-coverage.csv) |
| Activity、Fragment、Dialog 到布局和材料的映射 | [resource-map.tsv](materials/resource-map.tsv) |
| 品牌位图、背景、图标、字体及权利状态 | [brand-assets.md](materials/brand-assets.md) |
| 80 个 Android XML、脚本和字体生成输入 | [tools/md3_res](../../../tools/md3_res) |
| 分辨率、遥控器、弱网、页面和 Dialog 验收 | [qa-checklist.md](materials/qa-checklist.md) |
| 原始证据 | 本目录 44 张 PNG 与 5 张 JPG 联系表 |

## 交付边界

- 海报、剧照、台标和 EPG 属于运行时内容源数据，不作为品牌素材复制进仓库；裁切、遮罩和降噪参数已写入主方案与品牌素材清单。
- 系统中文 sans 字体用于 UI 正文，不新增运行时字体依赖。
- Material Symbols 字体只作为矢量 path 的生成输入；随包许可见 [LICENSE-MATERIAL-SYMBOLS.txt](../../../tools/md3_res/LICENSE-MATERIAL-SYMBOLS.txt)。
- 现有角色和品牌位图的作者及商用授权元数据在仓库中不可证实；发布前必须按 [brand-assets.md](materials/brand-assets.md) 完成权利确认。

