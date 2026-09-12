# 详情页小窗↔大窗口切换黑屏修复（2026-09-02）

版本：2026-09-02  
适用项目：`android`（PonyoTV）  
测试环境：MuMu 安卓 15.0，ADB `127.0.0.1:16384`，包名 `com.darkings.ponyotv`

本文记录详情页预览小窗与全屏大窗口互相切换时黑屏的根因、代码修复、构建安装，以及在 MuMu 上实际执行的回归结果。不能把未执行的测试写成已通过。

---

## 1. 问题

详情页播放中：

- 小窗口切大窗口黑屏
- 大窗口切小窗口也黑屏

切换路径在 `DetailActivity.setFullPreview()`：改容器 `LayoutParams` 后调用 `PlayFragment.rebindPreviewSurface()` → `MyVideoView.rebindDisplay()` → `VideoView.addDisplay()` 重建 RenderView。

---

## 2. 根因

原逻辑在切换时：

1. 立即解绑旧 Surface
2. 移除并释放旧 RenderView
3. 立即创建新 RenderView
4. 新 Surface 尚未 `surfaceCreated()`
5. 播放器短时间没有有效输出目标，或仍持有已销毁 Surface

更致命的一点：旧 View 的 `release()` / `surfaceDestroyed()` 会 `setDisplay(null)`，把刚绑上的新 Surface 清掉。

---

## 3. 修复策略

- 新 RenderView 先挂到容器
- 在 `surfaceCreated()` / `onSurfaceTextureAvailable()` 时绑定播放器
- 新 Surface 可用后再拆旧 View
- 拆旧 View 前先丢掉旧 View 的播放器引用，避免 `surfaceDestroyed` 清掉新 Surface
- 不释放播放器，不重新 `prepare`
- 详情页预览强制 `SurfaceRenderViewFactory`
- `rebindPreviewSurface()` 两次 `post()`，等布局完成再重绑

---

## 4. 代码改动

| 文件 | 作用 |
| --- | --- |
| `android/app/src/main/java/com/github/tvbox/osc/player/render/SurfaceRenderView.java` | `surfaceCreated/Changed` 绑定有效 Holder；`Destroyed` 解绑；`attachToPlayer` 补绑已有 Surface；`release()` 不再 `setDisplay(null)` |
| `android/player/src/main/java/xyz/doikki/videoplayer/render/TextureRenderView.java` | 创建新 Surface 并绑定；销毁时解绑释放；`release()` 不 `setSurface(null)` |
| `android/player/src/main/java/xyz/doikki/videoplayer/player/VideoView.java` | `addDisplay()` 先挂新 View；新 Surface 就绪后再 `oldRender.release()` + `removeView`；`resume()` 在 Surface 无效时只等 callback |
| `android/app/src/main/java/com/github/tvbox/osc/player/MyVideoView.java` | `rebindDisplay()` 保持播放器实例和播放状态，只重建 RenderView |
| `android/app/src/main/java/com/github/tvbox/osc/ui/fragment/PlayFragment.java` | 预览强制 SurfaceView；两次 `post()` 后再 `rebindDisplay()` |

`VideoView.detachOldRender()` 关键顺序：

1. 新 View 已 `addView`
2. 等 `surfaceCreated` 或 300ms 兜底
3. **先** `oldRender.release()`（只清旧 View 的播放器引用）
4. **再** `removeView(oldView)`

如果先 `removeView`，`surfaceDestroyed` 仍会拿到旧播放器引用并 `setDisplay(null)`。

---

## 5. 构建、安装、MuMu

命令与结果：

