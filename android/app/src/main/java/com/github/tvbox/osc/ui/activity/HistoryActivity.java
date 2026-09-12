package com.github.tvbox.osc.ui.activity;

import android.content.Intent;
import android.os.Bundle;
import android.view.KeyEvent;
import android.view.View;
import android.view.animation.BounceInterpolator;
import android.widget.FrameLayout;
import android.widget.TextView;

import com.chad.library.adapter.base.BaseQuickAdapter;
import com.github.tvbox.osc.R;
import com.github.tvbox.osc.api.ApiConfig;
import com.github.tvbox.osc.base.BaseActivity;
import com.github.tvbox.osc.bean.SourceBean;
import com.github.tvbox.osc.bean.VodInfo;
import com.github.tvbox.osc.cache.RoomDataManger;
import com.github.tvbox.osc.event.RefreshEvent;
import com.github.tvbox.osc.ui.adapter.HistoryAdapter;
import com.github.tvbox.osc.ui.dialog.ConfirmClearDialog;
import com.github.tvbox.osc.util.FastClickCheckUtil;
import com.github.tvbox.osc.util.HawkConfig;
import com.orhanobut.hawk.Hawk;
import com.owen.tvrecyclerview.widget.TvRecyclerView;
import com.owen.tvrecyclerview.widget.V7GridLayoutManager;

import org.greenrobot.eventbus.EventBus;
import org.greenrobot.eventbus.Subscribe;
import org.greenrobot.eventbus.ThreadMode;

import java.util.ArrayList;
import java.util.List;

/** History screen with explicit TV edit mode and recoverable focus. */
public class HistoryActivity extends BaseActivity {
    public static HistoryAdapter historyAdapter;

    private TextView tvEdit;
    private TextView tvDeleteSelected;
    private TextView tvClear;
    private TextView tvDone;
    private TvRecyclerView mGridView;
    private View emptyState;
    private TextView emptyTitle;
    private TextView emptyBody;
    private TextView emptyPrimary;
    private TextView emptySecondary;

    private boolean editMode;
    private String lastFocusedKey;
    private int lastFocusedPosition;

    @Override
    protected int getLayoutResID() {
        return R.layout.activity_history;
    }

    @Override
    protected void init() {
        initView();
        initData(true);
    }

