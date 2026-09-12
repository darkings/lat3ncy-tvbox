package com.github.tvbox.osc.ui.activity;

import android.content.Intent;
import android.graphics.Typeface;
import android.os.Build;
import android.os.Bundle;
import android.os.Looper;
import android.text.SpannableString;
import android.text.Spanned;
import android.text.TextUtils;
import android.text.style.ForegroundColorSpan;
import android.text.style.RelativeSizeSpan;
import android.text.style.StyleSpan;
import android.view.View;
import android.view.ViewGroup;
import android.view.animation.PathInterpolator;
import android.widget.LinearLayout;
import android.widget.TextView;

import androidx.lifecycle.ViewModelProvider;

import com.chad.library.adapter.base.BaseQuickAdapter;
import com.github.catvod.crawler.JsLoader;
import com.github.tvbox.osc.R;
import com.github.tvbox.osc.api.ApiConfig;
import com.github.tvbox.osc.base.BaseActivity;
import com.github.tvbox.osc.callback.EmptyCallback;
import com.github.tvbox.osc.callback.LoadingCallback;
import com.github.tvbox.osc.callback.SearchLoadingCallback;
import com.github.tvbox.osc.bean.AbsXml;
import com.github.tvbox.osc.bean.Movie;
import com.github.tvbox.osc.bean.SourceBean;
import com.github.tvbox.osc.event.RefreshEvent;
import com.github.tvbox.osc.event.ServerEvent;
import com.github.tvbox.osc.ui.adapter.FastListAdapter;
import com.github.tvbox.osc.ui.adapter.FastSearchAdapter;
import com.github.tvbox.osc.ui.adapter.SearchWordAdapter;
import com.github.tvbox.osc.util.FastClickCheckUtil;
import com.github.tvbox.osc.util.VodPlayData;
import com.github.tvbox.osc.util.HistoryHelper;
import com.github.tvbox.osc.util.SearchHelper;
import com.github.tvbox.osc.viewmodel.SourceViewModel;
import com.lzy.okgo.OkGo;
import com.owen.tvrecyclerview.widget.TvRecyclerView;
import com.owen.tvrecyclerview.widget.V7GridLayoutManager;
import com.owen.tvrecyclerview.widget.V7LinearLayoutManager;

import org.greenrobot.eventbus.EventBus;
import org.greenrobot.eventbus.Subscribe;
import org.greenrobot.eventbus.ThreadMode;

import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import com.github.tvbox.osc.util.ToastUtil;

/**
 * @author pj567
 * @date :2020/12/23
 * @description:
 */
public class FastSearchActivity extends BaseActivity {

    @Override
    protected Class<? extends com.kingja.loadsir.callback.Callback> getLoadingCallbackClass() {
        // 搜索页使用搜索专用加载动画, 不用换源/内容加载动画
        return SearchLoadingCallback.class;
    }

    private static final int SEARCH_THREAD_COUNT = 4;
    private static final int MAX_RESULT_PER_SOURCE = 20;
    private static final int MAX_TOTAL_RESULT = 200;
    private static final int SEARCH_MAX_THREAD_COUNT = Build.VERSION.SDK_INT >= 30 ? 18 : 12;
    private static final int SEARCH_PUMP_SECONDS = 2;
    private static final int SEARCH_NEXT_BATCH_SECONDS = 3;
    private static final int SEARCH_SITE_TIMEOUT_SECONDS = 10;
    private static final long POSTER_FOCUS_ANIM_DURATION = 300L;
    private static final float POSTER_FOCUS_SCALE = 1.05f;
    private static final String SEARCH_ALL_NAME = "\u5168\u90e8";
    private LinearLayout llLayout;
    private TextView mSearchTitle;
    private TvRecyclerView mGridView;
    private TvRecyclerView mGridViewFilter;
    private TvRecyclerView mGridViewWord;
    private TvRecyclerView mGridViewWordFenci;
    SourceViewModel sourceViewModel;

    private SearchWordAdapter searchWordAdapter;
    private FastSearchAdapter searchAdapter;
    private FastSearchAdapter searchAdapterFilter;
    private FastListAdapter spListAdapter;
    private String searchTitle = "";
    private HashMap<String, String> spNames;
    private boolean isFilterMode = false;
    private String searchFilterKey = "";    // 过滤的key
    private HashMap<String, ArrayList<Movie.Video>> resultVods; // 搜索结果
    private final List<String> quickSearchWord = new ArrayList<>();
    private final Set<String> wordListNames = new HashSet<>();
    private int wordListVersion = 0;
    private String selectedWordName = "";
    private HashMap<String, String> mCheckSources = null;

    @Override
    protected int getLayoutResID() {
        return R.layout.activity_fast_search;
    }

    @Override
    protected void init() {
        spNames = new HashMap<String, String>();
        resultVods = new HashMap<String, ArrayList<Movie.Video>>();
        initView();
        initViewModel();
        LoadingCallback.bindRetry(this, new Runnable() {
            @Override
            public void run() {
                if (!TextUtils.isEmpty(searchTitle)) {
                    search(searchTitle);
                }
            }
        });
        initData();
    }

    @Override
    protected void onResume() {
        super.onResume();
        if (searchPaused) {
            resumePausedSearches();
        }
    }

