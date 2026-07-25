# Ponyo TV

Ponyo TV 是面向 Android TV 的 TVBox 美化版本。此仓库只发布可安装 APK、订阅源和订阅验证工具，不包含应用源码。

## 仓库结构

```
├── android/           App 源码（完整 Gradle 项目，不入库）
├── docs/              设计文档与实施计划
├── releases/          APK 发行版
├── source-manager/    自动化源管理系统
├── subscription/      订阅配置
└── tools/             独立辅助脚本
```

## 默认订阅

```text
https://cdn.jsdelivr.net/gh/darkings/lat3ncy-tvbox@main/subscription/ponyo.json
```

订阅中的 GitHub Raw 依赖统一通过 jsDelivr 获取，减少无代理网络下无法连接 `raw.githubusercontent.com` 的问题。

## APK

最新安装包位于 `releases/`。当前 Java 通用包同时支持：

- `arm64-v8a`
- `armeabi-v7a`

## 订阅维护

- `subscription/ponyo.json`：远程发布配置
- `tools/validate_subscription.py`：无代理依赖连通性检查
- `tools/prepare_subscription.py`：过滤明确失效源、统一名称并转换 GitHub CDN 地址

网络连通不等于影片一定可以播放。部分来源仍可能受地区、登录、令牌、上游规则和临时维护影响。
