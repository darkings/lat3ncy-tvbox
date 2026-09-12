package com.github.tvbox.osc.ui.adapter;

import android.text.TextUtils;
import android.view.View;
import android.view.ViewGroup;
import android.widget.TextView;

import com.chad.library.adapter.base.BaseQuickAdapter;
import com.chad.library.adapter.base.BaseViewHolder;
import com.github.tvbox.osc.R;

import java.util.ArrayList;

/**
 * 快速搜索左侧源列表。
 * 直接复用设置页左边栏 item_setting_menu：等宽行、浅焦点底、左侧 stateRail。
 */
public class FastListAdapter extends BaseQuickAdapter<String, BaseViewHolder> {
    private String selectedName = "\u5168\u90e8";

    public FastListAdapter() {
        // 不再用搜索芯片布局，和设置页左侧菜单同一套 item
        super(R.layout.item_setting_menu, new ArrayList<>());
    }

    @Override
    protected void convert(BaseViewHolder helper, String item) {
        helper.setText(R.id.tvName, item);
        View itemView = helper.itemView;
        // 子 TextView 不抢焦点，避免嵌套焦点把 DPAD 右移带偏
        if (itemView instanceof ViewGroup) {
            ((ViewGroup) itemView).setDescendantFocusability(ViewGroup.FOCUS_BLOCK_DESCENDANTS);
        }
        TextView textView = helper.getView(R.id.tvName);
        if (textView != null) {
            textView.setFocusable(false);
            textView.setDuplicateParentStateEnabled(true);
            textView.setEllipsize(TextUtils.TruncateAt.END);
        }
        updateSelection(itemView, item);
    }

    public void setSelectedName(String selectedName) {
        this.selectedName = TextUtils.isEmpty(selectedName) ? "\u5168\u90e8" : selectedName;
    }

    public void refreshVisibleSelection(ViewGroup parent) {
        if (parent == null) return;
        for (int i = 0; i < parent.getChildCount(); i++) {
            View child = parent.getChildAt(i);
            TextView textView = child.findViewById(R.id.tvName);
            if (textView != null) {
                updateSelection(child, textView.getText().toString());
            }
        }
    }

    private void updateSelection(View itemView, String item) {
        if (itemView == null) return;
        boolean selected = TextUtils.equals(item, selectedName);
        // TvRecyclerView 会把 selected 绑到焦点上，当前筛选源改用 activated，焦点离开后指示条还在
        itemView.setActivated(selected);
        TextView textView = itemView.findViewById(R.id.tvName);
        View rail = itemView.findViewById(R.id.stateRail);
        if (textView != null) {
            // setting_menu_text 认 selected：未聚焦的当前源仍显示主色
            textView.setSelected(selected);
            textView.setActivated(selected);
        }
        if (rail != null) {
            rail.setVisibility(selected ? View.VISIBLE : View.INVISIBLE);
        }
    }
}
