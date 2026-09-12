# Ponyo TV 品牌素材清单

本清单只记录当前工作区实际存在的素材、用途和约束，不替代版权或商标授权文件。

## 1. 核心品牌位图

| 素材 | 尺寸 | 大小 | SHA-256 | 建议用途 |
| --- | --- | ---: | --- | --- |
| [ponyo_icon.png](../../../../android/app/src/main/res/drawable-nodpi/ponyo_icon.png) | 160 × 160 | 30,848 B | 21ffb9d81a6977310aa30822b8331d7acc87868db98ea500bd45ad0c2d4e1b69 | 空状态、关于页、小型品牌角色；不作为海报或频道台标 |
| [ponyo_spritesheet.webp](../../../../android/app/src/main/res/drawable-nodpi/ponyo_spritesheet.webp) | 1536 × 1872；8 × 9 网格 | 1,955,954 B | e786fb62cf543dcae912a3be64a6cf30d2baccf6327979d7b6c5b1ea4217c6b7 | 启动、首页欢迎、等待和可恢复错误 |
| [app_banner.png](../../../../android/app/src/main/res/drawable/app_banner.png) | 320 × 180 | 26,988 B | b93d31192ef2e337e5b9bb463f539fbff9c1745506fc39c60e991b975878e9ce | Android TV Banner、关于页品牌锁定图 |
| [app_bg.png](../../../../android/app/src/main/res/drawable/app_bg.png) | 1280 × 720 | 48,416 B | 49df6dc54af311783bfcbf2a2f6ef7a022b111082d75b92129507a4efae6c3ba | 深色 App 背景基底 |

角色图集单元尺寸为 192 × 208。实际播放参数见 [motion-spec.json](motion-spec.json)。

## 2. 应用图标

| 密度 | 文件 | 尺寸 | 大小 |
| --- | --- | ---: | ---: |
| hdpi | [app_icon.png](../../../../android/app/src/main/res/drawable-hdpi/app_icon.png) | 192 × 192 | 35,124 B |
| xhdpi | [app_icon.png](../../../../android/app/src/main/res/drawable-xhdpi/app_icon.png) | 256 × 256 | 55,857 B |
| xxhdpi | [app_icon.png](../../../../android/app/src/main/res/drawable-xxhdpi/app_icon.png) | 384 × 384 | 105,970 B |
| xxxhdpi | [app_icon.png](../../../../android/app/src/main/res/drawable-xxxhdpi/app_icon.png) | 512 × 512 | 153,793 B |

使用规则：

- 不拉伸、不旋转、不加额外彩色背景。
- 图标外围必须保留至少 12.5% 安全区。
- App 图标只用于 Launcher、品牌栏和 Splash，不作为频道 logo、视频占位或错误图。
- TV Banner 使用 app_banner.png，不用方形图标强行拉成 16:9。

## 3. 背景与品牌容器

实际资源：

- [app_bg_layer.xml](../../../../android/app/src/main/res/drawable/app_bg_layer.xml)：深色背景图与暖色渐变叠加。
- [ponyo_splash_background.xml](../../../../android/app/src/main/res/drawable/ponyo_splash_background.xml)：浅色启动渐变。
- [ponyo_splash_window.xml](../../../../android/app/src/main/res/drawable/ponyo_splash_window.xml)：系统启动预览。
- [ponyo_top_bar.xml](../../../../android/app/src/main/res/drawable/ponyo_top_bar.xml)：透明顶部品牌栏容器。
- [ponyo_panel.xml](../../../../android/app/src/main/res/drawable/ponyo_panel.xml)：设置与普通面板。
- [ponyo_poster_surface.xml](../../../../android/app/src/main/res/drawable/ponyo_poster_surface.xml)：海报占位表面。

背景规则：

- 普通页面使用深色背景；只有 Splash 使用浅奶油渐变。
- 系统 Splash 与 activity_splash 首帧必须使用相同背景，避免闪屏。
- 不新增高对比纹理或重复角色水印。
- 动态壁纸只允许影响背景辅助色，不能改变文字、焦点和错误色。

## 4. 图标材料

可复用的矢量图标位于 [tools/md3_res](../../../../tools/md3_res)：

