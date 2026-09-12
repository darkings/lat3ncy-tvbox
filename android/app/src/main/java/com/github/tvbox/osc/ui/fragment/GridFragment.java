package com.github.tvbox.osc.ui.fragment;

import android.content.Context;
import android.os.Bundle;
import android.view.LayoutInflater;
import android.view.KeyEvent;
import android.view.MotionEvent;
import android.view.View;
import android.view.ViewConfiguration;
import android.view.animation.BounceInterpolator;

import androidx.annotation.NonNull;
import androidx.annotation.Nullable;
import androidx.core.content.ContextCompat;
import androidx.lifecycle.Observer;
import androidx.lifecycle.ViewModelProvider;
import androidx.recyclerview.widget.LinearLayoutManager;
import androidx.recyclerview.widget.RecyclerView;

import com.chad.library.adapter.base.BaseQuickAdapter;
import com.github.tvbox.osc.R;
import com.github.tvbox.osc.api.ApiConfig;
import com.github.tvbox.osc.base.BaseLazyFragment;
import com.github.tvbox.osc.callback.ErrorCallback;
import com.github.tvbox.osc.callback.LoadingCallback;
import com.github.tvbox.osc.bean.AbsSortXml;
import com.github.tvbox.osc.bean.AbsXml;
import com.github.tvbox.osc.bean.Movie;
import com.github.tvbox.osc.bean.MovieSort;
import com.github.tvbox.osc.bean.SourceBean;
import com.github.tvbox.osc.event.RefreshEvent;
import com.github.tvbox.osc.ui.activity.DetailActivity;
import com.github.tvbox.osc.ui.activity.HomeActivity;
import com.github.tvbox.osc.ui.activity.FastSearchActivity;
import com.github.tvbox.osc.ui.activity.SearchActivity;
import com.github.tvbox.osc.ui.adapter.GridAdapter;
import com.github.tvbox.osc.ui.adapter.GridFilterKVAdapter;
import com.github.tvbox.osc.ui.tv.widget.LoadMoreView;
import com.github.tvbox.osc.util.FastClickCheckUtil;
import com.github.tvbox.osc.util.HawkConfig;
import com.github.tvbox.osc.util.ImgUtil;
import com.github.tvbox.osc.util.LOG;
import com.github.tvbox.osc.viewmodel.SourceViewModel;
import com.orhanobut.hawk.Hawk;
import com.owen.tvrecyclerview.widget.TvRecyclerView;
import com.owen.tvrecyclerview.widget.V7GridLayoutManager;
import com.owen.tvrecyclerview.widget.V7LinearLayoutManager;

import java.util.ArrayList;
import java.util.List;
import java.util.Stack;
import android.view.ViewGroup;
import android.widget.LinearLayout;
import android.widget.TextView;
import android.widget.Toast;

import org.greenrobot.eventbus.EventBus;
import org.json.JSONException;
import org.json.JSONObject;
import com.github.tvbox.osc.util.ToastUtil;

/**
 * @author pj567
 * @date :2020/12/21
 * @description:
 */
public class GridFragment extends BaseLazyFragment {
    private MovieSort.SortData sortData = null;
    private TvRecyclerView mGridView;
    private SourceViewModel sourceViewModel;
    private GridAdapter gridAdapter;
    private int page = 1;
    private int maxPage = 1;
    private boolean isLoad = false;
    private boolean isRequesting = false;
    private int listRequestSeq;
    private boolean hasActionItems = false;
    private boolean isTop = true;
    private View focusedView = null;
    private float pullRefreshStartX;
    private float pullRefreshStartY;
    private boolean pullRefreshStartAtTop = false;
    private boolean pullRefreshReady = false;
    private int pullRefreshThreshold = 0;
    private View loadSirView = null;

    private static class GridInfo{
        public String sortID="";
        public TvRecyclerView mGridView;
        public GridAdapter gridAdapter;
        public int page = 1;
        public int maxPage = 1;
        public boolean isLoad = false;
        public boolean hasActionItems = false;
        public View focusedView= null;
    }
    Stack<GridInfo> mGrids = new Stack<GridInfo>(); //ui栈

    public static GridFragment newInstance(MovieSort.SortData sortData) {
        return new GridFragment().setArguments(sortData);
    }

