package com.github.tvbox.osc.ui.activity;

import android.content.Intent;
import android.os.Bundle;
import android.view.KeyEvent;
import android.view.View;
import android.view.animation.BounceInterpolator;
import android.widget.TextView;

import com.chad.library.adapter.base.BaseQuickAdapter;
import com.github.tvbox.osc.R;
import com.github.tvbox.osc.api.ApiConfig;
import com.github.tvbox.osc.base.BaseActivity;
import com.github.tvbox.osc.cache.RoomDataManger;
import com.github.tvbox.osc.cache.VodCollect;
import com.github.tvbox.osc.event.RefreshEvent;
import com.github.tvbox.osc.ui.adapter.CollectAdapter;
import com.github.tvbox.osc.ui.dialog.ConfirmClearDialog;
import com.github.tvbox.osc.util.FastClickCheckUtil;
import com.github.tvbox.osc.ui.activity.DetailActivity;
import com.owen.tvrecyclerview.widget.TvRecyclerView;
import com.owen.tvrecyclerview.widget.V7GridLayoutManager;

import org.greenrobot.eventbus.EventBus;
import org.greenrobot.eventbus.Subscribe;
import org.greenrobot.eventbus.ThreadMode;

import java.util.ArrayList;
import java.util.List;

/** Collection screen with explicit TV edit mode and recoverable focus. */
public class CollectActivity extends BaseActivity {
    public static CollectAdapter collectAdapter;

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
        return R.layout.activity_collect;
    }

    @Override
    protected void init() {
        initView();
        initData(true);
    }

    /**
     * 从详情页返回时 Activity 可能仍在栈里，不会重新 init。
     * 这里按数据库重读收藏，避免列表停留在进入详情前的快照。
     */
    @Override
    protected void onResume() {
        super.onResume();
        if (collectAdapter != null) {
            initData(false);
        }
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

        emptyTitle.setText("还没有收藏");
        emptyBody.setText("在详情页选择收藏，影片会出现在这里");
        emptyPrimary.setText("去首页看看");
        emptySecondary.setText("搜索影片");
        emptyPrimary.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                goHome();
            }
        });
        emptySecondary.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                jumpActivity(SearchActivity.class);
            }
        });

        mGridView.setHasFixedSize(true);
        mGridView.setLayoutManager(new V7GridLayoutManager(this.mContext, 5));
        collectAdapter = new CollectAdapter();
        mGridView.setAdapter(collectAdapter);

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
                lastFocusedKey = collectAdapter.getItemKey(position);
                itemView.animate().scaleX(1.05f).scaleY(1.05f).setDuration(180)
                        .setInterpolator(new BounceInterpolator()).start();
            }

            @Override
            public void onItemClick(TvRecyclerView parent, View itemView, int position) {
            }
        });

        collectAdapter.setOnItemClickListener(new BaseQuickAdapter.OnItemClickListener() {
            @Override
            public void onItemClick(BaseQuickAdapter adapter, View view, int position) {
                if (position < 0 || position >= collectAdapter.getData().size()) return;
                lastFocusedPosition = position;
                lastFocusedKey = collectAdapter.getItemKey(position);
                FastClickCheckUtil.check(view);
                if (editMode) {
                    collectAdapter.toggleSelected(position);
                    return;
                }
                openCollectionItem(collectAdapter.getData().get(position));
            }
        });
        collectAdapter.setOnItemLongClickListener(new BaseQuickAdapter.OnItemLongClickListener() {
            @Override
            public boolean onItemLongClick(BaseQuickAdapter adapter, View view, int position) {
                if (!editMode) enterEditMode();
                if (position >= 0) collectAdapter.toggleSelected(position);
                return true;
            }
        });
    }

    private void initData(boolean requestFocus) {
        List<VodCollect> records = RoomDataManger.getAllVodCollect();
        collectAdapter.setNewData(new ArrayList<>(records));
        updateContentState(requestFocus);
    }

    private void updateContentState(boolean requestFocus) {
        if (collectAdapter.getData().isEmpty()) {
            editMode = false;
            collectAdapter.setEditMode(false);
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
        boolean hasData = !collectAdapter.getData().isEmpty();
        tvEdit.setVisibility(hasData && !editMode ? View.VISIBLE : View.GONE);
        tvDeleteSelected.setVisibility(hasData && editMode ? View.VISIBLE : View.GONE);
        tvClear.setVisibility(hasData ? View.VISIBLE : View.GONE);
        tvDone.setVisibility(hasData && editMode ? View.VISIBLE : View.GONE);
        collectAdapter.setEditMode(editMode);
    }

    private void enterEditMode() {
        if (collectAdapter.getData().isEmpty()) return;
        editMode = true;
        collectAdapter.setEditMode(true);
        updateToolbar();
        focusCard(lastFocusedKey, lastFocusedPosition);
    }

    private void finishEditMode() {
        editMode = false;
        collectAdapter.setEditMode(false);
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
        if (position >= 0 && position < collectAdapter.getData().size()) {
            lastFocusedPosition = position;
            lastFocusedKey = collectAdapter.getItemKey(position);
        }
    }

    private void focusCard(final String key, int fallbackPosition) {
        if (collectAdapter.getData().isEmpty()) return;
        int position = collectAdapter.findPosition(key);
        if (position < 0) {
            position = Math.max(0, Math.min(fallbackPosition, collectAdapter.getData().size() - 1));
        }
        final int targetPosition = position;
        lastFocusedPosition = targetPosition;
        lastFocusedKey = collectAdapter.getItemKey(targetPosition);
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
        if (collectAdapter.getSelectedCount() == 0) return;
        rememberFocusedCard();
        final String restoreKey = lastFocusedKey;
        final int restorePosition = lastFocusedPosition;
        String title = "删除选中的 " + collectAdapter.getSelectedCount() + " 项？";
        ConfirmClearDialog dialog = new ConfirmClearDialog(mContext, title, "删除后无法恢复", "删除",
                new ConfirmClearDialog.Listener() {
                    @Override
                    public void onConfirm() {
                        for (VodCollect item : collectAdapter.getSelectedItems()) {
                            RoomDataManger.deleteVodCollect(item.getId());
                        }
                        collectAdapter.clearSelection();
                        initData(false);
                        if (!collectAdapter.getData().isEmpty()) {
                            editMode = true;
                            collectAdapter.setEditMode(true);
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
        if (collectAdapter.getData().isEmpty()) return;
        rememberFocusedCard();
        final String restoreKey = lastFocusedKey;
        final int restorePosition = lastFocusedPosition;
        ConfirmClearDialog dialog = new ConfirmClearDialog(mContext, "清空全部收藏？", "清空后无法恢复", "清空",
                new ConfirmClearDialog.Listener() {
                    @Override
                    public void onConfirm() {
                        RoomDataManger.deleteVodCollectAll();
                        editMode = false;
                        collectAdapter.setEditMode(false);
                        initData(true);
                    }

                    @Override
                    public void onCancel() {
                        focusCard(restoreKey, restorePosition);
                    }
                });
        dialog.show();
    }

    private void openCollectionItem(VodCollect item) {
        if (ApiConfig.get().getSource(item.sourceKey) != null) {
            Bundle bundle = new Bundle();
            bundle.putString("id", item.vodId);
            bundle.putString("sourceKey", item.sourceKey);
            bundle.putString("title", item.name);
            bundle.putString("picture", item.pic);
            jumpActivity(DetailActivity.class, bundle);
        } else {
            Intent intent = new Intent(mContext, SearchActivity.class);
            intent.putExtra("title", item.name);
            startActivity(intent);
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
        if (event.type == RefreshEvent.TYPE_HISTORY_REFRESH
                || event.type == RefreshEvent.TYPE_COLLECT_REFRESH) {
            initData(true);
        }
    }

    @Override
    protected void onDestroy() {
        super.onDestroy();
        EventBus.getDefault().unregister(this);
        collectAdapter = null;
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