```text
C:\Program Files\Netease\MuMu\nx_main\mumu-cli.exe info --vmindex all
# index 0，is_android_started=false

C:\Program Files\Netease\MuMu\nx_main\mumu-cli.exe control --vmindex 0 launch
# errcode=0

C:\Program Files\Netease\MuMu\nx_main\mumu-cli.exe info --vmindex 0
# is_android_started=true, adb_port=16384, player_state=start_finished

cd C:\Users\Jie\Projects\lat3ncy-tvbox\android
.\gradlew.bat :app:assembleJavaDebug --stacktrace
# BUILD SUCCESSFUL in 43s

adb connect 127.0.0.1:16384
# 127.0.0.1:16384 device product:a52xq model:SM_A5260

adb -s 127.0.0.1:16384 install -r -d app\build\outputs\apk\java\debug\PonyoTV_debug-java.apk
# Success，APK 45194858 bytes，时间 2026-09-02 23:09:26
```

首页首次加载约 20s 后源 `43-HG` 可用。进入《百变智多星》详情页，预览走 IJK + `HlsCacheProxy`，线路 `lzm3u8`。

---

## 6. MuMu 回归（实际执行）

测试片源：详情页《百变智多星》预览，IJK，SurfaceView。

| 场景 | 操作 | 结果 | 证据 |
| --- | --- | --- | --- |
| 播放中 小窗→大窗 | 点预览块 / 确定键 | **通过**。约 1s 内全屏出画，无黑屏 | `test_switch_full3.png` / `test_switch_full4.png`；日志 `echo-previewBlock click previewActive=true`，`echo-rebind-display state=7 playing=true size=1080x606`，`echo-surface-created valid=true`，`echo-surface-changed w=1920 h=1077` |
| 播放中 大窗→小窗 | BACK 退出全屏 | **通过**。小窗立刻出画并继续播 | `test_switch_back1.png` / `test_switch_back3.png`；日志 `echo-rebind-display state=7 playing=true`，`echo-surface-changed w=705 h=395` |
| 暂停后切换 | 发 `KEYCODE_MEDIA_PAUSE` | **未真正暂停**。预览小窗没有进入暂停 UI，画面仍在播。随后切全屏仍有画面 | `test_switch_paused.png` 仍是小窗播放；`test_switch_paused_full.png` 全屏有画面。不能把“暂停态切换”标为已覆盖 |
| 缓冲中切换 | 预览起播阶段有 `echo-ijk-buffering-end` | **未在缓冲态专门切换**。正式切换发生在 `state=7 playing=true` | 日志时间 23:13 缓冲结束，23:14 才切全屏 |
| 播放失败/重播 | 未单独构造失败再切窗口 | **未测** | — |
| TextureView 路径 | 详情预览强制 SurfaceView | **本次未测 TextureView** | 代码 `applyPreviewRenderFactory()` |
| Exo 点播切换 | 本次点播走 IJK | **未测 Exo 点播窗口切换** | 直播另测，见流畅度记录 |

关键日志：

```text
23:14:26.079 echo-previewBlock click previewActive=true
23:14:26.092 echo-surface-changed w=1920 h=1077
23:14:26.109 echo-rebind-display state=7 playing=true size=1080x606
23:14:26.125 echo-surface-created valid=true
23:14:26.126 echo-surface-changed w=1920 h=1077

23:15:01.676 echo-surface-changed w=705 h=395
23:15:01.682 echo-rebind-display state=7 playing=true size=1080x606
23:15:01.692 echo-surface-created valid=true
```

`state=7` 是 `STATE_BUFFERED`，`playing=true` 表示播放器实例仍在播，没有被 `release()`。

截图目录：

```text
android/test_switch_preview.png
android/test_switch_full3.png
android/test_switch_full4.png
android/test_switch_back1.png
android/test_switch_back3.png
android/test_switch_paused_full.png
```

---

## 7. 结论

播放中小窗↔大窗这条主路径，在 MuMu + IJK + SurfaceView 上已经不再黑屏，播放器实例保持，画面连续。

未覆盖：暂停态、缓冲态、失败重播、TextureView、Exo 点播窗口切换。这些不能写成已修复已验证。