    private void initView() {
        EventBus.getDefault().register(this);
        llLayout = findViewById(R.id.llLayout);
        mSearchTitle = findViewById(R.id.mSearchTitle);
        mGridView = findViewById(R.id.mGridView);
        mGridViewWord = findViewById(R.id.mGridViewWord);
        mGridViewFilter = findViewById(R.id.mGridViewFilter);
        View wordRail = findViewById(R.id.llWord);
        if (wordRail instanceof ViewGroup) {
            // XML 虽已关裁剪，TvRecyclerView 仍可能在代码里改回默认值
            ((ViewGroup) wordRail).setClipChildren(false);
            ((ViewGroup) wordRail).setClipToPadding(false);
        }
        mGridViewWord.setClipChildren(false);
        mGridViewWord.setClipToPadding(false);

        mGridViewWord.setHasFixedSize(true);
        mGridViewWord.setLayoutManager(new V7LinearLayoutManager(this.mContext, 1, false));
        spListAdapter = new FastListAdapter();
        mGridViewWord.setAdapter(spListAdapter);

        spListAdapter.setOnItemClickListener(new BaseQuickAdapter.OnItemClickListener() {
            @Override
            public void onItemClick(BaseQuickAdapter adapter, View view, int position) {
                selectWord(spListAdapter.getItem(position));
            }
        });

        mGridViewWord.setOnItemListener(new TvRecyclerView.OnItemListener() {
            @Override
            public void onItemPreSelected(TvRecyclerView parent, View itemView, int position) {
            }

            @Override
            public void onItemSelected(TvRecyclerView parent, View itemView, int position) {
                selectWord(spListAdapter.getItem(position));
            }

            @Override
            public void onItemClick(TvRecyclerView parent, View itemView, int position) {
                selectWord(spListAdapter.getItem(position));
            }
        });
        mGridViewWord.setOnInBorderKeyEventListener(new TvRecyclerView.OnInBorderKeyEventListener() {
            @Override
            public boolean onInBorderKeyEvent(int direction, View view) {
                // 源列表到顶后不再往上跳出，避免焦点跑到分词/标题
                if (direction == View.FOCUS_UP) {
                    return true;
                }
                // 到达右边界时进入当前可见结果网格，而不是让系统再找一个“更靠右”的源按钮
                if (direction == View.FOCUS_RIGHT) {
                    focusVisibleResultGrid();
                    return true;
                }
                return false;
            }
        });

        mGridView.setHasFixedSize(true);
        mGridView.setLayoutManager(new V7GridLayoutManager(this.mContext, 4));

        searchAdapter = new FastSearchAdapter();
        mGridView.setAdapter(searchAdapter);
        mGridView.setOnItemListener(new TvRecyclerView.OnItemListener() {
            @Override
            public void onItemPreSelected(TvRecyclerView parent, View itemView, int position) {
                setPosterFocusScale(itemView, false);
            }

            @Override
            public void onItemSelected(TvRecyclerView parent, View itemView, int position) {
                setPosterFocusScale(itemView, true);
            }

            @Override
            public void onItemClick(TvRecyclerView parent, View itemView, int position) {
            }
        });

        searchAdapter.setOnItemClickListener(new BaseQuickAdapter.OnItemClickListener() {
            @Override
            public void onItemClick(BaseQuickAdapter adapter, View view, int position) {
                FastClickCheckUtil.check(view);
                // FIX-09: 移除 isSearchBusy 拦截。用户看到想看的影片应能立即点击，
                // pauseSearchTasks() 会安全停止剩余搜索任务，无需阻止用户操作。
                Movie.Video video = searchAdapter.getData().get(position);
                if (video != null && VodPlayData.isValidSearchVideo(video)) {
                    pauseSearchTasks();
                    Bundle bundle = new Bundle();
                    bundle.putString("id", video.id);
                    bundle.putString("sourceKey", video.sourceKey);
                    bundle.putString("title", video.name);
                    bundle.putString("picture", video.pic);
                    jumpActivity(DetailActivity.class, bundle);
                }
            }
        });


        mGridViewFilter.setLayoutManager(new V7GridLayoutManager(this.mContext, 4));
        searchAdapterFilter = new FastSearchAdapter();
        mGridViewFilter.setAdapter(searchAdapterFilter);
        mGridViewFilter.setOnItemListener(new TvRecyclerView.OnItemListener() {
            @Override
            public void onItemPreSelected(TvRecyclerView parent, View itemView, int position) {
                setPosterFocusScale(itemView, false);
            }

            @Override
            public void onItemSelected(TvRecyclerView parent, View itemView, int position) {
                setPosterFocusScale(itemView, true);
            }

            @Override
            public void onItemClick(TvRecyclerView parent, View itemView, int position) {
            }
        });
        searchAdapterFilter.setOnItemClickListener(new BaseQuickAdapter.OnItemClickListener() {
            @Override
            public void onItemClick(BaseQuickAdapter adapter, View view, int position) {
                FastClickCheckUtil.check(view);
                // FIX-09: 同上，移除搜索中点击拦截
                Movie.Video video = searchAdapterFilter.getData().get(position);
                if (video != null && VodPlayData.isValidSearchVideo(video)) {
                    pauseSearchTasks();
                    Bundle bundle = new Bundle();
                    bundle.putString("id", video.id);
                    bundle.putString("sourceKey", video.sourceKey);
                    bundle.putString("title", video.name);
                    bundle.putString("picture", video.pic);
                    jumpActivity(DetailActivity.class, bundle);
                }
            }
        });

        setLoadSir(llLayout);

        // 分词
        searchWordAdapter = new SearchWordAdapter();
        mGridViewWordFenci = findViewById(R.id.mGridViewWordFenci);
        mGridViewWordFenci.setAdapter(searchWordAdapter);
        mGridViewWordFenci.setLayoutManager(new V7LinearLayoutManager(this.mContext, 0, false));
        searchWordAdapter.setOnItemClickListener(new BaseQuickAdapter.OnItemClickListener() {
            @Override
            public void onItemClick(BaseQuickAdapter adapter, View view, int position) {
                String str = searchWordAdapter.getData().get(position);
                search(str);
            }
        });
        searchWordAdapter.setNewData(new ArrayList<>());
    }

