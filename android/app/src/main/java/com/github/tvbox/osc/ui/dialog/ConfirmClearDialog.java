package com.github.tvbox.osc.ui.dialog;

import android.content.Context;
import android.os.Bundle;
import android.view.View;
import android.widget.TextView;

import androidx.annotation.NonNull;

import com.github.tvbox.osc.R;

/** A TV-safe confirmation dialog whose default focus is always Cancel. */
public class ConfirmClearDialog extends BaseDialog {
    public interface Listener {
        void onConfirm();

        void onCancel();
    }

    private final String title;
    private final String body;
    private final String confirmText;
    private final Listener listener;
    private TextView confirm;
    private TextView cancel;
    private boolean settled;

    public ConfirmClearDialog(@NonNull Context context, String title, String body,
                              String confirmText, Listener listener) {
        super(context);
        this.title = title;
        this.body = body;
        this.confirmText = confirmText;
        this.listener = listener;
        setContentView(R.layout.dialog_confirm);
        setCanceledOnTouchOutside(true);
        setOnCancelListener(dialog -> notifyCancel());
    }

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        TextView titleView = findViewById(R.id.confirmation);
        TextView bodyView = findViewById(R.id.confirmBody);
        confirm = findViewById(R.id.btnConfirm);
        cancel = findViewById(R.id.btnCancel);
        titleView.setText(title);
        bodyView.setText(body);
        confirm.setText(confirmText);
        cancel.setText("取消");

        confirm.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                if (settled) return;
                settled = true;
                if (listener != null) listener.onConfirm();
                dismiss();
            }
        });
        cancel.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                notifyCancel();
                dismiss();
            }
        });
        cancel.setNextFocusRightId(R.id.btnConfirm);
        confirm.setNextFocusLeftId(R.id.btnCancel);
    }

    @Override
    public void show() {
        super.show();
        if (cancel != null) {
            cancel.post(new Runnable() {
                @Override
                public void run() {
                    cancel.requestFocus();
                }
            });
        }
    }

    private void notifyCancel() {
        if (settled) return;
        settled = true;
        if (listener != null) listener.onCancel();
    }

    @Override
    public void onBackPressed() {
        notifyCancel();
        super.onBackPressed();
    }
}
