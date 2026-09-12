package com.github.tvbox.osc.ui.adapter;

import android.widget.TextView;
import android.view.View;

import androidx.core.content.ContextCompat;

import com.chad.library.adapter.base.BaseQuickAdapter;
import com.chad.library.adapter.base.BaseViewHolder;
import com.github.tvbox.osc.R;
import com.github.tvbox.osc.bean.LiveSettingItem;

import java.util.ArrayList;


/**
 * @author pj567
 * @date :2021/1/12
 * @description:
 */
public class LiveSettingItemAdapter extends BaseQuickAdapter<LiveSettingItem, BaseViewHolder> {
    private int focusedItemIndex = -1;

    public LiveSettingItemAdapter() {
        super(R.layout.item_live_setting, new ArrayList<>());
    }

    @Override
    protected void convert(BaseViewHolder holder, LiveSettingItem item) {
        TextView tvItemName = holder.getView(R.id.tvSettingItemName);
        tvItemName.setText(item.getItemName());
        tvItemName.setSelected(true);
        int itemIndex = item.getItemIndex();
        boolean selected = item.isItemSelected();
        holder.itemView.setSelected(selected);
        holder.<View>getView(R.id.stateRail).setVisibility(selected ? View.VISIBLE : View.INVISIBLE);
        if (selected && itemIndex != focusedItemIndex) {
            tvItemName.setTextColor(ContextCompat.getColor(mContext, R.color.md3_primary));
        } else {
            tvItemName.setTextColor(ContextCompat.getColor(mContext, R.color.md3_on_surface));
        }
    }

    public void selectItem(int selectedItemIndex, boolean select, boolean unselectPreItemIndex) {
        if (unselectPreItemIndex) {
            int preSelectedItemIndex = getSelectedItemIndex();
            if (preSelectedItemIndex != -1) {
                int previousPosition = findPositionByItemIndex(preSelectedItemIndex);
                if (previousPosition != -1) {
                    getData().get(previousPosition).setItemSelected(false);
                    notifyItemChanged(previousPosition);
                }
            }
        }
        int selectedPosition = findPositionByItemIndex(selectedItemIndex);
        if (selectedPosition != -1) {
            getData().get(selectedPosition).setItemSelected(select);
            notifyItemChanged(selectedPosition);
        }
    }

    public void setFocusedItemIndex(int focusedItemIndex) {
        if (this.focusedItemIndex == focusedItemIndex) return;
        int preFocusItemIndex = this.focusedItemIndex;
        this.focusedItemIndex = focusedItemIndex;
        notifyItemByItemIndex(preFocusItemIndex);
        notifyItemByItemIndex(this.focusedItemIndex);
    }

    public int getSelectedItemIndex() {
        for (LiveSettingItem item : getData()) {
            if (item.isItemSelected())
                return item.getItemIndex();
        }
        return -1;
    }

    private int findPositionByItemIndex(int itemIndex) {
        for (int position = 0; position < getData().size(); position++) {
            if (getData().get(position).getItemIndex() == itemIndex) return position;
        }
        return -1;
    }

    private void notifyItemByItemIndex(int itemIndex) {
        int position = findPositionByItemIndex(itemIndex);
        if (position != -1) notifyItemChanged(position);
    }
}