    private void setPosterFocusScale(View itemView, boolean focused) {
        if (itemView == null) return;
        if (focused) {
            itemView.bringToFront();
        }
        float scale = focused ? POSTER_FOCUS_SCALE : 1.0f;
        itemView.animate()
                .scaleX(scale)
                .scaleY(scale)
                .setDuration(POSTER_FOCUS_ANIM_DURATION)
                .setInterpolator(new PathInterpolator(0.05f, 0.7f, 0.1f, 1f))
                .start();
    }

    private void initViewModel() {
        sourceViewModel = new ViewModelProvider(this).get(SourceViewModel.class);
    }

    private void filterResult(String spName) {
        if (TextUtils.isEmpty(spName)) return;
        selectedWordName = spName;
        setSelectedWordName(spName);
        if (TextUtils.equals(spName, SEARCH_ALL_NAME)) {
            // 全部结果：后续异步到货时仍刷新总列表
            isFilterMode = false;
            mGridView.setVisibility(View.VISIBLE);
            mGridViewFilter.setVisibility(View.GONE);
            return;
        }
        // 单源筛选：锁住右侧网格，避免搜索回调把总列表重新显示出来
        isFilterMode = true;
        mGridView.setVisibility(View.GONE);
        mGridViewFilter.setVisibility(View.VISIBLE);
        String key = spNames.get(spName);
        if (TextUtils.isEmpty(key)) return;

        if (TextUtils.equals(searchFilterKey, key)) return;
        searchFilterKey = key;

        List<Movie.Video> list = resultVods.get(key);
        if (list == null) {
            list = new ArrayList<>();
        }
        searchAdapterFilter.setNewData(list);
    }

    private void selectWord(String spName) {
        if (TextUtils.isEmpty(spName) || TextUtils.equals(selectedWordName, spName)) return;
        filterResult(spName);
    }

    private void updateWordListWhenIdle(final Runnable action) {
        if (action == null) return;
        if (mGridViewWord == null) {
            action.run();
            return;
        }
        if (mGridViewWord.isComputingLayout()) {
            mGridViewWord.post(new Runnable() {
                @Override
                public void run() {
                    updateWordListWhenIdle(action);
                }
            });
            return;
        }
        action.run();
    }

    private void setSelectedWordName(final String spName) {
        updateWordListWhenIdle(new Runnable() {
            @Override
            public void run() {
                spListAdapter.setSelectedName(spName);
                spListAdapter.refreshVisibleSelection(mGridViewWord);
            }
        });
    }

    private void setWordListData(List<String> data) {
        final List<String> wordList = new ArrayList<>(data);
        final int version = ++wordListVersion;
        wordListNames.clear();
        wordListNames.addAll(wordList);
        updateWordListWhenIdle(new Runnable() {
            @Override
            public void run() {
                if (version != wordListVersion) return;
                spListAdapter.setNewData(wordList);
                if (wordList.size() > 0 && TextUtils.equals(wordList.get(0), SEARCH_ALL_NAME)) {
                    mGridViewWord.setSelectedPosition(0);
                    mGridViewWord.setSelection(0);
                    requestWordListFirstFocus();
                }
            }
        });
    }

    private void requestWordListFirstFocus() {
        if (mGridViewWord == null) return;
        mGridViewWord.post(new Runnable() {
            @Override
            public void run() {
                if (isFinishing() || mGridViewWord == null) return;
                mGridViewWord.setSelectedPosition(0);
                mGridViewWord.setSelection(0);
                View firstChild = mGridViewWord.getChildAt(0);
                if (firstChild != null) {
                    firstChild.requestFocus();
                } else {
                    mGridViewWord.requestFocus();
                }
            }
        });
    }

    /**
     * 源列表按右时，把焦点交给当前可见的结果网格第一项。
     * 筛选模式走 mGridViewFilter，全部结果走 mGridView。
     */
    private void focusVisibleResultGrid() {
        final TvRecyclerView target = isFilterMode ? mGridViewFilter : mGridView;
        if (target == null || target.getVisibility() != View.VISIBLE) {
            return;
        }
        target.post(new Runnable() {
            @Override
            public void run() {
                if (isFinishing() || target.getVisibility() != View.VISIBLE) {
                    return;
                }
                View firstChild = target.getChildAt(0);
                if (firstChild != null) {
                    firstChild.requestFocus();
                } else if (target.getAdapter() != null && target.getAdapter().getItemCount() > 0) {
                    target.setSelection(0);
                    target.requestFocus();
                }
            }
        });
    }