    public GridFragment setArguments(MovieSort.SortData sortData) {
        this.sortData = sortData;
        return this;
    }

    @Override
    protected int getLayoutResID() {
        return R.layout.fragment_grid;
    }

    @Override
    public void onViewCreated(@NonNull View view, @Nullable Bundle savedInstanceState) {
        super.onViewCreated(view, savedInstanceState);
        TvRecyclerView gridView = view.findViewById(R.id.mGridView);
        if (gridView != null && gridView.getLayoutManager() == null) {
            gridView.setLayoutManager(new V7LinearLayoutManager(mContext, 1, false));
        }
    }

    @Override
    protected void init() {
        initView();
        initViewModel();
        initData();
    }

    private void changeView(String id,Boolean isFolder){
        if(isFolder){
            this.sortData.flag =style==null?"1":"2"; // 修改sortData.flag
        }else {
            this.sortData.flag ="2"; // 修改sortData.flag
        }
        initView();
        this.sortData.id =id; // 修改sortData.id为新的ID
        initViewModel();
        initData();
    }
    public boolean isFolederMode(){ return (getUITag() =='1'); }
    // 获取当前页面UI的显示模式 ‘0’ 正常模式 '1' 文件夹模式 '2' 显示缩略图的文件夹模式
    public char getUITag(){
        return (sortData == null || sortData.flag == null || sortData.flag.length() ==0 || style!=null) ?  '0' : sortData.flag.charAt(0);
    }
    // 是否允许聚合搜索 sortData.flag的第二个字符为‘1’时允许聚搜
    public boolean enableFastSearch(){  return sortData.flag == null || sortData.flag.length() < 2 || (sortData.flag.charAt(1) == '1'); }
    // 保存当前页面
    private void saveCurrentView(){
        if(this.mGridView == null) return;
        GridInfo info = new GridInfo();
        info.sortID = this.sortData.id;
        info.mGridView = this.mGridView;
        info.gridAdapter = this.gridAdapter;
        info.page = this.page;
        info.maxPage = this.maxPage;
        info.isLoad = this.isLoad;
        info.hasActionItems = this.hasActionItems;
        info.focusedView = this.focusedView;
        this.mGrids.push(info);
    }
    // 丢弃当前页面，将页面还原成上一个保存的页面
    public boolean restoreView(){
        if(mGrids.empty()) return false;
        this.showSuccess();
        ((ViewGroup) mGridView.getParent()).removeView(this.mGridView); // 重父窗口移除当前控件
        GridInfo info = mGrids.pop();// 还原上次保存的控件
        this.sortData.id = info.sortID;
        this.mGridView = info.mGridView;
        this.gridAdapter = info.gridAdapter;
        this.page = info.page;
        this.maxPage = info.maxPage;
        this.isLoad = info.isLoad;
        this.hasActionItems = info.hasActionItems;
        this.focusedView = info.focusedView;
        this.mGridView.setVisibility(View.VISIBLE);
//        if(this.focusedView != null){ this.focusedView.requestFocus(); }
        if(mGridView != null) mGridView.requestFocus();
        return true;
    }

    private ImgUtil.Style style;
    // 更改当前页面
    private void createView() {
        this.saveCurrentView(); // 保存当前页面
        if(mGridView == null){ // 从layout中拿view
            mGridView = findViewById(R.id.mGridView);
        }else{ // 复制当前view
            TvRecyclerView v3 = new TvRecyclerView(this.mContext);
            v3.setSpacingWithMargins(10,10);
            v3.setLayoutParams(mGridView.getLayoutParams());
            v3.setPadding(mGridView.getPaddingLeft(), mGridView.getPaddingTop(), mGridView.getPaddingRight(), mGridView.getPaddingBottom());
            v3.setClipToPadding(mGridView.getClipToPadding());
            ((ViewGroup) mGridView.getParent()).addView(v3);
            mGridView.setVisibility(View.GONE);
            mGridView = v3;
            mGridView.setVisibility(View.VISIBLE);
        }
        mGridView.setHasFixedSize(true);
        style=ImgUtil.initStyle();
        gridAdapter = new GridAdapter(isFolederMode(), style);
        this.page =1;
        this.maxPage =1;
        this.isLoad = false;
    }

