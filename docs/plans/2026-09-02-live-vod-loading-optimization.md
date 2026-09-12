# 直播 / 点播加载与流畅度优化（2026-09-02）

版本：2026-09-02  
适用项目：`android`（PonyoTV）  
测试环境：MuMu 安卓 15.0，ADB `127.0.0.1:16384`

本文记录本轮对点播 HLS 代理、IJK 点播参数、Exo 缓冲的最小调整，以及在 MuMu 上实际看到的加载行为。没有无基线的盲目调参。

---

## 1. 基线（改之前）

### 点播

`PlayFragment.goPlayUrl()`：

- m3u8 且 `HawkConfig.HLS_CACHE=true` 时走 `HlsCacheProxy.wrap()`
- MPD 走 Exo
- 详情预览强制 SurfaceView
- 换线路会释放旧播放器再设 URL

`HlsCacheProxy` 原常量：

```text
PREFETCH_AHEAD = 4
LIVE_KEEP = 8
LIVE_BEHIND = 3
prefetchPool = 8 线程
```

风险：缺 `#EXT-X-ENDLIST` 的点播列表可能被当成直播，进入 pin / 历史窗口，裁掉后面分片。

IJK 点播原参数：

```text
max_cached_duration=3000
infbuf=0
threads=2
```

Exo 原缓冲：

```text
setBufferDurationsMs(15_000, 30_000, 1_000, 3_000)
setTargetBufferBytes(32 * 1024 * 1024)
```

### 直播

`LivePlayActivity.wrapLivePlayUrl()` 已确认：

- 非 m3u8 不代理
- Exo / 系统播放器不走 `HlsCacheProxy`
- IJK 默认也不走整片代理
- 只有 `LIVE_HLS_PROXY=true` 才 `HlsCacheProxy.wrap()`

直播 IJK 直连已有 packet-buffering、high-water-mark、timeout、framedrop，本轮不改直播 IJK 直连参数。

---

## 2. 本轮改动

### 2.1 `HlsCacheProxy.java`

| 项 | 旧 | 新 | 原因 |
| --- | ---: | ---: | --- |
| `PREFETCH_AHEAD` | 4 | 2 | 少和正在播的分片抢带宽 |
| `prefetchPool` | 8 | 3 | 8 线程并发下载会把当前分片挤慢 |
| 本地直播窗口 playlist | 只要能拼出 history 就返回 | 仅 `livePins.containsKey(url)` | 点播不得误走直播窗口 |
| 直播判定 | 仅看有无 `#EXT-X-ENDLIST` | 还要 `Hawk.get(PLAYER_IS_LIVE, false)` | 点播缺 ENDLIST 时不能 pin |

`LIVE_KEEP=8`、`LIVE_BEHIND=3` 未改，且只在直播 pin 路径使用。

### 2.2 `IjkMediaPlayer.java` 点播

在原有 `max_cached_duration=3000` / `infbuf=0` / `threads=2` 上增加：

```text
packet-buffering=1
reconnect=1
analyzeduration=800000
probesize=512KB
first-high-water-mark-ms=1200
next-high-water-mark-ms=2500
timeout=10s
rw_timeout=20s
```

直播分支未改。

### 2.3 `ExoMediaPlayer.java`

```text
setBufferDurationsMs(12_000, 25_000, 800, 2_000)
setTargetBufferBytes(24 * 1024 * 1024)
```

首帧门槛从 1000ms 降到 800ms，目标缓冲从 15–30s 收到 12–25s。直播窗口恢复仍走 `BehindLiveWindowException` 追边。

---

## 3. MuMu 实测

构建安装与窗口切换同一 APK：`PonyoTV_debug-java.apk`，`assembleJavaDebug` 43s 成功。

### 3.1 点播

片源：`43-HG` / 《百变智多星》 / `lzm3u8`

日志：

```text
echo-hls-prefetch-ok ...
echo-ijk-buffering-end extra:0
echo-hls-stream-wait / echo-hls-stream-open / echo-hls-hit
```

观察：

- 预览约数秒后出画（先有封面/0B/s，随后正片）
- 预取线程从 8 降到 3 后，仍能 `prefetch-ok` 并 `hit` 后续分片
- 播放中窗口切换没有打断 HLS 代理
- 未做 Exo 点播对照，也没有改前/改后的精确首帧毫秒数，不能声称“首帧快了 X ms”

### 3.2 直播

入口：首页「直播」→ `LivePlayActivity`

日志：

```text
echo-load live config https://api.ponyo.fun/ponyo.json
echo-liveurl https://api.ponyo.fun/aggregated-live.m3u
echo-live-list-len:15194
echo-live-parse groups:9 firstGroupChannels:18
echo-live-url:http://t.061899.xyz/tl/tl.php?id=cctv4
echo-type-直播
echo-live-ijk-opts proxy=off packet-buffering=1 first-hwm=1500
echo-ijk-onError what:-10000 extra:0
echo-liveSwitchPlayer: 1 -> 2
echo-exo-live-load-control
echo-live-playState-error:-1 url:...id=cctv4
echo-live-url:http://t.061899.xyz/tl/tl.php?id=cctv4m
echo-live-started url:...id=cctv4m
```

时间线（设备时钟）：

| 时间 | 事件 |
| --- | --- |
| 23:18:24 | 开始拉直播配置 |
| 23:18:25.810 | 第一路 `cctv4`，IJK 直连 |
| 23:18:26.292 | IJK 失败 `-10000` |
| 23:18:29.794 | 自动切 Exo |
| 23:18:41.448 | Exo 仍失败 |
| 23:18:44.956 | 切备用 URL `cctv4m` |
| 23:18:45.765 | `echo-live-started` |
| 约 23:18:50 | 截图已有凤凰卫视画面，码率约 482Kbps |

截图：`android/test_live2.png`

结论：

- 直播默认仍不走 `HlsCacheProxy`（日志 `proxy=off`），符合现有策略
- 自动切播放器 / 切源生效
- 第一路源本身失败，不是本次 IJK 点播参数改坏直播；直播 IJK 分支未改
- 从进直播页到稳定出画大约 20s，主要耗在失败源和切源，不能把这次 20s 写成“优化后的首帧时间”

---

## 4. 明确没做的事

- 没有打开 `LIVE_HLS_PROXY`
- 没有改直播 IJK 直连 high-water-mark
- 没有改点播换线路仍释放播放器的行为
- 没有量化卡顿次数 / 首帧 P50
- 没有在真机（非 MuMu）上测

---

## 5. 结论

本轮是防护性优化：点播 HLS 不再误入直播窗口，预取并发下降，点播 IJK 探测/重连更完整，Exo 起播缓冲略收。MuMu 上点播可播、直播在切源后可播。流畅度提升没有对照数据，只能记为“行为更安全、预取更克制”，不能写成已证明更流畅。
