package com.github.tvbox.osc.ui.adapter;

import android.graphics.Color;
import android.view.View;
import android.widget.TextView;

import com.chad.library.adapter.base.BaseQuickAdapter;
import com.chad.library.adapter.base.BaseViewHolder;
import com.github.tvbox.osc.R;
import com.github.tvbox.osc.bean.ParseBean;

import java.util.ArrayList;

public class ParseAdapter extends BaseQuickAdapter<ParseBean, BaseViewHolder> {
    public ParseAdapter() {
        super(R.layout.item_play_parse, new ArrayList<>());
    }

    @Override
    protected void convert(BaseViewHolder helper, ParseBean item) {
        TextView tvParse = helper.getView(R.id.tvParse);
        tvParse.setVisibility(View.VISIBLE);
        if (item.isDefault()) {
            tvParse.setTextColor(mContext.getResources().getColor(R.color.md3_tertiary));
        } else {
            tvParse.setTextColor(mContext.getResources().getColor(R.color.md3_on_surface));
        }
        tvParse.setText(item.getName());
        if (helper.getLayoutPosition() == 0) {
            helper.itemView.setNextFocusLeftId(R.id.play_more);
        }
    }
}
