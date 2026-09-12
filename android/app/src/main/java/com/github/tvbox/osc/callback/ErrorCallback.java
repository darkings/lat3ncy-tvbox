package com.github.tvbox.osc.callback;

import android.app.Activity;
import android.content.Context;
import android.content.ContextWrapper;
import android.view.View;
import android.view.ViewGroup;
import android.view.ViewParent;
import android.widget.TextView;

import com.github.tvbox.osc.R;
import com.kingja.loadsir.callback.Callback;

import java.util.WeakHashMap;

/**
 * 统一错误状态组件：title / body / primaryAction / secondaryAction / technicalDetails，
 * 状态与动作由页面通过 bind() 传入，组件内不硬编码业务文案。
 */
public class ErrorCallback extends Callback {

    public interface ErrorActionListener {
        void onPrimary();

        void onSecondary();
    }

    private static final WeakHashMap<Context, ErrorState> STATES = new WeakHashMap<>();
    private static final WeakHashMap<Context, ErrorActionListener> ACTIONS = new WeakHashMap<>();

    private static class ErrorState {
        String title;
        String body;
        String primaryAction;
        String secondaryAction;
        String technicalDetails;
    }

    public static void bind(Context context, String title, String body, String primaryAction,
                            String secondaryAction, String technicalDetails, ErrorActionListener listener) {
        Context owner = unwrapOwner(context);
        ErrorState state = new ErrorState();
        state.title = title;
        state.body = body;
        state.primaryAction = primaryAction;
        state.secondaryAction = secondaryAction;
        state.technicalDetails = technicalDetails == null ? "" : technicalDetails;
        STATES.put(owner, state);
        if (listener != null) {
            ACTIONS.put(owner, listener);
        }
    }

    /**
     * LoadSir 的 onViewCreate 可能拿到 ContextThemeWrapper，而 bind() 用的是 Activity。
     * 统一解包到 Activity，避免“重试”按钮找不到 listener。
     */
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

    @Override
    protected int onCreateView() {
        return R.layout.loadsir_error_layout;
    }

    @Override
    protected void onViewCreate(Context context, View view) {
        super.onViewCreate(context, view);

        // LoadSir wraps callbacks in a full-screen focusable container. That
        // container must yield focus to the actionable controls for DPAD use.
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

        Context owner = unwrapOwner(context);
        ErrorState state = STATES.get(owner);
        if (state == null) {
            state = STATES.get(context);
        }
        ErrorActionListener boundListener = ACTIONS.get(owner);
        if (boundListener == null) {
            boundListener = ACTIONS.get(context);
        }
        final ErrorActionListener listener = boundListener;

        TextView tvTitle = view.findViewById(R.id.tvErrorTitle);
        TextView tvBody = view.findViewById(R.id.tvErrorBody);
        TextView tvTechnicalToggle = view.findViewById(R.id.tvErrorTechnicalToggle);
        TextView tvDetails = view.findViewById(R.id.tvErrorDetails);
        TextView btnPrimary = view.findViewById(R.id.btnErrorPrimary);
        TextView btnSecondary = view.findViewById(R.id.btnErrorSecondary);

        if (state != null) {
            tvTitle.setText(state.title);
            tvBody.setText(state.body);
            btnPrimary.setText(state.primaryAction);
            if (state.secondaryAction != null && !state.secondaryAction.trim().isEmpty()) {
                btnSecondary.setVisibility(View.VISIBLE);
                btnSecondary.setText(state.secondaryAction);
            } else {
                btnSecondary.setVisibility(View.GONE);
            }
            if (state.technicalDetails != null && !state.technicalDetails.trim().isEmpty()) {
                tvDetails.setText(state.technicalDetails);
                tvTechnicalToggle.setVisibility(View.VISIBLE);
            } else {
                tvTechnicalToggle.setVisibility(View.GONE);
                tvDetails.setVisibility(View.GONE);
            }
        }

        tvTechnicalToggle.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                boolean expanded = tvDetails.getVisibility() == View.VISIBLE;
                tvDetails.setVisibility(expanded ? View.GONE : View.VISIBLE);
                tvTechnicalToggle.setText(expanded ? "技术信息" : "收起技术信息");
            }
        });

        btnPrimary.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                if (listener != null) {
                    listener.onPrimary();
                } else if (v.getContext() instanceof android.app.Activity) {
                    ((android.app.Activity) v.getContext()).onBackPressed();
                }
            }
        });
        btnSecondary.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                if (listener != null) {
                    listener.onSecondary();
                }
            }
        });

        btnPrimary.setNextFocusRightId(R.id.btnErrorSecondary);
        btnSecondary.setNextFocusLeftId(R.id.btnErrorPrimary);
        btnPrimary.post(new Runnable() {
            @Override
            public void run() {
                if (btnPrimary.getVisibility() == View.VISIBLE) {
                    btnPrimary.requestFocus();
                }
            }
        });
    }
}
