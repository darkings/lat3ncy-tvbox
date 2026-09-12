package com.github.tvbox.osc.ui.dialog;

import android.content.Context;
import android.content.DialogInterface;
import android.view.Gravity;
import android.view.LayoutInflater;
import android.view.MotionEvent;
import android.view.View;
import android.view.ViewGroup;
import android.view.WindowManager;
import android.view.animation.PathInterpolator;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import androidx.annotation.NonNull;

import com.chad.library.adapter.base.BaseQuickAdapter;
import com.github.tvbox.osc.R;
import com.github.tvbox.osc.bean.MovieSort;
import com.github.tvbox.osc.ui.adapter.GridFilterKVAdapter;
import com.github.tvbox.osc.util.HawkConfig;
import com.owen.tvrecyclerview.widget.TvRecyclerView;
import com.owen.tvrecyclerview.widget.V7LinearLayoutManager;
import com.orhanobut.hawk.Hawk;

import org.jetbrains.annotations.NotNull;

import java.util.ArrayList;

/**
 * TV 筛选面板：筛选条件滚动，重置/应用固定在底部，Selected 与 Focused 分开表达。
 */
public class GridFilterDialog extends BaseDialog {
    public LinearLayout filterRoot;
    public LinearLayout filterContent;
    private ScrollView filterScroll;

    private int anchorTopY = -1;
    private PanelHeightListener panelHeightListener;
    private Runnable panelHiddenListener;
    private Callback dismissCallback;
    private MovieSort.SortData activeSortData;
    private boolean selectChange = false;

    public interface PanelHeightListener {
        void onHeight(int height);
    }

    public interface Callback {
        void change();
    }

    private final DialogInterface.OnDismissListener internalDismissListener = new DialogInterface.OnDismissListener() {
        @Override
        public void onDismiss(DialogInterface dialogInterface) {
            if (selectChange && dismissCallback != null) {
                dismissCallback.change();
            }
            selectChange = false;
            if (panelHiddenListener != null) {
                panelHiddenListener.run();
            }
        }
    };

    public GridFilterDialog(@NonNull @NotNull Context context) {
        super(context);
        setCanceledOnTouchOutside(false);
        setCancelable(true);
        setContentView(R.layout.dialog_grid_filter);
        filterRoot = findViewById(R.id.filterRoot);
        filterContent = findViewById(R.id.filterContent);
        filterScroll = findViewById(R.id.filterScroll);
        setOnDismissListener(internalDismissListener);
        bindOutsideTouchDismiss();
    }

    public void setAnchorTopY(int y) {
        anchorTopY = y;
    }

    public void setPanelHeightListener(PanelHeightListener listener) {
        panelHeightListener = listener;
    }

    public void setPanelHiddenListener(Runnable runnable) {
        panelHiddenListener = runnable;
    }

    public void setOnDismiss(Callback callback) {
        dismissCallback = callback;
    }

    public void setData(MovieSort.SortData sortData) {
        activeSortData = sortData;
        filterContent.removeAllViews();
        if (sortData == null || sortData.filters == null) {
            requestFirstFilterFocus();
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
                    itemView.animate().cancel();
                    itemView.animate().scaleX(1.0f).scaleY(1.0f).setDuration(100).start();
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
                    if (next.equals(current)) {
                        activeSortData.filterSelect.remove(key);
                    } else {
                        activeSortData.filterSelect.put(key, next);
                    }
                    selectChange = true;
                    adapter.setSelectedActual(activeSortData.filterSelect.get(key));
                    // 选中后立即关闭；再次 setData 会从 filterSelect 恢复已选背景
                    dismiss();
                }
            });
            adapter.bind(displayValues, actualValues, sortData.filterSelect.get(key));
            filterContent.addView(line);
        }
        requestFirstFilterFocus();
    }

    public void show() {
        selectChange = false;
        super.show();
        try {
            if (getWindow() != null) getWindow().setWindowAnimations(R.style.FilterDialogAnim);
        } catch (Throwable ignored) {
        }
        WindowManager.LayoutParams layoutParams = getWindow().getAttributes();
        layoutParams.gravity = Gravity.TOP | Gravity.CENTER_HORIZONTAL;
        layoutParams.width = ViewGroup.LayoutParams.MATCH_PARENT;
        layoutParams.height = ViewGroup.LayoutParams.MATCH_PARENT;
        layoutParams.dimAmount = 0f;
        getWindow().getDecorView().setPadding(0, 0, 0, 0);
        getWindow().setAttributes(layoutParams);
        if (anchorTopY >= 0 && filterRoot.getLayoutParams() instanceof ViewGroup.MarginLayoutParams) {
            ViewGroup.MarginLayoutParams lp = (ViewGroup.MarginLayoutParams) filterRoot.getLayoutParams();
            lp.topMargin = anchorTopY;
            filterRoot.setLayoutParams(lp);
        }
        filterRoot.post(() -> {
            fitFilterHeight();
            if (panelHeightListener != null) panelHeightListener.onHeight(filterRoot.getHeight());
            requestFirstFilterFocus();
        });
    }

    private void fitFilterHeight() {
        if (filterScroll == null || filterContent == null) return;
        int max = (int) getContext().getResources().getDimension(R.dimen.md3_filter_panel_max_height);
        int desired = filterContent.getMeasuredHeight();
        int target = desired > 0 ? Math.min(desired, max) : max;
        ViewGroup.LayoutParams lp = filterScroll.getLayoutParams();
        if (lp != null && lp.height != target) {
            lp.height = target;
            filterScroll.setLayoutParams(lp);
            filterScroll.requestLayout();
            filterRoot.post(() -> {
                if (panelHeightListener != null) panelHeightListener.onHeight(filterRoot.getHeight());
            });
        }
    }

    private void bindOutsideTouchDismiss() {
        View rootView = findViewById(R.id.root);
        rootView.setOnTouchListener((v, event) -> {
            if (event.getAction() == MotionEvent.ACTION_UP && !isTouchInsideFilter(event)) {
                dismiss();
                return true;
            }
            return isTouchInsideFilter(event);
        });
    }

    private boolean isTouchInsideFilter(MotionEvent event) {
        return event.getX() >= filterRoot.getLeft()
                && event.getX() <= filterRoot.getRight()
                && event.getY() >= filterRoot.getTop()
                && event.getY() <= filterRoot.getBottom();
    }

    private void requestFirstFilterFocus() {
        filterRoot.postDelayed(() -> {
            View target = findFocusableChild(filterContent);
            if (target != null) target.requestFocus();
        }, 100);
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
