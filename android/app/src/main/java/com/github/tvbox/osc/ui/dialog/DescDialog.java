package com.github.tvbox.osc.ui.dialog;

import android.content.Context;
import android.view.View;
import android.view.ViewGroup;
import android.widget.TextView;

import androidx.annotation.NonNull;
import androidx.core.widget.NestedScrollView;

import com.github.tvbox.osc.R;

import org.jetbrains.annotations.NotNull;

/**
 * 详情页「影片简介」弹窗。
 * 布局和文案对齐 docs/ui-audit/2026-08-10/materials：
 * copy-deck.dialogs.desc + design-tokens 的 dialog / type / shape。
 */
public class DescDialog extends BaseDialog {

    public DescDialog(@NonNull @NotNull Context context) {
        super(context, R.style.CustomDialogStyleDim);
        setContentView(R.layout.dialog_desc);
        setCanceledOnTouchOutside(true);
        setCancelable(true);

        View close = findViewById(R.id.descClose);
        if (close != null) {
            close.setOnClickListener(v -> dismiss());
        }
    }

    public void setDescribe(String describe) {
        TextView tvDescribe = findViewById(R.id.describe);
        if (tvDescribe != null) {
            tvDescribe.setText(describe == null ? "" : describe);
        }
        View close = findViewById(R.id.descClose);
        NestedScrollView scroll = findViewById(R.id.descScroll);
        limitScrollHeight(scroll);
        // TV 遥控器优先落到「关闭」，长文再靠方向键滚到正文。
        if (close != null) {
            close.post(close::requestFocus);
        } else if (scroll != null) {
            scroll.post(scroll::requestFocus);
        } else if (tvDescribe != null) {
            tvDescribe.requestFocus();
        }
    }

    /**
     * NestedScrollView 没有可用的 maxHeight 属性。
     * 短简介保持 wrap_content，长简介按令牌限制到 400 design-mm。
     */
    private void limitScrollHeight(NestedScrollView scroll) {
        if (scroll == null) {
            return;
        }
        final int maxBodyHeight = getContext().getResources().getDimensionPixelSize(R.dimen.vs_400);
        scroll.post(() -> {
            View child = scroll.getChildAt(0);
            if (child == null) {
                return;
            }
            int contentHeight = child.getMeasuredHeight();
            ViewGroup.LayoutParams lp = scroll.getLayoutParams();
            if (contentHeight > maxBodyHeight) {
                lp.height = maxBodyHeight;
            } else {
                lp.height = ViewGroup.LayoutParams.WRAP_CONTENT;
            }
            scroll.setLayoutParams(lp);
        });
    }
}
