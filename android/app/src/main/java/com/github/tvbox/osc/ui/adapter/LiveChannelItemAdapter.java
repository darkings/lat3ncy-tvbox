package com.github.tvbox.osc.ui.adapter;

import android.widget.TextView;
import android.view.View;

import androidx.core.content.ContextCompat;

import com.chad.library.adapter.base.BaseQuickAdapter;
import com.chad.library.adapter.base.BaseViewHolder;
import com.github.tvbox.osc.R;
import com.github.tvbox.osc.bean.LiveChannelItem;

import java.util.ArrayList;

/**
 * @author pj567
 * @date :2021/1/12
 * @description:
 */
public class LiveChannelItemAdapter extends BaseQuickAdapter<LiveChannelItem, BaseViewHolder> {
    private int selectedChannelIndex = -1;
    private int focusedChannelIndex = -1;

    public LiveChannelItemAdapter() {
        super(R.layout.item_live_channel, new ArrayList<>());
    }

    @Override
    protected void convert(BaseViewHolder holder, LiveChannelItem item) {
        TextView tvChannelNum = holder.getView(R.id.tvChannelNum);
        TextView tvChannel = holder.getView(R.id.tvChannelName);
        tvChannelNum.setText(String.format("%s", item.getChannelNum()));
        tvChannel.setText(item.getChannelName());
        tvChannelNum.setSelected(true);
        tvChannel.setSelected(true);
        int channelIndex = item.getChannelIndex();
        boolean selected = channelIndex == selectedChannelIndex;
        holder.itemView.setSelected(selected);
        holder.<View>getView(R.id.stateRail).setVisibility(selected ? View.VISIBLE : View.INVISIBLE);
        if (channelIndex == selectedChannelIndex && channelIndex != focusedChannelIndex) {
            int selectedColor = ContextCompat.getColor(mContext, R.color.md3_primary);
            tvChannelNum.setTextColor(selectedColor);
            tvChannel.setTextColor(selectedColor);
        }
        else{
            int defaultColor = ContextCompat.getColor(mContext, R.color.md3_on_surface);
            tvChannelNum.setTextColor(defaultColor);
            tvChannel.setTextColor(defaultColor);
        }
    }

    public void setSelectedChannelIndex(int selectedChannelIndex) {
        if (selectedChannelIndex == this.selectedChannelIndex) return;
        int preSelectedChannelIndex = this.selectedChannelIndex;
        this.selectedChannelIndex = selectedChannelIndex;
        notifyItemByChannelIndex(preSelectedChannelIndex);
        notifyItemByChannelIndex(this.selectedChannelIndex);
    }

    public void setFocusedChannelIndex(int focusedChannelIndex) {
        if (focusedChannelIndex == this.focusedChannelIndex) return;
        int preFocusedChannelIndex = this.focusedChannelIndex;
        this.focusedChannelIndex = focusedChannelIndex;
        notifyItemByChannelIndex(preFocusedChannelIndex);
        notifyItemByChannelIndex(this.focusedChannelIndex);
        if (this.focusedChannelIndex == -1) notifyItemByChannelIndex(this.selectedChannelIndex);
    }

    private void notifyItemByChannelIndex(int channelIndex) {
        for (int position = 0; position < getData().size(); position++) {
            if (getData().get(position).getChannelIndex() == channelIndex) {
                notifyItemChanged(position);
                return;
            }
        }
    }
}