    private void initView() {
        this.createView();
        if(isFolederMode()){
            mGridView.setLayoutManager(new V7LinearLayoutManager(this.mContext, 1, false));
        }else{
        // Ponyo TV 的海报页保持固定五列；在 720p/1080p/4K 上都要让首末列完整可见。
        // 原先按 isBaseOnWidth() 切到六列时，720p 会露出第六张半卡并裁切焦点边界。
        int spanCount = 5;
            if (spanCount == 1) {
                mGridView.setLayoutManager(new V7LinearLayoutManager(mContext, spanCount, false));
            } else {
                mGridView.setLayoutManager(new V7GridLayoutManager(mContext, spanCount));
            }
        }
        mGridView.setAdapter(gridAdapter);

        gridAdapter.setOnLoadMoreListener(new BaseQuickAdapter.RequestLoadMoreListener() {
            @Override
            public void onLoadMoreRequested() {
                gridAdapter.setEnableLoadMore(true);
                listRequestSeq = sourceViewModel.getList(sortData, page);
            }
        }, mGridView);
        mGridView.setOnItemListener(new TvRecyclerView.OnItemListener() {
            @Override
            public void onItemPreSelected(TvRecyclerView parent, View itemView, int position) {
                itemView.animate().scaleX(1.0f).scaleY(1.0f).setDuration(300).setInterpolator(new BounceInterpolator()).start();
            }

            @Override
            public void onItemSelected(TvRecyclerView parent, View itemView, int position) {
                itemView.animate().scaleX(1.05f).scaleY(1.05f).setDuration(300).setInterpolator(new BounceInterpolator()).start();
            }

            @Override
            public void onItemClick(TvRecyclerView parent, View itemView, int position) {

            }
        });
        mGridView.setOnInBorderKeyEventListener(new TvRecyclerView.OnInBorderKeyEventListener() {
            @Override
            public boolean onInBorderKeyEvent(int direction, View focused) {
                if (direction == View.FOCUS_UP) {
                }
                return false;
            }
        });
        gridAdapter.setOnItemClickListener(new BaseQuickAdapter.OnItemClickListener() {
            @Override
            public void onItemClick(BaseQuickAdapter adapter, View view, int position) {
                FastClickCheckUtil.check(view);
                Movie.Video video = gridAdapter.getData().get(position);
                if (video != null) {
                    if (video.action != null) {
                        sourceViewModel.action(video.sourceKey, video.action);
                        return;
                    }
                    Bundle bundle = new Bundle();
                    bundle.putString("id", video.id);
                    bundle.putString("sourceKey", video.sourceKey);
                    bundle.putString("title", video.name);
                    if( video.tag !=null && (video.tag.equals("folder") || video.tag.equals("cover"))){
                        focusedView = view;
                        if(("12".indexOf(getUITag()) != -1)){
                            changeView(video.id,video.tag.equals("folder"));
                        }else {
                            changeView(video.id,false);
                        }
                    }
                    else{
                        if(video.id == null || video.id.isEmpty() || video.id.startsWith("msearch:")){
                            if(Hawk.get(HawkConfig.FAST_SEARCH_MODE, true) && enableFastSearch()){
                                jumpActivity(FastSearchActivity.class, bundle);
                            }else {
                                jumpActivity(SearchActivity.class, bundle);
                            }
                        }else {
                            bundle.putString("picture", video.pic);
                            jumpActivity(DetailActivity.class, bundle);
                        }
                    }

                }
            }
        });
        gridAdapter.setOnItemLongClickListener(new BaseQuickAdapter.OnItemLongClickListener() {
            @Override
            public boolean onItemLongClick(BaseQuickAdapter adapter, View view, int position) {
                FastClickCheckUtil.check(view);
                Movie.Video video = gridAdapter.getData().get(position);
                if (video != null) {
                    Bundle bundle = new Bundle();
                    bundle.putString("id", video.id);
                    bundle.putString("sourceKey", video.sourceKey);
                    bundle.putString("title", video.name);
                    jumpActivity(FastSearchActivity.class, bundle);
                }
                return true;
            }
        });
        gridAdapter.setLoadMoreView(new LoadMoreView());
        setLoadSir2(mGridView);
        initPullRefresh();
    }

