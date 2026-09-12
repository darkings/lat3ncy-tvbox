package com.github.tvbox.osc.ui.activity;

import android.os.Bundle;
import android.os.Handler;
import android.view.KeyEvent;
import android.view.View;
import android.view.ViewGroup;
import android.widget.TextView;

import androidx.viewpager.widget.ViewPager;

import com.chad.library.adapter.base.BaseQuickAdapter;
import com.github.tvbox.osc.R;
import com.github.tvbox.osc.api.ApiConfig;
import com.github.tvbox.osc.base.BaseActivity;
import com.github.tvbox.osc.base.BaseLazyFragment;
import com.github.tvbox.osc.ui.adapter.SettingMenuAdapter;
import com.github.tvbox.osc.ui.adapter.SettingPageAdapter;
import com.github.tvbox.osc.ui.fragment.ModelSettingFragment;
import com.github.tvbox.osc.util.AppManager;
import com.github.tvbox.osc.util.HawkConfig;
import com.orhanobut.hawk.Hawk;
import com.owen.tvrecyclerview.widget.TvRecyclerView;
import com.owen.tvrecyclerview.widget.V7LinearLayoutManager;

import java.util.ArrayList;
import java.util.List;

/**
 * @author pj567
 * @date :2020/12/23
 * @description:
 */
public class SettingActivity extends BaseActivity {
    private TvRecyclerView mGridView;
    private ViewPager mViewPager;
    private SettingMenuAdapter sortAdapter;
    private SettingPageAdapter pageAdapter;
    private List<BaseLazyFragment> fragments = new ArrayList<>();
    private boolean sortChange = false;
    private int defaultSelected = 0;
    private int sortFocused = 0;
    private Handler mHandler = new Handler();
    private String homeSourceKey;
    private String currentApi;
    private int homeRec;
    private String currentLiveApi;

    @Override
    protected int getLayoutResID() {
        return R.layout.activity_setting;
    }

    @Override
    protected void init() {
        initView();
        initData();
    }

    private void initView() {
        mGridView = findViewById(R.id.mGridView);
        mViewPager = findViewById(R.id.mViewPager);
        // ViewPager 保留相邻页面用于切换，但设置页不能让相邻 Fragment 越界覆盖导航栏。
        mViewPager.setClipChildren(true);
        mViewPager.setClipToPadding(true);
        sortAdapter = new SettingMenuAdapter();
        mGridView.setAdapter(sortAdapter);
        mGridView.setLayoutManager(new V7LinearLayoutManager(this.mContext, 1, false));
        sortAdapter.setOnItemChildClickListener(new BaseQuickAdapter.OnItemChildClickListener() {
            @Override
            public void onItemChildClick(BaseQuickAdapter adapter, View view, int position) {
                if (view.getId() == R.id.tvName) {
                    if (view.getParent() != null) {
                        ((ViewGroup) view.getParent()).requestFocus();
                        sortFocused = position;
                        if (sortFocused != defaultSelected) {
                            defaultSelected = sortFocused;
                            mViewPager.setCurrentItem(sortFocused, false);
                            sortAdapter.setSelectedPosition(sortFocused);
                        }
                    }
                }
            }
        });
        mGridView.setOnItemListener(new TvRecyclerView.OnItemListener() {
            @Override
            public void onItemPreSelected(TvRecyclerView parent, View itemView, int position) {
                if (itemView != null) {
                    TextView tvName = itemView.findViewById(R.id.tvName);
                    tvName.setTextColor(getResources().getColor(R.color.md3_on_surface_variant));
                }
            }

            @Override
            public void onItemSelected(TvRecyclerView parent, View itemView, int position) {
                if (itemView != null) {
                    sortChange = true;
                    sortFocused = position;
                    Hawk.put("setting_last_group", position);
                    TextView tvName = itemView.findViewById(R.id.tvName);
                    tvName.setTextColor(getResources().getColor(R.color.md3_focus_text));
                }
            }

            @Override
            public void onItemClick(TvRecyclerView parent, View itemView, int position) {
                // 遥控器确认键切换分组（与点击 tvName 等效）
                android.util.Log.i("Setting", "onItemClick position=" + position);
                sortFocused = position;
                if (sortFocused != defaultSelected) {
                    defaultSelected = sortFocused;
                    mViewPager.setCurrentItem(sortFocused, false);
                    sortAdapter.setSelectedPosition(sortFocused);
                }
            }
        });
    }