- 导航：icon_back.xml。
- 首页入口：icon_history.xml、icon_live.xml、icon_search.xml、icon_push.xml、icon_collect.xml、icon_setting.xml。
- 操作：icon_clear.xml、icon_delete.xml、icon_filter.xml、icon_filter_off.xml。
- 播放：icon_play.xml、icon_pre.xml、icon_lock.xml、icon_unlock.xml、icon_video.xml。
- 状态：icon_loading.xml、icon_empty.xml、icon_error.xml、icon_img_placeholder.xml。
- 品牌辅助：icon_brand_waves.xml。

使用规则：

- 正常图标使用 Text secondary。
- 聚焦图标使用 On primary container。
- 危险图标仅在确认步骤使用 Error。
- 图标与文字组合的间距为 12 design-mm。
- 不混用 emoji、位图表情和 Material 图标表达同一类操作。

## 5. 字体与生成材料

[MaterialSymbolsRounded.ttf](../../../../tools/md3_res/MaterialSymbolsRounded.ttf) 仅作为生成矢量 path 的工具输入，当前大小 15,080,092 B，SHA-256：

619eaa2f2e270723cf0cd06d2aba126ade66fee94e380c3e6a61e2e496279e0c

规则：

- APK 应使用已经提取的 vector XML，不因本方案新增运行时字体依赖。
- 生成脚本为 [extract_symbols.py](../../../../tools/md3_res/extract_symbols.py)。
- Material Symbols 为 Google Material Symbols 项目的一部分；随包 Apache-2.0 文本见 [LICENSE-MATERIAL-SYMBOLS.txt](../../../../tools/md3_res/LICENSE-MATERIAL-SYMBOLS.txt)。发布或再分发时必须保留该许可和来源说明。
- UI 正文字体继续使用 Android 系统 sans 字体，避免额外包体和中文缺字风险。

## 6. 运行时内容图像规则

海报、详情剧照和频道台标由内容源在运行时提供，不复制进本品牌素材包。实现时使用以下固定处理方式，不再等待额外设计稿：

- 海报：`centerCrop` 到 2:3；圆角、尺寸和焦点值取 `design-tokens.json` 的 `component.poster`；底部文字 scrim 最多占卡高 24%；加载失败使用 `ponyo_poster_surface.xml` 与 `icon_img_placeholder.xml`。
- 详情剧照：仅在内容源提供可靠 16:9 backdrop 时使用，`centerCrop` 后叠加从 `#00000000` 到 `#E6000000` 的纵向渐变；禁止实时全屏模糊。没有 backdrop 时直接使用 `app_bg_layer.xml`，不把低分辨率竖版海报放大成全屏背景。
- 频道台标：使用 `centerInside` 放入 64 × 64 design-mm 的 Surface 容器；没有台标时使用 `icon_live.xml`，不使用品牌角色代替。
- QR：生成内容由页面运行时决定，quiet zone 固定纯白；品牌素材不得侵入二维码矩阵和 quiet zone。

## 7. 来源与权利状态

| 类别 | 当前可确认信息 | 发布前动作 |
| --- | --- | --- |
| 应用名称 Ponyo TV | 本地项目已使用该名称；当前目录未发现商标授权文件 | 产品所有者确认名称、域名和商标使用风险 |
| 角色图、图标和图集 | 当前工作区已有成品；未发现作者、生成记录或授权元数据 | 由素材提供者补充来源、作者和可商用授权 |
| Material Symbols | 上游为 Google Material Symbols；当前为生成工具输入；Apache-2.0 文本已随包提供 | 对外分发时保留许可证与来源说明 |
| 海报与影片图片 | 来自内容源的运行时数据，不属于品牌素材包 | 遵循内容源和发行地区要求，不打包为品牌资产 |

本方案没有对任何素材作权利保证。若权利状态无法确认，优先替换名称或角色，而不是在发布后补救。

## 8. 禁止用法

- 角色常驻覆盖首页海报。
- 角色进入视频播放区或直播画面。
- 将品牌图标用作频道台标、海报失败图或加载 spinner。
- 旋转、倾斜或裁掉角色的头、手、脚。
- 在角色背后使用高饱和荧光色。
- 同一页面同时展示方形 App 图标、横向 Banner 和动画角色三套品牌锁定图。
- 把海报或第三方内容图当作品牌背景素材保存进 APK。
