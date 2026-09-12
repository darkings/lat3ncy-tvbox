package com.github.tvbox.osc.ui.adapter;

import android.text.TextUtils;
import android.view.View;
import android.widget.ImageView;
import android.widget.TextView;

import com.chad.library.adapter.base.BaseQuickAdapter;
import com.chad.library.adapter.base.BaseViewHolder;
import com.github.tvbox.osc.R;
import com.github.tvbox.osc.api.ApiConfig;
import com.github.tvbox.osc.bean.Movie;
import com.github.tvbox.osc.bean.SourceBean;
import com.github.tvbox.osc.util.HawkConfig;
import com.github.tvbox.osc.util.ImgUtil;
import com.github.tvbox.osc.util.PosterCardLayout;
import com.github.tvbox.osc.util.PosterMetaFormatter;
import com.github.tvbox.osc.util.QualityBadge;
import com.orhanobut.hawk.Hawk;

import java.util.ArrayList;

import me.jessyan.autosize.utils.AutoSizeUtils;

/** Search result adapter: lite mode uses a structured result row; normal mode is a shared poster card. */
public class SearchAdapter extends BaseQuickAdapter<Movie.Video, BaseViewHolder> {
    private static final int POSTER_WIDTH = 200;
    private static final int POSTER_HEIGHT = 300;

    public SearchAdapter() {
        super(Hawk.get(HawkConfig.SEARCH_VIEW, 0) == 0
                ? R.layout.item_search_lite
                : R.layout.item_search_normal, new ArrayList<>());
    }

    @Override
    protected void convert(BaseViewHolder helper, Movie.Video item) {
        SourceBean source = item == null ? null : ApiConfig.get().getSource(item.sourceKey);
        String sourceName = source == null ? "来源" : source.getName();
        PosterMetaFormatter.Meta meta = PosterMetaFormatter.forVideo(item);
        if (Hawk.get(HawkConfig.SEARCH_VIEW, 0) == 0) {
            String type = item == null ? "" : item.type;
            helper.setText(R.id.tvSearchSource, sourceName);
            helper.setText(R.id.tvName, meta.title);
            setOptional(helper.getView(R.id.tvSearchMeta), type);
            helper.itemView.setSelected(false);
            helper.itemView.setContentDescription(meta.contentDescription + "，来源 " + sourceName);
            return;
        }

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
        if (!TextUtils.isEmpty(item == null ? "" : item.pic)) {
            ImgUtil.load(item.pic, imageView, radius, width, height, meta.title);
        } else {
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
