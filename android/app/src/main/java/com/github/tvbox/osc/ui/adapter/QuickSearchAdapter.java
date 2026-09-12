package com.github.tvbox.osc.ui.adapter;

import com.chad.library.adapter.base.BaseQuickAdapter;
import com.chad.library.adapter.base.BaseViewHolder;
import com.github.tvbox.osc.R;
import com.github.tvbox.osc.bean.Movie;
import com.github.tvbox.osc.util.VodPlayData;

import java.util.ArrayList;

/**
 * @author pj567
 * @date :2020/12/23
 * @description:
 */
public class QuickSearchAdapter extends BaseQuickAdapter<Movie.Video, BaseViewHolder> {
    public QuickSearchAdapter() {
        super(R.layout.item_quick_search_lite, new ArrayList<>());
    }

    @Override
    protected void convert(BaseViewHolder helper, Movie.Video item) {
        // lite
        String sourceName = VodPlayData.getSourceName(item == null ? null : item.sourceKey);
        String name = item == null || item.name == null ? "" : item.name;
        String type = item == null || item.type == null ? "" : item.type;
        String note = item == null || item.note == null ? "" : item.note;
        helper.setText(R.id.tvName, String.format("%s  %s %s %s", sourceName, name, type, note));
        boolean valid = VodPlayData.isValidSearchVideo(item);
        helper.itemView.setAlpha(valid ? 1f : 0.45f);
        helper.itemView.setEnabled(valid);
        // with preview
        /*
        helper.setText(R.id.tvName, item.name);
        helper.setText(R.id.tvSite, ApiConfig.get().getSource(item.sourceKey).getName());
        helper.setVisible(R.id.tvNote, item.note != null && !item.note.isEmpty());
        if (item.note != null && !item.note.isEmpty()) {
            helper.setText(R.id.tvNote, item.note);
        }
        ImageView ivThumb = helper.getView(R.id.ivThumb);
        if (!TextUtils.isEmpty(item.pic)) {
            Picasso.get()
                    .load(item.pic)
                    .transform(new RoundTransformation(MD5.string2MD5(item.pic + "position=" + helper.getLayoutPosition()))
                            .centerCorp(true)
                            .override(AutoSizeUtils.mm2px(mContext, 300), AutoSizeUtils.mm2px(mContext, 400))
                            .roundRadius(AutoSizeUtils.mm2px(mContext, 10), RoundTransformation.RoundType.ALL))
                    .placeholder(R.drawable.error_loading)
                    .error(R.drawable.error_loading)
                    .into(ivThumb);
        } else {
            ivThumb.setImageResource(R.drawable.error_loading);
        }
        */
    }
}