    private void appendFilterResultsIfNeeded(List<Movie.Video> data) {
        if (!isFilterMode || TextUtils.isEmpty(searchFilterKey) || data == null || data.isEmpty()) {
            return;
        }
        List<Movie.Video> filtered = new ArrayList<>();
        for (Movie.Video video : data) {
            if (video != null && TextUtils.equals(video.sourceKey, searchFilterKey)) {
                filtered.add(video);
            }
        }
        if (filtered.isEmpty() || searchAdapterFilter == null) {
            return;
        }
        if (searchAdapterFilter.getData().size() > 0) {
            searchAdapterFilter.addData(filtered);
        } else {
            searchAdapterFilter.setNewData(filtered);
        }
    }

    private void addWordListDataIfAbsent(final String name) {
        if (TextUtils.isEmpty(name) || !wordListNames.add(name)) return;
        final int version = wordListVersion;
        updateWordListWhenIdle(new Runnable() {
            @Override
            public void run() {
                if (version != wordListVersion) return;
                List<String> names = spListAdapter.getData();
                for (int i = 0; i < names.size(); ++i) {
                    if (TextUtils.equals(name, names.get(i))) {
                        return;
                    }
                }
                spListAdapter.addData(name);
            }
        });
    }

    private void fenci() {
        if (!quickSearchWord.isEmpty()) return; // 如果经有分词了，不再进行二次分词
        quickSearchWord.addAll(SearchHelper.splitWords(searchTitle));
        List<String> words = new ArrayList<>(new HashSet<>(quickSearchWord));
        EventBus.getDefault().post(new RefreshEvent(RefreshEvent.TYPE_QUICK_SEARCH_WORD, words));
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
//                        quickSearchWord.clear();
//                        try {
//                            for (JsonElement je : new Gson().fromJson(json, JsonArray.class)) {
//                                quickSearchWord.add(je.getAsJsonObject().get("t").getAsString());
//                            }
//                        } catch (Throwable th) {
//                            th.printStackTrace();
//                        }
//                        quickSearchWord.addAll(SearchHelper.splitWords(searchTitle));
//                        List<String> words = new ArrayList<>(new HashSet<>(quickSearchWord));
//                        EventBus.getDefault().post(new RefreshEvent(RefreshEvent.TYPE_QUICK_SEARCH_WORD, words));
//                    }
//
//                    @Override
//                    public void onError(Response<String> response) {
//                        super.onError(response);
//                    }
//                });
    }

    private void initData() {
        initCheckedSourcesForSearch();
        Intent intent = getIntent();
        if (intent != null && intent.hasExtra("title")) {
            String title = intent.getStringExtra("title");
            showLoading();
            search(title);
        }
    }

    @Subscribe(threadMode = ThreadMode.MAIN)
    public void server(ServerEvent event) {
        if (event.type == ServerEvent.SERVER_SEARCH) {
            String title = (String) event.obj;
            showLoading();
            search(title);
        }
    }

    @Subscribe(threadMode = ThreadMode.MAIN)
    public void refresh(RefreshEvent event) {
        if (event.type == RefreshEvent.TYPE_SEARCH_RESULT) {
            try {
                searchData(event.obj == null ? null : (AbsXml) event.obj);
            } catch (Exception e) {
                searchData(null);
            }
        } else if (event.type == RefreshEvent.TYPE_QUICK_SEARCH_WORD) {
            if (event.obj != null) {
                List<String> data = (List<String>) event.obj;
                searchWordAdapter.setNewData(data);
            }
        }
        updateSearchStatus();
    }

    private void initCheckedSourcesForSearch() {
        mCheckSources = SearchHelper.getSourcesForSearch();
    }

    private void search(String title) {
        cancel();
        showLoading();
        this.searchTitle = title;
        fenci();
        mGridView.setVisibility(View.INVISIBLE);
        mGridViewFilter.setVisibility(View.GONE);
        searchAdapter.setNewData(new ArrayList<>());
        searchAdapterFilter.setNewData(new ArrayList<>());

        selectedWordName = "";
        filterResult(SEARCH_ALL_NAME);
        resultVods.clear();
        searchFilterKey = "";
        isFilterMode = false;
        spNames.clear();
        totalSearchCount.set(0);
        timedOutSearchCount.set(0);
        updateSearchStatus();

        //写入历史记录
        HistoryHelper.setSearchHistory(title);

        searchResult();
    }

    private ExecutorService searchExecutorService = null;
    private ScheduledExecutorService searchTimeoutExecutor = null;
    private final AtomicInteger allRunCount = new AtomicInteger(0);
    private final Set<String> pendingSearchKeys = Collections.synchronizedSet(new HashSet<String>());
    private final List<SearchTask> waitingSearchTasks = Collections.synchronizedList(new ArrayList<SearchTask>());
    private final Set<String> startedSearchKeys = Collections.synchronizedSet(new HashSet<String>());
    private final Set<String> releasedSearchKeys = Collections.synchronizedSet(new HashSet<String>());
    private final AtomicInteger searchTokenSeq = new AtomicInteger(0);
    private final AtomicInteger totalSearchCount = new AtomicInteger(0);
    private final AtomicInteger timedOutSearchCount = new AtomicInteger(0);
    private final AtomicInteger inFlightSearchCount = new AtomicInteger(0);
    private final Set<String> shownSearchKeys = Collections.synchronizedSet(new HashSet<String>());
    private String currentSearchToken = "";
    private boolean searchPaused = false;

