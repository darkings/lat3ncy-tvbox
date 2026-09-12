package com.github.tvbox.osc.util;

import android.annotation.SuppressLint;
import android.content.Context;
import android.view.LayoutInflater;
import android.view.View;
import android.widget.TextView;
import android.widget.Toast;

import com.github.tvbox.osc.R;

/**
 * 统一 Toast 样式封装。
 *
 * 设计依据: docs/ui-audit/2026-08-10/materials/design-tokens.json + motion-spec.json
 *   普通提示: 容器 surfaceHigh(#2F2824) + 文字 textPrimary(#F0DED9) + 描边 outlineSubtle
 *   错误提示: 容器 errorContainer(#93000A) + 文字 onErrorContainer(#FFDAD6) + 描边 error
 *   圆角 12(control) / 字号 20(label) / 位置 屏幕底部居中(系统默认)
 *
 * 特性:
 *   - 相同样式+文案的 Toast 在显示期间重复触发时直接复用, 避免连弹叠加
 *   - 提供 info / error / show 三个入口, 全 App 统一收口
 */
public final class ToastUtil {

    /** 当前正在显示的 Toast, 用于去重防连弹 */
    private static Toast sCurrentToast;
    /** 当前 Toast 的文案+样式指纹, 相同则复用不重建 */
    private static String sCurrentKey;

    private ToastUtil() {
        // 工具类禁止实例化
    }

    /** 普通信息提示 (LENGTH_SHORT) */
    public static void info(Context context, CharSequence msg) {
        show(context, msg, false, Toast.LENGTH_SHORT);
    }

    /** 普通信息提示, 可指定时长 */
    public static void info(Context context, CharSequence msg, int duration) {
        show(context, msg, false, duration);
    }

    /** 错误/失败提示 (LENGTH_SHORT) */
    public static void error(Context context, CharSequence msg) {
        show(context, msg, true, Toast.LENGTH_SHORT);
    }

    /** 错误/失败提示, 可指定时长 */
    public static void error(Context context, CharSequence msg, int duration) {
        show(context, msg, true, duration);
    }

    /**
     * 统一入口。
     *
     * @param context  上下文 (内部用 applicationContext 防泄漏)
     * @param msg      文案
     * @param isError  是否错误样式
     * @param duration Toast.LENGTH_SHORT / LENGTH_LONG
     */
    @SuppressLint("ShowToast")
    public static void show(Context context, CharSequence msg, boolean isError, int duration) {
        if (context == null || msg == null || msg.length() == 0) {
            return;
        }
        Context app = context.getApplicationContext();
        // 指纹: 样式 + 文案, 相同则认为是同一条提示
        String key = (isError ? "E:" : "I:") + msg;

        // 相同样式+文案正在显示 -> 直接复用, 不重建不连弹
        if (sCurrentToast != null && key.equals(sCurrentKey)) {
            sCurrentToast.show();
            return;
        }

        // 取消上一条不同的 Toast
        cancel();

        // 用自定义布局构建 Toast
        View view = LayoutInflater.from(app).inflate(R.layout.view_toast, null);
        TextView tv = view.findViewById(R.id.tvToast);
        tv.setText(msg);
        if (isError) {
            // 错误样式: 换容器背景 + 文字色
            view.setBackgroundResource(R.drawable.bg_toast_error);
            tv.setTextColor(app.getResources().getColor(R.color.md3_on_error_container));
        }

        Toast toast = new Toast(app);
        toast.setDuration(duration);
        toast.setView(view);
        // 位置: 不调用 setGravity, 保持系统默认的屏幕底部居中
        toast.show();

        sCurrentToast = toast;
        sCurrentKey = key;
    }

    /** 取消当前正在显示的 Toast 并清空状态 */
    public static void cancel() {
        if (sCurrentToast != null) {
            try {
                sCurrentToast.cancel();
            } catch (Throwable ignored) {
                // 防御: 个别 ROM cancel 可能抛异常
            }
            sCurrentToast = null;
            sCurrentKey = null;
        }
    }
}
