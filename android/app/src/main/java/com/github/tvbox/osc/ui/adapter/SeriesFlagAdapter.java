package com.github.tvbox.osc.ui.adapter;

import android.app.Activity;
import android.view.View;
import android.widget.TextView;

import com.chad.library.adapter.base.BaseQuickAdapter;
import com.chad.library.adapter.base.BaseViewHolder;
import com.github.tvbox.osc.R;
import com.github.tvbox.osc.bean.VodInfo;

import java.util.ArrayList;

/**
 * @author pj567
 * @date :2020/12/22
 * @description:
 */
public class SeriesFlagAdapter extends BaseQuickAdapter<VodInfo.VodSeriesFlag, BaseViewHolder> {
    public SeriesFlagAdapter() {
        super(R.layout.item_series_flag, new ArrayList<>());
    }

    @Override
    protected void convert(BaseViewHolder helper, VodInfo.VodSeriesFlag item) {
        TextView tvSeries = helper.getView(R.id.tvSeriesFlag);
        TextView tvMeta = helper.getView(R.id.tvSeriesFlagMeta);
        View stateRail = helper.getView(R.id.stateRail);
        helper.itemView.setSelected(item.selected);
        stateRail.setVisibility(item.selected ? View.VISIBLE : View.INVISIBLE);
        helper.setText(R.id.tvSeriesFlag, item.displayName == null || item.displayName.isEmpty() ? item.name : item.displayName);
        if (tvMeta != null) {
            tvMeta.setText(item.statusText == null || item.statusText.isEmpty() ? "线路" : item.statusText);
        }
        View mSeriesGroupTv = ((Activity) helper.itemView.getContext()).findViewById(R.id.mSeriesGroupTv);
        View mGridViewQuality = ((Activity) helper.itemView.getContext()).findViewById(R.id.mGridViewQuality);
        if (mSeriesGroupTv != null && mSeriesGroupTv.getVisibility() == View.VISIBLE) {
            helper.itemView.setNextFocusDownId(R.id.mSeriesSortTv);
        } else if (mGridViewQuality != null && mGridViewQuality.getVisibility() == View.VISIBLE) {
            helper.itemView.setNextFocusDownId(R.id.mGridViewQuality);
        }else {
            helper.itemView.setNextFocusDownId(R.id.mGridView);
        }
        if (helper.getLayoutPosition() == getData().size() - 1) {
            helper.itemView.setId(View.generateViewId());
            helper.itemView.setNextFocusRightId(helper.itemView.getId());
        }else {
            helper.itemView.setNextFocusRightId(View.NO_ID);
        }
    }
}
