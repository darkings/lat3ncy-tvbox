package com.github.tvbox.osc.ui.activity;

import android.Manifest;
import android.animation.Animator;
import android.animation.AnimatorSet;
import android.animation.IntEvaluator;
import android.animation.ObjectAnimator;
import android.annotation.SuppressLint;
import android.app.ActivityManager;
import android.content.DialogInterface;
import android.content.Intent;
import android.graphics.Typeface;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.text.SpannableString;
import android.text.Spanned;
import android.text.TextUtils;
import android.text.style.ForegroundColorSpan;
import android.text.style.StyleSpan;
import android.util.TypedValue;
import android.view.KeyEvent;
import android.view.View;
import android.view.ViewGroup;
import android.view.animation.AccelerateInterpolator;
import android.view.animation.AlphaAnimation;
import android.view.animation.Animation;
import android.view.animation.PathInterpolator;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.TextView;
import android.widget.Toast;

import androidx.annotation.NonNull;
import androidx.constraintlayout.widget.ConstraintLayout;
import androidx.lifecycle.Observer;
import androidx.lifecycle.ViewModelProvider;
import androidx.recyclerview.widget.DiffUtil;
import androidx.recyclerview.widget.RecyclerView;
import androidx.viewpager.widget.ViewPager;

import com.github.tvbox.osc.R;
import com.github.tvbox.osc.api.ApiConfig;
import com.github.tvbox.osc.base.App;
import com.github.tvbox.osc.base.BaseActivity;
import com.github.tvbox.osc.base.BaseLazyFragment;
import com.github.tvbox.osc.bean.AbsSortXml;
import com.github.tvbox.osc.bean.Movie;
import com.github.tvbox.osc.bean.MovieSort;
import com.github.tvbox.osc.bean.SourceBean;
import com.github.tvbox.osc.event.RefreshEvent;
import com.github.tvbox.osc.server.ControlManager;
import com.github.tvbox.osc.ui.adapter.HomePageAdapter;
import com.github.tvbox.osc.ui.adapter.SelectDialogAdapter;
import com.github.tvbox.osc.ui.adapter.SortAdapter;
import com.github.tvbox.osc.ui.dialog.SelectDialog;
import com.github.tvbox.osc.ui.dialog.TipDialog;
import com.github.tvbox.osc.ui.fragment.GridFragment;
import com.github.tvbox.osc.ui.fragment.UserFragment;
import com.github.tvbox.osc.ui.tv.widget.DefaultTransformer;
import com.github.tvbox.osc.ui.tv.widget.FixedSpeedScroller;
import com.github.tvbox.osc.ui.tv.widget.GridFilterPanel;
import com.github.tvbox.osc.ui.tv.widget.NoScrollViewPager;
import com.github.tvbox.osc.ui.tv.widget.PonyoTopBarView;
import com.github.tvbox.osc.ui.tv.widget.ViewObj;
import com.github.tvbox.osc.util.AppManager;
import com.github.tvbox.osc.util.DefaultConfig;
import com.github.tvbox.osc.util.FastClickCheckUtil;
import com.github.tvbox.osc.util.FileUtils;
import com.github.tvbox.osc.util.HawkConfig;
import com.github.tvbox.osc.util.LOG;
import com.github.tvbox.osc.util.MD5;
import com.github.tvbox.osc.viewmodel.SourceViewModel;
import com.orhanobut.hawk.Hawk;
import com.owen.tvrecyclerview.widget.TvRecyclerView;
import com.owen.tvrecyclerview.widget.V7GridLayoutManager;
import com.owen.tvrecyclerview.widget.V7LinearLayoutManager;

import org.greenrobot.eventbus.EventBus;
import org.greenrobot.eventbus.Subscribe;
import org.greenrobot.eventbus.ThreadMode;
import org.jetbrains.annotations.NotNull;

import java.io.File;
import java.lang.reflect.Field;
import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Date;
import java.util.List;
import java.util.Locale;
import java.util.Objects;

import me.jessyan.autosize.utils.AutoSizeUtils;
import com.github.tvbox.osc.util.ToastUtil;

public class HomeActivity extends BaseActivity {
    private LinearLayout topLayout;
    private LinearLayout contentLayout;
    private TextView tvDate;
    private TextView tvName;
    private TvRecyclerView mGridView;
    private NoScrollViewPager mViewPager;
    private PonyoTopBarView ponyoTopBar;
    private GridFilterPanel filterPanel;
    private SourceViewModel sourceViewModel;
    private SortAdapter sortAdapter;
    private HomePageAdapter pageAdapter;
    private View currentView;
    private final List<BaseLazyFragment> fragments = new ArrayList<>();
    private boolean isDownOrUp = false;
    private boolean sortChange = false;
    private int currentSelected = 0;
    private int sortFocused = 0;
    public View sortFocusView = null;
    private String loadingSourceKey;
    private int homeSortRequestSeq;
    private String previousHomeName;
    private SourceBean previousHomeSource;
    /** 顶栏左右键仅预览，不改变当前来源；确定键才提交。 */
    private SourceBean pendingHomeSource;
    private boolean homeSortLoading = false;
    private boolean refreshHomeRec = false;
    private final Handler mHandler = new Handler(Looper.getMainLooper());
    private long mExitTime = 0;
    private boolean eventBusRegistered = false;
    private final Runnable mRunnable = new Runnable() {
        @SuppressLint("SetTextI18n")
        @Override
        public void run() {
            Date date = new Date();
            SimpleDateFormat timeFormat = new SimpleDateFormat("yyyy/MM/dd  E  HH:mm", Locale.CHINA);
            tvDate.setText(timeFormat.format(date));
            mHandler.postDelayed(this, 1000);
        }
    };
    private final Runnable refreshTopInfoTextSizeRunnable = new Runnable() {
        @Override
        public void run() {
            refreshTopInfoTextSize();
        }
    };

    @Override
    protected int getLayoutResID() {
        return R.layout.activity_home;
    }

    boolean useCacheConfig = false;

    @Override
    protected void init() {
        EventBus.getDefault().register(this);
        eventBusRegistered = true;
        ControlManager.get().startServer();
        initView();
        initViewModel();
        useCacheConfig = false;
        Intent intent = getIntent();
        if (intent != null && intent.getExtras() != null) {
            Bundle bundle = intent.getExtras();
            useCacheConfig = bundle.getBoolean("useCache", false);
        }
        initData();
    }

