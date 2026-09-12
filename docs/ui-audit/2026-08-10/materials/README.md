# Ponyo TV UI 资料包

本目录是 [全页面视觉审计与深度美化方案](../ponyo-tv-ui-deep-beautification-audit.md) 的配套交付。统一入口见 [上级 README](../README.md)。主文档中提到的色板、尺寸、焦点、动效、文案、页面证据、资源映射和验收资料均在这里。

## 文件

- [design-tokens.json](design-tokens.json)：机器可读的颜色、字体、栅格、焦点和组件尺寸。
- [style-board.svg](style-board.svg)：可编辑的矢量视觉板。
- [style-board.png](style-board.png)：从 SVG 实际渲染并视觉验收的 3200 × 1800 预览。
- [copy-deck.json](copy-deck.json)：11 个 Activity、通用状态、主要操作和 20 个 Dialog 的正式文案。
- [motion-spec.json](motion-spec.json)：焦点、页面、Dialog、加载和角色动画参数。
- [screen-coverage.csv](screen-coverage.csv)：44 张截图逐张判定，防止误用错误截图。
- [resource-map.tsv](resource-map.tsv)：页面、类、布局、重点元素和资料路径。
- [brand-assets.md](brand-assets.md)：实际位图、图标、背景、字体材料与权利状态。
- [qa-checklist.md](qa-checklist.md)：实现、遥控器、弱网和截图验收清单。

## 实际素材目录

- 44 张原始截图与 5 张联系表：上一级目录。
- 80 个现有实现资源和生成输入，以及配套许可证：[tools/md3_res](../../../../tools/md3_res)。
- 当前 Android 本地工作副本中的品牌位图：[android/app/src/main/res](../../../../android/app/src/main/res)。

注意：根目录 README 说明仓库不包含 App 源码，android 目录当前也被 .gitignore 忽略。因此 brand-assets.md 和 resource-map.tsv 对 android 的链接是本机审计依据，不代表这些文件已经纳入 Git 版本控制。

## 使用顺序

1. 先读取主审计文档与 screen-coverage.csv，确认页面和证据。
2. 将 design-tokens.json 映射到 Android values 资源。
3. 从 tools/md3_res 复用图标、选择器和生成脚本。
4. 按 copy-deck.json 和 motion-spec.json 完成状态与动效。
5. 使用 qa-checklist.md 在 720p、1080p、4K 和真实遥控器上验收。

本资料包没有修改 android 目录中的 App 实现。
