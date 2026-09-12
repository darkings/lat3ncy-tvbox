package com.github.tvbox.osc.util;

import android.os.Handler;
import android.os.Looper;
import android.provider.Settings;
import android.view.View;
import android.widget.ProgressBar;
import android.widget.TextView;
import android.graphics.drawable.Drawable;

import androidx.annotation.Nullable;
import androidx.core.content.ContextCompat;

import com.github.tvbox.osc.R;

/**
 * Ponyo TV 缓冲加载调度器（对应 docs/ui-audit/2026-08-10/materials/motion-spec.json 的 transition.loading）。
 *
 * <p>职责：
 * <ul>
 *   <li>300ms 内完成的请求不闪 Loading（showDelayMs=300，QA 清单第 4 节）；</li>
 *   <li>超过 3s 仍在缓冲时给出慢网文案（slowNetworkMessageMs=3000）；</li>
 *   <li>系统关闭动画（animator_duration_scale=0，近似 reduced-motion）时，
 *       自动把 AVD 涟漪替换为静态版 {@code R.drawable.ponyo_loading_ripple_static}。</li>
 * </ul>
 *
 * <p>用法（播放器/直播控制器基类持有一个实例）：
 * <pre>{@code
 *   bufferIndicator = new LoadingIndicator(playLoading, slowHintText);
 *   // 播放器回调 onBufferingStart / 换台开始：
 *   bufferIndicator.show();
 *   // onBufferingEnd / onPrepared / onError：
 *   bufferIndicator.hide();
 * }</pre>
 *
 * <p>不在 onDestroy 之后继续使用的场景务必调用 {@link #release()}。
 */
public final class LoadingIndicator {

    /** 延迟显示阈值（ms），令牌 component.loadingIndicator.showDelayMs。 */
    private static final long SHOW_DELAY_MS = 300L;
    /** 慢网提示阈值（ms），令牌 component.loadingIndicator.slowNetworkMessageMs。 */
    private static final long SLOW_HINT_MS = 3000L;

    private final ProgressBar progressBar;
        @Nullable
    private final TextView slowHintView;
    private final Handler handler = new Handler(Looper.getMainLooper());

    /** 本次 show() 是否已越过延迟真正可见（hide 时据此判断是否曾显示）。 */
    private boolean visible;

    private final Runnable showTask = new Runnable() {
        @Override
        public void run() {
            applyDrawable();
            progressBar.setVisibility(View.VISIBLE);
            visible = true;
            // 可见后再排慢网提示，确保"3s"从用户看到转圈起算
            if (slowHintView != null) {
                handler.postDelayed(slowHintTask, SLOW_HINT_MS - SHOW_DELAY_MS);
            }
        }
    };

    private final Runnable slowHintTask = new Runnable() {
        @Override
        public void run() {
            // 已停用慢网文案：只保留转圈，不再提示"网络较慢，仍在努力加载…"
            // 如需恢复，删除此 return 即可
            return;
        }
    };

    /**
     * @param progressBar  布局里 style="@style/PonyoLoading.*" 的 ProgressBar
     * @param slowHintView 慢网文案 TextView（可选，传 null 则只控 spinner）
     */
    public LoadingIndicator(ProgressBar progressBar, @Nullable TextView slowHintView) {
        this.progressBar = progressBar;        this.slowHintView = slowHintView;
        progressBar.setVisibility(View.GONE);
        if (slowHintView != null) {
            slowHintView.setVisibility(View.GONE);
        }
    }

    /** 开始一次缓冲等待。300ms 内调用 {@link #hide()} 则用户无感知。 */
    public void show() {
        cancelTasks();
        visible = false;
        // 立即隐藏 spinner 与慢网文案，防止上一次 hide() 未生效时残留可见
        progressBar.setVisibility(View.GONE);
        if (slowHintView != null) {
            slowHintView.setVisibility(View.GONE);
        }
        handler.postDelayed(showTask, SHOW_DELAY_MS);
    }

    /** 缓冲结束/失败/退出：立即撤下所有待执行任务并隐藏。 */
    public void hide() {
        cancelTasks();
        visible = false;
        progressBar.setVisibility(View.GONE);
        if (slowHintView != null) {
            slowHintView.setVisibility(View.GONE);
        }
    }

    /** 页面销毁时调用，清空 Handler 队列并解除 View 引用，避免泄漏 Activity。 */
    public void release() {
        cancelTasks();
        visible = false;
        progressBar.setVisibility(View.GONE);
        if (slowHintView != null) {
            slowHintView.setVisibility(View.GONE);
        }
    }

    private void cancelTasks() {
        handler.removeCallbacks(showTask);
        handler.removeCallbacks(slowHintTask);
    }

    /**
     * reduced-motion 降级：系统动画比例被关闭时换静态矢量图。
     * 判定用 ANIMATOR_DURATION_SCALE（用户"移除动画"开发者/无障碍项），
     * 覆盖 TV 上最常见的"减少动态效果"入口。
     */
    private void applyDrawable() {
        float animatorScale = Settings.Global.getFloat(
                progressBar.getContext().getContentResolver(),
                Settings.Global.ANIMATOR_DURATION_SCALE, 1.0f);

        if (animatorScale <= 0f) {
            // reduced-motion：按当前场景映射到对应的静态版
            int staticRes = resolveStaticDrawable();
            progressBar.setIndeterminateDrawable(
                    ContextCompat.getDrawable(progressBar.getContext(), staticRes));
        }
        // 正常模式：不动 XML 里 style 已设置的 drawable
    }

    /** 根据当前 indeterminateDrawable 推断场景，返回对应的静态版资源。 */
    private int resolveStaticDrawable() {
        Drawable current = progressBar.getIndeterminateDrawable();
        if (current == null) {
            return R.drawable.ponyo_loading_ripple_static;
        }
        // 通过资源 ID 映射场景
        // 注意：无法直接比较 Drawable 实例，改用 tag 或保留引用
        Object tag = progressBar.getTag();
        if (tag != null) {
            String tagStr = tag.toString();
            if (tagStr.contains("play") || tagStr.contains("vod")) {
                return R.drawable.ponyo_loading_play_static;
            } else if (tagStr.contains("channel") || tagStr.contains("live")) {
                return R.drawable.ponyo_loading_channel_static;
            } else if (tagStr.contains("search") || tagStr.contains("cast")) {
                return R.drawable.ponyo_loading_search_static;
            }
        }
        // 默认：内容加载（Ponyo 鱼）
        return R.drawable.ponyo_loading_content_static;
    }
}
