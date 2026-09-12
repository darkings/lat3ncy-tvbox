package com.github.tvbox.osc.ui.adapter;

import android.graphics.Bitmap;
import android.text.TextUtils;
import android.view.View;
import android.widget.ImageView;

import com.chad.library.adapter.base.BaseQuickAdapter;
import com.chad.library.adapter.base.BaseViewHolder;
import com.github.tvbox.osc.R;
import com.github.tvbox.osc.bean.Movie;
import com.github.tvbox.osc.util.ImgUtil;
import com.github.tvbox.osc.util.PosterCardLayout;
import com.github.tvbox.osc.util.PosterMetaFormatter;

import java.util.ArrayList;

import me.jessyan.autosize.utils.AutoSizeUtils;

/** Grid cards use the shared 2:3 poster contract; list mode stays a text-row variant. */
public class GridAdapter extends BaseQuickAdapter<Movie.Video, BaseViewHolder> {
    private static final int POSTER_WIDTH = 200;
    private static final int POSTER_HEIGHT = 300;
    private static final int POSTER_RADIUS_DP = 12;

    private boolean mShowList;
    public ImgUtil.Style style;

    public GridAdapter(boolean showList, ImgUtil.Style style) {
        super(showList ? R.layout.item_list : R.layout.item_grid, new ArrayList<>());
        this.mShowList = showList || (style != null && "list".equals(style.type));
        this.style = style;
    }

    @Override
    protected void convert(BaseViewHolder helper, Movie.Video item) {
        PosterMetaFormatter.Meta meta = PosterMetaFormatter.forVideo(item);
        if (mShowList) {
            helper.setText(R.id.tvNote, item == null ? "" : item.note);
            helper.setText(R.id.tvName, meta.title);
            bindImage(helper.getView(R.id.ivThumb), item == null ? "" : item.pic,
                    AutoSizeUtils.mm2px(mContext, 240),
                    AutoSizeUtils.mm2px(mContext, 336), meta.title);
            helper.itemView.setContentDescription(meta.contentDescription);
            return;
        }

        TextViewState.setBadge(helper.getView(R.id.tvYear), meta.badge);
        PosterCardLayout.apply(helper.itemView, meta);
        helper.setVisible(R.id.tvLang, false);
        helper.setVisible(R.id.tvArea, false);
        helper.setVisible(R.id.tvActor, false);
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
            return;
        }
        if (ImgUtil.isBase64Image(pic)) {
            Bitmap bitmap = ImgUtil.decodeBase64ToBitmap(pic);
            if (bitmap != null) {
                imageView.setImageBitmap(bitmap);
                return;
            }
            imageView.setImageDrawable(ImgUtil.createImagePlaceholderDrawable(width, height, radius));
            return;
        }
        ImgUtil.load(pic, imageView, radius, width, height, label);
    }

    private static final class TextViewState {
        private static void setBadge(android.widget.TextView view, String text) {
            if (TextUtils.isEmpty(text)) {
                view.setText("");
                view.setVisibility(View.GONE);
            } else {
                view.setText(text);
                view.setVisibility(View.VISIBLE);
            }
        }

        private static void setOptional(android.widget.TextView view, String text) {
            setBadge(view, text);
        }
    }
}
