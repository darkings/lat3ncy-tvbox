package com.github.tvbox.osc.ui.adapter;

import android.view.View;

import com.chad.library.adapter.base.BaseQuickAdapter;
import com.chad.library.adapter.base.BaseViewHolder;
import com.github.tvbox.osc.R;

import java.util.ArrayList;

/**
 * @author pj567
 * @date :2020/12/23
 * @description:
 */
public class SettingMenuAdapter extends BaseQuickAdapter<String, BaseViewHolder> {
    private int selectedPosition;

    public SettingMenuAdapter() {
        super(R.layout.item_setting_menu, new ArrayList<>());
    }

    @Override
    protected void convert(BaseViewHolder helper, String item) {
        helper.setText(R.id.tvName, item);
        helper.addOnClickListener(R.id.tvName);
        boolean selected = helper.getLayoutPosition() == selectedPosition;
        helper.itemView.setSelected(selected);
        helper.<View>getView(R.id.stateRail).setVisibility(selected ? View.VISIBLE : View.INVISIBLE);
    }

    public void setSelectedPosition(int selectedPosition) {
        if (this.selectedPosition == selectedPosition) return;
        int previous = this.selectedPosition;
        this.selectedPosition = selectedPosition;
        if (previous >= 0 && previous < getItemCount()) notifyItemChanged(previous);
        if (selectedPosition >= 0 && selectedPosition < getItemCount()) notifyItemChanged(selectedPosition);
    }
}