    private void searchResult() {
        try {
            if (searchExecutorService != null) {
                searchExecutorService.shutdownNow();
                searchExecutorService = null;
                JsLoader.stopAll();
            }
            if (searchTimeoutExecutor != null) {
                searchTimeoutExecutor.shutdownNow();
                searchTimeoutExecutor = null;
            }
        } catch (Throwable th) {
            th.printStackTrace();
        } finally {
            searchAdapter.setNewData(new ArrayList<>());
            searchAdapterFilter.setNewData(new ArrayList<>());
            allRunCount.set(0);
            pendingSearchKeys.clear();
            waitingSearchTasks.clear();
            startedSearchKeys.clear();
            releasedSearchKeys.clear();
            inFlightSearchCount.set(0);
            shownSearchKeys.clear();
            currentSearchToken = String.valueOf(searchTokenSeq.incrementAndGet());
            searchPaused = false;
            totalSearchCount.set(0);
            timedOutSearchCount.set(0);
            updateSearchStatus();
        }
        List<SourceBean> searchRequestList = new ArrayList<>();
        searchRequestList.addAll(ApiConfig.get().getSourceBeanList());
        SourceBean home = ApiConfig.get().getHomeSourceBean();
        searchRequestList.remove(home);
        searchRequestList.add(0, home);


        ArrayList<SearchTask> fastSearchTasks = new ArrayList<>();
        ArrayList<SearchTask> blockingSearchTasks = new ArrayList<>();
        ArrayList<String> hots = new ArrayList<>();
        hots.add(SEARCH_ALL_NAME);

        setWordListData(hots);
        for (SourceBean bean : searchRequestList) {
            if (!bean.isSearchable()) {
                continue;
            }
            if (mCheckSources != null && !mCheckSources.containsKey(bean.getKey())) {
                continue;
            }
            SearchTask task = new SearchTask(bean.getKey(), searchTitle, currentSearchToken, isBlockingSearchSource(bean));
            if (task.blocking) {
                blockingSearchTasks.add(task);
            } else {
                fastSearchTasks.add(task);
            }
            this.spNames.put(bean.getName(), bean.getKey());
        }
        ArrayList<SearchTask> searchTasks = new ArrayList<>();
        searchTasks.addAll(fastSearchTasks);
        searchTasks.addAll(blockingSearchTasks);

        if (searchTasks.size() <= 0) {
            showEmpty();
            setSearchStatusText("\u65e0\u641c\u7d22\u6e90", "\u7ed3\u679c 0");
            return;
        }
        for (SearchTask task : searchTasks) {
            pendingSearchKeys.add(task.sourceKey);
        }
        allRunCount.set(searchTasks.size());
        totalSearchCount.set(searchTasks.size());
        updateSearchStatus();
        searchExecutorService = createSearchExecutor();
        searchTimeoutExecutor = Executors.newSingleThreadScheduledExecutor();
        waitingSearchTasks.addAll(searchTasks);
        startNextSearchBatch(currentSearchToken);
        startSearchPump(currentSearchToken);
        updateSearchStatus();
    }

    // 向过滤栏添加有结果的spname
    private String addWordAdapterIfNeed(String key) {
        try {
            String name = "";
            for (String n : spNames.keySet()) {
                if (TextUtils.equals(spNames.get(n), key)) {
                    name = n;
                }
            }
            if (TextUtils.isEmpty(name)) return key;

            addWordListDataIfAbsent(name);
            return key;
        } catch (Exception e) {
            return key;
        }
    }

    private boolean matchSearchResult(String name, String searchTitle) {
        if (TextUtils.isEmpty(name) || TextUtils.isEmpty(searchTitle)) return false;
        searchTitle = searchTitle.trim();
        String[] arr = searchTitle.split("\\s+");
        int matchNum = 0;
        for(String one : arr) {
            if (name.contains(one)) matchNum++;
        }
        return matchNum == arr.length;
    }

