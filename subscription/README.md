# Ponyo TV 订阅

推荐使用无代理测试通过的 jsDelivr 地址：

```text
https://cdn.jsdelivr.net/gh/darkings/lat3ncy-tvbox@main/subscription/ponyo.json
```

本轮维护对远程依赖进行了两轮无代理检查，删除连续不可达的来源，并统一了站源显示名称。应用中还包含同内容的 `assets/ponyo.json`，远程获取失败时会自动回退。

重新验证：

```text
python3 tools/validate_subscription.py subscription/ponyo.json \
  --accelerator https://cdn.jsdelivr.net \
  --rounds 2 --output subscription/source-health-final.json
```

验证结果分为：

- `verified`：引用的远程依赖全部通过检查
- `partial`：多线路中至少有一条通过，或测试期间出现瞬时失败
- `builtin-or-conditional`：内置实现，或需要运行时参数、登录与地区条件
- `unreachable`：全部检测请求均失败

HTTP 可访问不代表搜索和播放永久可用，上游接口仍可能随时变化。
