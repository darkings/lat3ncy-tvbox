package com.github.tvbox.osc.ui.activity;

import android.annotation.SuppressLint;
import android.content.DialogInterface;
import android.content.Intent;
import android.content.res.Configuration;
import android.graphics.Color;
import android.graphics.Outline;
import android.graphics.PointF;
import android.graphics.Rect;
import android.os.Build;
import android.os.Bundle;
import android.text.Html;
import android.text.TextUtils;
import android.util.DisplayMetrics;
import android.view.KeyEvent;
import android.view.View;
import android.view.ViewGroup;
import android.view.ViewOutlineProvider;
import android.widget.FrameLayout;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.TextView;
import android.widget.Toast;

import androidx.fragment.app.FragmentContainerView;
import androidx.lifecycle.Observer;
import androidx.lifecycle.ViewModelProvider;
import androidx.recyclerview.widget.LinearSmoothScroller;

import com.chad.library.adapter.base.BaseQuickAdapter;
import com.chad.library.adapter.base.BaseViewHolder;
import com.github.tvbox.osc.R;
import com.github.tvbox.osc.api.ApiConfig;
import com.github.tvbox.osc.base.App;
import com.github.tvbox.osc.base.BaseActivity;
import com.github.tvbox.osc.callback.ErrorCallback;
import com.github.tvbox.osc.bean.AbsXml;
import com.github.tvbox.osc.bean.Movie;
import com.github.tvbox.osc.bean.SourceBean;
import com.github.tvbox.osc.bean.VodInfo;
import com.github.tvbox.osc.cache.RoomDataManger;
import com.github.tvbox.osc.event.RefreshEvent;
import com.github.tvbox.osc.ui.adapter.SeriesAdapter;
import com.github.tvbox.osc.ui.adapter.SeriesFlagAdapter;
import com.github.tvbox.osc.ui.dialog.DescDialog;
import com.github.tvbox.osc.ui.dialog.QuickSearchDialog;
import com.github.tvbox.osc.ui.fragment.PlayFragment;
import com.github.tvbox.osc.util.DefaultConfig;
import com.github.tvbox.osc.util.FastClickCheckUtil;
import com.github.tvbox.osc.util.HawkConfig;
import com.github.tvbox.osc.util.LOG;
import com.github.tvbox.osc.util.MD5;
import com.github.tvbox.osc.util.SearchHelper;
import com.github.tvbox.osc.util.SubtitleHelper;
import com.github.tvbox.osc.util.VodPlayData;
import com.github.tvbox.osc.viewmodel.SourceViewModel;
import com.lzy.okgo.OkGo;
import com.orhanobut.hawk.Hawk;
import com.owen.tvrecyclerview.widget.TvRecyclerView;
import com.owen.tvrecyclerview.widget.V7GridLayoutManager;
import com.owen.tvrecyclerview.widget.V7LinearLayoutManager;

import org.greenrobot.eventbus.EventBus;
import org.greenrobot.eventbus.Subscribe;
import org.greenrobot.eventbus.ThreadMode;
import org.json.JSONArray;
import org.json.JSONObject;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.ObjectInputStream;
import java.io.ObjectOutputStream;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Objects;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import me.jessyan.autosize.utils.AutoSizeUtils;

import android.graphics.Paint;
import com.github.tvbox.osc.util.ToastUtil;

/**
 * @author pj567
 * @date :2020/12/22
 * @description:
 */

public class DetailActivity extends BaseActivity {
    private LinearLayout llLayout;
    // 顶部区域：左侧海报/预览小窗 + 右侧信息面板，空态(无可播放线路)时整体隐藏
    private View topLayout;
    private FragmentContainerView llPlayerFragmentContainer;
    private View llPlayerFragmentContainerBlock;
    private View llPlayerPlace;
    private PlayFragment playFragment = null;
    private View thumbContainer;
    private ImageView ivThumb;
    private TextView tvName;
    private TextView tvYear;
    private TextView tvSite;
    private TextView tvArea;
    private TextView tvLang;
    private TextView tvType;
    private TextView tvActor;
    private TextView tvDirector;
    private TextView tvDirActorSep;
    private TextView tvDes;
    private TextView tvPlay;
//    private TextView tvSort;
    private TextView tvDesc;
    private TextView tvSeriesSort;
    private TextView tvQuickSearch;
    private TextView tvCollect;
    private TvRecyclerView mGridViewFlag;
    private TvRecyclerView mGridViewQuality;
    private TvRecyclerView mGridView;
    private TvRecyclerView mSeriesGroupView;
    private LinearLayout mEmptyPlayList;
    private View playlistPanel;
    private TextView mEmptyQuickSearch;
    private TextView mEmptyBack;
    private ImageView ivPreviewFallback;
    private TextView tvPreviewHint;
    private LinearLayout tvSeriesGroup;
    private SourceViewModel sourceViewModel;
    private Movie.Video mVideo;
    private VodInfo vodInfo;
    private SeriesFlagAdapter seriesFlagAdapter;
    private BaseQuickAdapter<String, BaseViewHolder> qualityAdapter;
    private BaseQuickAdapter<String, BaseViewHolder> seriesGroupAdapter;
    private SeriesAdapter seriesAdapter;
    public String vodId;
    public String sourceKey;
    public String firstsourceKey;
    boolean seriesSelect = false;
    private View seriesFlagFocus = null;
    /**
     * 焦点落到新线路时 {@link #onItemSelected} 会先切源。
     * 触摸点击通常在 400ms 内再进 {@link #onItemClick}，不能把这次当成“再点当前线路进全屏”。
     * 遥控器是先挪焦点（已换播），过一会儿再按 OK，这时应当进全屏。
     */
    private boolean flagSwitchedBySelection;
    private long flagSelectedAtMs;
    private boolean isReverse;
    private String preFlag="";
    private boolean firstReverse;
    private V7GridLayoutManager mGridViewLayoutMgr = null;
    private HashMap<String, String> mCheckSources = null;
    private final ArrayList<String> seriesGroupOptions = new ArrayList<>();
    private final ArrayList<String> qualityOptions = new ArrayList<>();
    private View currentSeriesGroupView;
    private int selectedSeriesGroupPosition;
    private int GroupCount;
    private int qualityPosition;
    boolean showPreview = Hawk.get(HawkConfig.SHOW_PREVIEW, true);; // true 开启 false 关闭
    private Movie.Video snapshotVideo;
    private VodInfo snapshotVodInfo;
    private VodInfo snapshotPreviewVodInfo;
    private String snapshotSourceKey;
    private String snapshotFirstSourceKey;
    private String snapshotVodId;
    private String snapshotName;
    private String snapshotPicture;
    private boolean hasDetailSnapshot;
    private boolean switchingSource;
    private int detailRequestSeq;
    private String pendingVodId;
    private String pendingSourceKey;

    private LinearSmoothScroller smoothScroller;

    @Override
    protected int getLayoutResID() {
        return R.layout.activity_detail;
    }

    @Override
    protected void init() {
        EventBus.getDefault().register(this);
        initView();
        initViewModel();
        initData();
    }

