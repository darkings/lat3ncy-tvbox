package com.github.tvbox.osc.ui.adapter;

import android.widget.TextView;
import android.view.View;

import androidx.core.content.ContextCompat;

import com.chad.library.adapter.base.BaseQuickAdapter;
import com.chad.library.adapter.base.BaseViewHolder;
import com.github.tvbox.osc.R;
import com.github.tvbox.osc.bean.LiveChannelGroup;
import com.github.tvbox.osc.bean.LiveEpgDate;

import java.util.ArrayList;


public class LiveEpgDateAdapter extends BaseQuickAdapter<LiveEpgDate, BaseViewHolder> {

    private int selectedIndex = -1;
    private int focusedIndex = -1;

    public LiveEpgDateAdapter() {
        super(R.layout.item_live_channel_group, new ArrayList<>());
    }

    @Override
    protected void convert(BaseViewHolder holder, LiveEpgDate item) {
        TextView tvGroupName = holder.getView(R.id.tvChannelGroupName);
        tvGroupName.setText(item.getDatePresented());
        boolean selected = item.getIndex() == selectedIndex;
        holder.itemView.setSelected(selected);
        holder.<View>getView(R.id.stateRail).setVisibility(selected ? View.VISIBLE : View.INVISIBLE);
        if (item.getIndex() == selectedIndex && item.getIndex() != focusedIndex) {
            tvGroupName.setTextColor(ContextCompat.getColor(mContext, R.color.md3_primary));
        }else {
            tvGroupName.setTextColor(ContextCompat.getColor(mContext, R.color.md3_on_surface_variant));
        }
    }

    public void setSelectedIndex(int selectedIndex) {
        if (selectedIndex == this.selectedIndex) return;
        int preSelectedIndex = this.selectedIndex;
        this.selectedIndex = selectedIndex;
        notifyItemByDateIndex(preSelectedIndex);
        notifyItemByDateIndex(this.selectedIndex);
    }

    public int getSelectedIndex() {
        return selectedIndex;
    }

    public void setFocusedIndex(int focusedIndex) {
        if (this.focusedIndex == focusedIndex) return;
        int previousFocusedIndex = this.focusedIndex;
        this.focusedIndex = focusedIndex;
        notifyItemByDateIndex(previousFocusedIndex);
        notifyItemByDateIndex(this.focusedIndex);
        if (this.focusedIndex == -1) notifyItemByDateIndex(this.selectedIndex);
    }

    private void notifyItemByDateIndex(int dateIndex) {
        for (int position = 0; position < getData().size(); position++) {
            if (getData().get(position).getIndex() == dateIndex) {
                notifyItemChanged(position);
                return;
            }
        }
    }
}
