package com.github.tvbox.osc.ui.dialog;

import android.content.Context;
import android.widget.TextView;

import androidx.annotation.NonNull;

import com.github.tvbox.osc.R;
import com.github.tvbox.osc.util.DefaultConfig;

import org.jetbrains.annotations.NotNull;

public class AboutDialog extends BaseDialog {

    public AboutDialog(@NonNull @NotNull Context context) {
        super(context);
        setContentView(R.layout.dialog_about);

        TextView tvVersion = findViewById(R.id.aboutVersion);
        String versionName = DefaultConfig.getAppVersionName(context);
        int versionCode = DefaultConfig.getAppVersionCode(context);
        tvVersion.setText("版本 " + versionName + " · 构建 " + versionCode);

        findViewById(R.id.aboutClose).setOnClickListener(v -> dismiss());
    }
}
