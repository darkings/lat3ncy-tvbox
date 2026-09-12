package com.github.tvbox.osc.util;

import android.text.TextUtils;
import android.view.View;
import android.view.ViewGroup;
import android.widget.TextView;

import com.github.tvbox.osc.R;

/** Shared layout behavior for poster-shaped cards. */
public final class PosterCardLayout {
    private PosterCardLayout() {
    }

    /** Bind the shared title hierarchy and keep a 1/3-height bottom scrim. */
    public static void apply(View card, PosterMetaFormatter.Meta meta) {
        if (card == null || meta == null) return;

        TextView title = card.findViewById(R.id.tvName);
        TextView subtitle = card.findViewById(R.id.tvNote);
        if (title != null) title.setText(meta.title);
        if (subtitle != null) {
            subtitle.setText(meta.subtitle);
            subtitle.setVisibility(TextUtils.isEmpty(meta.subtitle) ? View.GONE : View.VISIBLE);
        }

        final View scrim = card.findViewById(R.id.posterScrim);
        if (scrim == null) return;

        // 遮罩固定占海报高度 1/3。一行、两行标题共用同一底部渐变，
        // 不再按行数收缩，避免两行被截断或一行时遮罩过矮。
        setScrimHeight(card, scrim, R.dimen.md3_poster_scrim_height);
    }

    private static void setScrimHeight(View card, View scrim, int heightRes) {
        int targetHeight = card.getResources().getDimensionPixelSize(heightRes);
        ViewGroup.LayoutParams params = scrim.getLayoutParams();
        if (params != null && params.height != targetHeight) {
            params.height = targetHeight;
            scrim.setLayoutParams(params);
        }
    }
}
