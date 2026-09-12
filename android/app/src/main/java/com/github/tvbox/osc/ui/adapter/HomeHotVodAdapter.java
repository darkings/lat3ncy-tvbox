package com.github.tvbox.osc.ui.adapter;

import android.graphics.Bitmap;
import android.text.TextUtils;
import android.view.View;
import android.widget.FrameLayout;
import android.widget.ImageView;
import android.widget.TextView;

import com.chad.library.adapter.base.BaseQuickAdapter;
import com.chad.library.adapter.base.BaseViewHolder;
import com.github.tvbox.osc.R;
import com.github.tvbox.osc.bean.Movie;
import com.github.tvbox.osc.util.HawkConfig;
import com.github.tvbox.osc.util.ImgUtil;
import com.github.tvbox.osc.util.PosterCardLayout;
import com.github.tvbox.osc.util.PosterMetaFormatter;
import com.orhanobut.hawk.Hawk;

import java.util.ArrayList;

import me.jessyan.autosize.utils.AutoSizeUtils;

/** Home recommendation/history cards share the same poster geometry and copy hierarchy. */
public class HomeHotVodAdapter extends BaseQuickAdapter<Movie.Video, BaseViewHolder> {
    private static final int POSTER_WIDTH = 200;
    private static final int POSTER_HEIGHT = 300;
    private static final int POSTER_RADIUS_DP = 12;

    public HomeHotVodAdapter(ImgUtil.Style style, String tvRate) {
        super(R.layout.item_user_hot_vod, new ArrayList<>());
    }

    @Override
    protected void convert(BaseViewHolder helper, Movie.Video item) {
        PosterMetaFormatter.Meta meta = PosterMetaFormatter.forVideo(item);

        // Delete mode remains a data action, but no longer paints a full-card overlay.
        FrameLayout deleteLayer = helper.getView(R.id.delFrameLayout);
        deleteLayer.setVisibility(View.GONE);

        TextView rateView = helper.getView(R.id.tvRate);
        setOptional(rateView, meta.badge);
        PosterCardLayout.apply(helper.itemView, meta);
        helper.itemView.setSelected(false);
        helper.itemView.setContentDescription(meta.contentDescription);

        bindImage(helper.getView(R.id.ivThumb), item == null ? "" : item.pic,
                AutoSizeUtils.mm2px(mContext, POSTER_WIDTH),
                AutoSizeUtils.mm2px(mContext, POSTER_HEIGHT), meta.title);
    }

    private void bindImage(ImageView imageView, String rawPic, int width, int height, String label) {
        int radius = AutoSizeUtils.dp2px(mContext, POSTER_RADIUS_DP);
        String pic = rawPic == null ? "" : rawPic.trim();
        if (TextUtils.isEmpty(pic)) {
            imageView.setImageDrawable(ImgUtil.createImagePlaceholderDrawable(width, height, radius));
        } else if (ImgUtil.isBase64Image(pic)) {
            Bitmap bitmap = ImgUtil.decodeBase64ToBitmap(pic);
            imageView.setImageDrawable(bitmap == null
                    ? ImgUtil.createImagePlaceholderDrawable(width, height, radius)
                    : new android.graphics.drawable.BitmapDrawable(mContext.getResources(), bitmap));
        } else {
            ImgUtil.load(pic, imageView, radius, width, height, label);
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