    private void searchData(AbsXml absXml) {
        if (!isCurrentSearchResult(absXml)) {
            return;
        }
        String sourceKey = absXml == null ? "" : absXml.sourceKey;
        boolean finished = markSearchFinished(sourceKey, absXml.searchToken);
        if (finished) {
            releaseSearchSlotAndStartNext(sourceKey, absXml.searchToken);
        }
        // 超时/取消后到的结果不丢弃，仍展示（每个源只展示一次）
        if (!TextUtils.isEmpty(sourceKey) && shownSearchKeys.add(sourceKey)) {
            String lastSourceKey = "";
            if (absXml != null && absXml.movie != null && absXml.movie.videoList != null && absXml.movie.videoList.size() > 0) {
                List<Movie.Video> data = new ArrayList<>();
                for (Movie.Video video : absXml.movie.videoList) {
                    if (!matchSearchResult(video.name, searchTitle)) continue;
                    if (data.size() >= MAX_RESULT_PER_SOURCE) break;
                    if (searchAdapter.getData().size() + data.size() >= MAX_TOTAL_RESULT) break;
                    data.add(video);
                    if (!resultVods.containsKey(video.sourceKey)) {
                        resultVods.put(video.sourceKey, new ArrayList<Movie.Video>());
                    }
                    resultVods.get(video.sourceKey).add(video);
                    if (!TextUtils.equals(video.sourceKey, lastSourceKey)) {
                        lastSourceKey = this.addWordAdapterIfNeed(video.sourceKey);
                    }
                }
                if (!data.isEmpty()) {
                    if (searchAdapter.getData().size() > 0) {
                        searchAdapter.addData(data);
                    } else {
                        showSuccess();
                        if (!isFilterMode)
                            mGridView.setVisibility(View.VISIBLE);
                        searchAdapter.setNewData(data);
                    }
                    // 当前正在看某个源时，迟到的结果也要补进右侧筛选网格
                    appendFilterResultsIfNeeded(data);
                }
            }
        }
        if (finished) {
            finishSearchIfDone();
        }
    }

    private void scheduleSearchAdvance(final String sourceKey, final String searchToken) {
        if (searchTimeoutExecutor == null) return;
        searchTimeoutExecutor.schedule(new Runnable() {
            @Override
            public void run() {
                if (!isCurrentSearchToken(searchToken)) return;
                if (isSearchPending(sourceKey, searchToken) && releaseSearchSlot(sourceKey, searchToken)) {
                    startNextSearchTask(searchToken);
                }
            }
        }, SEARCH_NEXT_BATCH_SECONDS, TimeUnit.SECONDS);
    }

    private void startSearchPump(final String searchToken) {
        if (searchTimeoutExecutor == null) return;
        searchTimeoutExecutor.scheduleWithFixedDelay(new Runnable() {
            @Override
            public void run() {
                try {
                    if (!isCurrentSearchToken(searchToken) || allRunCount.get() <= 0) return;
                    if (getWaitingSearchCount() > 0) {
                        startNextSearchBatch(searchToken);
                        updateSearchStatusOnUiThread();
                    }
                } catch (Throwable th) {
                    th.printStackTrace();
                }
            }
        }, SEARCH_PUMP_SECONDS, SEARCH_PUMP_SECONDS, TimeUnit.SECONDS);
    }

    private void updateSearchStatusOnUiThread() {
        runOnUiThread(new Runnable() {
            @Override
            public void run() {
                updateSearchStatus();
            }
        });
    }

    private void scheduleSearchTimeout(final String sourceKey, final String searchToken) {
        if (searchTimeoutExecutor == null) return;
        searchTimeoutExecutor.schedule(new Runnable() {
            @Override
            public void run() {
                if (!isCurrentSearchToken(searchToken)) return;
                if (markSearchFinished(sourceKey, searchToken)) {
                    timedOutSearchCount.incrementAndGet();
                    releaseSearchSlotAndStartNext(sourceKey, searchToken);
                    runOnUiThread(new Runnable() {
                        @Override
                        public void run() {
                            updateSearchStatus();
                            finishSearchIfDone();
                        }
                    });
                }
            }
        }, SEARCH_SITE_TIMEOUT_SECONDS, TimeUnit.SECONDS);
    }

    private boolean submitSearchTask(SearchTask task) {
        if (!isSearchPending(task.sourceKey, task.searchToken)) return false;
        if (searchExecutorService == null || searchExecutorService.isShutdown()) return false;
        try {
            searchExecutorService.execute(task);
        } catch (RejectedExecutionException e) {
            return false;
        }
        inFlightSearchCount.incrementAndGet();
        scheduleSearchAdvance(task.sourceKey, task.searchToken);
        scheduleSearchTimeout(task.sourceKey, task.searchToken);
        updateSearchStatusOnUiThread();
        return true;
    }

    private ExecutorService createSearchExecutor() {
        // LinkedBlockingQueue 保证 execute() 永不阻塞调用线程，避免线程池打满后卡死调度器
        return new ThreadPoolExecutor(SEARCH_THREAD_COUNT, SEARCH_MAX_THREAD_COUNT, 30L, TimeUnit.SECONDS, new LinkedBlockingQueue<Runnable>());
    }

    private void startNextSearchBatch(String searchToken) {
        for (int i = 0; i < SEARCH_THREAD_COUNT; i++) {
            if (!startNextSearchTask(searchToken)) {
                return;
            }
        }
    }

    private boolean startNextSearchTask(String searchToken) {
        if (!isCurrentSearchToken(searchToken)) return false;
        // 在途任务数达到并发上限时不再加塞，等待已有任务完成/超时释放槽位
        if (inFlightSearchCount.get() >= SEARCH_THREAD_COUNT) return false;
        SearchTask task = takeNextSearchTask(searchToken);
        if (task == null) {
            return false;
        }
        if (!submitSearchTask(task)) {
            startedSearchKeys.remove(task.sourceKey);
            synchronized (waitingSearchTasks) {
                waitingSearchTasks.add(0, task);
            }
            return false;
        }
        return true;
    }