    private void initView() {
        this.topLayout = findViewById(R.id.topLayout);
        this.tvDate = findViewById(R.id.tvDate);
        this.tvName = findViewById(R.id.tvName);
        this.contentLayout = findViewById(R.id.contentLayout);
        this.mGridView = findViewById(R.id.mGridView);
        this.mViewPager = findViewById(R.id.mViewPager);
        this.ponyoTopBar = findViewById(R.id.ponyoTopBar);
        this.ponyoTopBar.setReduceMotion(Hawk.get(HawkConfig.REDUCE_MOTION, false));
        this.filterPanel = findViewById(R.id.filterPanel);
        this.sortAdapter = new SortAdapter();
        this.mGridView.setLayoutManager(new V7LinearLayoutManager(this.mContext, 0, false));
        this.mGridView.setSpacingWithMargins(0, AutoSizeUtils.dp2px(this.mContext, 10.0f));
        this.mGridView.setAdapter(this.sortAdapter);
        sortAdapter.registerAdapterDataObserver(new RecyclerView.AdapterDataObserver() {
            @Override
            public void onChanged() {
                mGridView.post(() -> {
                    View firstChild = Objects.requireNonNull(mGridView.getLayoutManager()).findViewByPosition(0);
                    if (firstChild != null && !topLayout.isFocused()) {
                        mGridView.setSelectedPosition(0);
                        firstChild.requestFocus();
                    }
                });
            }
        });
        this.mGridView.setOnItemListener(new TvRecyclerView.OnItemListener() {
            public void onItemPreSelected(TvRecyclerView tvRecyclerView, View view, int position) {
                if (view != null && !HomeActivity.this.isDownOrUp) {
                    mHandler.postDelayed(new Runnable() {
                        @Override
                        public void run() {
                            TextView textView = view.findViewById(R.id.tvTitle);
                            textView.getPaint().setFakeBoldText(false);
                            if (sortFocused == p) {
                                view.animate().scaleX(1.05f).scaleY(1.05f).setDuration(200)
                                        .setInterpolator(new PathInterpolator(0.05f, 0.7f, 0.1f, 1f)).start();
                                textView.setTextColor(HomeActivity.this.getResources().getColor(R.color.md3_focus_text));
                            } else {
                            if (!Hawk.get(HawkConfig.REDUCE_MOTION, false)) {
                                contentLayout.invalidate();
                                view.animate().scaleX(1.0f).scaleY(1.0f).setDuration(180)
                                        .setInterpolator(new PathInterpolator(0.3f, 0f, 0.8f, 0.15f))
                                        .withEndAction(() -> contentLayout.invalidate())
                                        .start();
                            } else {
                                view.setScaleX(1.0f);
                                view.setScaleY(1.0f);
                                contentLayout.invalidate();
                            }
                                MovieSort.SortData selectedData = sortAdapter.getItem(p);
                                textView.setTextColor(HomeActivity.this.getResources().getColor(
                                        selectedData != null && selectedData.select
                                                ? R.color.md3_primary : R.color.md3_on_surface_variant));
                                view.findViewById(R.id.tvFilter).setVisibility(View.GONE);
                                view.findViewById(R.id.tvFilterColor).setVisibility(View.GONE);
                            }
                            textView.invalidate();
                        }

                        public final int p = position;
                    }, 10);
                }
            }

            public void onItemSelected(TvRecyclerView tvRecyclerView, View view, int position) {
                if (view != null) {
                    if (filterPanel != null && filterPanel.isPanelVisible() && position != HomeActivity.this.sortFocused) {
                        closeFilterPanel();
                    }
                    if (position > HomeActivity.this.sortFocused) {
                        playPonyoOnce(PonyoTopBarView.State.DPAD_RIGHT);
                    } else if (position < HomeActivity.this.sortFocused) {
                        playPonyoOnce(PonyoTopBarView.State.DPAD_LEFT);
                    }
                    HomeActivity.this.currentView = view;
                    HomeActivity.this.isDownOrUp = false;
                    HomeActivity.this.sortChange = true;
                    // 减动效模式：跳过焦点缩放动画
                    if (!Hawk.get(HawkConfig.REDUCE_MOTION, false)) {
                        view.animate().scaleX(1.05f).scaleY(1.05f).setDuration(200)
                                .setInterpolator(new PathInterpolator(0.05f, 0.7f, 0.1f, 1f)).start();
                    } else {
                        view.setScaleX(1.05f);
                        view.setScaleY(1.05f);
                    }
                    TextView textView = view.findViewById(R.id.tvTitle);
                    textView.getPaint().setFakeBoldText(true);
                    textView.setTextColor(HomeActivity.this.getResources().getColor(R.color.md3_focus_text));
                    textView.invalidate();
                    MovieSort.SortData sortData = sortAdapter.getItem(position);
                    if (!sortData.filters.isEmpty()) {
                        showFilterIcon(sortData.filterSelectCount());
                    }
                    HomeActivity.this.sortFocusView = view;
                    HomeActivity.this.sortFocused = position;
                        sortAdapter.setSelectedPosition(position);
                        mHandler.removeCallbacks(mDataRunnable);
                    mHandler.postDelayed(mDataRunnable, 200);
                }
            }

            @Override
            public void onItemClick(TvRecyclerView parent, View itemView, int position) {
                if (itemView != null && currentSelected == position) {
                    BaseLazyFragment baseLazyFragment = fragments.get(currentSelected);
                    if ((baseLazyFragment instanceof GridFragment) && !sortAdapter.getItem(position).filters.isEmpty()) {// 弹出筛选
                        if (filterPanel != null && filterPanel.isPanelVisible()) {
                            closeFilterPanel();
                        } else {
                            showFilterPanel((GridFragment) baseLazyFragment);
                        }
                    } else if (baseLazyFragment instanceof UserFragment) {
                        showSiteSwitch();
                    }
                }
            }
        });

        this.mGridView.setOnInBorderKeyEventListener(new TvRecyclerView.OnInBorderKeyEventListener() {
            public boolean onInBorderKeyEvent(int direction, View view) {
                if (direction != View.FOCUS_DOWN) {
                    return false;
                }
                if (filterPanel != null && filterPanel.isPanelVisible()) {
                    filterPanel.focusFirstFilter();
                    return true;
                }
                BaseLazyFragment baseLazyFragment = fragments.get(sortFocused);
                if (!(baseLazyFragment instanceof GridFragment)) {
                    return false;
                }
                return !((GridFragment) baseLazyFragment).isLoad();
            }
        });
        View.OnClickListener refreshTopBarListener = new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                FastClickCheckUtil.check(v);
                refreshCurrentSourceFromTopBar();
            }
        };
        topLayout.setOnClickListener(refreshTopBarListener);
        tvName.setOnClickListener(refreshTopBarListener);
        topLayout.setOnKeyListener(new View.OnKeyListener() {
            @Override
            public boolean onKey(View v, int keyCode, KeyEvent event) {
                if (event.getAction() != KeyEvent.ACTION_DOWN) return false;
                if (keyCode == KeyEvent.KEYCODE_DPAD_LEFT) {
                    if (ApiConfig.get().getSwitchSourceBeanList().size() < 2) {
                        ponyoTopBar.stopHeldDirection();
                        playPonyoOnce(PonyoTopBarView.State.BLOCKED);
                        return true;
                    }
                    return switchHomeSource(-1);
                }
                if (keyCode == KeyEvent.KEYCODE_DPAD_RIGHT) {
                    if (ApiConfig.get().getSwitchSourceBeanList().size() < 2) {
                        ponyoTopBar.stopHeldDirection();
                        playPonyoOnce(PonyoTopBarView.State.BLOCKED);
                        return true;
                    }
                    return switchHomeSource(1);
                }
                // 确定键交给 View 默认处理: 短按 onClick, 长按 onLongClick
                if (keyCode == KeyEvent.KEYCODE_DPAD_CENTER
                        || keyCode == KeyEvent.KEYCODE_ENTER
                        || keyCode == KeyEvent.KEYCODE_NUMPAD_ENTER) {
                    return false;
                }
                return false;
            }
        });
        View.OnLongClickListener refreshAllListener = new View.OnLongClickListener() {
            @Override
            public boolean onLongClick(View v) {
                refreshFromTopBar();
                return true;
            }
        };
        topLayout.setOnLongClickListener(refreshAllListener);
        tvName.setOnLongClickListener(refreshAllListener);
        setLoadSir(this.contentLayout);
        com.github.tvbox.osc.callback.LoadingCallback.bindRetry(this, new Runnable() {
            @Override
            public void run() {
                retryHomeLoad();
            }
        });
        //mHandler.postDelayed(mFindFocus, 500);
    }


    private boolean skipNextUpdate = false;

    private void initViewModel() {
        sourceViewModel = new ViewModelProvider(this).get(SourceViewModel.class);
        sourceViewModel.sortResult.observe(this, new Observer<AbsSortXml>() {
            @Override
            public void onChanged(AbsSortXml absXml) {
                if (skipNextUpdate) {
                    skipNextUpdate = false;
                    return;
                }
                if (!homeSortLoading && loadingSourceKey == null) {
                    return;
                }
            // 分类结果必须属于当前请求；不要把旧源或“清空”哨兵结果当成当前源数据。
            if (absXml == null || TextUtils.isEmpty(absXml.sourceKey)
                    || TextUtils.isEmpty(loadingSourceKey)
                    || !loadingSourceKey.equals(absXml.sourceKey)
                    || (absXml.requestSeq != 0 && absXml.requestSeq != homeSortRequestSeq)) {
                return;
            }
                SourceBean home = ApiConfig.get().getHomeSourceBean();
                showSuccess();
                setPonyoState(PonyoTopBarView.State.IDLE);
                playPonyoOnce(PonyoTopBarView.State.SUCCESS);
                clearHomePages();
                List<MovieSort.SortData> newSortData;
                if (absXml != null && absXml.classes != null && absXml.classes.sortList != null) {
                    newSortData = DefaultConfig.adjustSort(ApiConfig.get().getHomeSourceBean().getKey(), absXml.classes.sortList, true);
                } else {
                    newSortData = DefaultConfig.adjustSort(ApiConfig.get().getHomeSourceBean().getKey(), new ArrayList<>(), true);
                }
            updateSortData(newSortData);
            sortAdapter.setSelectedPosition(Math.max(0, Math.min(currentSelected, newSortData.size() - 1)));
            initViewPager(absXml);
                updateHomeRec(absXml);
                if (home != null && home.getName() != null && !home.getName().isEmpty()) {
                    setHomeTitle(home.getName());
                }
                tvName.clearAnimation();
                homeSortLoading = false;
                loadingSourceKey = null;
                previousHomeName = null;
                previousHomeSource = null;
            }
        });
        sourceViewModel.sortError.observe(this, new Observer<AbsSortXml>() {
            @Override
            public void onChanged(AbsSortXml failed) {
                if (failed == null || TextUtils.isEmpty(failed.sourceKey) || TextUtils.isEmpty(loadingSourceKey)
                        || !loadingSourceKey.equals(failed.sourceKey)
                        || (failed.requestSeq != 0 && failed.requestSeq != homeSortRequestSeq)) {
                    return;
                }
                homeSortLoading = false;
                tvName.clearAnimation();
                showHomeErrorState();
                pendingHomeSource = null;
                if (previousHomeSource != null) {
                    ApiConfig.get().setSourceBean(previousHomeSource);
                    if (previousHomeName != null && !previousHomeName.isEmpty()) {
                        tvName.setText(previousHomeName);
                    }
                }
                previousHomeSource = null;
                previousHomeName = null;
            }
        });
    }

    private void showHomeErrorState() {
        if (isActivityUnavailable()) return;
        setPonyoState(PonyoTopBarView.State.WAITING);
        playPonyoOnce(PonyoTopBarView.State.FAILED);
        com.github.tvbox.osc.callback.ErrorCallback.bind(this,
                "首页内容加载失败", "没有成功读取当前来源", "重试", "更换来源", "",
                new com.github.tvbox.osc.callback.ErrorCallback.ErrorActionListener() {
                    @Override
                    public void onPrimary() {
                        retryHomeLoad();
                    }

                    @Override
                    public void onSecondary() {
                        showSiteSwitch();
                    }
                });
        showError();
    }

    /**
     * 错误遮罩点“重试”时必须先清掉旧请求状态，否则 sortResult/sortError
     * 会因 homeSortLoading=false 或序号不匹配而直接丢弃新结果。
     */
    private void retryHomeLoad() {
        if (isActivityUnavailable()) return;
        dismissHomeDialogs();
        homeSortLoading = false;
        loadingSourceKey = null;
        homeSortRequestSeq = 0;
        initData();
    }

    private boolean dataInitOk = false;
    private boolean jarInitOk = false;
    private boolean searchSpiderWarmStarted = false;
    private boolean configRefreshStarted = false;
    private TipDialog mConfigErrorDialog;

    private void initData() {
        if (dataInitOk && jarInitOk) {
            loadHomeSort(false);
            if (hasPermission(Manifest.permission.WRITE_EXTERNAL_STORAGE)) {
                LOG.e("有");
            } else {
                LOG.e("无");
            }
            // 仅在“下次进入=直播”且本次走了在线配置(非缓存)时, 才自动进直播;
            // 否则停在主页(点播)。修复设置项 DEFAULT_LOAD_LIVE 之前未被读取的问题。
            if (!useCacheConfig && Hawk.get(HawkConfig.DEFAULT_LOAD_LIVE, false)) {
                jumpActivity(LivePlayActivity.class);
            }
            // DEBUG: 支持 extra 强制进直播，方便 ADB 测试
            if (getIntent().getBooleanExtra("force_live", false)) {
                jumpActivity(LivePlayActivity.class);
            }
            //爬虫预热 仅首次加载
            if(!useCacheConfig)warmSearchSpidersOnce();
            return;
        }
        tvNameAnimation();
        setPonyoState(PonyoTopBarView.State.BUSY);
        showLoading();
        if (dataInitOk && !jarInitOk) {
            if (!ApiConfig.get().getSpider().isEmpty()) {
                ApiConfig.get().loadJar(useCacheConfig, ApiConfig.get().getSpider(), new ApiConfig.LoadConfigCallback() {
                    @Override
                    public void success() {
                        jarInitOk = true;
                        mHandler.postDelayed(new Runnable() {
                            @Override
                            public void run() {
//                                if (!useCacheConfig) ToastUtil.info(HomeActivity.this, "自定义jar加载成功");
                                initData();
                            }
                        }, 50);
                    }

                    @Override
                    public void notice(String msg) {
                        mHandler.post(new Runnable() {
                            @Override
                            public void run() {
                                ToastUtil.info(HomeActivity.this, msg);
                            }
                        });
                    }

                    @Override
                    public void error(String msg) {
                        playPonyoOnce(PonyoTopBarView.State.FAILED);
                        jarInitOk = true;
                        dataInitOk = true;
                        mHandler.postDelayed(new Runnable() {
                            @Override
                            public void run() {
                                ToastUtil.info(HomeActivity.this, msg+" jar load err");
                                initData();
                            }
                        },50);
                    }
                });
            }
            return;
        }
        // 有本地配置缓存时先缓存快速启动，避免返回主页时长时间重新下载源；网络刷新由冷启动/后台静默刷新完成
        final boolean useCacheStart = !useCacheConfig && hasConfigCache();
        ApiConfig.get().loadConfig(useCacheConfig || useCacheStart, new ApiConfig.LoadConfigCallback() {
            @Override
            public void notice(String msg) {
                mHandler.post(new Runnable() {
                    @Override
                    public void run() {
                        ToastUtil.info(HomeActivity.this, msg);
                    }
                });
            }

            @Override
            public void success() {
                dataInitOk = true;
                if (ApiConfig.get().getSpider().isEmpty()) {
                    jarInitOk = true;
                }
                mHandler.postDelayed(new Runnable() {
                    @Override
                    public void run() {
                        initData();
                    }
                }, 50);
                if (useCacheStart) {
                    refreshConfigSilently();
                }
            }

            @Override
            public void error(String msg) {
                setPonyoState(PonyoTopBarView.State.WAITING);
                playPonyoOnce(PonyoTopBarView.State.FAILED);
                if (msg.equalsIgnoreCase("-1")) {
                    mHandler.post(new Runnable() {
                        @Override
                        public void run() {
                            dataInitOk = true;
                            jarInitOk = true;
                            initData();
                        }
                    });
                    return;
                }
                mHandler.post(new Runnable() {
                    @Override
                    public void run() {
                        if (isActivityUnavailable()) {
                            return;
                        }
                        if (mConfigErrorDialog == null)
                            mConfigErrorDialog = new TipDialog(HomeActivity.this, msg, "重试", "取消", new TipDialog.OnListener() {
                                @Override
                                public void left() {
                                    mHandler.post(new Runnable() {
                                        @Override
                                        public void run() {
                                            dismissConfigErrorDialog();
                                            initData();
                                        }
                                    });
                                }

                                @Override
                                public void right() {
                                    dataInitOk = true;
                                    jarInitOk = true;
                                    mHandler.post(new Runnable() {
                                        @Override
                                        public void run() {
                                            dismissConfigErrorDialog();
                                            initData();
                                        }
                                    });
                                }

                                @Override
                                public void cancel() {
                                    dataInitOk = true;
                                    jarInitOk = true;
                                    mHandler.post(new Runnable() {
                                        @Override
                                        public void run() {
                                            dismissConfigErrorDialog();
                                            initData();
                                        }
                                    });
                                }
                            });
                        if (!mConfigErrorDialog.isShowing())
                            mConfigErrorDialog.show();
                    }
                });
            }
        }, this);
    }

    private boolean hasConfigCache() {
        try {
            String apiUrl = Hawk.get(HawkConfig.API_URL, "");
            if (apiUrl == null || apiUrl.isEmpty()) return false;
            return new File(App.getInstance().getFilesDir().getAbsolutePath() + "/" + MD5.encode(apiUrl)).exists();
        } catch (Throwable th) {
            return false;
        }
    }

    // 缓存启动后静默拉取最新配置更新缓存，失败时保持缓存可用，不打扰当前界面
    private void refreshConfigSilently() {
        if (configRefreshStarted) return;
        configRefreshStarted = true;
        mHandler.postDelayed(new Runnable() {
            @Override
            public void run() {
                if (isFinishing() || isDestroyed()) return;
                try {
                    ApiConfig.get().loadConfig(false, new ApiConfig.LoadConfigCallback() {
                        @Override
                        public void notice(String msg) {
                        }

                        @Override
                        public void success() {
                            LOG.i("echo-config refresh silently success");
                        }

                        @Override
                        public void error(String msg) {
                            LOG.i("echo-config refresh silently error:" + msg);
                        }
                    }, HomeActivity.this);
                } catch (Throwable th) {
                    th.printStackTrace();
                }
            }
        }, 3000);
    }

    // MD3 two-level home title: app name (primary, bold) + source name (variant)
    private void setHomeTitle(String sourceName) {
        String appName = getString(R.string.app_name);
        if (sourceName == null || sourceName.isEmpty()) {
            tvName.setText(appName);
            return;
        }
        String text = appName + "  ·  " + sourceName;
        SpannableString span = new SpannableString(text);
        span.setSpan(new ForegroundColorSpan(getResources().getColor(R.color.md3_primary)), 0, appName.length(), Spanned.SPAN_EXCLUSIVE_EXCLUSIVE);
        span.setSpan(new StyleSpan(Typeface.BOLD), 0, appName.length(), Spanned.SPAN_EXCLUSIVE_EXCLUSIVE);
        span.setSpan(new ForegroundColorSpan(getResources().getColor(R.color.md3_on_surface_variant)), appName.length(), text.length(), Spanned.SPAN_EXCLUSIVE_EXCLUSIVE);
        tvName.setText(span);
    }

    private void warmSearchSpidersOnce() {
        if (searchSpiderWarmStarted) return;
        searchSpiderWarmStarted = true;
        ApiConfig.get().warmSearchSpiders();
    }

    private void loadHomeSort(boolean keepCurrentContent) {
        SourceBean home = ApiConfig.get().getHomeSourceBean();
        homeSortLoading = keepCurrentContent;
        if (keepCurrentContent && home != null && home.getName() != null && !home.getName().isEmpty()) {
            if (previousHomeName == null) {
                previousHomeName = tvName.getText() == null ? null : tvName.getText().toString();
            }
            setHomeTitle(home.getName());
        }
        tvNameAnimation();
            if (home == null) {
                loadingSourceKey = null;
                if (!keepCurrentContent) showLoading();
                return;
            }
        loadingSourceKey = home.getKey();
        if (!keepCurrentContent) {
            showLoading();
        }
        homeSortRequestSeq = sourceViewModel.getSort(loadingSourceKey);
    }

    private void initViewPager(AbsSortXml absXml) {
        if (sortAdapter.getData().size() > 0) {
            for (MovieSort.SortData data : sortAdapter.getData()) {
                if (data.id.equals("my0")) {
                    if (Hawk.get(HawkConfig.HOME_REC, HawkConfig.DEFAULT_HOME_REC) == 1 && absXml != null && absXml.videoList != null && absXml.videoList.size() > 0) {
                        fragments.add(UserFragment.newInstance(absXml.videoList));
                    } else {
                        fragments.add(UserFragment.newInstance(null));
                    }
                } else {
                    GridFragment gridFragment = GridFragment.newInstance(data);
                    fragments.add(gridFragment);
                }
            }
            pageAdapter = new HomePageAdapter(getSupportFragmentManager(), fragments);
            try {
                Field field = ViewPager.class.getDeclaredField("mScroller");
                field.setAccessible(true);
                FixedSpeedScroller scroller = new FixedSpeedScroller(mContext, new AccelerateInterpolator());
                field.set(mViewPager, scroller);
                scroller.setmDuration(300);
            } catch (Exception e) {
            }
            mViewPager.setPageTransformer(true, new DefaultTransformer());
            mViewPager.setAdapter(pageAdapter);
            mViewPager.setCurrentItem(currentSelected, false);
        }
    }

    // 筛选面板展开时 tab 图标切换为“漏斗关闭”，收起后还原为“漏斗”
    private void updateFilterTabIcon(boolean opened) {
        View item = sortFocusView;
        if (item == null) return;
        ImageView filter = item.findViewById(R.id.tvFilter);
        ImageView filterColor = item.findViewById(R.id.tvFilterColor);
        int res = opened ? R.drawable.icon_filter_off : R.drawable.icon_filter;
        if (filter != null) filter.setImageResource(res);
        if (filterColor != null) filterColor.setImageResource(res);
    }

    public void showFilterPanel(GridFragment fragment) {
        if (fragment == null || filterPanel == null) return;
        MovieSort.SortData sortData = fragment.getSortData();
        if (sortData == null || sortData.filters == null || sortData.filters.isEmpty()) return;
        filterPanel.setData(sortData);
        filterPanel.setOnChange(() -> {
            fragment.toggleFilterColor();
            fragment.refreshForFilter();
            showFilterIcon(sortData.filterSelectCount());
        });
        // 点选子分类后关面板；再次打开仍走 setData(sortData)，已选项从 filterSelect 恢复
        filterPanel.setOnSelectClose(this::closeFilterPanel);
        filterPanel.showPanel();
        updateFilterTabIcon(true);
    }

    private void closeFilterPanel() {
        if (filterPanel == null || !filterPanel.isPanelVisible()) return;
        View focused = getCurrentFocus();
        boolean focusInside = focused != null && isDescendantOf(filterPanel, focused);
        filterPanel.hidePanel();
        updateFilterTabIcon(false);
        if (focusInside) {
            mGridView.requestFocus();
        }
    }

    private boolean isDescendantOf(ViewGroup ancestor, View view) {
        if (view == null) return false;
        View current = view;
        while (current != null) {
            if (current == ancestor) return true;
            if (!(current.getParent() instanceof View)) return false;
            current = (View) current.getParent();
        }
        return false;
    }

    private void clearHomePages() {
        mHandler.removeCallbacks(mDataRunnable);
        currentSelected = 0;
        sortFocused = 0;
        sortChange = false;
        sortFocusView = null;
        currentView = null;
        if (pageAdapter != null) {
            mViewPager.setAdapter(null);
            pageAdapter.removeAll();
            pageAdapter = null;
        } else if (!fragments.isEmpty()) {
            fragments.clear();
        }
    }

    private void updateSortData(List<MovieSort.SortData> newSortData) {
        if (newSortData == null) {
            newSortData = new ArrayList<>();
        }
        List<MovieSort.SortData> oldSortData = sortAdapter.getData();
        if (oldSortData.isEmpty()
                || newSortData.isEmpty()
                || oldSortData.get(0) == null
                || newSortData.get(0) == null
                || !"my0".equals(oldSortData.get(0).id)
                || !"my0".equals(newSortData.get(0).id)) {
            sortAdapter.setNewData(newSortData);
            return;
        }
        int oldTailCount = oldSortData.size() - 1;
        if (oldTailCount > 0) {
            oldSortData.subList(1, oldSortData.size()).clear();
            sortAdapter.notifyItemRangeRemoved(1, oldTailCount);
        }
        if (newSortData.size() > 1) {
            oldSortData.addAll(newSortData.subList(1, newSortData.size()));
            sortAdapter.notifyItemRangeInserted(1, newSortData.size() - 1);
        }
    }

    @SuppressLint("NotifyDataSetChanged")
    @Override
    public void onBackPressed() {
        if (filterPanel != null && filterPanel.isPanelVisible()) {
            closeFilterPanel();
            return;
        }
        // 打断加载
        if (homeSortLoading) {
            cancelHomeSortLoading();
            return;
        }
        if (isLoading()) {
            refreshEmpty();
            return;
        }
        // 如果处于 VOD 删除模式，则退出该模式并刷新界面
        if (HawkConfig.hotVodDelete) {
            HawkConfig.hotVodDelete = false;
            UserFragment.homeHotVodAdapter.notifyDataSetChanged();
            return;
        }

        // 检查 fragments 状态
        if (this.fragments.size() <= 0 || this.sortFocused >= this.fragments.size() || this.sortFocused < 0) {
            doExit();
            return;
        }

        BaseLazyFragment baseLazyFragment = this.fragments.get(this.sortFocused);
        if (baseLazyFragment instanceof GridFragment) {
            GridFragment grid = (GridFragment) baseLazyFragment;
            // 如果当前 Fragment 能恢复之前保存的 UI 状态，则直接返回
            if (grid.restoreView()) {
                return;
            }
            // 如果 sortFocusView 存在且没有获取焦点，则请求焦点
            if (this.sortFocusView != null && !this.sortFocusView.isFocused()) {
                this.sortFocusView.requestFocus();
            }
            // 如果当前不是第一个界面，则将列表设置到第一项
            else if (this.sortFocused != 0) {
                this.mGridView.setSelection(0);
            } else {
                doExit();
            }
        } else if (baseLazyFragment instanceof UserFragment && UserFragment.tvHotList.canScrollVertically(-1)) {
            // 如果 UserFragment 列表可以向上滚动，则滚动到顶部
            UserFragment.tvHotList.scrollToPosition(0);
            this.mGridView.setSelection(0);
        } else {
            doExit();
        }
    }

    private void doExit() {
        // 如果两次返回间隔小于 2000 毫秒，则退出应用
        if (System.currentTimeMillis() - mExitTime < 2000) {
            unregisterEventBus();
            ControlManager.get().stopServer();
            if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.LOLLIPOP) {
                ActivityManager activityManager = (ActivityManager) getSystemService(ACTIVITY_SERVICE);
                if (activityManager != null) {
                    for (ActivityManager.AppTask appTask : activityManager.getAppTasks()) {
                        appTask.finishAndRemoveTask();
                    }
                } else {
                    finishAndRemoveTask();
                }
            } else {
                AppManager.getInstance().finishAllActivity();
                finish();
            }
        } else {
            // 否则仅提示用户，再按一次退出应用
            mExitTime = System.currentTimeMillis();
            ToastUtil.info(mContext, "再按一次返回键退出应用");
        }
    }

    @Override
    protected void onResume() {
        super.onResume();
        refreshTopInfoTextSize();
        mHandler.removeCallbacks(refreshTopInfoTextSizeRunnable);
        mHandler.postDelayed(refreshTopInfoTextSizeRunnable, 350);
        mHandler.post(mRunnable);
    }


    @Override
    protected void onPause() {
        super.onPause();
        mHandler.removeCallbacks(refreshTopInfoTextSizeRunnable);
        mHandler.removeCallbacks(mRunnable);
    }

    private void refreshTopInfoTextSize() {
        if (tvName == null || tvDate == null) {
            return;
        }
        tvName.setTextSize(TypedValue.COMPLEX_UNIT_PX, getResources().getDimension(R.dimen.ts_22));
        tvDate.setTextSize(TypedValue.COMPLEX_UNIT_PX, getResources().getDimension(R.dimen.ts_20));
    }

    @Subscribe(threadMode = ThreadMode.MAIN)
    public void refresh(RefreshEvent event) {
        if (event.type == RefreshEvent.TYPE_PUSH_URL) {
            if (ApiConfig.get().getSource("push_agent") != null) {
                Intent newIntent = new Intent(mContext, DetailActivity.class);
                newIntent.putExtra("id", (String) event.obj);
                newIntent.putExtra("sourceKey", "push_agent");
                newIntent.setFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TOP);
                HomeActivity.this.startActivity(newIntent);
            }
        } else if (event.type == RefreshEvent.TYPE_FILTER_CHANGE) {
            if (currentView != null) {
                showFilterIcon((int) event.obj);
            }
        } else if (event.type == RefreshEvent.TYPE_HOME_SOURCE_CHANGE) {
            refreshHome(false);
        }
    }

    private void showFilterIcon(int count) {
        if (currentView == null) return;
        View filter = currentView.findViewById(R.id.tvFilter);
        View filterColor = currentView.findViewById(R.id.tvFilterColor);
        if (filter == null || filterColor == null) return;
        // 仅当前分类支持筛选时才显示筛选图标（防止主页/无筛选分类误显示）
        if (sortFocused < 0 || sortFocused >= sortAdapter.getData().size()) return;
        MovieSort.SortData sortData = sortAdapter.getItem(sortFocused);
        boolean filterable = sortData != null && sortData.filters != null && !sortData.filters.isEmpty();
        if (!filterable) {
            filter.setVisibility(View.GONE);
            filterColor.setVisibility(View.GONE);
            return;
        }
        boolean visible = count > 0;
        filterColor.setVisibility(visible ? View.VISIBLE : View.GONE);
        filter.setVisibility(visible ? View.GONE : View.VISIBLE);
    }

    private final Runnable mDataRunnable = new Runnable() {
        @Override
        public void run() {
            if (sortChange) {
                sortChange = false;
                BaseLazyFragment baseLazyFragment = fragments.get(sortFocused);
                if (sortFocused != currentSelected) {
                    currentSelected = sortFocused;
                    mViewPager.setCurrentItem(sortFocused, false);
                    // 顶栏始终保留为可聚焦的来源入口；上移只移动焦点，不因焦点移动刷新内容。
                    if (baseLazyFragment instanceof GridFragment && ((GridFragment) baseLazyFragment).shouldReloadOnSelect()) {
                        ((GridFragment) baseLazyFragment).forceRefresh();
                    }
                } else if (baseLazyFragment instanceof GridFragment && ((GridFragment) baseLazyFragment).shouldReloadOnSelect()) {
                    ((GridFragment) baseLazyFragment).forceRefresh();
                }
            }
        }
    };

    private long menuKeyDownTime = 0;
    private static final long LONG_PRESS_THRESHOLD = 2000; // 设置长按的阈值，单位是毫秒
    private final Runnable ponyoSettingsHint = new Runnable() {
        @Override
        public void run() {
            playPonyoOnce(PonyoTopBarView.State.SETTINGS);
        }
    };

    private boolean isCategoryDirectionBlocked(int keyCode) {
        if (mGridView == null || sortAdapter == null || !mGridView.hasFocus()) return false;
        if (keyCode == KeyEvent.KEYCODE_DPAD_LEFT) return sortFocused <= 0;
        return keyCode == KeyEvent.KEYCODE_DPAD_RIGHT
                && sortFocused >= Math.max(0, sortAdapter.getItemCount() - 1);
    }

    @Override
    public boolean dispatchKeyEvent(KeyEvent event) {
        if (topHide < 0)
            return false;
        int keyCode = event.getKeyCode();
        int action = event.getAction();
        if (keyCode == KeyEvent.KEYCODE_DPAD_LEFT || keyCode == KeyEvent.KEYCODE_DPAD_RIGHT) {
            if (action == KeyEvent.ACTION_DOWN) {
                if (event.getRepeatCount() == 0 && isCategoryDirectionBlocked(keyCode)) {
                    if (ponyoTopBar != null) ponyoTopBar.stopHeldDirection();
                    playPonyoOnce(PonyoTopBarView.State.BLOCKED);
                } else if (!isCategoryDirectionBlocked(keyCode) && ponyoTopBar != null) {
                    ponyoTopBar.startHeldDirection(keyCode == KeyEvent.KEYCODE_DPAD_LEFT
                            ? PonyoTopBarView.State.DPAD_LEFT : PonyoTopBarView.State.DPAD_RIGHT);
                }
            } else if (action == KeyEvent.ACTION_UP) {
                if (ponyoTopBar != null) ponyoTopBar.stopHeldDirection();
            }
        } else if (action == KeyEvent.ACTION_DOWN && event.getRepeatCount() == 0) {
            switch (keyCode) {
                case KeyEvent.KEYCODE_DPAD_UP:
                    playPonyoOnce(PonyoTopBarView.State.DPAD_UP);
                    break;
                case KeyEvent.KEYCODE_DPAD_DOWN:
                    playPonyoOnce(PonyoTopBarView.State.DPAD_DOWN);
                    break;
                case KeyEvent.KEYCODE_DPAD_CENTER:
                case KeyEvent.KEYCODE_ENTER:
                case KeyEvent.KEYCODE_NUMPAD_ENTER:
                    playPonyoOnce(PonyoTopBarView.State.CONFIRM);
                    break;
                case KeyEvent.KEYCODE_BACK:
                    playPonyoOnce(PonyoTopBarView.State.BACK);
                    break;
                case KeyEvent.KEYCODE_MENU:
                    playPonyoOnce(PonyoTopBarView.State.MENU);
                    break;
                default:
                    // 音量、静音和电源等系统键保持原有分发路径。
                    break;
            }
        }
        if (keyCode == KeyEvent.KEYCODE_MENU) {
            if (action == KeyEvent.ACTION_DOWN && event.getRepeatCount() == 0) {
                menuKeyDownTime = System.currentTimeMillis();
                mHandler.removeCallbacks(ponyoSettingsHint);
                mHandler.postDelayed(ponyoSettingsHint, LONG_PRESS_THRESHOLD);
            } else if (action == KeyEvent.ACTION_UP) {
                mHandler.removeCallbacks(ponyoSettingsHint);
                long pressDuration = System.currentTimeMillis() - menuKeyDownTime;
                if (pressDuration >= LONG_PRESS_THRESHOLD) {
                    playPonyoOnce(PonyoTopBarView.State.SETTINGS);
                    jumpActivity(SettingActivity.class);;
                }else {
                    showSiteSwitch();
                }
            }
        }
        return super.dispatchKeyEvent(event);
    }

    byte topHide = 0;

    private void changeTop(boolean hide) {
        ViewObj viewObj = new ViewObj(topLayout, (ViewGroup.MarginLayoutParams) topLayout.getLayoutParams());
        AnimatorSet animatorSet = new AnimatorSet();
        animatorSet.addListener(new Animator.AnimatorListener() {
            @Override
            public void onAnimationStart(Animator animation) {

            }

            @Override
            public void onAnimationEnd(Animator animation) {
                topHide = (byte) (hide ? 1 : 0);
            }

            @Override
            public void onAnimationCancel(Animator animation) {

            }

            @Override
            public void onAnimationRepeat(Animator animation) {

            }
        });
        if (hide && topHide == 0) {
            animatorSet.playTogether(ObjectAnimator.ofObject(viewObj, "marginTop", new IntEvaluator(),
                            AutoSizeUtils.mm2px(this.mContext, 10.0f),
                            AutoSizeUtils.mm2px(this.mContext, 0.0f)),
                    ObjectAnimator.ofObject(viewObj, "height", new IntEvaluator(),
                            AutoSizeUtils.mm2px(this.mContext, 50.0f),
                            AutoSizeUtils.mm2px(this.mContext, 1.0f)),
                    ObjectAnimator.ofFloat(this.topLayout, "alpha", 1.0f, 0.0f));
            animatorSet.setDuration(200);
            animatorSet.start();
            return;
        }
        if (!hide && topHide == 1) {
            animatorSet.playTogether(ObjectAnimator.ofObject(viewObj, "marginTop", new IntEvaluator(),
                            AutoSizeUtils.mm2px(this.mContext, 0.0f),
                            AutoSizeUtils.mm2px(this.mContext, 10.0f)),
                    ObjectAnimator.ofObject(viewObj, "height", new IntEvaluator(),
                            AutoSizeUtils.mm2px(this.mContext, 1.0f),
                            AutoSizeUtils.mm2px(this.mContext, 50.0f)),
                    ObjectAnimator.ofFloat(this.topLayout, "alpha", 0.0f, 1.0f));
            animatorSet.setDuration(200);
            animatorSet.start();
        }
    }

    @Override
    protected void onDestroy() {
        dismissHomeDialogs();
        mHandler.removeCallbacksAndMessages(null);
        com.github.tvbox.osc.callback.LoadingCallback.unbindRetry(this);
        super.onDestroy();
        unregisterEventBus();
        if (isFinishing()) {
            ControlManager.get().stopServer();
        }
    }

    private void unregisterEventBus() {
        if (eventBusRegistered) {
            EventBus.getDefault().unregister(this);
            eventBusRegistered = false;
        }
    }

    private SelectDialog<SourceBean> mSiteSwitchDialog;

    public void showSiteSwitch() {
        if (isActivityUnavailable()) return;
        List<SourceBean> sites = ApiConfig.get().getSwitchSourceBeanList();
        if (sites.isEmpty()) return;
        int select = sites.indexOf(ApiConfig.get().getHomeSourceBean());
        if (select < 0 || select >= sites.size()) select = 0;
        if (mSiteSwitchDialog == null) {
            mSiteSwitchDialog = new SelectDialog<>(HomeActivity.this);
            TvRecyclerView tvRecyclerView = mSiteSwitchDialog.findViewById(R.id.list);
            // 根据 sites 数量动态计算列数
            int spanCount = (int) Math.floor(sites.size() / 20.0);
            spanCount = Math.min(spanCount, 2);
            tvRecyclerView.setLayoutManager(new V7GridLayoutManager(mSiteSwitchDialog.getContext(), spanCount + 1));
            // 设置对话框宽度
            ConstraintLayout cl_root = mSiteSwitchDialog.findViewById(R.id.cl_root);
            ViewGroup.LayoutParams clp = cl_root.getLayoutParams();
            clp.width = AutoSizeUtils.mm2px(mSiteSwitchDialog.getContext(), 380 + 200 * spanCount);
            mSiteSwitchDialog.setTip("请选择首页数据源");
            View sourceSectionLabel = mSiteSwitchDialog.findViewById(R.id.sourceSectionLabel);
            if (sourceSectionLabel != null) {
                sourceSectionLabel.setVisibility(View.VISIBLE);
            }
            mSiteSwitchDialog.setOnDismissListener(dialog -> mHandler.postDelayed(new Runnable() {
                @Override
                public void run() {
                    if (mGridView == null || sortAdapter == null || sortAdapter.getItemCount() == 0) return;
                    int position = Math.max(0, Math.min(sortFocused, sortAdapter.getItemCount() - 1));
                    mGridView.setSelectedPosition(position);
                    View item = mGridView.getLayoutManager() == null
                            ? null : mGridView.getLayoutManager().findViewByPosition(position);
                    if (item != null) item.requestFocus();
                }
            }, 180));
        }
        mSiteSwitchDialog.setAdapter(new SelectDialogAdapter.SelectDialogInterface<SourceBean>() {
            @Override
            public void click(SourceBean value, int pos) {
                dismissSiteSwitchDialog();
                previousHomeSource = ApiConfig.get().getHomeSourceBean();
                previousHomeName = tvName.getText() == null ? null : tvName.getText().toString();
                ApiConfig.get().setSourceBean(value);
                if (value.getName() != null && !value.getName().isEmpty()) {
                    setHomeTitle(value.getName());
                }
                refreshHome(false);
            }
            @Override
            public String getDisplay(SourceBean val) {
                return val.getName();
            }
        }, new DiffUtil.ItemCallback<SourceBean>() {
            @Override
            public boolean areItemsTheSame(@NonNull SourceBean oldItem, @NonNull SourceBean newItem) {
                return oldItem == newItem;
            }
            @Override
            public boolean areContentsTheSame(@NonNull SourceBean oldItem, @NonNull SourceBean newItem) {
                return oldItem.getKey().equals(newItem.getKey());
            }
        }, sites, select);
 if (!mSiteSwitchDialog.isShowing()) {
 mSiteSwitchDialog.show();
 TvRecyclerView sourceList = mSiteSwitchDialog.findViewById(R.id.list);
 final int sourceFocusPosition = select;
 sourceList.postDelayed(new Runnable() {
 @Override public void run() {
 View sourceView = sourceList.getLayoutManager() != null ? sourceList.getLayoutManager().findViewByPosition(sourceFocusPosition) : null;
 if (sourceView != null) {
 sourceView.setFocusable(true);
 sourceView.requestFocus();
 sourceView.requestFocusFromTouch();
 }
 }
 }, 180);
 }
    }

    private void refreshHome()
    {
        refreshHome(true);
    }

    private boolean switchHomeSource(int direction) {
        List<SourceBean> sites = ApiConfig.get().getSwitchSourceBeanList();
        if (sites.size() < 2) return true;
        SourceBean current = ApiConfig.get().getHomeSourceBean();
        int index = sites.indexOf(current);
        if (index < 0) index = 0;
        int next = (index + direction) % sites.size();
        if (next < 0) next += sites.size();
        SourceBean target = sites.get(next);
        if (target == null || target == current) return true;
        // 记录当前源，供加载失败时回退
        previousHomeSource = current;
        previousHomeName = tvName.getText() == null ? null : tvName.getText().toString();
        ApiConfig.get().setSourceBean(target);
        if (target.getName() != null && !target.getName().isEmpty()) {
            setHomeTitle(target.getName());
        }
        loadHomeSort(false);
        return true;
    }

    /**
     * 顶栏短按：只刷新当前首页源。
     * 仅清除当前源的分类内存缓存，然后重新 getSort；不清配置/JAR/直播缓存。
     */
    private void refreshCurrentSourceFromTopBar() {
        if (!dataInitOk || !jarInitOk) {
            jumpActivity(SettingActivity.class);
            return;
        }
        if (isActivityUnavailable()) return;
        SourceBean home = ApiConfig.get().getHomeSourceBean();
        if (home == null || home.getKey() == null) {
            ToastUtil.error(mContext, "当前源无效");
            return;
        }
        String sourceKey = home.getKey();
        String sourceName = home.getName() == null ? sourceKey : home.getName();
        LOG.i("echo-refresh-current-source key:" + sourceKey);
        SourceViewModel.clearSortCache(sourceKey);
        setPonyoState(PonyoTopBarView.State.BUSY);
        ToastUtil.info(mContext, "正在刷新当前源：" + sourceName);
        loadHomeSort(false);
    }

    /**
     * 顶栏长按：全量刷新。清配置/JAR/直播缓存后重新拉取全部源，再刷新首页分类。
     * 初始化未完成时仍跳设置页（保持原有引导路径）。
     */
    private void refreshFromTopBar() {
        if (!dataInitOk || !jarInitOk) {
            jumpActivity(SettingActivity.class);
            return;
        }
        if (isActivityUnavailable()) return;
        setPonyoState(PonyoTopBarView.State.BUSY);
        ToastUtil.info(mContext, "正在刷新全部源…");
        clearSourceCaches();
        SourceViewModel.clearRuntimeCache();
        LOG.i("echo-refresh-all-sources");
        // useCache=false：强制从源地址重新拉取，绕过本地配置缓存
        ApiConfig.get().loadConfig(false, new ApiConfig.LoadConfigCallback() {
            @Override
            public void success() {
                // 配置已刷新。若存在爬虫 spider（JAR 缓存已被清除），需重新下载 JAR 后再刷新主页，
                // 否则主页分类/播放会因 JAR 缺失而失败。
                String spider = ApiConfig.get().getSpider();
                if (!spider.isEmpty()) {
                    ApiConfig.get().loadJar(false, spider, new ApiConfig.LoadConfigCallback() {
                        @Override
                        public void success() {
                            jarInitOk = true;
                            mHandler.post(new Runnable() {
                                @Override
                                public void run() {
                                    if (isActivityUnavailable()) return;
                                    setPonyoState(PonyoTopBarView.State.IDLE);
                                    playPonyoOnce(PonyoTopBarView.State.SUCCESS);
                                    ToastUtil.info(mContext, "全部源已更新");
                                    loadHomeSort(false);
                                }
                            });
                        }

                        @Override
                        public void notice(String msg) {
                        }

                        @Override
                        public void error(String msg) {
                            // JAR 重新下载失败：仍刷新主页（纯 API 源可用），并提示 jar 异常
                            jarInitOk = true;
                            mHandler.post(new Runnable() {
                                @Override
                                public void run() {
                                    if (isActivityUnavailable()) return;
                                    setPonyoState(PonyoTopBarView.State.IDLE);
                                    playPonyoOnce(PonyoTopBarView.State.FAILED);
                                    ToastUtil.error(mContext, "源已更新，但爬虫加载失败：" + msg);
                                    loadHomeSort(false);
                                }
                            });
                        }
                    });
                    return;
                }
                jarInitOk = true;
                mHandler.post(new Runnable() {
                    @Override
                    public void run() {
                        if (isActivityUnavailable()) return;
                        setPonyoState(PonyoTopBarView.State.IDLE);
                        playPonyoOnce(PonyoTopBarView.State.SUCCESS);
                        ToastUtil.info(mContext, "全部源已更新");
                        loadHomeSort(false);
                    }
                });
            }

            @Override
            public void notice(String msg) {
                mHandler.post(new Runnable() {
                    @Override
                    public void run() {
                        if (isActivityUnavailable()) return;
                        ToastUtil.info(mContext, msg);
                    }
                });
            }

            @Override
            public void error(String msg) {
                // 网络拉取失败且缓存已删：dataInit/jarInit 标记复位，提示用户重试
                jarInitOk = true;
                mHandler.post(new Runnable() {
                    @Override
                    public void run() {
                        if (isActivityUnavailable()) return;
                        setPonyoState(PonyoTopBarView.State.IDLE);
                        playPonyoOnce(PonyoTopBarView.State.FAILED);
                        ToastUtil.error(mContext, "源更新失败：" + msg);
                    }
                });
            }
        }, this);
    }

    /**
     * 顶栏点击刷新：清除 3 类源相关缓存，保证后续拉取拿到服务器最新数据。
     * 1) 主订阅配置缓存 filesDir/MD5(apiUrl)
     * 2) 直播配置缓存 filesDir/MD5(liveApiUrl)
     * 3) 爬虫 JAR 缓存目录 filesDir/csp/
     * 清除后重置 jarInitOk，使 loadConfig 成功后经 initData() 重新下载 JAR。
     */
    private void clearSourceCaches() {
        try {
            java.io.File filesDir = App.getInstance().getFilesDir();
            // 1) 主配置缓存
            String apiUrl = Hawk.get(HawkConfig.API_URL, "");
            if (!apiUrl.isEmpty()) {
                java.io.File configCache = new java.io.File(filesDir, MD5.encode(apiUrl));
                if (configCache.exists() && !configCache.delete()) {
                    LOG.i("echo---delete config cache failed:" + configCache.getAbsolutePath());
                }
            }
            // 2) 直播配置缓存
            String liveApiUrl = Hawk.get(HawkConfig.LIVE_API_URL, "");
            if (!liveApiUrl.isEmpty()) {
                java.io.File liveCache = new java.io.File(filesDir, MD5.encode(liveApiUrl));
                if (liveCache.exists() && !liveCache.delete()) {
                    LOG.i("echo---delete live cache failed:" + liveCache.getAbsolutePath());
                }
            }
            // 2b) 直播频道内存缓存失效：否则 LIVE_API_URL 未变时，进直播页仍用旧内存频道列表
            ApiConfig.get().invalidateLiveConfig();
            // 2c) 清空已持久化的直播源分组，强制重新解析 lives 数组
            Hawk.put(HawkConfig.LIVE_GROUP_LIST, new com.google.gson.JsonArray());
            // 2d) 清空当前直播 API：使 parseJson 走 691 行重置分支，把 LIVE_API_URL
            //     重设为 lives[0]（聚合直播），同时 getLiveGroupIndexKey 退化为基础 key
            Hawk.put(HawkConfig.LIVE_API_URL, "");
            // 2e) 直播源选中索引重置为 0：硬刷新回到置顶的聚合/测速优选源，
            //     否则 parseJson 会按持久化的旧索引(如 epg.pw)继续加载旧频道
            Hawk.put(HawkConfig.LIVE_GROUP_INDEX, 0);
            // 3) 爬虫 JAR 缓存目录
            java.io.File cspDir = new java.io.File(filesDir, "csp");
            if (cspDir.exists()) {
                FileUtils.recursiveDelete(cspDir);
            }
            // JAR 已删除，重置标记使 initData() 重新走 loadJar 下载流程
            jarInitOk = false;
        } catch (Throwable th) {
            th.printStackTrace();
        }
    }

    private void updateHomeRec(AbsSortXml absXml) {
        if (!refreshHomeRec) return;
        refreshHomeRec = false;
        if (Hawk.get(HawkConfig.HOME_REC, HawkConfig.DEFAULT_HOME_REC) != 1) return;
        if (absXml == null || absXml.videoList == null || UserFragment.homeHotVodAdapter == null) return;
        UserFragment.homeHotVodAdapter.setNewData(absXml.videoList);
    }

    private void refreshHome(final boolean restart)
    {
        if (Thread.currentThread() != android.os.Looper.getMainLooper().getThread()) {
            mHandler.post(new Runnable() {
                @Override
                public void run() {
                    refreshHome(restart);
                }
            });
            return;
        }
        if (isActivityUnavailable()) {
            return;
        }
        dismissHomeDialogs();
        if (!restart) {
            loadHomeSort(false);
            return;
        }
        Intent intent = new Intent(getApplicationContext(), HomeActivity.class);
        intent.setFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TASK);
        Bundle bundle = new Bundle();
        bundle.putBoolean("useCache", true);
        intent.putExtras(bundle);
        HomeActivity.this.startActivity(intent);
    }

    private boolean isActivityUnavailable() {
        return isFinishing() || (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.JELLY_BEAN_MR1 && isDestroyed());
    }

    private void dismissHomeDialogs() {
        dismissConfigErrorDialog();
        dismissSiteSwitchDialog();
    }

    private void dismissConfigErrorDialog() {
        if (mConfigErrorDialog != null) {
            if (mConfigErrorDialog.isShowing()) {
                mConfigErrorDialog.dismiss();
            }
            mConfigErrorDialog = null;
        }
    }

    private void dismissSiteSwitchDialog() {
        if (mSiteSwitchDialog != null) {
            if (mSiteSwitchDialog.isShowing()) {
                mSiteSwitchDialog.dismiss();
            }
            mSiteSwitchDialog = null;
        }
    }

    private void refreshEmpty()
    {
        skipNextUpdate=true;
        showSuccess();
        cancelHomeSortLoading();
        clearHomePages();
        sortAdapter.setNewData(DefaultConfig.adjustSort(ApiConfig.get().getHomeSourceBean().getKey(), new ArrayList<>(), true));
        initViewPager(null);
        tvName.clearAnimation();
    }

    private void cancelHomeSortLoading() {
        homeSortLoading = false;
        loadingSourceKey = null;
        pendingHomeSource = null;
        tvName.clearAnimation();
        if (previousHomeSource != null) {
            ApiConfig.get().setSourceBean(previousHomeSource);
        }
        if (previousHomeName != null && !previousHomeName.isEmpty()) {
            tvName.setText(previousHomeName);
        }
        previousHomeSource = null;
        previousHomeName = null;
    }

    private void tvNameAnimation()
    {
        tvName.clearAnimation();
        AlphaAnimation blinkAnimation = new AlphaAnimation(0.0f, 1.0f);
        blinkAnimation.setDuration(500);
        blinkAnimation.setStartOffset(20);
        blinkAnimation.setRepeatMode(Animation.REVERSE);
        blinkAnimation.setRepeatCount(Animation.INFINITE);
        tvName.startAnimation(blinkAnimation);
    }

    private void setPonyoState(PonyoTopBarView.State state) {
        if (ponyoTopBar != null) ponyoTopBar.setBaseState(state);
    }

    private void playPonyoOnce(PonyoTopBarView.State state) {
        if (ponyoTopBar != null) ponyoTopBar.playOnce(state);
    }

    public void showPonyoReview() {
        playPonyoOnce(PonyoTopBarView.State.REVIEW);
    }

    public void showPonyoJump() {
        playPonyoOnce(PonyoTopBarView.State.DPAD_UP);
    }
}

