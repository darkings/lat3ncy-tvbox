package com.github.tvbox.osc.ui.adapter;

import com.chad.library.adapter.base.BaseQuickAdapter;
import com.chad.library.adapter.base.BaseViewHolder;
import com.github.tvbox.osc.R;
import com.github.tvbox.osc.bean.MovieSort;

import java.util.ArrayList;

import android.view.View;

/** 首页真实来源分类的 TV 横向导航适配器。 */
public class SortAdapter extends BaseQuickAdapter<MovieSort.SortData, BaseViewHolder> {
    public SortAdapter() {
        super(R.layout.item_home_sort, new ArrayList<>());
    }

    @Override
    protected void convert(BaseViewHolder helper, MovieSort.SortData item) {
        helper.setText(R.id.tvTitle, item.name);
        helper.getView(R.id.sortSelectedBar).setVisibility(item.select ? View.VISIBLE : View.INVISIBLE);
        // selected 表示当前内容页；focused 由 TV RecyclerView 独立管理。
        helper.itemView.setSelected(item.select);
    }

    /**
     * 更新当前分类的已选态，不抢占 RecyclerView 焦点。
     */
    public void setSelectedPosition(int position) {
        for (int i = 0; i < getData().size(); i++) {
            MovieSort.SortData item = getData().get(i);
            boolean selected = i == position;
            if (item.select != selected) {
                item.select = selected;
                notifyItemChanged(i);
            }
        }
    }
}
