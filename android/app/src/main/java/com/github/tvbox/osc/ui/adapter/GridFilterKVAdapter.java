package com.github.tvbox.osc.ui.adapter;

import android.widget.TextView;

import androidx.core.content.ContextCompat;

import com.chad.library.adapter.base.BaseQuickAdapter;
import com.chad.library.adapter.base.BaseViewHolder;
import com.github.tvbox.osc.R;

import java.util.ArrayList;
import java.util.List;

/**
 * 筛选芯片适配器。展示名和实际筛选值分开保存，convert 时按实际值画已选态，
 * 避免 RecyclerView 复用或再次展开时把选中背景清掉。
 */
public class GridFilterKVAdapter extends BaseQuickAdapter<String, BaseViewHolder> {
    private List<String> actualValues = new ArrayList<>();
    private String selectedActual;

    public GridFilterKVAdapter() {
        super(R.layout.item_grid_filter_value, new ArrayList<>());
    }

    /**
     * 绑定一行筛选值：展示文案、接口实际值、当前已选项。
     */
    public void bind(List<String> displayValues, List<String> actualValues, String selectedActual) {
        this.actualValues = actualValues != null ? new ArrayList<>(actualValues) : new ArrayList<>();
        this.selectedActual = selectedActual;
        setNewData(displayValues != null ? new ArrayList<>(displayValues) : new ArrayList<>());
    }

    /**
     * 点选后只更新已选值并刷新可见芯片，不必重建整行。
     */
    public void setSelectedActual(String selectedActual) {
        this.selectedActual = selectedActual;
        notifyDataSetChanged();
    }

    @Override
    protected void convert(BaseViewHolder helper, String item) {
        TextView value = helper.getView(R.id.filterValue);
        value.setText(item);
        int position = helper.getAdapterPosition();
        String actual = (position >= 0 && position < actualValues.size())
                ? actualValues.get(position) : null;
        // 库会把焦点项强制 setSelected(true)，已选不能靠 selected 状态；用背景区分。
        boolean isSelected = selectedActual != null && selectedActual.equals(actual);
        value.setBackgroundResource(isSelected
                ? R.drawable.md3_filter_value_selected : R.drawable.md3_filter_value);
        value.setTextColor(ContextCompat.getColor(helper.itemView.getContext(),
                isSelected ? R.color.md3_on_primary : R.color.md3_on_surface));
        value.getPaint().setFakeBoldText(isSelected);
    }
}