    private void initView() {
        // 触摸屏设备（如模拟器）默认处于触摸模式，DPAD 焦点系统会失效；
        // 详情页是纯遥控器操作页面，这里显式退出触摸模式。
        getWindow().getDecorView().requestFocusFromTouch();
        llLayout = findViewById(R.id.llLayout);
        topLayout = findViewById(R.id.topLayout);
        llPlayerPlace = findViewById(R.id.previewPlayerPlace);
        llPlayerFragmentContainer = findViewById(R.id.previewPlayer);
        llPlayerFragmentContainerBlock = findViewById(R.id.previewPlayerBlock);
        applyPreviewRoundCorners();
        thumbContainer = findViewById(R.id.thumbContainer);
        ivThumb = findViewById(R.id.ivThumb);
        applyThumbPreviewStyle();
        tvName = findViewById(R.id.tvName);
        tvYear = findViewById(R.id.tvYear);
        tvSite = findViewById(R.id.tvSite);
        tvArea = findViewById(R.id.tvArea);
        tvLang = findViewById(R.id.tvLang);
        tvType = findViewById(R.id.tvType);
        tvActor = findViewById(R.id.tvActor);
        tvDirector = findViewById(R.id.tvDirector);
        tvDirActorSep = findViewById(R.id.tvDirActorSep);
        tvDes = findViewById(R.id.tvDes);
        tvPlay = findViewById(R.id.tvPlay);
//        tvSort = findViewById(R.id.tvSort);
        tvDesc = findViewById(R.id.tvDesc);
        tvSeriesSort = findViewById(R.id.mSeriesSortTv);
        tvCollect = findViewById(R.id.tvCollect);
        tvQuickSearch = findViewById(R.id.tvQuickSearch);
        mEmptyPlayList = findViewById(R.id.mEmptyPlaylist);
        playlistPanel = findViewById(R.id.playlistPanel);
        mEmptyQuickSearch = findViewById(R.id.mEmptyQuickSearch);
        mEmptyBack = findViewById(R.id.mEmptyBack);
        ivPreviewFallback = findViewById(R.id.ivPreviewFallback);
        tvPreviewHint = findViewById(R.id.tvPreviewHint);
        mGridView = findViewById(R.id.mGridView);
        mGridView.setHasFixedSize(false);
        this.mGridViewLayoutMgr = new V7GridLayoutManager(this.mContext, 6);
        mGridView.setLayoutManager(this.mGridViewLayoutMgr);
//        mGridView.setLayoutManager(new V7LinearLayoutManager(this.mContext, 0, false));

        smoothScroller = new LinearSmoothScroller(mContext) {
            @Override
            protected float calculateSpeedPerPixel(DisplayMetrics displayMetrics) {
                return 100f / displayMetrics.densityDpi;
            }
            @Override
            public PointF computeScrollVectorForPosition(int targetPosition) {
                return mGridViewLayoutMgr.computeScrollVectorForPosition(targetPosition);
            }
        };

        seriesAdapter = new SeriesAdapter(this.mGridViewLayoutMgr);
        mGridView.setAdapter(seriesAdapter);
        mGridViewFlag = findViewById(R.id.mGridViewFlag);
        mGridViewFlag.setHasFixedSize(true);
        mGridViewFlag.setLayoutManager(new V7LinearLayoutManager(this.mContext, 0, false));
        seriesFlagAdapter = new SeriesFlagAdapter();
        mGridViewFlag.setAdapter(seriesFlagAdapter);
        mGridViewQuality = findViewById(R.id.mGridViewQuality);
        mGridViewQuality.setHasFixedSize(true);
        mGridViewQuality.setLayoutManager(new V7LinearLayoutManager(this.mContext, 0, false));
        qualityAdapter = new BaseQuickAdapter<String, BaseViewHolder>(R.layout.item_series_flag, qualityOptions) {
            @Override
            protected void convert(BaseViewHolder helper, String item) {
                helper.setText(R.id.tvSeriesFlag, item);
                helper.setText(R.id.tvSeriesFlagMeta, "清晰度");
                boolean selected = helper.getLayoutPosition() == qualityPosition;
                helper.itemView.setSelected(selected);
                helper.<View>getView(R.id.stateRail).setVisibility(selected ? View.VISIBLE : View.INVISIBLE);
                helper.itemView.setNextFocusUpId(tvSeriesGroup.getVisibility() == View.VISIBLE ? R.id.mSeriesSortTv : R.id.mGridViewFlag);
                helper.itemView.setNextFocusDownId(R.id.mGridView);
            }
        };
        mGridViewQuality.setAdapter(qualityAdapter);
        mGridViewQuality.setOnItemListener(new TvRecyclerView.OnItemListener() {
            @Override
            public void onItemPreSelected(TvRecyclerView parent, View itemView, int position) {
            }

            @Override
            public void onItemSelected(TvRecyclerView parent, View itemView, int position) {
            }

            @Override
            public void onItemClick(TvRecyclerView parent, View itemView, int position) {
                if (playFragment == null) return;
                if (position == qualityPosition) {
                    if (showPreview && !fullWindows && playFragment.getPlayer().isPlaying()) enterFullPreview();
                    return;
                }
                if (playFragment.selectQuality(position)) {
                    qualityPosition = position;
                    qualityAdapter.notifyDataSetChanged();
                }
            }
        });
        isReverse = false;
        firstReverse = false;
        preFlag = "";
        if (showPreview) {
            ensurePlayFragment();
        }
        llPlayerFragmentContainerBlock.setFocusable(showPreview);

        mSeriesGroupView = findViewById(R.id.mSeriesGroupView);
        tvSeriesGroup = findViewById(R.id.mSeriesGroupTv);
        mSeriesGroupView.setHasFixedSize(true);
        mSeriesGroupView.setLayoutManager(new V7LinearLayoutManager(this.mContext, 0, false));
        seriesGroupAdapter = new BaseQuickAdapter<String, BaseViewHolder>(R.layout.item_series_group, seriesGroupOptions) {
            @Override
            protected void convert(BaseViewHolder helper, String item) {
                TextView tvSeries = helper.getView(R.id.tvSeriesFlag);
                tvSeries.setText(item);
                boolean selected = helper.getLayoutPosition() == selectedSeriesGroupPosition;
                helper.itemView.setSelected(selected);
                helper.<View>getView(R.id.stateRail).setVisibility(selected ? View.VISIBLE : View.INVISIBLE);
                helper.setText(R.id.tvSeriesFlagMeta, "");
                helper.getView(R.id.tvSeriesFlagMeta).setVisibility(View.GONE);
                helper.itemView.setNextFocusUpId(R.id.mGridViewFlag);
                if (helper.getLayoutPosition() == getData().size() - 1) {
                    helper.itemView.setId(View.generateViewId());
                    helper.itemView.setNextFocusRightId(helper.itemView.getId());
                }else {
                    helper.itemView.setNextFocusRightId(View.NO_ID);
                }
            }
        };
        mSeriesGroupView.setAdapter(seriesGroupAdapter);

        llPlayerFragmentContainerBlock.setOnFocusChangeListener((v, hasFocus) -> {
            tvPreviewHint.setVisibility(hasFocus ? View.VISIBLE : View.GONE);
        });
        enableDpadNavigation(llPlayerFragmentContainerBlock);
        enableDpadNavigation(tvPlay);
        enableDpadNavigation(tvQuickSearch);
        enableDpadNavigation(tvDesc);
        enableDpadNavigation(tvCollect);
        enableDpadNavigation(mEmptyQuickSearch);
        enableDpadNavigation(mEmptyBack);

        llPlayerFragmentContainerBlock.setOnClickListener(v -> {
            // 与 tvPlay 相同：预览不在有效播放状态时，进全屏前先重新起播，避免黑屏。
            boolean previewActive = playFragment != null && playFragment.isPreviewPlaybackActive();
            LOG.i("echo-previewBlock click previewActive=" + previewActive);
            enterFullPreview();
            if (!previewActive || firstReverse) {
                jumpToPlay();
            }
            firstReverse = false;
        });

        tvPlay.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                FastClickCheckUtil.check(v);
                if (showPreview) {
                    // 预览已播完/被释放/从未起播时，仅进全屏会得到黑屏；
                    // 先判断预览是否处于有效播放状态，无效则重新起播。
                    boolean previewActive = playFragment != null && playFragment.isPreviewPlaybackActive();
                    LOG.i("echo-tvPlay click previewActive=" + previewActive);
                    enterFullPreview();
                    if (!previewActive || firstReverse) {
                        jumpToPlay();
                    }
                    firstReverse = false;
                } else {
                    jumpToPlay();
                }
            }
        });

        tvQuickSearch.setOnClickListener(v -> openQuickSearchDialog());
        mEmptyQuickSearch.setOnClickListener(v -> openQuickSearchDialog());
        mEmptyBack.setOnClickListener(v -> {
            if (restoreDetailSnapshot()) {
                ToastUtil.info(DetailActivity.this, "已恢复上一个来源");
                return;
            }
            finish();
        });
        tvCollect.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                FastClickCheckUtil.check(v);
                if (vodInfo == null || VodPlayData.isBlank(sourceKey) || VodPlayData.isBlank(vodInfo.id)) {
                    ToastUtil.error(DetailActivity.this, "当前内容不可收藏");
                    return;
                }
                boolean collected = RoomDataManger.isVodCollect(sourceKey, vodInfo.id);
                if (!collected) {
                    RoomDataManger.insertVodCollect(sourceKey, vodInfo);
                    ToastUtil.info(DetailActivity.this, "已加入收藏夹");
                } else {
                    RoomDataManger.deleteVodCollect(sourceKey, vodInfo);
                    ToastUtil.info(DetailActivity.this, "已移除收藏夹");
                }
                refreshCollectState();
                EventBus.getDefault().post(new RefreshEvent(RefreshEvent.TYPE_COLLECT_REFRESH));
            }
        });
        tvSeriesSort.setOnClickListener(new View.OnClickListener() {
            @SuppressLint("NotifyDataSetChanged")
            @Override
            public void onClick(View v) {
                List<VodInfo.VodSeries> seriesList = getCurrentSeriesList();
                if (vodInfo != null && !seriesList.isEmpty()) {
                    vodInfo.reverseSort = !vodInfo.reverseSort;
                    isReverse = !isReverse;
                    tvSeriesSort.setText(isReverse?"倒序":"正序");
                    vodInfo.reverse();
                    vodInfo.playIndex = Math.max(0, seriesList.size() - 1 - vodInfo.playIndex);
                    firstReverse = !firstReverse;
                    setSeriesGroupOptions();
                    seriesAdapter.notifyDataSetChanged();

                    customSeriesScrollPos(vodInfo.playIndex);
                    if(currentSeriesGroupView != null) {
                        TextView txtView = currentSeriesGroupView.findViewById(R.id.tvSeriesFlag);
                        txtView.setTextColor(getResources().getColor(R.color.md3_on_surface));
                    }
                }
            }
        });
        tvDesc.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                FastClickCheckUtil.check(v);
                openDescDialog();
            }
        });

        mGridView.setOnItemListener(new TvRecyclerView.OnItemListener() {
            @Override
            public void onItemPreSelected(TvRecyclerView parent, View itemView, int position) {
                seriesSelect = false;
            }

            @Override
            public void onItemSelected(TvRecyclerView parent, View itemView, int position) {
                seriesSelect = true;
            }

            @Override
            public void onItemClick(TvRecyclerView parent, View itemView, int position) {
            }
        });
        mGridViewFlag.setOnItemListener(new TvRecyclerView.OnItemListener() {
            /**
             * 切换线路（或确认当前线路）。
             * @return true = 线路发生了变化（已换播小窗）；false = 点击的就是当前线路（未换播）
             */
            private boolean refresh(View itemView, int position) {
                String newFlag = seriesFlagAdapter.getData().get(position).name;
                if (vodInfo != null && !vodInfo.playFlag.equals(newFlag)) {
                    String oldFlag = vodInfo.playFlag;
                    int oldIndex = Math.max(vodInfo.playIndex, 0);
                    VodInfo.VodSeries currentSeries = null;
                    List<VodInfo.VodSeries> oldSeriesList = vodInfo.seriesMap == null ? null : vodInfo.seriesMap.get(oldFlag);
                    if (oldSeriesList != null && !oldSeriesList.isEmpty()) {
                        int safeOldIndex = Math.max(0, Math.min(oldIndex, oldSeriesList.size() - 1));
                        currentSeries = oldSeriesList.get(safeOldIndex);
                    }
                    for (int i = 0; i < vodInfo.seriesFlags.size(); i++) {
                        VodInfo.VodSeriesFlag flag = vodInfo.seriesFlags.get(i);
                        if (flag.name.equals(oldFlag)) {
                            flag.selected = false;
                            View oldItemView = mGridViewFlag.getLayoutManager().findViewByPosition(i);
                            if (oldItemView != null) {
                                oldItemView.setSelected(false);
                                updateStateRail(oldItemView, false);
                            }
                            break;
                        }
                    }
                    VodInfo.VodSeriesFlag flag = vodInfo.seriesFlags.get(position);
                    flag.selected = true;
                    itemView.setSelected(true);
                    updateStateRail(itemView, true);
                    // clean pre flag select status
                    if (oldSeriesList != null && oldSeriesList.size() > oldIndex) {
                        oldSeriesList.get(oldIndex).selected = false;
                    }
                    vodInfo.playFlag = newFlag;
                    List<VodInfo.VodSeries> newSeriesList = vodInfo.seriesMap == null ? null : vodInfo.seriesMap.get(newFlag);
                    if (newSeriesList != null && !newSeriesList.isEmpty()) {
                        vodInfo.playIndex = findSameEpisodeIndex(currentSeries, newSeriesList, oldIndex);
                        for (VodInfo.VodSeries series : newSeriesList) {
                            series.selected = false;
                        }
                        newSeriesList.get(vodInfo.playIndex).selected = true;
                    }
                    refreshList();
                    // ===== 线路切换改造 =====
                    // 切线路后预览小窗仍停留在旧线路的画面；这里让小窗立即换播新线路
                    // 对应集（jumpToPlay 在 showPreview 下只 setData 小窗，不进全屏），
                    // 用户可留在详情页对比不同线路，点"播放"或再点当前集才进全屏。
                    if (showPreview && playFragment != null) {
                        jumpToPlay();
                    }
                    return true; // 线路已切换，小窗已换播
                }
                seriesFlagFocus = itemView;
                return false; // 点击的就是当前线路，未换播
            }

            @Override
            public void onItemPreSelected(TvRecyclerView parent, View itemView, int position) {
//                seriesSelect = false;
            }

            @Override
            public void onItemSelected(TvRecyclerView parent, View itemView, int position) {
                // 遥控器挪焦点：只换小窗，不进全屏。
                flagSwitchedBySelection = refresh(itemView, position);
                flagSelectedAtMs = android.os.SystemClock.uptimeMillis();
            }

            @Override
            public void onItemClick(TvRecyclerView parent, View itemView, int position) {
                // 触摸点击通常先 onItemSelected 再立刻 onItemClick，必须留在详情页。
                // 遥控器是焦点已切完、过一会儿再按 OK，应按“再点当前线路”进全屏。
                boolean switchedNow = refresh(itemView, position);
                long sinceSelect = android.os.SystemClock.uptimeMillis() - flagSelectedAtMs;
                boolean sameGesture = flagSwitchedBySelection && sinceSelect >= 0 && sinceSelect < 400;
                flagSwitchedBySelection = false;
                if (switchedNow || sameGesture) {
                    LOG.i("echo-flag-click switch stayPreview flag=" + (vodInfo == null ? "" : vodInfo.playFlag)
                            + " now=" + switchedNow + " gesture=" + sameGesture + " dt=" + sinceSelect);
                    return;
                }
                if (showPreview && !fullWindows
                        && previewVodInfo != null && vodInfo != null
                        && TextUtils.equals(vodInfo.playFlag, previewVodInfo.playFlag)
                        && playFragment != null && playFragment.isPreviewPlaybackActive()) {
                    LOG.i("echo-flag-click sameFlag enterFull flag=" + vodInfo.playFlag);
                    enterFullPreview();
                }
            }
        });
        seriesAdapter.setOnItemClickListener(new BaseQuickAdapter.OnItemClickListener() {
            @Override
            public void onItemClick(BaseQuickAdapter adapter, View view, int position) {
                FastClickCheckUtil.check(view);
                List<VodInfo.VodSeries> seriesList = getCurrentSeriesList();
                if (vodInfo != null && !seriesList.isEmpty() && position >= 0 && position < seriesList.size()) {
                    boolean reload = false;
                    for (int j = 0; j < seriesList.size(); j++) {
                        seriesAdapter.getData().get(j).selected = false;
                        seriesAdapter.notifyItemChanged(j);
                    }
                    //解决倒叙不刷新
                    if (vodInfo.playIndex != position) {
                        seriesAdapter.getData().get(position).selected = true;
                        seriesAdapter.notifyItemChanged(position);
                        vodInfo.playIndex = position;

                        reload = true;
                    }
                    //解决当前集不刷新的BUG
                    if (!preFlag.isEmpty() && !vodInfo.playFlag.equals(preFlag)) {
                        reload = true;
                    }
                    boolean isCurrentPlaying = !showPreview || isCurrentPreviewPlaying(position);
                    if (showPreview && !isCurrentPlaying) {
                        reload = true;
                    }

                    seriesAdapter.getData().get(vodInfo.playIndex).selected = true;
                    seriesAdapter.notifyItemChanged(vodInfo.playIndex);
                    // ===== 选集交互改造 =====
                    // 点击未选中的集：仅切换选中并留在详情页（小窗预览换集播），不进全屏；
                    // 再次点击当前已选中的集（reload=false：同集同线路且预览正在播这集）：进全屏。
                    // 原逻辑是点任意集直接 enterFullPreview()，用户无法在详情页对比切换集。
                    if (showPreview && !fullWindows && !reload && previewVodInfo != null && TextUtils.equals(vodInfo.playFlag, previewVodInfo.playFlag) && playFragment.getPlayer().isPlaying()) enterFullPreview();
                    if (!showPreview || reload) {
                        jumpToPlay();
                        firstReverse=false;
                    }
                }
            }
        });

        mSeriesGroupView.setOnItemListener(new TvRecyclerView.OnItemListener() {
            @Override
            public void onItemPreSelected(TvRecyclerView parent, View itemView, int position) {
                TextView txtView = itemView.findViewById(R.id.tvSeriesFlag);
                txtView.setTextColor(getResources().getColor(R.color.md3_on_surface));
//                currentSeriesGroupView = null;
            }

            @Override
            public void onItemSelected(TvRecyclerView parent, View itemView, int position) {
                selectSeriesGroup(itemView, position);
                if (vodInfo != null && !getCurrentSeriesList().isEmpty()) {
                    int targetPos = position * GroupCount;
//                    mGridView.smoothScrollToPosition(targetPos);
                    customSeriesScrollPos(targetPos);
                }
                currentSeriesGroupView = itemView;
                currentSeriesGroupView.isSelected();
            }

            @Override
            public void onItemClick(TvRecyclerView parent, View itemView, int position) { }
        });
        tvSeriesSort.setOnFocusChangeListener((view, hasFocus) -> {
            if (hasFocus) {
                if (vodInfo != null && !getCurrentSeriesList().isEmpty()) {
                    int firstVisible = mGridView.getFirstVisiblePosition();
                    int lastVisible = mGridView.getLastVisiblePosition();
                    if (vodInfo.playIndex < firstVisible || vodInfo.playIndex > lastVisible) {
                        customSeriesScrollPos(vodInfo.playIndex);
                    }
                }
            } else {
                tvSeriesSort.setTextColor(getResources().getColor(R.color.md3_on_surface));
            }
        });
        seriesGroupAdapter.setOnItemClickListener(new BaseQuickAdapter.OnItemClickListener() {
            @Override
            public void onItemClick(BaseQuickAdapter adapter, View view, int position) {
                FastClickCheckUtil.check(view);
                selectSeriesGroup(view, position);
                if (vodInfo != null && !getCurrentSeriesList().isEmpty()) {
                    int targetPos =  position * GroupCount+1;

                    customSeriesScrollPos(targetPos);
                }
                if(currentSeriesGroupView != null) {
                    TextView txtView = currentSeriesGroupView.findViewById(R.id.tvSeriesFlag);
                    txtView.setTextColor(getResources().getColor(R.color.md3_on_surface));
                }
                currentSeriesGroupView = view;
                currentSeriesGroupView.isSelected();
            }
        });

        if(showPreview){
            llPlayerFragmentContainerBlock.requestFocus();
        }else {
            tvPlay.requestFocus();
        }
        setLoadSir(llLayout);
    }

    //解决类似海贼王的超长动漫 焦点滚动失败的问题
    private void selectSeriesGroup(View selectedView, int position) {
        if (selectedSeriesGroupPosition == position) {
            selectedView.setSelected(true);
            updateStateRail(selectedView, true);
            return;
        }
        View previousView = mSeriesGroupView.getLayoutManager().findViewByPosition(selectedSeriesGroupPosition);
        if (previousView != null) {
            previousView.setSelected(false);
            updateStateRail(previousView, false);
        }
        selectedSeriesGroupPosition = position;
        selectedView.setSelected(true);
        updateStateRail(selectedView, true);
    }

    private void updateStateRail(View itemView, boolean selected) {
        View stateRail = itemView.findViewById(R.id.stateRail);
        if (stateRail != null) {
            stateRail.setVisibility(selected ? View.VISIBLE : View.INVISIBLE);
        }
    }

    void customSeriesScrollPos(int targetPos)
    {
        mGridViewLayoutMgr.scrollToPositionWithOffset(targetPos>10?targetPos - 10:0, 0);
        mGridView.postDelayed(() -> {
            this.smoothScroller.setTargetPosition(targetPos);
            mGridViewLayoutMgr.startSmoothScroll(smoothScroller);
            mGridView.smoothScrollToPosition(targetPos);
        }, 50);
    }

    private void initCheckedSourcesForSearch() {
        mCheckSources = SearchHelper.getSourcesForSearch();
    }

    private List<Runnable> pauseRunnable = null;

    private void jumpToPlay() {
        if (vodInfo != null && !getCurrentSeriesList().isEmpty()) {
            preFlag = vodInfo.playFlag;
            Bundle bundle = new Bundle();
            //保存历史
            insertVod(firstsourceKey, vodInfo);
        //   insertVod(sourceKey, vodInfo);
            bundle.putString("sourceKey", sourceKey);
            // 每次起播都整份快照。切线路/切源只改 playFlag 却复用旧 previewVodInfo 时，
            // 旧 id/name/sourceKey 会留在 PlayFragment 里，看起来就像源没切成功。
            previewVodInfo = vodInfo.copy();
            App.getInstance().setVodInfo(previewVodInfo);
            ensurePlayFragment();
            if (playFragment != null) playFragment.setData(bundle);
            if (!showPreview) {
                enterFullPreview();
            }
        }
    }

    @SuppressLint("NotifyDataSetChanged")
    void refreshList() {
        List<VodInfo.VodSeries> list = getCurrentSeriesList();
        if (list.isEmpty()) {
            showEmptyPlaylist();
            return;
        }
        if (list.size() <= vodInfo.playIndex) {
            vodInfo.playIndex = 0;
        }

        boolean canSelect = true;
        for (int j = 0; j < list.size(); j++) {
            VodInfo.VodSeries episode = list.get(j);
            episode.watched = j < vodInfo.playIndex;
            if(episode.selected){
                canSelect = false;
                break;
            }
        }
        if(canSelect) list.get(vodInfo.playIndex).selected = true;

        Paint pFont = new Paint();
//        pFont.setTypeface(Typeface.DEFAULT );
        Rect rect = new Rect();

        int listSize = list.size();
        int w = 1;
        for(int i =0; i < listSize; ++i){
            String name = list.get(i).name;
            pFont.getTextBounds(name, 0, name.length(), rect);
            if(w < rect.width()){
                w = rect.width();
            }
        }
        w += 32;
        int screenWidth = getWindowManager().getDefaultDisplay().getWidth()/3;
        int offset = screenWidth/w;
        if(offset <=2) offset =2;
        if(offset > 6) offset =6;
        mGridViewLayoutMgr.setSpanCount(offset);
        seriesAdapter.setNewData(list);

        setSeriesGroupOptions();

        mGridView.postDelayed(new Runnable() {
            @Override
            public void run() {
//                mGridView.smoothScrollToPosition(vodInfo.playIndex);
                customSeriesScrollPos(vodInfo.playIndex);
            }
        }, 100);
    }

    @SuppressLint("NotifyDataSetChanged")
    private void setSeriesGroupOptions(){
        List<VodInfo.VodSeries> list = getCurrentSeriesList();
        int listSize = list.size();
        int offset = mGridViewLayoutMgr.getSpanCount();
        seriesGroupOptions.clear();
        GroupCount = listSize >= 100 ? 50 : ((offset == 3 || offset == 6) ? 30 : 20);
        if(listSize > 1) {
            tvSeriesGroup.setVisibility(View.VISIBLE);
            int remainedOptionSize = listSize % GroupCount;
            int optionSize = listSize / GroupCount;

            for(int i = 0; i < optionSize; i++) {
                if(vodInfo.reverseSort)
//                    seriesGroupOptions.add(String.format("%d - %d", i * GroupCount + GroupCount, i * GroupCount + 1));
                    seriesGroupOptions.add(String.format("%d - %d", listSize - (i * GroupCount + 1)+1, listSize - (i * GroupCount + GroupCount)+1));
                else
                    seriesGroupOptions.add(String.format("%d - %d", i * GroupCount + 1, i * GroupCount + GroupCount));
            }
            if(remainedOptionSize > 0) {
                if(vodInfo.reverseSort)
//                    seriesGroupOptions.add(String.format("%d - %d", optionSize * GroupCount + remainedOptionSize, optionSize * GroupCount + 1));
                    seriesGroupOptions.add(String.format("%d - %d", listSize - (optionSize * GroupCount + 1)+1, listSize - (optionSize * GroupCount + remainedOptionSize)+1));
                else
                    seriesGroupOptions.add(String.format("%d - %d", optionSize * GroupCount + 1, optionSize * GroupCount + remainedOptionSize));
            }
//            if(vodInfo.reverseSort) Collections.reverse(seriesGroupOptions);

            selectedSeriesGroupPosition = Math.max(0, Math.min(vodInfo.playIndex / GroupCount, seriesGroupOptions.size() - 1));
            seriesGroupAdapter.notifyDataSetChanged();
        }else {
            tvSeriesGroup.setVisibility(View.GONE);
        }
        if (!mGridViewFlag.hasFocus()) seriesFlagAdapter.notifyDataSetChanged();
        mGridViewQuality.setNextFocusUpId(tvSeriesGroup.getVisibility() == View.VISIBLE ? R.id.mSeriesSortTv : R.id.mGridViewFlag);
    }

    private void updateQualityOptions(JSONObject result) {
        ArrayList<String> options = new ArrayList<>();
        try {
            Object value = result == null ? null : result.opt("url");
            JSONArray urls = value instanceof JSONArray ? (JSONArray) value : value instanceof String ? new JSONArray((String) value) : null;
            if (urls != null) for (int i = 0; i + 1 < urls.length(); i += 2) options.add(urls.optString(i));
        } catch (Throwable th) {
        }
        if (qualityOptions.equals(options)) {
            if (qualityPosition == 0) return;
            qualityPosition = 0;
            qualityAdapter.notifyDataSetChanged();
            return;
        }
        qualityOptions.clear();
        qualityOptions.addAll(options);
        qualityPosition = 0;
        boolean visible = showPreview && options.size() > 1;
        mGridViewQuality.setVisibility(visible ? View.VISIBLE : View.GONE);
        seriesFlagAdapter.notifyDataSetChanged();
        seriesAdapter.notifyDataSetChanged();
        qualityAdapter.setNewData(new ArrayList<>(qualityOptions));
        int up = tvSeriesGroup.getVisibility() == View.VISIBLE ? R.id.mSeriesSortTv : R.id.mGridViewFlag;
        int down = visible ? R.id.mGridViewQuality : R.id.mGridView;
        mGridViewQuality.setNextFocusUpId(up);
        mGridViewQuality.setNextFocusDownId(R.id.mGridView);
        tvSeriesSort.setNextFocusDownId(down);
        mSeriesGroupView.setNextFocusDownId(down);
    }

    private void setTextShow(TextView view, String tag, String info) {
        if (info == null || info.trim().isEmpty()) {
            view.setVisibility(View.GONE);
            return;
        }
        view.setVisibility(View.VISIBLE);
        view.setText(Html.fromHtml(getHtml(tag, info)));
    }

    private String removeHtmlTag(String info) {
        if (info == null)
            return "";
        // 只去掉 HTML 标签，保留换行和普通空格，避免简介被压成一行。
        return info.replaceAll("(?i)<br\\s*/?>", "\n")
                .replaceAll("\\<.*?\\>", "")
                .replaceAll("[ \\t\\x0B\\f\\r]+", " ")
                .replaceAll(" *\\n *", "\n")
                .trim();
    }

    /**
     * 简介按钮：优先用详情接口的 des，空则回退页内已展示文本。
     * 弹窗样式走 dialog_desc.xml 的 MD3 令牌，不再空点无反馈。
     */
    private void openDescDialog() {
        String describe = removeHtmlTag(mVideo == null ? null : mVideo.des);
        if (TextUtils.isEmpty(describe) && tvDes != null && tvDes.getVisibility() == View.VISIBLE) {
            CharSequence shown = tvDes.getText();
            if (shown != null) {
                describe = shown.toString().replaceFirst("^简介\\s*[·•]\\s*", "").trim();
            }
        }
        if (TextUtils.isEmpty(describe)) {
            ToastUtil.error(this, "暂无简介");
            return;
        }
        DescDialog dialog = new DescDialog(this);
        dialog.setDescribe(describe);
        dialog.show();
    }

    private void applyPreviewRoundCorners() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.LOLLIPOP) {
            return;
        }
        final float radius = getResources().getDimension(R.dimen.preview_player_radius);
        ViewOutlineProvider provider = new ViewOutlineProvider() {
            @Override
            public void getOutline(View view, Outline outline) {
                outline.setRoundRect(0, 0, view.getWidth(), view.getHeight(), radius);
            }
        };
        // 播放器容器不做 clipToOutline，避免 TextureView/SurfaceView 在圆角裁剪后丢 Surface。
        llPlayerFragmentContainer.setClipToOutline(false);
        llPlayerFragmentContainer.setOutlineProvider(null);
        llPlayerFragmentContainerBlock.setClipToOutline(true);
        llPlayerFragmentContainerBlock.setOutlineProvider(provider);
    }

    private void applyThumbPreviewStyle() {
        thumbContainer.setVisibility(showPreview ? View.GONE : View.VISIBLE);
        llPlayerPlace.setVisibility(showPreview ? View.VISIBLE : View.GONE);
        ivThumb.setVisibility(!showPreview ? View.VISIBLE : View.GONE);
        thumbContainer.setBackgroundResource(showPreview ? R.drawable.shape_detail_thumb_bg : R.drawable.shape_detail_thumb_idle_bg);
    }

    /**
     * 圆角只裁剪遮罩层，不裁剪真正承载播放器的容器。
     * 动态 clipToOutline 会在小窗/全屏切换时破坏 TextureView/SurfaceView 的 Surface。
     */
    private void setPreviewRoundClip(boolean enable) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.LOLLIPOP) {
            return;
        }
        llPlayerFragmentContainer.setClipToOutline(false);
        llPlayerFragmentContainerBlock.setClipToOutline(enable);
        llPlayerFragmentContainer.setBackgroundResource(enable ? R.drawable.preview_player_round : android.R.color.black);
    }


    private void initViewModel() {
        sourceViewModel = new ViewModelProvider(this).get(SourceViewModel.class);
        sourceViewModel.detailResult.observe(this, new Observer<AbsXml>() {
            @Override
            public void onChanged(AbsXml absXml) {
                if (absXml != null && absXml.requestSeq != 0 && absXml.requestSeq != detailRequestSeq) {
                    LOG.i("echo-detail ignore stale result seq=" + absXml.requestSeq + " current=" + detailRequestSeq);
                    return;
                }
                if (absXml != null && absXml.movie != null && absXml.movie.videoList != null && absXml.movie.videoList.size() > 0) {
                    if(!TextUtils.isEmpty(absXml.msg) && !absXml.msg.equals("数据列表")){
                        ToastUtil.info(DetailActivity.this, absXml.msg);
                        handleInvalidDetail(false);
                        return;
                    }
                    Movie.Video incoming = absXml.movie.videoList.get(0);
                    if (incoming == null) {
                        handleInvalidDetail(absXml.failed);
                        return;
                    }
                    incoming.id = pendingVodId != null ? pendingVodId : vodId;
                    if (TextUtils.isEmpty(incoming.name)) incoming.name = vod_name;
                    if (TextUtils.isEmpty(incoming.name)) incoming.name = "TVBox";
                    if ((incoming.pic == null || incoming.pic.isEmpty()) && !vod_picture.isEmpty()) {
                        incoming.pic = vod_picture;
                    }
                    VodInfo incomingInfo = new VodInfo();
                    incomingInfo.setVideo(incoming);
                    incomingInfo.sourceKey = incoming.sourceKey;
                    if (!VodPlayData.hasValidPlayData(incomingInfo)) {
                        LOG.i("echo-detail invalid play data source=" + incoming.sourceKey + " id=" + incoming.id);
                        handleInvalidDetail(false);
                        return;
                    }
                    commitDetail(incoming, incomingInfo);
                } else {
                    handleInvalidDetail(absXml == null || absXml.failed);
                }
            }
        });
    }

    private void commitDetail(Movie.Video incoming, VodInfo incomingInfo) {
        showSuccess();
        switchingSource = false;
        mVideo = incoming;
        vodInfo = incomingInfo;
        vodId = incoming.id;
        sourceKey = incoming.sourceKey;
        if (TextUtils.isEmpty(firstsourceKey)) {
            firstsourceKey = sourceKey;
        }
        vod_name = incoming.name;
        if (!TextUtils.isEmpty(incoming.pic)) {
            vod_picture = incoming.pic;
        }
        pendingVodId = null;
        pendingSourceKey = null;
        saveDetailSnapshot();
        bindDetailMeta();
        refreshCollectState();
        if (VodPlayData.hasValidPlayData(vodInfo)) {
            showPlaylist();
            VodInfo vodInfoRecord = RoomDataManger.getVodInfo(sourceKey, vodId);
            if (vodInfoRecord != null) {
                vodInfo.playIndex = Math.max(vodInfoRecord.playIndex, 0);
                vodInfo.playFlag = vodInfoRecord.playFlag;
                vodInfo.playerCfg = vodInfoRecord.playerCfg;
                vodInfo.reverseSort = vodInfoRecord.reverseSort;
            } else {
                vodInfo.playIndex = 0;
                vodInfo.playFlag = null;
                vodInfo.playerCfg = "";
                vodInfo.reverseSort = false;
            }
            tvPlay.setText(vodInfoRecord != null ? "继续播放" : "播放");
            updateSourceSummary();
            if (vodInfo.reverseSort) {
                vodInfo.reverse();
            }
            if (vodInfo.seriesMap != null && !vodInfo.seriesMap.isEmpty()
                    && (vodInfo.playFlag == null || !vodInfo.seriesMap.containsKey(vodInfo.playFlag))) {
                vodInfo.playFlag = vodInfo.seriesMap.keySet().iterator().next();
            }
            int flagScrollTo = 0;
            if (vodInfo.seriesFlags != null) {
                for (int j = 0; j < vodInfo.seriesFlags.size(); j++) {
                    VodInfo.VodSeriesFlag flag = vodInfo.seriesFlags.get(j);
                    if (flag.name.equals(vodInfo.playFlag)) {
                        flagScrollTo = j;
                        flag.selected = true;
                    } else {
                        flag.selected = false;
                    }
                }
                seriesFlagAdapter.setNewData(vodInfo.seriesFlags);
                mGridViewFlag.scrollToPosition(flagScrollTo);
            }
            refreshList();
            if (showPreview) {
                jumpToPlay();
                llPlayerFragmentContainer.setVisibility(View.VISIBLE);
                llPlayerFragmentContainerBlock.setVisibility(View.VISIBLE);
                toggleSubtitleTextSize();
            }
        } else {
            showEmptyPlaylist();
        }
    }

    private void bindDetailMeta() {
        if (mVideo == null) {
            return;
        }
        tvName.setText(mVideo.name);
        setTextShow(tvSite, "来源 · ", VodPlayData.getSourceName(firstsourceKey));
        setTextShow(tvYear, "年份 · ", mVideo.year == 0 ? "" : String.valueOf(mVideo.year));
        setTextShow(tvArea, "地区 · ", mVideo.area);
        setTextShow(tvLang, "语言 · ", mVideo.lang);
        if (!TextUtils.equals(firstsourceKey, sourceKey)) {
            setTextShow(tvType, "类型 · ", "[" + VodPlayData.getSourceName(sourceKey) + "] 解析");
        } else {
            setTextShow(tvType, "类型 · ", mVideo.type);
        }
        setTextShow(tvActor, "演员 · ", mVideo.actor);
        setTextShow(tvDirector, "导演 · ", mVideo.director);
        if (tvDirActorSep != null) {
            boolean showSep = tvDirector.getVisibility() == View.VISIBLE && tvActor.getVisibility() == View.VISIBLE;
            tvDirActorSep.setVisibility(showSep ? View.VISIBLE : View.GONE);
        }
        setTextShow(tvDes, "简介 · ", removeHtmlTag(mVideo.des));
        if (!TextUtils.isEmpty(mVideo.pic)) {
            com.github.tvbox.osc.util.ImgUtil.load(DefaultConfig.checkReplaceProxy(mVideo.pic), ivThumb, AutoSizeUtils.mm2px(mContext, 10), AutoSizeUtils.mm2px(mContext, 300), AutoSizeUtils.mm2px(mContext, 400), mVideo.name);
        } else {
            ivThumb.setImageDrawable(com.github.tvbox.osc.util.ImgUtil.createTextDrawable(mVideo.name));
        }
    }

    private void handleInvalidDetail(boolean failed) {
        if (restoreDetailSnapshot()) {
            ToastUtil.error(this, failed ? "该来源加载失败，已恢复上一个来源" : "该来源没有可播放内容，已恢复上一个来源");
            return;
        }
        if (failed) {
            showDetailError();
        } else {
            showSuccess();
            showEmptyPlaylist();
        }
        llPlayerFragmentContainer.setVisibility(View.GONE);
        llPlayerFragmentContainerBlock.setVisibility(View.GONE);
    }

    private void showPlaylist() {
        // 有可播放线路：恢复顶部海报/预览小窗 + 信息面板
        if (topLayout != null) topLayout.setVisibility(View.VISIBLE);
        if (playlistPanel != null) playlistPanel.setVisibility(View.VISIBLE);
        mGridViewFlag.setVisibility(View.VISIBLE);
        mGridView.setVisibility(View.VISIBLE);
        tvPlay.setVisibility(View.VISIBLE);
        mEmptyPlayList.setVisibility(View.GONE);
    }

    private void showEmptyPlaylist() {
        // 无可播放线路：隐藏顶部海报/预览小窗 + 信息面板，空态提示占满全屏
        if (topLayout != null) topLayout.setVisibility(View.GONE);
        if (playlistPanel != null) playlistPanel.setVisibility(View.GONE);
        mGridViewFlag.setVisibility(View.GONE);
        mGridView.setVisibility(View.GONE);
        tvSeriesGroup.setVisibility(View.GONE);
        tvPlay.setVisibility(View.GONE);
        mEmptyPlayList.setVisibility(View.VISIBLE);
        if (mEmptyQuickSearch != null) {
            mEmptyQuickSearch.post(() -> mEmptyQuickSearch.requestFocus());
        }
    }

    private void saveDetailSnapshot() {
        if (mVideo == null || vodInfo == null) {
            return;
        }
        snapshotVideo = mVideo;
        snapshotVodInfo = vodInfo.copy();
        snapshotPreviewVodInfo = previewVodInfo == null ? null : previewVodInfo.copy();
        snapshotSourceKey = sourceKey;
        snapshotFirstSourceKey = firstsourceKey;
        snapshotVodId = vodId;
        snapshotName = vod_name;
        snapshotPicture = vod_picture;
        hasDetailSnapshot = true;
    }

    private boolean restoreDetailSnapshot() {
        if (!hasDetailSnapshot || snapshotVideo == null || snapshotVodInfo == null) {
            switchingSource = false;
            return false;
        }
        switchingSource = false;
        pendingVodId = null;
        pendingSourceKey = null;
        mVideo = snapshotVideo;
        vodInfo = snapshotVodInfo.copy();
        previewVodInfo = snapshotPreviewVodInfo == null ? null : snapshotPreviewVodInfo.copy();
        sourceKey = snapshotSourceKey;
        firstsourceKey = snapshotFirstSourceKey;
        vodId = snapshotVodId;
        vod_name = snapshotName;
        vod_picture = snapshotPicture;
        showSuccess();
        bindDetailMeta();
        refreshCollectState();
        if (VodPlayData.hasValidPlayData(vodInfo)) {
            showPlaylist();
            updateSourceSummary();
            if (vodInfo.seriesFlags != null) {
                seriesFlagAdapter.setNewData(vodInfo.seriesFlags);
            }
            refreshList();
            if (showPreview && previewVodInfo != null) {
                llPlayerFragmentContainer.setVisibility(View.VISIBLE);
                llPlayerFragmentContainerBlock.setVisibility(View.VISIBLE);
            }
        } else {
            showEmptyPlaylist();
        }
        return true;
    }

    private List<VodInfo.VodSeries> getCurrentSeriesList() {
        return VodPlayData.getSeriesList(vodInfo);
    }

    private void refreshCollectState() {
        if (tvCollect == null) {
            return;
        }
        boolean collected = vodInfo != null && !VodPlayData.isBlank(sourceKey) && !VodPlayData.isBlank(vodInfo.id)
                && RoomDataManger.isVodCollect(sourceKey, vodInfo.id);
        tvCollect.setText(collected ? "取消收藏" : "加入收藏");
    }

    private void showDetailError() {
        ErrorCallback.bind(this, "内容加载失败", "当前来源暂时不可用", "重试", "返回", "",
                new ErrorCallback.ErrorActionListener() {
                    @Override
                    public void onPrimary() {
                        loadDetail(vodId, sourceKey, false);
                    }

                    @Override
                    public void onSecondary() {
                        finish();
                    }
                });
        showError();
    }

    private String getHtml(String label, String content) {
        if (content == null) {
            content = "";
        }
        return label + "<font color=\"#FFFFFF\">" + content + "</font>";
    }

    private String  vod_picture="";
    private String  vod_name="";
    private void initData() {
        Intent intent = getIntent();
        if (intent != null && intent.getExtras() != null) {
            Bundle bundle = intent.getExtras();
            vod_name=bundle.getString("title", "");
            vod_picture=bundle.getString("picture", "");
            loadDetail(bundle.getString("id", null), bundle.getString("sourceKey", ""), false);
        }
    }

    /**
     * 进入一次新的详情加载时重置预览：
     * 1) 若正处于全屏预览则先退出，避免布局停留在全屏；
     * 2) 停止播放器并隐藏预览容器/把手，防止旧片画面在加载期间残留；
     * 3) 清掉预览兜底封面与上次的 previewVodInfo 快照。
     * 数据回填成功后会重新 setData 起播并恢复显示，无需在此恢复。
     */
    private void resetPreviewForLoad() {
        if (!showPreview) return;
        try {
            if (fullWindows) {
                exitFullPreview();
            }
            if (playFragment != null && playFragment.getPlayer() != null) {
                playFragment.getPlayer().release();
            }
        } catch (Throwable th) {
            th.printStackTrace();
        }
        previewVodInfo = null;
        hidePreviewFallback();
        if (llPlayerFragmentContainer != null) {
            llPlayerFragmentContainer.setVisibility(View.GONE);
        }
        if (llPlayerFragmentContainerBlock != null) {
            llPlayerFragmentContainerBlock.setVisibility(View.GONE);
        }
    }

    private void loadDetail(String vid, String key) {
        loadDetail(vid, key, false);
    }

    private void loadDetail(String vid, String key, boolean keepCurrentUi) {
        if (vid == null || VodPlayData.isBlank(key) || !VodPlayData.isValidId(vid)) {
            ToastUtil.error(this, "该来源不可用，请选择其他来源");
            return;
        }
        if (ApiConfig.get().getSource(key) == null) {
            ToastUtil.error(this, "该来源不可用，请选择其他来源");
            return;
        }
        pendingVodId = vid;
        pendingSourceKey = key;
        switchingSource = keepCurrentUi && hasDetailSnapshot;
        if (!keepCurrentUi) {
            vodId = vid;
            sourceKey = key;
            firstsourceKey = key;
            resetPreviewForLoad();
            showLoading();
        }
        detailRequestSeq = sourceViewModel.getDetail(key, vid);
        refreshCollectState();
    }

    /**
     * 线路卡片只显示用户可理解的可用状态，不泄露解析过程字段。
     */
    private void updateSourceSummary() {
        if (vodInfo == null || vodInfo.seriesFlags == null) return;
        for (int i = 0; i < vodInfo.seriesFlags.size(); i++) {
            VodInfo.VodSeriesFlag flag = vodInfo.seriesFlags.get(i);
            if (flag == null || TextUtils.isEmpty(flag.name)) continue;
            List<VodInfo.VodSeries> episodes = VodPlayData.getSeriesList(vodInfo, flag.name);
            String state = VodPlayData.hasValidSeries(episodes) ? "可用" : "不可用";
            flag.displayName = flag.name;
            flag.statusText = state;
        }
        if (seriesFlagAdapter != null) seriesFlagAdapter.notifyDataSetChanged();
    }

    private String getReadableSourceName(String sourceKey) {
        try {
            SourceBean source = ApiConfig.get().getSource(sourceKey);
            if (source != null && !TextUtils.isEmpty(source.getName())) return source.getName();
        } catch (Throwable ignored) { }
        return sourceKey;
    }


    private boolean isFirstLoad = true;
    @Subscribe(threadMode = ThreadMode.MAIN)
    public void refresh(RefreshEvent event) {
        if (event.type == RefreshEvent.TYPE_REFRESH) {
            if (event.obj != null) {
                if (event.obj instanceof VodInfo) {
                    syncPlayingVodInfo((VodInfo) event.obj);
                } else if (event.obj instanceof Integer) {
                    int index = (int) event.obj;
                    List<VodInfo.VodSeries> playingList = getCurrentSeriesList();
                    for (int j = 0; j < playingList.size(); j++) {
                        seriesAdapter.getData().get(j).selected = false;
                        seriesAdapter.notifyItemChanged(j);
                    }
                    seriesAdapter.getData().get(index).selected = true;
                    seriesAdapter.notifyItemChanged(index);
                    if(!isFirstLoad)mGridView.setSelection(index);
                    vodInfo.playIndex = index;
                    //保存历史
                    insertVod(firstsourceKey, vodInfo);
                    isFirstLoad = false;
                } else if (event.obj instanceof JSONObject) {
                    vodInfo.playerCfg = event.obj.toString();
                    //保存历史
                    insertVod(firstsourceKey, vodInfo);
                }

            }
        } else if (event.type == RefreshEvent.TYPE_PREVIEW_ERROR) {
            showPreviewFallback();
        } else if (event.type == RefreshEvent.TYPE_PREVIEW_RESUME) {
            hidePreviewFallback();
        } else if (event.type == RefreshEvent.TYPE_PLAY_QUALITY) {
            updateQualityOptions(event.obj instanceof JSONObject ? (JSONObject) event.obj : null);
        } else if (event.type == RefreshEvent.TYPE_QUICK_SEARCH_SELECT) {
            if (event.obj != null) {
                Movie.Video video = (Movie.Video) event.obj;
                if (!VodPlayData.isValidSearchVideo(video)) {
                    ToastUtil.error(this, "该来源不可用，请选择其他来源");
                    return;
                }
                saveDetailSnapshot();
                loadDetail(video.id, video.sourceKey, true);
            }
        } else if (event.type == RefreshEvent.TYPE_QUICK_SEARCH_WORD_CHANGE) {
            if (event.obj != null) {
                String word = (String) event.obj;
                switchSearchWord(word);
            }
        } else if (event.type == RefreshEvent.TYPE_QUICK_SEARCH_RESULT) {
            try {
                searchData(event.obj == null ? null : (AbsXml) event.obj);
            } catch (Exception e) {
                searchData(null);
            }
        }
    }

    private String searchTitle = "";
    private boolean hadQuickStart = false;
    private final List<Movie.Video> quickSearchData = new ArrayList<>();
    private final List<String> quickSearchWord = new ArrayList<>();
    private ExecutorService searchExecutorService = null;

    private void switchSearchWord(String word) {
        OkGo.getInstance().cancelTag("quick_search");
        quickSearchData.clear();
        searchTitle = word;
        searchResult();
    }

    private void startQuickSearch() {
        initCheckedSourcesForSearch();
        if (hadQuickStart)
            return;
        hadQuickStart = true;
        OkGo.getInstance().cancelTag("quick_search");
        quickSearchWord.clear();
        searchTitle = mVideo.name;
        quickSearchData.clear();
        quickSearchWord.addAll(SearchHelper.splitWords(searchTitle));
        // 分词
//        OkGo.<String>get("http://api.pullword.com/get.php?source=" + URLEncoder.encode(searchTitle) + "&param1=0&param2=0&json=1")
//                .tag("fenci")
//                .execute(new AbsCallback<String>() {
//                    @Override
//                    public String convertResponse(okhttp3.Response response) throws Throwable {
//                        if (response.body() != null) {
//                            return response.body().string();
//                        } else {
//                            throw new IllegalStateException("网络请求错误");
//                        }
//                    }
//
//                    @Override
//                    public void onSuccess(Response<String> response) {
//                        String json = response.body();
//                        try {
//                            for (JsonElement je : new Gson().fromJson(json, JsonArray.class)) {
//                                quickSearchWord.add(je.getAsJsonObject().get("t").getAsString());
//                            }
//                        } catch (Throwable th) {
//                            th.printStackTrace();
//                        }
//                        List<String> words = new ArrayList<>(new HashSet<>(quickSearchWord));
//                        EventBus.getDefault().post(new RefreshEvent(RefreshEvent.TYPE_QUICK_SEARCH_WORD, words));
//                    }
//
//                    @Override
//                    public void onError(Response<String> response) {super.onError(response);}
//                });

        searchResult();
    }

    private void searchResult() {
        try {
            if (searchExecutorService != null) {
                searchExecutorService.shutdownNow();
                searchExecutorService = null;
            }
        } catch (Throwable th) {
            th.printStackTrace();
        }
        searchExecutorService = Executors.newFixedThreadPool(5);
        List<SourceBean> searchRequestList = new ArrayList<>();
        searchRequestList.addAll(ApiConfig.get().getSourceBeanList());
        SourceBean home = ApiConfig.get().getHomeSourceBean();
        searchRequestList.remove(home);
        searchRequestList.add(0, home);

        ArrayList<String> siteKey = new ArrayList<>();
        for (SourceBean bean : searchRequestList) {
            if (!bean.isSearchable() || !bean.isQuickSearch()) {
                continue;
            }
            if (mCheckSources != null && !mCheckSources.containsKey(bean.getKey())) {
                continue;
            }
            siteKey.add(bean.getKey());
        }
        for (String key : siteKey) {
            searchExecutorService.execute(new Runnable() {
                @Override
                public void run() {
                    sourceViewModel.getQuickSearch(key, searchTitle);
                }
            });
        }
    }

    private void searchData(AbsXml absXml) {
        if (absXml != null && absXml.movie != null && absXml.movie.videoList != null && absXml.movie.videoList.size() > 0) {
            List<Movie.Video> data = new ArrayList<>();
            for (Movie.Video video : absXml.movie.videoList) {
                if (video == null) continue;
                // 去除当前相同的影片
                if (TextUtils.equals(video.sourceKey, sourceKey) && TextUtils.equals(video.id, vodId))
                    continue;
                data.add(video);
            }
            quickSearchData.addAll(data);
            EventBus.getDefault().post(new RefreshEvent(RefreshEvent.TYPE_QUICK_SEARCH, data));
        }
    }

    private void syncPlayingVodInfo(VodInfo playingVodInfo) {
        if (playingVodInfo == null || vodInfo == null || vodInfo.seriesMap == null) {
            return;
        }
        // 换源后旧 PlayFragment 仍可能发出 TYPE_REFRESH。id/sourceKey 对不上就丢掉，
        // 否则会把详情页线路选中态同步回上一个源。
        if (!TextUtils.equals(playingVodInfo.id, vodInfo.id)
                || !TextUtils.equals(playingVodInfo.sourceKey, vodInfo.sourceKey)) {
            LOG.i("echo-sync-skip stale playInfo id=" + playingVodInfo.id
                    + " key=" + playingVodInfo.sourceKey
                    + " currentId=" + vodInfo.id
                    + " currentKey=" + vodInfo.sourceKey);
            return;
        }
        String newFlag = playingVodInfo.playFlag;
        if (TextUtils.isEmpty(newFlag) || !vodInfo.seriesMap.containsKey(newFlag)) {
            return;
        }
        List<VodInfo.VodSeries> newSeriesList = vodInfo.seriesMap.get(newFlag);
        if (newSeriesList == null || newSeriesList.isEmpty()) {
            return;
        }

        String oldFlag = vodInfo.playFlag;
        int oldIndex = vodInfo.playIndex;
        boolean sameFlag = TextUtils.equals(oldFlag, newFlag);
        VodInfo.VodSeries playingSeries = getPlayingSeries(playingVodInfo, newFlag);
        int newIndex = findSameEpisodeIndex(playingSeries, newSeriesList, playingVodInfo.playIndex);
        vodInfo.playFlag = newFlag;
        vodInfo.playIndex = newIndex;
        if (playingVodInfo.playerCfg != null) {
            vodInfo.playerCfg = playingVodInfo.playerCfg;
        }

        for (VodInfo.VodSeriesFlag flag : vodInfo.seriesFlags) {
            flag.selected = flag.name.equals(newFlag);
        }
        for (List<VodInfo.VodSeries> seriesList : vodInfo.seriesMap.values()) {
            if (seriesList == null) {
                continue;
            }
            for (VodInfo.VodSeries series : seriesList) {
                series.selected = false;
            }
        }
        newSeriesList.get(newIndex).selected = true;

        seriesFlagAdapter.notifyDataSetChanged();
        if (sameFlag && oldIndex >= 0 && oldIndex < newSeriesList.size()) {
            if (oldIndex != newIndex) {
                seriesAdapter.notifyItemChanged(oldIndex);
                seriesAdapter.notifyItemChanged(newIndex);
            }
        } else {
            refreshList();
        }
        int flagIndex = -1;
        for (int i = 0; i < vodInfo.seriesFlags.size(); i++) {
            if (vodInfo.seriesFlags.get(i).name.equals(newFlag)) {
                flagIndex = i;
                break;
            }
        }
        if (flagIndex >= 0) {
            mGridViewFlag.scrollToPosition(flagIndex);
            if (mGridViewFlag.hasFocus()) {
                mGridViewFlag.setSelection(flagIndex);
            }
        }
        if (!isFirstLoad) {
            mGridView.setSelection(newIndex);
        }

        insertVod(firstsourceKey, vodInfo);
        isFirstLoad = false;
    }

    private VodInfo.VodSeries getPlayingSeries(VodInfo playingVodInfo, String flag) {
        if (playingVodInfo == null || playingVodInfo.seriesMap == null || TextUtils.isEmpty(flag)) {
            return null;
        }
        List<VodInfo.VodSeries> playingList = playingVodInfo.seriesMap.get(flag);
        if (playingList == null || playingList.isEmpty()) {
            return null;
        }
        int safeIndex = Math.max(0, Math.min(playingVodInfo.playIndex, playingList.size() - 1));
        return playingList.get(safeIndex);
    }

    private boolean isCurrentPreviewPlaying(int position) {
        if (!showPreview || previewVodInfo == null || vodInfo == null || vodInfo.seriesMap == null || TextUtils.isEmpty(vodInfo.playFlag)) {
            return false;
        }
        if (!TextUtils.equals(vodInfo.playFlag, previewVodInfo.playFlag) || previewVodInfo.playIndex != position) {
            return false;
        }
        List<VodInfo.VodSeries> currentList = vodInfo.seriesMap.get(vodInfo.playFlag);
        if (currentList == null || position < 0 || position >= currentList.size()) {
            return false;
        }
        VodInfo.VodSeries currentSeries = currentList.get(position);
        VodInfo.VodSeries previewSeries = getPlayingSeries(previewVodInfo, previewVodInfo.playFlag);
        return currentSeries != null && previewSeries != null && TextUtils.equals(currentSeries.url, previewSeries.url);
    }

    private int findSameEpisodeIndex(VodInfo.VodSeries currentSeries, List<VodInfo.VodSeries> targetList, int fallbackIndex) {
        if (targetList == null || targetList.isEmpty()) {
            return 0;
        }
        if (currentSeries != null && !TextUtils.isEmpty(currentSeries.name)) {
            String currentName = normalizeEpisodeName(currentSeries.name);
            for (int i = 0; i < targetList.size(); i++) {
                VodInfo.VodSeries targetSeries = targetList.get(i);
                if (targetSeries != null && currentName.equals(normalizeEpisodeName(targetSeries.name))) {
                    return i;
                }
            }
            int currentEpisode = extractEpisodeNumber(currentSeries.name);
            if (currentEpisode >= 0) {
                for (int i = 0; i < targetList.size(); i++) {
                    VodInfo.VodSeries targetSeries = targetList.get(i);
                    if (targetSeries != null && extractEpisodeNumber(targetSeries.name) == currentEpisode) {
                        return i;
                    }
                }
            }
        }
        return Math.max(0, Math.min(fallbackIndex, targetList.size() - 1));
    }

    private String normalizeEpisodeName(String name) {
        if (name == null) {
            return "";
        }
        return name.toLowerCase(Locale.ROOT)
                .replaceAll("\\s+", "")
                .replaceAll("[\\[\\]【】()（）]", "")
                .replace("第", "")
                .replace("集", "")
                .replace("话", "")
                .replace("期", "");
    }

    private int extractEpisodeNumber(String name) {
        if (name == null) {
            return -1;
        }
        Matcher episodeMatcher = Pattern.compile("(?:第)?(\\d+)(?:集|话|期|$)").matcher(name);
        if (episodeMatcher.find()) {
            try {
                return Integer.parseInt(episodeMatcher.group(1));
            } catch (NumberFormatException ignored) {
            }
        }
        Matcher matcher = Pattern.compile("\\d+").matcher(name);
        if (matcher.find()) {
            try {
                return Integer.parseInt(matcher.group());
            } catch (NumberFormatException ignored) {
            }
        }
        return -1;
    }

    private void insertVod(String sourceKey, VodInfo vodInfo) {
        try {
            VodInfo.VodSeries noteSeries = VodPlayData.getSeries(vodInfo, vodInfo.playFlag, vodInfo.playIndex);
            vodInfo.playNote = noteSeries == null ? "" : noteSeries.name;
        } catch (Throwable th) {
            vodInfo.playNote = "";
        }
        RoomDataManger.insertVodRecord(sourceKey, vodInfo);
        EventBus.getDefault().post(new RefreshEvent(RefreshEvent.TYPE_HISTORY_REFRESH));
    }

    @Override
    protected void onDestroy() {
        super.onDestroy();
        try {
            if (searchExecutorService != null) {
                searchExecutorService.shutdownNow();
                searchExecutorService = null;
            }
        } catch (Throwable th) {
            th.printStackTrace();
        }
        OkGo.getInstance().cancelTag("fenci");
        OkGo.getInstance().cancelTag("detail");
        OkGo.getInstance().cancelTag("quick_search");
        releasePlayFragment();
        EventBus.getDefault().unregister(this);
    }

    @Override
    public void onBackPressed() {
        if (fullWindows) {
            if (playFragment.onBackPressed())
                return;
            exitFullPreview();
            return;
        }
        if(showPreview && playFragment!=null){
            try {
                playFragment.setPlayTitle(false);
                playFragment.setExitingPreview(true);
            } catch (Throwable th) {
                th.printStackTrace();
            }
        }
        super.onBackPressed();
    }

    @Override
    public boolean dispatchKeyEvent(KeyEvent event) {
        if (!fullWindows && event != null && event.getAction() == KeyEvent.ACTION_DOWN
                && event.getKeyCode() == KeyEvent.KEYCODE_DPAD_UP && handleSeriesDpadUp()) {
            return true;
        }
        if (event != null && playFragment != null && fullWindows) {
            if (playFragment.dispatchKeyEvent(event)) {
                return true;
            }
        }
        if (event != null && handleDetailDpad(event)) {
            return true;
        }
        return super.dispatchKeyEvent(event);
    }

    private boolean handleDetailDpad(KeyEvent event) {
        if (fullWindows || event.getKeyCode() < KeyEvent.KEYCODE_DPAD_UP || event.getKeyCode() > KeyEvent.KEYCODE_DPAD_RIGHT) {
            return false;
        }
        View focused = getCurrentFocus();
        if (focused == null) return false;
        if (event.getAction() != KeyEvent.ACTION_DOWN) return true;

        View next = null;
        switch (focused.getId()) {
            case R.id.previewPlayerBlock:
                if (event.getKeyCode() == KeyEvent.KEYCODE_DPAD_RIGHT) next = tvPlay;
                else if (event.getKeyCode() == KeyEvent.KEYCODE_DPAD_DOWN) next = mGridViewFlag;
                break;
            case R.id.tvPlay:
                if (event.getKeyCode() == KeyEvent.KEYCODE_DPAD_LEFT || event.getKeyCode() == KeyEvent.KEYCODE_DPAD_UP) next = llPlayerFragmentContainerBlock;
                else if (event.getKeyCode() == KeyEvent.KEYCODE_DPAD_RIGHT) next = tvQuickSearch;
                else if (event.getKeyCode() == KeyEvent.KEYCODE_DPAD_DOWN) next = mGridViewFlag;
                break;
            case R.id.tvQuickSearch:
                if (event.getKeyCode() == KeyEvent.KEYCODE_DPAD_LEFT) next = tvPlay;
                else if (event.getKeyCode() == KeyEvent.KEYCODE_DPAD_RIGHT) next = tvDesc;
                else if (event.getKeyCode() == KeyEvent.KEYCODE_DPAD_UP) next = tvPlay;
                else if (event.getKeyCode() == KeyEvent.KEYCODE_DPAD_DOWN) next = mGridViewFlag;
                break;
            case R.id.tvDesc:
                if (event.getKeyCode() == KeyEvent.KEYCODE_DPAD_LEFT) next = tvQuickSearch;
                else if (event.getKeyCode() == KeyEvent.KEYCODE_DPAD_RIGHT) next = tvCollect;
                else if (event.getKeyCode() == KeyEvent.KEYCODE_DPAD_UP) next = tvPlay;
                else if (event.getKeyCode() == KeyEvent.KEYCODE_DPAD_DOWN) next = mGridViewFlag;
                break;
            case R.id.tvCollect:
                if (event.getKeyCode() == KeyEvent.KEYCODE_DPAD_LEFT) next = tvDesc;
                else if (event.getKeyCode() == KeyEvent.KEYCODE_DPAD_UP) next = tvPlay;
                else if (event.getKeyCode() == KeyEvent.KEYCODE_DPAD_DOWN) next = mGridViewFlag;
                break;
            case R.id.mEmptyQuickSearch:
                if (event.getKeyCode() == KeyEvent.KEYCODE_DPAD_RIGHT) next = mEmptyBack;
                break;
            case R.id.mEmptyBack:
                if (event.getKeyCode() == KeyEvent.KEYCODE_DPAD_LEFT) next = mEmptyQuickSearch;
                break;
            default:
                return false;
        }
        if (next != null && next.getVisibility() == View.VISIBLE && next.isFocusable()) {
            next.setFocusableInTouchMode(true);
            next.requestFocus();
        }
        return next != null;
    }

    /**
     * TvRecyclerView 对嵌套网格的空间寻焦不总是尊重 item 的 nextFocusUpId。
     * 首行选集向上必须回到线路（有清晰度行时先回到清晰度），否则会跳过线路或卡在原地。
     */
    private boolean handleSeriesDpadUp() {
        if (mGridView == null || !mGridView.hasFocus() || mGridViewLayoutMgr == null) {
            return false;
        }
        View focused = getCurrentFocus();
        if (focused == null) {
            return false;
        }
        while (focused.getParent() != mGridView) {
            if (!(focused.getParent() instanceof View)) {
                return false;
            }
            focused = (View) focused.getParent();
        }
        int position = mGridView.getSelectedPosition();
        if (position < 0 || position >= mGridViewLayoutMgr.getSpanCount()) {
            return false;
        }
        TvRecyclerView target = mGridViewQuality != null
                && mGridViewQuality.getVisibility() == View.VISIBLE
                ? mGridViewQuality : mGridViewFlag;
        return target != null && target.getVisibility() == View.VISIBLE && target.requestFocus();
    }

    @Override
    public boolean onKeyDown(int keyCode, KeyEvent event) {
        if (event != null && playFragment != null && fullWindows) {
            if (playFragment.onKeyDown(keyCode,event)) {
                return true;
            }
        }
        return super.onKeyDown(keyCode, event);
    }

    @Override
    public boolean onKeyUp(int keyCode, KeyEvent event) {
        if (event != null && playFragment != null && fullWindows) {
            if (playFragment.onKeyUp(keyCode,event)) {
                return true;
            }
        }
        return super.onKeyUp(keyCode, event);
    }

    // preview
    VodInfo previewVodInfo = null;
    boolean fullWindows = false;
    private int previewOrientation;
    private boolean previewOrientationChanged;
    ViewGroup.LayoutParams windowsPreview = null;
    ViewGroup.LayoutParams windowsFull = null;

    void toggleFullPreview() {
        setFullPreview(!fullWindows);
    }

    void enterFullPreview() {
        setFullPreview(true);
    }

    void exitFullPreview() {
        boolean needRefreshSeries = previewOrientationChanged;
        setFullPreview(false);
        previewOrientationChanged = false;
        if (needRefreshSeries) refreshSeriesAfterFullPreview();
    }

    private void refreshSeriesAfterFullPreview() {
        if (seriesAdapter == null || vodInfo == null || vodInfo.seriesMap == null || TextUtils.isEmpty(vodInfo.playFlag)) return;
        if (vodInfo.seriesMap.get(vodInfo.playFlag) == null) return;
        mGridView.post(new Runnable() {
            @Override
            public void run() {
                mGridView.getRecycledViewPool().clear();
                mGridView.setAdapter(seriesAdapter);
                refreshList();
            }
        });
    }

    void setFullPreview(boolean full) {
        if (windowsPreview == null) {
            windowsPreview = llPlayerFragmentContainer.getLayoutParams();
        }
        if (windowsFull == null) {
            windowsFull = new FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT);
        }
        if (full) {
            previewOrientation = getResources().getConfiguration().orientation;
            previewOrientationChanged = false;
            hidePreviewFallback();
        }
        fullWindows = full;
        if (playFragment != null) {
            playFragment.setAutoSwitchLineEnabled(!fullWindows);
            playFragment.setPreviewMode(!fullWindows);
        }
        llPlayerFragmentContainer.setVisibility(fullWindows || showPreview ? View.VISIBLE : View.GONE);
        llPlayerFragmentContainer.setLayoutParams(fullWindows ? windowsFull : windowsPreview);
        setPreviewRoundClip(!fullWindows);
        // 不要在这里 rebindPreviewSurface()/addDisplay()：
        // 改 LayoutParams 本身就会让 SurfaceView 走 destroy→create。
        // 再新建一层 RenderView 会把 IJK 硬解解绑，小窗↔全屏出现绿屏。
        llPlayerFragmentContainerBlock.setVisibility(!fullWindows && showPreview ? View.VISIBLE : View.GONE);
        mGridView.setVisibility(fullWindows ? View.GONE : View.VISIBLE);
        mGridViewFlag.setVisibility(fullWindows ? View.GONE : View.VISIBLE);
        if (fullWindows) {
            tvSeriesGroup.setVisibility(View.GONE);
        } else {
            List<VodInfo.VodSeries> list = vodInfo == null || vodInfo.seriesMap == null || TextUtils.isEmpty(vodInfo.playFlag) ? null : vodInfo.seriesMap.get(vodInfo.playFlag);
            tvSeriesGroup.setVisibility(list != null && list.size() > 1 ? View.VISIBLE : View.GONE);
            seriesFlagAdapter.notifyDataSetChanged();
            if (showPreview) mGridView.requestFocus();
            else {
                if (playFragment != null) playFragment.pauseForHidden();
                mGridView.requestFocus();
            }
        }
        toggleSubtitleTextSize();
    }

    @Override
    public void onConfigurationChanged(Configuration newConfig) {
        super.onConfigurationChanged(newConfig);
        if (fullWindows && newConfig.orientation != previewOrientation) {
            previewOrientation = newConfig.orientation;
            previewOrientationChanged = true;
        }
    }

    void ensurePlayFragment() {
        if (playFragment != null) return;
        playFragment = new PlayFragment();
        getSupportFragmentManager().beginTransaction().add(R.id.previewPlayer, playFragment).commitNowAllowingStateLoss();
        playFragment.setPreviewMode(showPreview && !fullWindows);
    }

    void releasePlayFragment() {
        if (playFragment == null) return;
        getSupportFragmentManager().beginTransaction().remove(playFragment).commitNowAllowingStateLoss();
        playFragment = null;
    }

    void toggleSubtitleTextSize() {
        int subtitleTextSize  = SubtitleHelper.getTextSize(this);
        if (!fullWindows) {
            subtitleTextSize *= 0.6;
        }
        EventBus.getDefault().post(new RefreshEvent(RefreshEvent.TYPE_SUBTITLE_SIZE_CHANGE, subtitleTextSize));
    }

    /**
     * 带 OnClickListener 的普通 View 在 onKeyDown 中会吞掉 DPAD 方向键，
     * 这里手动执行方向寻焦以维持焦点路径。
     */
    private void enableDpadNavigation(View view) {
        view.setOnKeyListener((v, keyCode, event) -> {
            if (event.getAction() != KeyEvent.ACTION_DOWN) return false;
            int direction = -1;
            switch (keyCode) {
                case KeyEvent.KEYCODE_DPAD_UP:
                    direction = View.FOCUS_UP;
                    break;
                case KeyEvent.KEYCODE_DPAD_DOWN:
                    direction = View.FOCUS_DOWN;
                    break;
                case KeyEvent.KEYCODE_DPAD_LEFT:
                    direction = View.FOCUS_LEFT;
                    break;
                case KeyEvent.KEYCODE_DPAD_RIGHT:
                    direction = View.FOCUS_RIGHT;
                    break;
                default:
                    return false;
            }
            View next = v.focusSearch(direction);
            if (next != null) {
                next.requestFocus(direction);
            }
            return true;
        });
    }

    private void openQuickSearchDialog() {
        startQuickSearch();
        QuickSearchDialog quickSearchDialog = new QuickSearchDialog(DetailActivity.this);
        EventBus.getDefault().post(new RefreshEvent(RefreshEvent.TYPE_QUICK_SEARCH, quickSearchData));
        EventBus.getDefault().post(new RefreshEvent(RefreshEvent.TYPE_QUICK_SEARCH_WORD, quickSearchWord));
        quickSearchDialog.show();
        if (pauseRunnable != null && pauseRunnable.size() > 0) {
            searchExecutorService = Executors.newFixedThreadPool(5);
            for (Runnable runnable : pauseRunnable) {
                searchExecutorService.execute(runnable);
            }
            pauseRunnable.clear();
            pauseRunnable = null;
        }
        quickSearchDialog.setOnDismissListener(new DialogInterface.OnDismissListener() {
            @Override
            public void onDismiss(DialogInterface dialog) {
                try {
                    if (searchExecutorService != null) {
                        pauseRunnable = searchExecutorService.shutdownNow();
                        searchExecutorService = null;
                    }
                } catch (Throwable th) {
                    th.printStackTrace();
                }
            }
        });
    }

    private void showPreviewFallback() {
        if (!showPreview || ivPreviewFallback == null) return;
        if (ivPreviewFallback.getVisibility() == View.VISIBLE) return;
        if (mVideo != null && !TextUtils.isEmpty(mVideo.pic)) {
            com.github.tvbox.osc.util.ImgUtil.load(DefaultConfig.checkReplaceProxy(mVideo.pic), ivPreviewFallback, AutoSizeUtils.mm2px(mContext, 10), AutoSizeUtils.mm2px(mContext, 300), AutoSizeUtils.mm2px(mContext, 400), mVideo.name);
        } else {
            ivPreviewFallback.setImageDrawable(com.github.tvbox.osc.util.ImgUtil.createTextDrawable(mVideo == null ? "TVBox" : mVideo.name));
        }
        ivPreviewFallback.setVisibility(View.VISIBLE);
        tvPreviewHint.setVisibility(View.GONE);
    }

    private void hidePreviewFallback() {
        if (ivPreviewFallback == null) return;
        ivPreviewFallback.setVisibility(View.GONE);
        tvPreviewHint.setVisibility(llPlayerFragmentContainerBlock.hasFocus() ? View.VISIBLE : View.GONE);
    }
}
