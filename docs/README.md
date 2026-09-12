# Ponyo TV 文档索引

本目录集中存放设计文档、实施计划与审计交付包。所有文档按日期前缀命名，便于按时间线追溯。

## 目录结构

```text
docs/
├── README.md              本索引
├── design/                设计文档（方案与架构决策）
├── plans/                 实施计划与工作记录
├── ui-audit/              UI 审计交付包
├── loading-animations-preview.html      加载动画方案预览
└── ponyo-loading-icons-preview.html     加载图标变体预览
```

## 设计文档 `design/`

| 文档 | 主题 |
|:---|:---|
| [2026-07-24-source-manager-phase1-2-design.md](design/2026-07-24-source-manager-phase1-2-design.md) | 源管理系统阶段一+二设计：服务器地基、数据库与导入去重 |
| [2026-07-25-source-manager-phase3-ab-design.md](design/2026-07-25-source-manager-phase3-ab-design.md) | 阶段三 A+B 设计：源健康引擎 v1、安全扫描与无代理连通性 |

## 实施计划 `plans/`

| 文档 | 主题 |
|:---|:---|
| [2026-07-25-source-manager-phase1-2.md](plans/2026-07-25-source-manager-phase1-2.md) | 阶段一+二实现计划 |
| [2026-07-25-source-manager-phase3-ab.md](plans/2026-07-25-source-manager-phase3-ab.md) | 阶段三 A+B 实现计划 |
| [2026-08-01-source-manager-bottleneck-execution-plan.md](plans/2026-08-01-source-manager-bottleneck-execution-plan.md) | 剩余瓶颈与依赖式执行计划 |
| [2026-08-01-source-manager-session-log.md](plans/2026-08-01-source-manager-session-log.md) | 运行诊断与真实播放源推进工作记录 |
| [2026-08-12-source-naming-spec.md](plans/2026-08-12-source-naming-spec.md) | 订阅源命名规范 v2 |
| [2026-08-14-drpys-runtime-in-app.md](plans/2026-08-14-drpys-runtime-in-app.md) | App 内嵌 drpyS 运行时实施计划与进度 |
| [2026-09-02-live-vod-loading-optimization.md](plans/2026-09-02-live-vod-loading-optimization.md) | 直播/点播加载与流畅度优化 |
| [2026-09-02-player-window-switch-black-screen.md](plans/2026-09-02-player-window-switch-black-screen.md) | 详情页小窗↔大窗口切换黑屏修复 |
| [2026-09-02-source-manager-security-timeout-and-vod-release.md](plans/2026-09-02-source-manager-security-timeout-and-vod-release.md) | scan_security 超时修复与点播精选发布闭环 |

## UI 审计交付包 `ui-audit/`

`ui-audit/2026-08-10/` 是完整交付包，入口见 [README.md](ui-audit/2026-08-10/README.md)。

| 内容 | 说明 |
|:---|:---|
| `ponyo-tv-ui-deep-beautification-audit.md` | 主方案：最终页面方案与验收标准 |
| `PONYO_TV_DEEP_VISUAL_REDESIGN.md` | 补充分析稿 |
| `ponyo-tv-ui-remediation-plan-v2.md` | 整改计划 |
| `materials/` | 资料包：design-tokens、copy-deck、motion-spec、style-board、resource-map、qa-checklist 等 |
| `实施记录/` | `IMPLEMENTATION.md` 与 33 张验收截图 |

## 预览文件

| 文件 | 用途 |
|:---|:---|
| [loading-animations-preview.html](loading-animations-preview.html) | 加载动画 5 套方案预览 |
| [ponyo-loading-icons-preview.html](ponyo-loading-icons-preview.html) | 加载图标 5 个变体预览，对应 `android/app/src/main/res/drawable/ponyo_loading_*_vector.xml` |

## 相关文档

仓库根目录另有以下文档：

| 文档 | 定位 |
|:---|:---|
| [AGENTS.md](../AGENTS.md) | 仓库工作约定：同步机制、语法检查、清理边界 |
| [PLAN.md](../PLAN.md) | 产品级总计划：自动采集、测速与精选订阅 |
| [README.md](../README.md) | 仓库入口：订阅地址、APK 与维护工具 |
| [source-manager/README.md](../source-manager/README.md) | 源管理系统说明 |
| [source-manager/review.md](../source-manager/review.md) | 复审报告与 A01-A24 硬性验收标准 |
| [source-manager/PLAN_DISCOVERY_MEDIA_AUTHENTICITY.md](../source-manager/PLAN_DISCOVERY_MEDIA_AUTHENTICITY.md) | 媒体真实性与剩余采集计划 |