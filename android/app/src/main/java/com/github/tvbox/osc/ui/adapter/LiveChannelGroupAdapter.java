package com.github.tvbox.osc.ui.adapter;

import android.widget.TextView;
import android.view.View;

import androidx.core.content.ContextCompat;

import com.chad.library.adapter.base.BaseQuickAdapter;
import com.chad.library.adapter.base.BaseViewHolder;
import com.github.tvbox.osc.R;
import com.github.tvbox.osc.bean.LiveChannelGroup;

import java.util.ArrayList;


/**
 * @author pj567
 * @date :2021/1/12
 * @description:
 */
public class LiveChannelGroupAdapter extends BaseQuickAdapter<LiveChannelGroup, BaseViewHolder> {
    private int selectedGroupIndex = -1;
    private int focusedGroupIndex = -1;

    public LiveChannelGroupAdapter() {
        super(R.layout.item_live_channel_group, new ArrayList<>());
    }

    @Override
    protected void convert(BaseViewHolder holder, LiveChannelGroup item) {
        TextView tvGroupName = holder.getView(R.id.tvChannelGroupName);
        tvGroupName.setText(item.getGroupName());
        tvGroupName.setSelected(true);
        int groupIndex = item.getGroupIndex();
        boolean selected = groupIndex == selectedGroupIndex;
        holder.itemView.setSelected(selected);
        holder.<View>getView(R.id.stateRail).setVisibility(selected ? View.VISIBLE : View.INVISIBLE);
        if (groupIndex == selectedGroupIndex && groupIndex != focusedGroupIndex) {
            tvGroupName.setTextColor(ContextCompat.getColor(mContext, R.color.md3_primary));
        } else {
            tvGroupName.setTextColor(ContextCompat.getColor(mContext, R.color.md3_on_surface));
        }
    }

    public void setSelectedGroupIndex(int selectedGroupIndex) {
        if (selectedGroupIndex == this.selectedGroupIndex) return;
        int preSelectedGroupIndex = this.selectedGroupIndex;
        this.selectedGroupIndex = selectedGroupIndex;
        notifyItemByGroupIndex(preSelectedGroupIndex);
        notifyItemByGroupIndex(this.selectedGroupIndex);
    }

    public int getSelectedGroupIndex() {
        return selectedGroupIndex;
    }

    public void setFocusedGroupIndex(int focusedGroupIndex) {
        if (this.focusedGroupIndex == focusedGroupIndex) return;
        int previousFocusedGroupIndex = this.focusedGroupIndex;
        this.focusedGroupIndex = focusedGroupIndex;
        notifyItemByGroupIndex(previousFocusedGroupIndex);
        notifyItemByGroupIndex(this.focusedGroupIndex);
        if (this.focusedGroupIndex == -1) notifyItemByGroupIndex(this.selectedGroupIndex);
    }

    private void notifyItemByGroupIndex(int groupIndex) {
        for (int position = 0; position < getData().size(); position++) {
            if (getData().get(position).getGroupIndex() == groupIndex) {
                notifyItemChanged(position);
                return;
            }
        }
    }
}
