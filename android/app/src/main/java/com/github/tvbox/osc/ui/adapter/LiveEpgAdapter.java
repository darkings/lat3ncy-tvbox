package com.github.tvbox.osc.ui.adapter;

import android.annotation.SuppressLint;
import android.util.Log;
import android.view.View;
import android.widget.TextView;

import androidx.core.content.ContextCompat;

import com.chad.library.adapter.base.BaseQuickAdapter;
import com.chad.library.adapter.base.BaseViewHolder;
import com.github.tvbox.osc.R;
import com.github.tvbox.osc.ui.tv.widget.AudioWaveView;
import com.github.tvbox.osc.bean.Epginfo;

import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Date;
import java.util.List;

public class LiveEpgAdapter extends BaseQuickAdapter<Epginfo, BaseViewHolder> {
    private int selectedEpgIndex = -1;
    private int focusedEpgIndex = -1;
    public static float fontSize = 20;
    private final int defaultShiyiSelection = 0;
    private boolean ShiyiSelection = false;
    private String shiyiDate = null;
    private final String currentEpgDate = null;
    private final int focusSelection = -1;
    private boolean source_include_back = false;

    SimpleDateFormat timeFormat = new SimpleDateFormat("yyyy-MM-dd");
    public LiveEpgAdapter() {
        super(R.layout.epglist_item, new ArrayList<>());
    }

    public void CanBack( Boolean source_include_back){
        this.source_include_back = source_include_back;
    }

    @SuppressLint("SetTextI18n")
    @Override
    protected void convert(BaseViewHolder holder, Epginfo value) {
        TextView textview = holder.getView(R.id.tv_epg_name);
        TextView timeview = holder.getView(R.id.tv_epg_time);
        TextView shiyi = holder.getView(R.id.shiyi);
        View liveNowChip = holder.getView(R.id.live_now_chip);
        AudioWaveView wqddg_AudioWaveView = holder.getView(R.id.wqddg_AudioWaveView);
        int onSurfaceColor = ContextCompat.getColor(mContext, R.color.md3_on_surface);
        int primaryColor = ContextCompat.getColor(mContext, R.color.md3_primary);
        int onPrimaryColor = ContextCompat.getColor(mContext, R.color.md3_on_primary);
        int onTertiaryColor = ContextCompat.getColor(mContext, R.color.md3_on_tertiary);
        boolean selected = value.index == selectedEpgIndex;
        holder.itemView.setSelected(selected);
        holder.<View>getView(R.id.stateRail).setVisibility(selected ? View.VISIBLE : View.INVISIBLE);
        textview.setSelected(true);
        timeview.setSelected(true);
        liveNowChip.setVisibility(View.GONE);
        liveNowChip.setBackgroundResource(R.drawable.live_epg_replay_badge);
        shiyi.setVisibility(View.GONE);
        wqddg_AudioWaveView.setVisibility(View.GONE);
        if (value.index == selectedEpgIndex && value.index != focusedEpgIndex && (value.currentEpgDate.equals(shiyiDate) || value.currentEpgDate.equals(timeFormat.format(new Date())))) {
            textview.setTextColor(primaryColor);
            timeview.setTextColor(primaryColor);
        }else {
            textview.setTextColor(onSurfaceColor);
            timeview.setTextColor(onSurfaceColor);
        }
        if (new Date().compareTo(value.startdateTime) >= 0 && new Date().compareTo(value.enddateTime) <= 0) {
            liveNowChip.setVisibility(View.VISIBLE);
            liveNowChip.setBackgroundResource(R.drawable.live_epg_live_badge);
            shiyi.setVisibility(View.VISIBLE);
            shiyi.setBackground(null);
            shiyi.setText("直播中");
            shiyi.setTextColor(onPrimaryColor);
        } else if (new Date().compareTo(value.enddateTime) > 0 && source_include_back ) {
            liveNowChip.setVisibility(View.VISIBLE);
            liveNowChip.setBackgroundResource(R.drawable.live_epg_replay_badge);
            shiyi.setVisibility(View.VISIBLE);
            shiyi.setBackground(null);
            shiyi.setTextColor(onTertiaryColor);
            shiyi.setText("回看");
        } else {
            liveNowChip.setVisibility(View.GONE);
            shiyi.setVisibility(View.GONE);
        }
        textview.setText(value.title);
        timeview.setText(value.start + "--" + value.end);
        if (!ShiyiSelection) {
            Date now = new Date();
            if (now.compareTo(value.startdateTime) >= 0 && now.compareTo(value.enddateTime) <= 0) {
                wqddg_AudioWaveView.setVisibility(View.VISIBLE);
                textview.setFreezesText(true);
                timeview.setFreezesText(true);
            } else {
                wqddg_AudioWaveView.setVisibility(View.GONE);
            }
        } else {
            if (value.index == this.selectedEpgIndex && value.currentEpgDate.equals(shiyiDate)) {
                wqddg_AudioWaveView.setVisibility(View.VISIBLE);
                textview.setFreezesText(true);
                timeview.setFreezesText(true);
                liveNowChip.setVisibility(View.VISIBLE);
                liveNowChip.setBackgroundResource(R.drawable.live_epg_live_badge);
                shiyi.setVisibility(View.VISIBLE);
                shiyi.setBackground(null);
                shiyi.setText("回看中");
                shiyi.setTextColor(onPrimaryColor);
                if (new Date().compareTo(value.startdateTime) >= 0 && new Date().compareTo(value.enddateTime) <= 0) {
                    shiyi.setText("直播中");
                    shiyi.setTextColor(onPrimaryColor);
                }
            } else {
                wqddg_AudioWaveView.setVisibility(View.GONE);
            }
        }

    }
    public void setShiyiSelection(int i, boolean t, String currentEpgDate) {
        int previousSelectedIndex = this.selectedEpgIndex;
        this.selectedEpgIndex = i;
        this.shiyiDate = t ? currentEpgDate : null;
        ShiyiSelection = t;
        notifyItemByEpgIndex(previousSelectedIndex);
        notifyItemByEpgIndex(this.selectedEpgIndex);

    }
    public int getSelectedIndex() {
        return selectedEpgIndex;
    }

    public void setSelectedEpgIndex(int selectedEpgIndex) {
        if (selectedEpgIndex == this.selectedEpgIndex) {
            notifyItemByEpgIndex(this.selectedEpgIndex);
            return;
        }
        int preSelectedEpgIndex = this.selectedEpgIndex;
        this.selectedEpgIndex = selectedEpgIndex;
        notifyItemByEpgIndex(preSelectedEpgIndex);
        notifyItemByEpgIndex(this.selectedEpgIndex);
    }


    public int getFocusedEpgIndex() {
        return focusedEpgIndex;
    }

    public void setFocusedEpgIndex(int focusedEpgIndex) {
        if (this.focusedEpgIndex == focusedEpgIndex) return;
        int previousFocusedEpgIndex = this.focusedEpgIndex;
        this.focusedEpgIndex = focusedEpgIndex;
        notifyItemByEpgIndex(previousFocusedEpgIndex);
        notifyItemByEpgIndex(this.focusedEpgIndex);
        if (this.focusedEpgIndex == -1) notifyItemByEpgIndex(this.selectedEpgIndex);
    }

    private void notifyItemByEpgIndex(int epgIndex) {
        for (int position = 0; position < getData().size(); position++) {
            if (getData().get(position).index == epgIndex) {
                notifyItemChanged(position);
                return;
            }
        }
    }
}