    private void initView() {
        EventBus.getDefault().register(this);
        tvEdit = findViewById(R.id.tvEdit);
        tvDeleteSelected = findViewById(R.id.tvDeleteSelected);
        tvClear = findViewById(R.id.tvClear);
        tvDone = findViewById(R.id.tvDone);
        mGridView = findViewById(R.id.mGridView);
        emptyState = findViewById(R.id.emptyState);
        emptyTitle = findViewById(R.id.emptyTitle);
        emptyBody = findViewById(R.id.emptyBody);
        emptyPrimary = findViewById(R.id.emptyPrimary);
        emptySecondary = findViewById(R.id.emptySecondary);

        emptyTitle.setText("还没有观看记录");
        emptyBody.setText("看过的影片会自动出现在这里");
        emptyPrimary.setText("去首页看看");
        emptySecondary.setVisibility(View.GONE);
        emptyPrimary.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                goHome();
            }
        });

        mGridView.setHasFixedSize(true);
        mGridView.setLayoutManager(new V7GridLayoutManager(this.mContext, 5));
        historyAdapter = new HistoryAdapter();
        mGridView.setAdapter(historyAdapter);

        tvEdit.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                enterEditMode();
            }
        });
        tvDeleteSelected.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                confirmDeleteSelected();
            }
        });
        tvClear.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                confirmClearAll();
            }
        });
        tvDone.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                finishEditMode();
            }
        });

        mGridView.setOnInBorderKeyEventListener(new TvRecyclerView.OnInBorderKeyEventListener() {
            @Override
            public boolean onInBorderKeyEvent(int direction, View focused) {
                if (direction == View.FOCUS_UP) {
                    focusToolbar();
                    return true;
                }
                return false;
            }
        });
        mGridView.setOnItemListener(new TvRecyclerView.OnItemListener() {
            @Override
            public void onItemPreSelected(TvRecyclerView parent, View itemView, int position) {
                itemView.animate().scaleX(1.0f).scaleY(1.0f).setDuration(180)
                        .setInterpolator(new BounceInterpolator()).start();
            }

            @Override
            public void onItemSelected(TvRecyclerView parent, View itemView, int position) {
                lastFocusedPosition = position;
                lastFocusedKey = historyAdapter.getItemKey(position);
                itemView.animate().scaleX(1.05f).scaleY(1.05f).setDuration(180)
                        .setInterpolator(new BounceInterpolator()).start();
            }

            @Override
            public void onItemClick(TvRecyclerView parent, View itemView, int position) {
            }
        });

        historyAdapter.setOnItemClickListener(new BaseQuickAdapter.OnItemClickListener() {
            @Override
            public void onItemClick(BaseQuickAdapter adapter, View view, int position) {
                if (position < 0 || position >= historyAdapter.getData().size()) return;
                lastFocusedPosition = position;
                lastFocusedKey = historyAdapter.getItemKey(position);
                FastClickCheckUtil.check(view);
                if (editMode) {
                    historyAdapter.toggleSelected(position);
                    return;
                }
                openHistoryItem(historyAdapter.getData().get(position));
            }
        });
        historyAdapter.setOnItemLongClickListener(new BaseQuickAdapter.OnItemLongClickListener() {
            @Override
            public boolean onItemLongClick(BaseQuickAdapter adapter, View view, int position) {
                if (!editMode) enterEditMode();
                if (position >= 0) historyAdapter.toggleSelected(position);
                return true;
            }
        });
    }

    private void initData(boolean requestFocus) {
        List<VodInfo> records = RoomDataManger.getAllVodRecord(100);
        List<VodInfo> data = new ArrayList<>();
        for (VodInfo info : records) {
            if (info.playNote != null && !info.playNote.isEmpty()) {
                info.note = "上次看到" + info.playNote;
            }
            data.add(info);
        }
        historyAdapter.setNewData(data);
        updateContentState(requestFocus);
    }

    private void updateContentState(boolean requestFocus) {
        if (historyAdapter.getData().isEmpty()) {
            editMode = false;
            historyAdapter.setEditMode(false);
            mGridView.setVisibility(View.GONE);
            emptyState.setVisibility(View.VISIBLE);
            tvEdit.setVisibility(View.GONE);
            tvDeleteSelected.setVisibility(View.GONE);
            tvClear.setVisibility(View.GONE);
            tvDone.setVisibility(View.GONE);
            emptyPrimary.post(new Runnable() {
                @Override
                public void run() {
                    emptyPrimary.requestFocus();
                }
            });
            return;
        }

        mGridView.setVisibility(View.VISIBLE);
        emptyState.setVisibility(View.GONE);
        updateToolbar();
        if (requestFocus) {
            focusCard(lastFocusedKey, lastFocusedPosition);
        }
    }

    private void updateToolbar() {
        boolean hasData = !historyAdapter.getData().isEmpty();
        tvEdit.setVisibility(hasData && !editMode ? View.VISIBLE : View.GONE);
        tvDeleteSelected.setVisibility(hasData && editMode ? View.VISIBLE : View.GONE);
        tvClear.setVisibility(hasData ? View.VISIBLE : View.GONE);
        tvDone.setVisibility(hasData && editMode ? View.VISIBLE : View.GONE);
        historyAdapter.setEditMode(editMode);
    }

    private void enterEditMode() {
        if (historyAdapter.getData().isEmpty()) return;
        editMode = true;
        historyAdapter.setEditMode(true);
        updateToolbar();
        focusCard(lastFocusedKey, lastFocusedPosition);
    }

    private void finishEditMode() {
        editMode = false;
        historyAdapter.setEditMode(false);
        updateContentState(true);
    }

    private void focusToolbar() {
        TextView target = editMode ? tvDeleteSelected : tvEdit;
        if (target.getVisibility() == View.VISIBLE) target.requestFocus();
    }

    private int focusedPosition() {
        View child = mGridView.getFocusedChild();
        int position = child == null ? -1 : mGridView.getChildAdapterPosition(child);
        return position >= 0 ? position : lastFocusedPosition;
    }

    private void rememberFocusedCard() {
        int position = focusedPosition();
        if (position >= 0 && position < historyAdapter.getData().size()) {
            lastFocusedPosition = position;
            lastFocusedKey = historyAdapter.getItemKey(position);
        }
    }

    private void focusCard(final String key, int fallbackPosition) {
        if (historyAdapter.getData().isEmpty()) return;
        int position = historyAdapter.findPosition(key);
        if (position < 0) {
            position = Math.max(0, Math.min(fallbackPosition, historyAdapter.getData().size() - 1));
        }
        final int targetPosition = position;
        lastFocusedPosition = targetPosition;
        lastFocusedKey = historyAdapter.getItemKey(targetPosition);
        mGridView.scrollToPosition(targetPosition);
        mGridView.post(new Runnable() {
            @Override
            public void run() {
                View child = mGridView.getLayoutManager().findViewByPosition(targetPosition);
                if (child != null) {
                    child.requestFocus();
                } else {
                    mGridView.requestFocus();
                }
            }
        });
    }

    private void confirmDeleteSelected() {
        if (historyAdapter.getSelectedCount() == 0) return;
        rememberFocusedCard();
        final String restoreKey = lastFocusedKey;
        final int restorePosition = lastFocusedPosition;
        String title = "删除选中的 " + historyAdapter.getSelectedCount() + " 项？";
        ConfirmClearDialog dialog = new ConfirmClearDialog(mContext, title, "删除后无法恢复", "删除",
                new ConfirmClearDialog.Listener() {
                    @Override
                    public void onConfirm() {
                        for (VodInfo item : historyAdapter.getSelectedItems()) {
                            RoomDataManger.deleteVodRecord(item.sourceKey, item);
                        }
                        historyAdapter.clearSelection();
                        initData(false);
                        if (!historyAdapter.getData().isEmpty()) {
                            editMode = true;
                            historyAdapter.setEditMode(true);
                            updateToolbar();
                            focusCard(restoreKey, restorePosition);
                        }
                    }

                    @Override
                    public void onCancel() {
                        focusCard(restoreKey, restorePosition);
                    }
                });
        dialog.show();
    }

    private void confirmClearAll() {
        if (historyAdapter.getData().isEmpty()) return;
        rememberFocusedCard();
        final String restoreKey = lastFocusedKey;
        final int restorePosition = lastFocusedPosition;
        ConfirmClearDialog dialog = new ConfirmClearDialog(mContext, "清空全部历史记录？", "清空后无法恢复", "清空",
                new ConfirmClearDialog.Listener() {
                    @Override
                    public void onConfirm() {
                        RoomDataManger.deleteVodRecordAll();
                        editMode = false;
                        historyAdapter.setEditMode(false);
                        initData(true);
                    }

                    @Override
                    public void onCancel() {
                        focusCard(restoreKey, restorePosition);
                    }
                });
        dialog.show();
    }

    private void openHistoryItem(VodInfo info) {
        Bundle bundle = new Bundle();
        bundle.putString("id", info.id);
        bundle.putString("sourceKey", info.sourceKey);
        bundle.putString("title", info.name);
        SourceBean source = ApiConfig.get().getSource(info.sourceKey);
        if (source != null) {
            bundle.putString("picture", info.pic);
            jumpActivity(DetailActivity.class, bundle);
        } else if (Hawk.get(HawkConfig.FAST_SEARCH_MODE, true)) {
            jumpActivity(FastSearchActivity.class, bundle);
        } else {
            jumpActivity(SearchActivity.class, bundle);
        }
    }

    private void goHome() {
        Intent intent = new Intent(this, HomeActivity.class);
        intent.addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP | Intent.FLAG_ACTIVITY_SINGLE_TOP);
        startActivity(intent);
        finish();
    }

    @Subscribe(threadMode = ThreadMode.MAIN)
    public void refresh(RefreshEvent event) {
        if (event.type == RefreshEvent.TYPE_HISTORY_REFRESH) {
            initData(true);
        }
    }

    @Override
    protected void onDestroy() {
        super.onDestroy();
        EventBus.getDefault().unregister(this);
        historyAdapter = null;
    }

    @Override
    public boolean dispatchKeyEvent(KeyEvent event) {
        if (editMode && event.getKeyCode() == KeyEvent.KEYCODE_BACK) {
            if (event.getAction() == KeyEvent.ACTION_UP) {
                finishEditMode();
            }
            return true;
        }
        return super.dispatchKeyEvent(event);
    }

    @Override
    public void onBackPressed() {
        if (editMode) {
            finishEditMode();
            return;
        }
        super.onBackPressed();
    }
}