    private SearchTask takeNextSearchTask(String searchToken) {
        synchronized (waitingSearchTasks) {
            while (!waitingSearchTasks.isEmpty()) {
                SearchTask task = waitingSearchTasks.remove(0);
                if (!isSearchPending(task.sourceKey, searchToken) || !startedSearchKeys.add(task.sourceKey)) {
                    continue;
                }
                return task;
            }
        }
        return null;
    }

    private void resumePausedSearches() {
        if (!searchPaused) {
            return;
        }
        searchPaused = false;
        List<String> sourceKeys = getPendingSearchKeys();
        if (sourceKeys.isEmpty()) {
            finishSearchIfDone();
            return;
        }
        currentSearchToken = String.valueOf(searchTokenSeq.incrementAndGet());
        waitingSearchTasks.clear();
        startedSearchKeys.clear();
        releasedSearchKeys.clear();
        inFlightSearchCount.set(0);
        shownSearchKeys.clear();
        for (String sourceKey : sourceKeys) {
            SourceBean bean = ApiConfig.get().getSource(sourceKey);
            waitingSearchTasks.add(new SearchTask(sourceKey, searchTitle, currentSearchToken, isBlockingSearchSource(bean)));
        }
        if (searchExecutorService == null || searchExecutorService.isShutdown()) {
            searchExecutorService = createSearchExecutor();
        }
        if (searchTimeoutExecutor == null || searchTimeoutExecutor.isShutdown()) {
            searchTimeoutExecutor = Executors.newSingleThreadScheduledExecutor();
        }
        startNextSearchBatch(currentSearchToken);
        startSearchPump(currentSearchToken);
        updateSearchStatus();
    }

    /**
     * 进入详情时只暂停未完成的源，不得清空已展示的 adapter，
     * 也不得走 search()/searchResult() 那种会 setNewData(empty) 的路径。
     */
    private void pauseSearchTasks() {
        try {
            if (searchExecutorService != null) {
                searchExecutorService.shutdownNow();
                searchExecutorService = null;
                JsLoader.stopAll();
            }
            if (searchTimeoutExecutor != null) {
                searchTimeoutExecutor.shutdownNow();
                searchTimeoutExecutor = null;
            }
            searchPaused = allRunCount.get() > 0;
            if (searchPaused) {
                cancel();
                // 作废当前 token，丢弃暂停期间迟到的回调，但保留 pendingSearchKeys 供恢复。
                currentSearchToken = "";
            }
            updateSearchStatus();
        } catch (Throwable th) {
            th.printStackTrace();
        }
    }

    private boolean isCurrentSearchResult(AbsXml absXml) {
        return absXml != null && isCurrentSearchToken(absXml.searchToken);
    }

    private boolean isCurrentSearchToken(String searchToken) {
        return !TextUtils.isEmpty(searchToken) && searchToken.equals(currentSearchToken);
    }

    /**
     * 搜索仍在进行时禁止点击结果。
     * 旧逻辑还要求两个 adapter 都为空，导致“部分结果已到、其余源仍在搜”
     * 时被当成空闲，点击后 pause 与迟到回调竞态，列表会被清空。
     */
    private boolean isSearchBusy() {
        return !searchPaused && allRunCount.get() > 0;
    }

    private boolean markSearchFinished(String sourceKey, String searchToken) {
        if (!isCurrentSearchToken(searchToken)) return false;
        synchronized (pendingSearchKeys) {
            if (TextUtils.isEmpty(sourceKey)) {
                return false;
            }
            if (!pendingSearchKeys.remove(sourceKey)) {
                return false;
            }
            allRunCount.set(pendingSearchKeys.size());
            return true;
        }
    }

    private boolean releaseSearchSlot(String sourceKey, String searchToken) {
        if (!isCurrentSearchToken(searchToken) || TextUtils.isEmpty(sourceKey)) return false;
        if (releasedSearchKeys.add(sourceKey)) {
            inFlightSearchCount.decrementAndGet();
            return true;
        }
        return false;
    }

    private void releaseSearchSlotAndStartNext(String sourceKey, String searchToken) {
        if (releaseSearchSlot(sourceKey, searchToken)) {
            startNextSearchTask(searchToken);
        }
    }

    private boolean isSearchPending(String sourceKey, String searchToken) {
        if (!isCurrentSearchToken(searchToken) || TextUtils.isEmpty(sourceKey)) return false;
        synchronized (pendingSearchKeys) {
            return pendingSearchKeys.contains(sourceKey);
        }
    }

    private boolean isBlockingSearchSource(SourceBean bean) {
        return bean == null || bean.getType() == 3;
    }

    private List<String> getPendingSearchKeys() {
        synchronized (pendingSearchKeys) {
            return new ArrayList<>(pendingSearchKeys);
        }
    }

    private int getWaitingSearchCount() {
        synchronized (waitingSearchTasks) {
            return waitingSearchTasks.size();
        }
    }

    private void finishSearchIfDone() {
        if (allRunCount.get() > 0) return;
        searchPaused = false;
        updateSearchStatus();
        if (searchAdapter.getData().size() == 0) {
            showFastSearchEmpty();
        }
        cancel();
        if (searchTimeoutExecutor != null) {
            searchTimeoutExecutor.shutdownNow();
            searchTimeoutExecutor = null;
        }
        // 回收搜索线程池，避免卡死的 JS 源线程跨搜索泄漏
        if (searchExecutorService != null) {
            searchExecutorService.shutdownNow();
            searchExecutorService = null;
            JsLoader.stopAll();
        }
    }

