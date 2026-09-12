package com.github.tvbox.osc.ui.tv.widget;

import android.content.Context;
import android.util.AttributeSet;
import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.view.animation.PathInterpolator;
import android.widget.LinearLayout;
import android.widget.TextView;

import com.chad.library.adapter.base.BaseQuickAdapter;
import com.github.tvbox.osc.R;
import com.github.tvbox.osc.bean.MovieSort;
import com.github.tvbox.osc.ui.adapter.GridFilterKVAdapter;
import com.github.tvbox.osc.util.HawkConfig;
import com.owen.tvrecyclerview.widget.TvRecyclerView;
import com.owen.tvrecyclerview.widget.V7LinearLayoutManager;
import com.orhanobut.hawk.Hawk;

import java.util.ArrayList;

/**
 * 首页分类的内联筛选面板：不是 Dialog，作为 contentLayout 的一部分显示，
 * 高度随内容自适应，焦点可以在分类 Tab、面板和内容网格之间自然上下移动。
 */
public class GridFilterPanel extends LinearLayout {
    public interface Callback {
        void change();
    }

    private LinearLayout filterContent;
    private MovieSort.SortData activeSortData;
    private Callback changeCallback;
    private Runnable closeCallback;

    public GridFilterPanel(Context context) {
        this(context, null);
    }

    public GridFilterPanel(Context context, AttributeSet attrs) {
        super(context, attrs);
        LayoutInflater.from(context).inflate(R.layout.view_grid_filter, this, true);
        filterContent = findViewById(R.id.filterContent);
    }

    public void setOnChange(Callback callback) {
        changeCallback = callback;
    }

    /**
     * 点选任意筛选值后由首页收起面板，并把焦点还回分类栏。
     */
    public void setOnSelectClose(Runnable callback) {
        closeCallback = callback;
    }

    public boolean isPanelVisible() {
        return getVisibility() == View.VISIBLE;
    }

    public void showPanel() {
        setVisibility(View.VISIBLE);
        post(() -> focusFirstFilter());
    }

    public void hidePanel() {
        setVisibility(View.GONE);
    }

    public void focusFirstFilter() {
        View target = findFocusableChild(filterContent);
        if (target != null) {
            target.requestFocus();
        }
    }

    public void setData(MovieSort.SortData sortData) {
        activeSortData = sortData;
        filterContent.removeAllViews();
        if (sortData == null || sortData.filters == null) {
            return;
        }
        if (sortData.filterSelect == null) {
            sortData.filterSelect = new java.util.HashMap<>();
        }

        LayoutInflater inflater = LayoutInflater.from(getContext());
        for (MovieSort.SortFilter filter : sortData.filters) {
            if (filter == null || filter.values == null || filter.values.isEmpty()) {
                continue;
            }
            View line = inflater.inflate(R.layout.item_grid_filter, filterContent, false);
            TextView name = line.findViewById(R.id.filterName);
            name.setText(filter.name);
            TvRecyclerView gridView = line.findViewById(R.id.mFilterKv);
            gridView.setHasFixedSize(true);
            gridView.setLayoutManager(new V7LinearLayoutManager(getContext(), 0, false));
            gridView.setOnItemListener(new TvRecyclerView.OnItemListener() {
                @Override
                public void onItemPreSelected(TvRecyclerView parent, View itemView, int position) {
                    if (itemView == null) return;
                    GridFilterPanel.this.invalidate();
                    itemView.animate().cancel();
                    itemView.animate().scaleX(1.0f).scaleY(1.0f).setDuration(100)
                            .withEndAction(() -> GridFilterPanel.this.invalidate())
                            .start();
                }

                @Override
                public void onItemSelected(TvRecyclerView parent, View itemView, int position) {
                    if (itemView == null) return;
                    if (Hawk.get(HawkConfig.REDUCE_MOTION, false)) {
                        itemView.setScaleX(1.0f);
                        itemView.setScaleY(1.0f);
                        return;
                    }
                    itemView.animate().cancel();
                    itemView.animate().scaleX(1.06f).scaleY(1.06f).setDuration(120)
                            .setInterpolator(new PathInterpolator(0.05f, 0.7f, 0.1f, 1f)).start();
                }

                @Override
                public void onItemClick(TvRecyclerView parent, View itemView, int position) {
                }
            });

            final String key = filter.key;
            final ArrayList<String> displayValues = new ArrayList<>(filter.values.keySet());
            final ArrayList<String> actualValues = new ArrayList<>(filter.values.values());
            GridFilterKVAdapter adapter = new GridFilterKVAdapter();
            gridView.setAdapter(adapter);
            adapter.setOnItemClickListener(new BaseQuickAdapter.OnItemClickListener() {
                @Override
                public void onItemClick(BaseQuickAdapter clicked, View view, int position) {
                    if (position < 0 || position >= actualValues.size() || activeSortData == null) {
                        return;
                    }
                    String current = activeSortData.filterSelect.get(key);
                    String next = actualValues.get(position);
                    if (next == null) {
                        return;
                    }
                    String selected;
                    if (next.equals(current)) {
                        // 再点已选项 = 取消该组筛选
                        activeSortData.filterSelect.remove(key);
                        selected = null;
                    } else {
                        activeSortData.filterSelect.put(key, next);
                        selected = next;
                    }
                    adapter.setSelectedActual(selected);
                    flushImmediateRefresh();
                    // 选中/取消后立即关面板，再次展开仍从 filterSelect 画已选态
                    if (closeCallback != null) {
                        closeCallback.run();
                    }
                }
            });
            // 再次展开时用当前 filterSelect 画选中芯片，而不是先清成未选再补
            adapter.bind(displayValues, actualValues, sortData.filterSelect.get(key));
            filterContent.addView(line);
        }
    }

    private void flushImmediateRefresh() {
        if (changeCallback == null) {
            return;
        }
        changeCallback.change();
    }

    private View findFocusableChild(View view) {
        if (view == null) return null;
        if (view.isFocusable() && view.getVisibility() == View.VISIBLE) return view;
        if (view instanceof ViewGroup) {
            ViewGroup group = (ViewGroup) view;
            for (int i = 0; i < group.getChildCount(); i++) {
                View result = findFocusableChild(group.getChildAt(i));
                if (result != null) return result;
            }
        }
        return null;
    }
}