    private void initPullRefresh() {
        pullRefreshThreshold = ViewConfiguration.get(mContext).getScaledTouchSlop() * 6;
        mGridView.addOnItemTouchListener(new RecyclerView.OnItemTouchListener() {
            @Override
            public boolean onInterceptTouchEvent(@NonNull RecyclerView rv, @NonNull MotionEvent event) {
                return handlePullRefreshTouch(rv, event);
            }

            @Override
            public void onTouchEvent(@NonNull RecyclerView rv, @NonNull MotionEvent event) {
            }

            @Override
            public void onRequestDisallowInterceptTouchEvent(boolean disallowIntercept) {
            }
        });
        loadSirView = (View) mGridView.getParent();
        if (loadSirView != null) {
            loadSirView.setOnTouchListener(new View.OnTouchListener() {
                @Override
                public boolean onTouch(View v, MotionEvent event) {
                    return handlePullRefreshTouch(v, event);
                }
            });
        }
    }

    private void bindPullRefreshTouch(View view) {
        if (view == null || view == mGridView) return;
        view.setOnTouchListener(new View.OnTouchListener() {
            @Override
            public boolean onTouch(View v, MotionEvent event) {
                return handlePullRefreshTouch(v, event);
            }
        });
        if (view instanceof ViewGroup) {
            ViewGroup group = (ViewGroup) view;
            for (int i = 0; i < group.getChildCount(); i++) {
                bindPullRefreshTouch(group.getChildAt(i));
            }
        }
    }

    private boolean handlePullRefreshTouch(View view, MotionEvent event) {
        switch (event.getActionMasked()) {
            case MotionEvent.ACTION_DOWN:
                pullRefreshStartX = event.getX();
                pullRefreshStartY = event.getY();
                pullRefreshStartAtTop = !view.canScrollVertically(-1);
                pullRefreshReady = false;
                break;
            case MotionEvent.ACTION_MOVE:
                float diffX = Math.abs(event.getX() - pullRefreshStartX);
                float diffY = event.getY() - pullRefreshStartY;
                pullRefreshReady = pullRefreshStartAtTop && diffY > pullRefreshThreshold && diffY > diffX;
                break;
            case MotionEvent.ACTION_UP:
                if (pullRefreshReady) {
                    pullRefreshReady = false;
                    forceRefresh();
                    return true;
                }
                break;
            case MotionEvent.ACTION_CANCEL:
                pullRefreshReady = false;
                break;
        }
        return false;
    }

    @Override
    protected void showEmpty() {
        super.showEmpty();
        bindPullRefreshTouch(loadSirView);
    }

    private void initViewModel() {
        if(sourceViewModel != null) { return;}
        sourceViewModel = new ViewModelProvider(this).get(SourceViewModel.class);
        sourceViewModel.listResult.observe(this, new Observer<AbsXml>() {
            @Override
            public void onChanged(AbsXml absXml) {
                if (absXml != null && absXml.requestSeq != 0 && absXml.requestSeq != listRequestSeq) {
                    LOG.i("echo-list ignore stale result seq=" + absXml.requestSeq + " current=" + listRequestSeq);
                    return;
                }
                isRequesting = false;
                if (absXml != null && absXml.movie != null && absXml.movie.videoList != null && absXml.movie.videoList.size() > 0) {
                    if (page == 1) {
                        showSuccess();
                        isLoad = true;
                        hasActionItems = hasActionVideo(absXml.movie.videoList);
                        gridAdapter.setNewData(absXml.movie.videoList);
                    } else {
                        hasActionItems = hasActionItems || hasActionVideo(absXml.movie.videoList);
                        gridAdapter.addData(absXml.movie.videoList);
                    }
                    page++;
                    maxPage = absXml.movie.pagecount;
                    if (maxPage>0 && page > maxPage) {
                        gridAdapter.loadMoreEnd();
                        gridAdapter.setEnableLoadMore(false);
                        if(page>2)ToastUtil.error(getContext(), "没有更多了");
                    }else {
                        gridAdapter.loadMoreComplete();
                        gridAdapter.setEnableLoadMore(true);
                    }
                } else {
                    if (page == 1) {
                        boolean keepOldList = gridAdapter != null && gridAdapter.getData() != null && !gridAdapter.getData().isEmpty();
                        if (absXml != null && absXml.failed && keepOldList) {
                            showSuccess();
                            ToastUtil.error(getContext(), "筛选结果加载失败，已保留当前列表");
                            gridAdapter.loadMoreComplete();
                            gridAdapter.setEnableLoadMore(true);
                            return;
                        }
                        hasActionItems = false;
                        if (absXml == null || absXml.failed) {
                            showErrorState();
                        } else {
                            showEmpty();
                        }
                    } else if (absXml != null && absXml.failed) {
                        ToastUtil.error(getContext(), "加载失败，请稍后重试");
                        gridAdapter.loadMoreComplete();
                        gridAdapter.setEnableLoadMore(true);
                        return;
                    } else if(page > 2){// 只有一页数据时不提示
                        ToastUtil.error(getContext(), "没有更多了");
                    }
                    gridAdapter.loadMoreEnd();
                    gridAdapter.setEnableLoadMore(false);
                }
            }
        });
        sourceViewModel.sortError.observe(this, new Observer<AbsSortXml>() {
            @Override
            public void onChanged(AbsSortXml failed) {
                SourceBean home = ApiConfig.get().getHomeSourceBean();
                if (failed == null || home == null || failed.sourceKey == null || !failed.sourceKey.equals(home.getKey())) {
                    return;
                }
                isRequesting = false;
                if (page == 1) {
                    showErrorState();
                }
            }
        });
        sourceViewModel.actionResult.observe(this, new Observer<JSONObject>() {
            @Override
            public void onChanged(JSONObject jsonObject) {
                if (jsonObject == null) return;
                String msg = jsonObject.optString("msg");
                if (!msg.isEmpty()) {
                    ToastUtil.info(getContext(), msg);
                    forceRefresh();
                }
            }
        });
    }