    private void showFastSearchEmpty() {
        final String word = searchTitle == null ? "" : searchTitle.trim();
        int timeouts = timedOutSearchCount.get();
        String body;
        if (timeouts > 0) {
            body = TextUtils.isEmpty(word)
                    ? String.format("有 %d 个来源未响应，可重试或返回修改关键词", timeouts)
                    : String.format("有 %d 个来源未响应，可重试或修改「%s」", timeouts, word);
        } else {
            body = TextUtils.isEmpty(word)
                    ? "换个关键词再试一次"
                    : String.format("换个关键词，或为「%s」搜索更多来源", word);
        }
        EmptyCallback.bind(this, "没有找到相关影片", body, "重新搜索", "返回",
                new EmptyCallback.EmptyActionListener() {
                    @Override
                    public void onPrimary() {
                        if (!TextUtils.isEmpty(word)) {
                            search(word);
                        }
                    }

                    @Override
                    public void onSecondary() {
                        finish();
                    }
                });
        showEmpty();
    }

    private int getStartedSearchCount() {
        synchronized (startedSearchKeys) {
            return startedSearchKeys.size();
        }
    }

    private int getResultCount() {
        return searchAdapter == null ? 0 : searchAdapter.getData().size();
    }

    private void updateSearchStatus() {
        if (Looper.myLooper() != Looper.getMainLooper()) {
            updateSearchStatusOnUiThread();
            return;
        }
        int total = totalSearchCount.get();
        int pending = allRunCount.get();
        int finished = Math.max(0, total - pending);
        int started = Math.min(total, getStartedSearchCount());
        int results = getResultCount();
        int timeouts = timedOutSearchCount.get();

        String firstLine;
        String secondLine;
        String progressBody = "已完成 " + finished + "/" + total + " · 找到 " + results + " 个结果";
        if (total <= 0) {
            firstLine = "准备搜索";
            secondLine = "正在读取可用来源";
        } else if (searchPaused && pending > 0) {
            firstLine = "搜索已暂停";
            secondLine = results > 0 ? "已找到 " + results + " 个结果" : "可返回后继续搜索";
        } else if (pending <= 0) {
            if (results > 0) {
                firstLine = timeouts > 0 ? "搜索完成，部分来源未响应" : "搜索完成";
            } else {
                firstLine = timeouts > 0 ? "未找到结果，部分来源未响应" : "没有找到相关影片";
            }
            secondLine = "已完成 " + total + "/" + total + " · 找到 " + results + " 个结果";
            if (timeouts > 0) {
                secondLine += " · " + timeouts + " 个来源未响应";
            }
        } else {
            firstLine = "正在搜索更多来源";
            secondLine = progressBody;
        }
        setSearchStatusText(firstLine, secondLine);
    }

    private void setSearchStatusText(String firstLine, String secondLine) {
        if (mSearchTitle == null) return;
        String text = firstLine + "\n" + secondLine;
        SpannableString span = new SpannableString(text);
        int split = firstLine.length();
        span.setSpan(new StyleSpan(Typeface.BOLD), 0, split, Spanned.SPAN_EXCLUSIVE_EXCLUSIVE);
        span.setSpan(new RelativeSizeSpan(1.05f), 0, split, Spanned.SPAN_EXCLUSIVE_EXCLUSIVE);
        span.setSpan(new RelativeSizeSpan(0.78f), split + 1, text.length(), Spanned.SPAN_EXCLUSIVE_EXCLUSIVE);
        span.setSpan(new ForegroundColorSpan(getResources().getColor(R.color.md3_on_surface_variant)), split + 1, text.length(), Spanned.SPAN_EXCLUSIVE_EXCLUSIVE);
        mSearchTitle.setText(span);
    }

    private class SearchTask implements Runnable {
        private final String sourceKey;
        private final String title;
        private final String searchToken;
        private final boolean blocking;

        private SearchTask(String sourceKey, String title, String searchToken, boolean blocking) {
            this.sourceKey = sourceKey;
            this.title = title;
            this.searchToken = searchToken;
            this.blocking = blocking;
        }

        @Override
        public void run() {
            if (!isSearchPending(sourceKey, searchToken)) return;
            try {
                sourceViewModel.getSearch(sourceKey, title, searchToken);
            } catch (Throwable th) {
                th.printStackTrace();
                if (markSearchFinished(sourceKey, searchToken)) {
                    runOnUiThread(new Runnable() {
                        @Override
                        public void run() {
                            updateSearchStatus();
                            finishSearchIfDone();
                        }
                    });
                }
            }
        }
    }

    private void cancel() {
        OkGo.getInstance().cancelTag("search");
    }

    @Override
    protected void onDestroy() {
        super.onDestroy();
        cancel();
        try {
            if (searchExecutorService != null) {
                searchExecutorService.shutdownNow();
                searchExecutorService = null;
                JsLoader.stopAll();
            }
            if (searchTimeoutExecutor != null) {
                searchTimeoutExecutor.shutdownNow();
                searchTimeoutExecutor = null;
            }
        } catch (Throwable th) {
            th.printStackTrace();
        }
        EventBus.getDefault().unregister(this);
        LoadingCallback.unbindRetry(this);
    }
}

