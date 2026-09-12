package com.github.tvbox.osc.ui.adapter;

import android.text.TextUtils;
import android.util.Log;
import android.view.View;
import android.widget.ImageView;
import android.widget.TextView;

import com.chad.library.adapter.base.BaseQuickAdapter;
import com.chad.library.adapter.base.BaseViewHolder;
import com.github.tvbox.osc.R;
import com.github.tvbox.osc.api.ApiConfig;
import com.github.tvbox.osc.bean.Movie;
import com.github.tvbox.osc.bean.SourceBean;
import com.github.tvbox.osc.util.ImgUtil;
import com.github.tvbox.osc.util.PosterCardLayout;
import com.github.tvbox.osc.util.PosterMetaFormatter;
import com.github.tvbox.osc.util.QualityBadge;

import java.util.ArrayList;

import me.jessyan.autosize.utils.AutoSizeUtils;

/** Aggregated search results use the same poster card as normal search results. */
public class FastSearchAdapter extends BaseQuickAdapter<Movie.Video, BaseViewHolder> {
    private static final String TAG = "FastSearchAdapter";
    private static final int POSTER_WIDTH = 200;
    private static final int POSTER_HEIGHT = 300;

    public FastSearchAdapter() {
        super(R.layout.item_search, new ArrayList<>());
    }

    @Override
    protected void convert(BaseViewHolder helper, Movie.Video item) {
        PosterMetaFormatter.Meta meta = PosterMetaFormatter.forVideo(item);
        SourceBean source = item == null ? null : ApiConfig.get().getSource(item.sourceKey);
        String sourceName = source == null ? "来源" : source.getName();
        setOptional(helper.getView(R.id.tvSite), sourceName);
        PosterCardLayout.apply(helper.itemView, meta);
        helper.itemView.setSelected(false);
        helper.itemView.setContentDescription(meta.contentDescription + "，来源 " + sourceName);

        // 右上角清晰度角标：当前源对该片的实测清晰度（异步查询，命中才显示）
        QualityBadge.bind(helper.getView(R.id.tvQuality),
                item == null ? "" : item.sourceKey,
                item == null ? "" : item.name);

        ImageView imageView = helper.getView(R.id.ivThumb);
        int width = AutoSizeUtils.mm2px(mContext, POSTER_WIDTH);
        int height = AutoSizeUtils.mm2px(mContext, POSTER_HEIGHT);
        int radius = AutoSizeUtils.dp2px(mContext, 12);
        String pic = item == null || item.pic == null ? "" : item.pic.trim();
        if (!TextUtils.isEmpty(pic)) {
            ImgUtil.load(pic, imageView, radius, width, height, meta.title);
        } else {
            Log.d(TAG, "empty image for item: " + meta.title);
            imageView.setImageDrawable(ImgUtil.createImagePlaceholderDrawable(width, height, radius));
        }
    }

    private static void setOptional(TextView view, String value) {
        if (TextUtils.isEmpty(value)) {
            view.setText("");
            view.setVisibility(View.GONE);
        } else {
            view.setText(value);
            view.setVisibility(View.VISIBLE);
        }
    }
}