    public boolean isLoad() {
        return isLoad || !mGrids.empty(); //如果有缓存页的话也可以认为是加载了数据的
    }

    public boolean shouldReloadOnSelect() {
        return !isRequesting && mGrids.empty() && (hasActionItems || !isLoad);
    }

    private void initData() {
        LoadingCallback.bindRetry(this, this::forceRefresh);
        boolean keepVisibleList = page == 1
                && gridAdapter != null
                && gridAdapter.getData() != null
                && !gridAdapter.getData().isEmpty();
        if (!keepVisibleList) {
            showLoading();
        }
        isRequesting = true;
        isLoad = false;
        hasActionItems = false;
        scrollTop();
        toggleFilterColor();
        listRequestSeq = sourceViewModel.getList(sortData, page);
    }

    @Override
    public void onDestroyView() {
        LoadingCallback.unbindRetry(this);
        super.onDestroyView();
    }

    private boolean hasActionVideo(List<Movie.Video> videos) {
        if (videos == null) return false;
        for (Movie.Video video : videos) {
            if (video != null && video.action != null) return true;
        }
        return false;
    }

    public void toggleFilterColor() {
        if (sortData!=null && sortData.filters != null && !sortData.filters.isEmpty()) {
            int count = sortData.filterSelectCount();
            EventBus.getDefault().post(new RefreshEvent(RefreshEvent.TYPE_FILTER_CHANGE, count));
        }
    }

    public boolean isTop() {
        return isTop;
    }

    public void scrollTop() {
        isTop = true;
        if (mGridView == null) return;
        mGridView.scrollToPosition(0);
    }

    // 筛选面板展开/收起状态监听（用于 tab 图标切换等）
    public MovieSort.SortData getSortData() {
        return sortData;
    }

    public void showFilter() {
        if (getActivity() instanceof HomeActivity) {
            ((HomeActivity) getActivity()).showFilterPanel(this);
        }
    }

    private void showErrorState() {
        ErrorCallback.bind(getContext(), "内容加载失败", "当前来源暂时不可用", "重试", "更换来源", "",
                new ErrorCallback.ErrorActionListener() {
                    @Override
                    public void onPrimary() {
                        forceRefresh();
                    }

                    @Override
                    public void onSecondary() {
                        if (getActivity() instanceof HomeActivity) {
                            ((HomeActivity) getActivity()).showSiteSwitch();
                        }
                    }
                });
        showError();
    }

    public void forceRefresh() {
        if (mGridView == null || gridAdapter == null || sourceViewModel == null) return;
        page = 1;
        initData();
    }

    /**
     * 筛选选中后刷新列表。已有海报时 initData() 不会盖 Loading，避免看起来像“点了没反应”。
     */
    public void refreshForFilter() {
        forceRefresh();
    }
}