    private void initData() {
        currentApi = Hawk.get(HawkConfig.API_URL, "");
        homeSourceKey = ApiConfig.get().getHomeSourceBean().getKey();
        homeRec = Hawk.get(HawkConfig.HOME_REC, HawkConfig.DEFAULT_HOME_REC);
        currentLiveApi = Hawk.get(HawkConfig.LIVE_API_URL, "");
        String[] groups = {"通用", "内容", "播放", "网络", "外观", "数据与关于"};
        sortAdapter.setNewData(java.util.Arrays.asList(groups));
        sortAdapter.setSelectedPosition(defaultSelected);
        initViewPager();
    }

    private void initViewPager() {
        for (int i = 0; i < 6; i++) {
            fragments.add(ModelSettingFragment.newInstance(i));
        }
        pageAdapter = new SettingPageAdapter(getSupportFragmentManager(), fragments);
        mViewPager.setAdapter(pageAdapter);
        mViewPager.setCurrentItem(0);
        // 恢复最后分组
        int last = Hawk.get("setting_last_group", 0);
        if (last > 0 && last < 6) {
            mViewPager.setCurrentItem(last, false);
            sortFocused = last;
            defaultSelected = last;
            sortAdapter.setSelectedPosition(last);
            // 同步左侧菜单选中到恢复的分组，避免菜单高亮与内容区不一致
            final int target = last;
            mGridView.post(() -> {
                View itemView = mGridView.getLayoutManager().findViewByPosition(target);
                if (itemView != null) {
                    mGridView.setSelectedPosition(target);
                    itemView.requestFocus();
                }
            });
        }
    }

    private Runnable mDataRunnable = new Runnable() {
        @Override
        public void run() {
            if (sortChange) {
                sortChange = false;
                if (sortFocused != defaultSelected) {
                    defaultSelected = sortFocused;
                    mViewPager.setCurrentItem(sortFocused, false);
                    sortAdapter.setSelectedPosition(sortFocused);
                }
            }
        }
    };

    private Runnable mDevModeRun = new Runnable() {
        @Override
        public void run() {
            devMode = "";
        }
    };


    public interface DevModeCallback {
        void onChange();
    }

    public static DevModeCallback callback = null;

    String devMode = "";

    @Override
    public boolean dispatchKeyEvent(KeyEvent event) {
        if (event.getAction() == KeyEvent.ACTION_DOWN) {
            mHandler.removeCallbacks(mDataRunnable);
            int keyCode = event.getKeyCode();
            if (keyCode == KeyEvent.KEYCODE_DPAD_RIGHT && mGridView != null && mGridView.hasFocus()) {
                int page = mViewPager == null ? defaultSelected : mViewPager.getCurrentItem();
                if (page >= 0 && page < fragments.size()
                        && fragments.get(page) instanceof ModelSettingFragment
                        && ((ModelSettingFragment) fragments.get(page)).restoreLastFocus()) {
                    return true;
                }
            }
            switch (keyCode) {
                case KeyEvent.KEYCODE_0:
                    mHandler.removeCallbacks(mDevModeRun);
                    devMode += "0";
                    mHandler.postDelayed(mDevModeRun, 200);
                    if (devMode.length() >= 4) {
                        if (callback != null) {
                            callback.onChange();
                        }
                    }
                    break;
            }
        } else if (event.getAction() == KeyEvent.ACTION_UP) {
            mHandler.postDelayed(mDataRunnable, 200);
        }
        return super.dispatchKeyEvent(event);
    }

    @Override
    public void onBackPressed() {
        if (currentApi.equals(Hawk.get(HawkConfig.API_URL, ""))) {
            if (homeRec != Hawk.get(HawkConfig.HOME_REC, HawkConfig.DEFAULT_HOME_REC)) {
                jumpActivity(HomeActivity.class, createBundle());
            }else if(!currentLiveApi.equals(Hawk.get(HawkConfig.LIVE_API_URL, ""))){
                jumpActivity(HomeActivity.class, createBundle());
            }
        } else {
            AppManager.getInstance().finishActivity(HomeActivity.class);
            jumpActivity(HomeActivity.class);
            finish();
            return;
        }
        super.onBackPressed();
    }

    private Bundle createBundle() {
        Bundle bundle = new Bundle();
        bundle.putBoolean("useCache", true);
        return bundle;
    }
}
