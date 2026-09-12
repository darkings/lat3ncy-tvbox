package com.github.tvbox.osc.callback;

import android.app.Activity;
import android.content.Context;
import android.content.ContextWrapper;
import android.graphics.drawable.Animatable;
import android.graphics.drawable.Drawable;
import android.view.View;
import android.view.ViewGroup;
import android.view.ViewParent;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.TextView;

import com.github.tvbox.osc.R;
import com.kingja.loadsir.callback.Callback;

import java.util.Map;
import java.util.WeakHashMap;

import androidx.fragment.app.Fragment;

/**
 * 三阶段 Loading：300ms 内不闪烁；8s 提供重试（页面需 bindRetry）。
 * 注意：Callback.copy() 会序列化深拷贝，状态与回调一律走静态注册表。
 */
public class LoadingCallback extends Callback {

    private static final long SHOW_DELAY_MS = 300;
    private static final long RETRY_DELAY_MS = 8000;
    private static final WeakHashMap<Object, Runnable> RETRY_LISTENERS = new WeakHashMap<>();

    /**
     * 用页面自己的对象当 key，避免 HomeActivity 和 GridFragment 共用 Activity Context 时互相覆盖。
     */
    public static void bindRetry(Object owner, Runnable retry) {
        if (owner == null) {
            return;
        }
        if (retry != null) {
            RETRY_LISTENERS.put(owner, retry);
        } else {
            RETRY_LISTENERS.remove(owner);
        }
    }

    public static void unbindRetry(Object owner) {
        if (owner != null) {
            RETRY_LISTENERS.remove(owner);
        }
    }

    @Override
    protected int onCreateView() {
        return R.layout.loadsir_loading_layout;
    }

    @Override
    protected void onViewCreate(Context context, View view) {
        super.onViewCreate(context, view);

        // LoadSir's full-screen wrapper must yield focus to the contextual
        // retry action when this screen is used with a TV remote.
        view.setFocusable(false);
        view.setFocusableInTouchMode(false);
        view.setClickable(false);
        if (view instanceof ViewGroup) {
            ((ViewGroup) view).setDescendantFocusability(ViewGroup.FOCUS_AFTER_DESCENDANTS);
        }
        ViewParent parent = view.getParent();
        if (parent instanceof View) {
            View parentView = (View) parent;
            parentView.setFocusable(false);
            parentView.setFocusableInTouchMode(false);
            parentView.setClickable(false);
            if (parentView instanceof ViewGroup) {
                ((ViewGroup) parentView).setDescendantFocusability(ViewGroup.FOCUS_AFTER_DESCENDANTS);
            }
        }

        final LinearLayout content = view.findViewById(R.id.llLoadingContent);
        final TextView btnRetry = view.findViewById(R.id.btnLoadingRetry);
        final Runnable retry = findRetry(context);

        if (btnRetry != null) {
            btnRetry.setText("重试");
            btnRetry.setVisibility(View.GONE);
        }

        // ProgressBar 不会保证自动 start AnimatedVectorDrawable，这里显式启动。
        startLoadingDrawables(view);

        if (content != null) {
            // 0-300ms 不闪烁：先隐藏内容，延迟显示
            content.setVisibility(View.INVISIBLE);
            view.postDelayed(new Runnable() {
                @Override
                public void run() {
                    if (content.getVisibility() == View.INVISIBLE) {
                        content.setVisibility(View.VISIBLE);
                        startLoadingDrawables(view);
                    }
                }
            }, SHOW_DELAY_MS);
        }
        // 8s 仍未完成则提供重试退路（页面 bindRetry 后生效）
        if (btnRetry != null && retry != null) {
            view.postDelayed(new Runnable() {
                @Override
                public void run() {
                    btnRetry.setVisibility(View.VISIBLE);
                    btnRetry.setOnClickListener(new View.OnClickListener() {
                        @Override
                        public void onClick(View v) {
                            retry.run();
                        }
                    });
                    btnRetry.requestFocus();
                }
            }, RETRY_DELAY_MS);
        }
    }

    /**
     * LoadSir 传入的可能是包装后的 Context。先解包到 Activity，再精确匹配，最后回退到同页 Fragment。
     */
    private static Runnable findRetry(Context context) {
        if (context == null) {
            return null;
        }
        Context owner = unwrapOwner(context);
        Runnable exact = RETRY_LISTENERS.get(owner);
        if (exact != null) {
            return exact;
        }
        exact = RETRY_LISTENERS.get(context);
        if (exact != null) {
            return exact;
        }
        for (Map.Entry<Object, Runnable> entry : RETRY_LISTENERS.entrySet()) {
            Object key = entry.getKey();
            if (key instanceof Activity && (key == owner || key == context)) {
                return entry.getValue();
            }
            if (key instanceof Fragment) {
                Fragment fragment = (Fragment) key;
                if (fragment.getContext() == context || fragment.getContext() == owner
                        || fragment.getActivity() == owner || fragment.getActivity() == context) {
                    return entry.getValue();
                }
            }
        }
        return null;
    }

    private static Context unwrapOwner(Context context) {
        Context current = context;
        while (current instanceof ContextWrapper) {
            if (current instanceof Activity) {
                return current;
            }
            Context base = ((ContextWrapper) current).getBaseContext();
            if (base == current) {
                break;
            }
            current = base;
        }
        return context;
    }

    private static void startLoadingDrawables(View root) {
        if (!(root instanceof ViewGroup)) {
            startIfAnimatable(root);
            return;
        }
        ViewGroup group = (ViewGroup) root;
        for (int i = 0; i < group.getChildCount(); i++) {
            startLoadingDrawables(group.getChildAt(i));
        }
        if (root instanceof ProgressBar) {
            startIfAnimatable(root);
        }
    }

    private static void startIfAnimatable(View view) {
        Drawable drawable = null;
        if (view instanceof ProgressBar) {
            drawable = ((ProgressBar) view).getIndeterminateDrawable();
        }
        if (drawable instanceof Animatable) {
            Animatable animatable = (Animatable) drawable;
            if (!animatable.isRunning()) {
                animatable.start();
            }
        }
    }
}