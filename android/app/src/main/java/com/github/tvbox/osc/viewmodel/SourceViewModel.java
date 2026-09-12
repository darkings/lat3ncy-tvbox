package com.github.tvbox.osc.viewmodel;

import android.text.TextUtils;

import android.util.Base64;
import android.os.Handler;
import android.os.Looper;

import androidx.annotation.NonNull;
import androidx.lifecycle.MutableLiveData;
import androidx.lifecycle.ViewModel;

import com.github.catvod.net.OkHttp;
import com.github.catvod.crawler.Spider;
import com.github.tvbox.osc.api.ApiConfig;
import com.github.tvbox.osc.base.App;
import com.github.tvbox.osc.bean.AbsJson;
import com.github.tvbox.osc.bean.AbsSortJson;
import com.github.tvbox.osc.bean.AbsSortXml;
import com.github.tvbox.osc.bean.AbsXml;
import com.github.tvbox.osc.bean.Movie;
import com.github.tvbox.osc.bean.MovieSort;
import com.github.tvbox.osc.bean.SourceBean;
import com.github.tvbox.osc.event.RefreshEvent;
import com.github.tvbox.osc.player.thirdparty.RemoteTVBox;
import com.github.tvbox.osc.util.DefaultConfig;
import com.github.tvbox.osc.util.FileUtils;
import com.github.tvbox.osc.util.HawkConfig;
import com.github.tvbox.osc.util.LOG;
import com.github.tvbox.osc.util.MD5;
import com.github.tvbox.osc.util.thunder.Thunder;
import com.google.gson.Gson;
import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import com.google.gson.reflect.TypeToken;
import com.lzy.okgo.OkGo;
import com.lzy.okgo.callback.AbsCallback;
import com.lzy.okgo.model.Response;
import com.lzy.okgo.request.GetRequest;
import com.orhanobut.hawk.Hawk;
import com.thoughtworks.xstream.XStream;
import com.thoughtworks.xstream.io.xml.DomDriver;

import org.greenrobot.eventbus.EventBus;
import org.json.JSONArray;
import org.json.JSONObject;


import java.io.IOException;

import java.io.UnsupportedEncodingException;
import java.net.URLDecoder;
import java.net.URLEncoder;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.Iterator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.Callable;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicInteger;

import okhttp3.Call;

/**
 * @author pj567
 * @date :2020/12/18
 * @description:
 */
public class SourceViewModel extends ViewModel {
    private static final String PUSH_AGENT = "push_agent";
    private static final String PUSH_FALLBACK = "push_fallback";
    private static final String PUSH_HEADERS_MARKER = "@Headers=";

    public MutableLiveData<AbsSortXml> sortResult;
    /** Non-null 表示最近一次分类请求失败，携带 sourceKey / requestSeq。 */
    public MutableLiveData<AbsSortXml> sortError;
    public MutableLiveData<AbsXml> listResult;
    public MutableLiveData<AbsXml> searchResult;
    public MutableLiveData<AbsXml> quickSearchResult;
    public MutableLiveData<AbsXml> detailResult;
    public MutableLiveData<JSONObject> actionResult;
    public MutableLiveData<JSONObject> playResult;
    public Gson gson;
    private final Handler mainHandler = new Handler(Looper.getMainLooper());
    private final AtomicInteger playRequestSeq = new AtomicInteger();
    private final AtomicInteger detailRequestSeq = new AtomicInteger();
    private final AtomicInteger listRequestSeq = new AtomicInteger();
    private final AtomicInteger sortRequestSeq = new AtomicInteger();
    private String lastSortTag;

    public SourceViewModel() {
        sortResult = new MutableLiveData<>();
        sortError = new MutableLiveData<>();
        listResult = new MutableLiveData<>();
        searchResult = new MutableLiveData<>();
        quickSearchResult = new MutableLiveData<>();
        detailResult = new MutableLiveData<>();
        actionResult = new MutableLiveData<>();
        playResult = new MutableLiveData<>();
        gson=new Gson();
    }

    public static final ExecutorService spThreadPool = Executors.newSingleThreadExecutor();
    private static final ExecutorService httpPrepareThreadPool = Executors.newFixedThreadPool(3);

    // 豆瓣源缓存时间戳: 1小时内复用, 超时重新拉取
    private static final long DOUBAN_CACHE_TTL_MS = 60L * 60L * 1000L;
    private static final ConcurrentHashMap<String, Long> sortCacheTime = new ConcurrentHashMap<>();

    //homeContent缓存，最多存储20个sourceKey的AbsSortXml对象
    private static final Map<String, AbsSortXml> sortCache = new LinkedHashMap<String, AbsSortXml>(20, 0.75f, true) {
        @Override
        protected boolean removeEldestEntry(Entry<String, AbsSortXml> eldest) {
            boolean evict = size() > 20;
            if (evict && eldest != null) {
                sortCacheTime.remove(eldest.getKey());
            }
            return evict;
        }
    };

    private static void cacheSort(String sourceKey, AbsSortXml sortXml) {
        attachSortSource(sourceKey, sortXml);
        // 有分类即可缓存; 推荐视频可空, 避免 HOME_REC=1 时源永远不进缓存导致切回重拉
        if (sortXml == null || sortXml.classes == null || sortXml.classes.sortList == null || sortXml.classes.sortList.isEmpty()) {
            return;
        }
        if (hasActionSort(sortXml)) {
            return;
        }
        synchronized (sortCache) {
            sortCache.put(sourceKey, sortXml);
        }
        sortCacheTime.put(sourceKey, System.currentTimeMillis());
        LOG.i("echo-sort-cache-put source:" + sourceKey + " size:" + sortCache.size());
    }

    public static void clearSortCache(String sourceKey) {
        synchronized (sortCache) {
            sortCache.remove(sourceKey);
        }
        sortCacheTime.remove(sourceKey);
        LOG.i("echo-sort-cache-clear source:" + sourceKey);
    }

    public static void clearRuntimeCache() {
        synchronized (sortCache) {
            sortCache.clear();
        }
        sortCacheTime.clear();
        extendCache.clear();
        LOG.i("echo-sort-cache-clear-all");
    }

    private static AbsSortXml attachSortSource(String sourceKey, AbsSortXml sortXml) {
        if (sortXml != null) {
            sortXml.sourceKey = sourceKey;
        }
        return sortXml;
    }

    private void postSortResult(String sourceKey, AbsSortXml sortXml, int requestSeq) {
        if (sortXml == null) {
            // 失败只发 sortError，由 HomeActivity 显示错误并回退上一源；
            // 不再 post 空 AbsSortXml，避免 sortResult 观察者把空结果当有效结果
            // 重建成「只有主页」的分类栏。
            AbsSortXml failed = new AbsSortXml();
            failed.sourceKey = sourceKey;
            failed.requestSeq = requestSeq;
            failed.failed = true;
            sortError.postValue(failed);
            return;
        }
        sortXml.requestSeq = requestSeq;
        sortXml.failed = false;
        sortError.postValue(null);
        sortResult.postValue(attachSortSource(sourceKey, sortXml));
    }

    private static boolean hasActionSort(AbsSortXml sortXml) {
        if (sortXml == null) return false;
        if (hasActionVideo(sortXml.videoList)) return true;
        return sortXml.list != null && hasActionVideo(sortXml.list.videoList);
    }

    private static boolean hasHomeRecVideos(AbsSortXml sortXml) {
        return sortXml != null && sortXml.videoList != null && !sortXml.videoList.isEmpty();
    }

    private static boolean hasActionVideo(List<Movie.Video> videos) {
        if (videos == null) return false;
        for (Movie.Video video : videos) {
            if (video != null && video.action != null) return true;
        }
        return false;
    }

    /** 豆瓣源超过 1 小时才视为过期, 其它源不过期。 */
    private static boolean isSortCacheExpired(String sourceKey, SourceBean sourceBean) {
        if (!isDoubanSource(sourceBean)) {
            return false;
        }
        Long cachedAt = sortCacheTime.get(sourceKey);
        if (cachedAt == null) {
            return true;
        }
        return System.currentTimeMillis() - cachedAt > DOUBAN_CACHE_TTL_MS;
    }

    private static boolean isFirstSource(String sourceKey) {
        List<SourceBean> sources = ApiConfig.get().getSourceBeanList();
        return !sources.isEmpty() && sources.get(0) != null && sourceKey.equals(sources.get(0).getKey());
    }

    private static boolean isDoubanSource(SourceBean sourceBean) {
        if (sourceBean == null) return false;
        return containsDouban(sourceBean.getKey())
                || containsDouban(sourceBean.getName())
                || containsDouban(sourceBean.getApi())
                || containsDouban(sourceBean.getExt());
    }

    private static boolean containsDouban(String value) {
        if (TextUtils.isEmpty(value)) return false;
        String lower = value.toLowerCase();
        return lower.contains("douban") || value.contains("\u8c46\u74e3");
    }


    // homeContent
    public int getSort(final String sourceKey) {
        final int requestSeq = sortRequestSeq.incrementAndGet();
        if (!TextUtils.isEmpty(lastSortTag)) {
            OkGo.getInstance().cancelTag(lastSortTag);
            lastSortTag = null;
        }
        sortError.postValue(null);
        if (sourceKey == null) {
            postSortResult(null, null, requestSeq);
            return requestSeq;
        }

        // 优先检查缓存
        SourceBean sourceBean = ApiConfig.get().getSource(sourceKey);
        if (sourceBean == null) {
            LOG.i("echo--getSort-source-null--" + sourceKey);
            postSortResult(sourceKey, null, requestSeq);
            return requestSeq;
        }
        if(sourceBean.getName().length()<=3 && sourceBean.getName().endsWith("搜")){
            postSortResult(sourceKey, null, requestSeq);
            return requestSeq;
        }

        AbsSortXml cached;
        synchronized (sortCache) {
            cached = sortCache.get(sourceKey);
        }
        // 空分类缓存不命中（旧版无 ac=list 参数时缓存的空结果），重新请求
        if (cached != null && cached.classes != null && cached.classes.sortList != null
                && !cached.classes.sortList.isEmpty()
                && !isSortCacheExpired(sourceKey, sourceBean)) {
            LOG.i("echo-sort-cache-hit source:" + sourceKey);
            attachSortSource(sourceKey, cached);
            postSortResult(sourceKey, cached, requestSeq);
            return requestSeq;
        }
        if (cached != null) {
            LOG.i("echo-sort-cache-miss-expired source:" + sourceKey);
        }

        LOG.i("echo-sort-fetch source:" + sourceKey);
        final int type = sourceBean.getType();
        if (type == 3) {
            Runnable waitResponse = new Runnable() {
                @Override
                public void run() {
                    ExecutorService executor = Executors.newSingleThreadExecutor();
                    Future<String> future = executor.submit(new Callable<String>() {
                        @Override
                        public String call() throws Exception {
                            Spider sp = ApiConfig.get().getCSP(sourceBean);
                            String json = sp.homeContent(true);
//                            LOG.i("echo--getSort :" + json);
                            return json;
                        }
                    });
                    String sortJson = null;
                    try {
                        sortJson = future.get(30, TimeUnit.SECONDS);
                    } catch (TimeoutException e) {
                        LOG.i("echo--getSort-timeout--" + sourceBean.getKey());
                        e.printStackTrace();
                        future.cancel(true);
                    } catch (InterruptedException | ExecutionException e) {
                        Throwable cause = e.getCause();
                        LOG.i("echo--getSort-error--" + sourceBean.getKey() + "--" + e.getClass().getSimpleName() + "--" + (cause != null ? cause.getClass().getSimpleName() + ":" + cause.getMessage() : e.getMessage()));
                        e.printStackTrace();
                    } finally {
                        if (sortJson != null) {
                            final AbsSortXml sortXml = sortJson(sortResult, sortJson);
                            attachSortSource(sourceKey, sortXml);
                            if (sortXml != null && Hawk.get(HawkConfig.HOME_REC, HawkConfig.DEFAULT_HOME_REC) == 1) {
                                AbsXml absXml = json(null, sortJson, sourceBean.getKey());
                                if (absXml != null && absXml.movie != null && absXml.movie.videoList != null && absXml.movie.videoList.size() > 0) {
                                    sortXml.videoList = absXml.movie.videoList;
                                    postSortResult(sourceKey, sortXml, requestSeq);
                                    cacheSort(sourceKey, sortXml);
                                } else {
                                    getHomeRecList(sourceBean, null, new HomeRecCallback() {
                                        @Override
                                        public void done(List<Movie.Video> videos) {
                                            sortXml.videoList = videos;
                                            postSortResult(sourceKey, sortXml, requestSeq);
                                            cacheSort(sourceKey, sortXml);
                                        }
                                    });
                                }
                            } else {
                                            postSortResult(sourceKey, sortXml, requestSeq);
                                cacheSort(sourceKey, sortXml);
                            }
                        } else {
                            postSortResult(sourceKey, null, requestSeq);
                        }
                        try {
                            executor.shutdown();
                        } catch (Throwable th) {
                            th.printStackTrace();
                        }
                    }
                }
            };
            httpPrepareThreadPool.execute(waitResponse);
        } else if (type == 0 || type == 1 || type == 2) {
            // macCMS：无参数默认只返回全部列表（无 class）；ac=list 同时返回分类与首页推荐
            // type=2 在部分订阅里被写成 JSON CMS（例如「暴风资源」），按 type=1 处理
            LOG.i("echo--getSort-req--" + sourceKey + "--type=" + type + "--" + sourceBean.getApi());
            lastSortTag = sourceBean.getKey() + "_sort";
            OkGo.<String>get(sourceBean.getApi())
                    .tag(lastSortTag)
                    .params("ac", "list")
                    .execute(new AbsCallback<String>() {
                        @Override
                        public String convertResponse(okhttp3.Response response) throws Throwable {
                            if (response.body() != null) {
                                return response.body().string();
                            } else {
                                throw new IllegalStateException("网络请求错误");
                            }
                        }

                        @Override
                        public void onSuccess(Response<String> response) {
                            AbsSortXml sortXml = null;
                            String body = response.body();
                            LOG.i("echo--getSort-body--" + sourceKey + "--len=" + (body == null ? "null" : String.valueOf(body.length()))
                                    + "--classIdx=" + (body == null ? "-1" : String.valueOf(body.indexOf("\"class\"")))
                                    + "--" + (body == null ? "null" : body.substring(0, Math.min(120, body.length()))));
                            if (type == 0) {
                                // 修复: macCMS type=0 源(如非凡/天堂)实际返回 JSON, 不能一律按 XML 解析;
                                // 按响应首字符嗅探: "{" 走 JSON, "<" 走 XML, 避免误判为"源失效"
                                String body0 = body == null ? "" : body.trim();
                                if (body0.startsWith("{")) {
                                    sortXml = sortJson(sortResult, body);
                                } else {
                                    sortXml = sortXml(sortResult, body);
                                }
                            } else {
                                // type=1 JSON CMS；type=2 在部分订阅里也被写成同一套接口
                                sortXml = sortJson(sortResult, body);
                            }
                            LOG.i("echo--getSort-ok--" + sourceKey + "--classes="
                                    + (sortXml == null ? "null" : (sortXml.classes == null || sortXml.classes.sortList == null
                                            ? "null-classes" : String.valueOf(sortXml.classes.sortList.size()))));
                            attachSortSource(sourceKey, sortXml);
                            if (sortXml != null && Hawk.get(HawkConfig.HOME_REC, HawkConfig.DEFAULT_HOME_REC) == 1 && sortXml.list != null && sortXml.list.videoList != null && sortXml.list.videoList.size() > 0) {
                                ArrayList<String> ids = new ArrayList<>();
                                for (Movie.Video vod : sortXml.list.videoList) {
                                    ids.add(vod.id);
                                }
                                final AbsSortXml finalSortXml = sortXml;
                                getHomeRecList(sourceBean, ids, new HomeRecCallback() {
                                    @Override
                                    public void done(List<Movie.Video> videos) {
                                        finalSortXml.videoList = videos;
                                        postSortResult(sourceKey, finalSortXml, requestSeq);
                                        cacheSort(sourceKey, finalSortXml);
                                    }
                                });
                            } else {
                                            postSortResult(sourceKey, sortXml, requestSeq);
                                cacheSort(sourceKey, sortXml);
                            }
                        }

                        @Override
                        public void onError(Response<String> response) {
                            super.onError(response);
                            LOG.i("echo--getSort-err--" + sourceKey + "--" + (response == null ? "null" : String.valueOf(response.code())));
                            postSortResult(sourceKey, null, requestSeq);
                        }
                    });
        }else if (type == 4) {
            String extend=sourceBean.getExt();
            extend=getFixUrl(extend);
            if(URLEncoder.encode(extend).length()<1000){
                lastSortTag = sourceBean.getKey() + "_sort";
                GetRequest<String> request = OkGo.<String>get(sourceBean.getApi())
                        .tag(lastSortTag)
                        .params("filter", "true");
                // 当 extend 不为空且非空字符串时添加参数
                if (extend != null && !extend.isEmpty()) {
                    request.params("extend", extend);
                }
                request.execute(new AbsCallback<String>() {
                            @Override
                            public String convertResponse(okhttp3.Response response) throws Throwable {
                                if (response.body() != null) {
                                    return response.body().string();
                                } else {
                                    throw new IllegalStateException("网络请求错误");
                                }
                            }

                            @Override
                            public void onSuccess(Response<String> response) {
                                String sortJson  = response.body();
                                if (sortJson != null) {
                                    final AbsSortXml sortXml = sortJson(sortResult, sortJson);
                                    attachSortSource(sourceKey, sortXml);
                                    if (sortXml != null && Hawk.get(HawkConfig.HOME_REC, HawkConfig.DEFAULT_HOME_REC) == 1) {
                                        AbsXml absXml = json(null, sortJson, sourceBean.getKey());
                                        if (absXml != null && absXml.movie != null && absXml.movie.videoList != null && absXml.movie.videoList.size() > 0) {
                                            sortXml.videoList = absXml.movie.videoList;
                                            postSortResult(sourceKey, sortXml, requestSeq);
                                            cacheSort(sourceKey, sortXml);
                                        } else {
                                            getHomeRecList(sourceBean, null, new HomeRecCallback() {
                                                @Override
                                                public void done(List<Movie.Video> videos) {
                                                    sortXml.videoList = videos;
                                                    postSortResult(sourceKey, sortXml, requestSeq);
                                                    cacheSort(sourceKey, sortXml);
                                                }
                                            });
                                        }
                                    } else {
                                        postSortResult(sourceKey, sortXml, requestSeq);
                                        cacheSort(sourceKey, sortXml);
                                    }
                                } else {
                                    postSortResult(sourceKey, null, requestSeq);
                                }
                            }

                            @Override
                            public void onError(Response<String> response) {
                                super.onError(response);
                                postSortResult(sourceKey, null, requestSeq);
                            }
                        });
            }else {
                try {
                    Map<String, String> params = new HashMap<>();
                    params.put("filter","true");
                    if (extend != null && !extend.isEmpty()) {
                        params.put("extend",extend);
                    }
                    RemoteTVBox.post(sourceBean.getApi(), params, new okhttp3.Callback() {
                        @Override
                        public void onFailure(@NonNull Call call, IOException e) {
                            postSortResult(sourceKey, null, requestSeq);
                        }

                        @Override
                        public void onResponse(@NonNull Call call, @NonNull okhttp3.Response response) throws IOException {
                            assert response.body() != null;
                            String sortJson = response.body().string();
                            final AbsSortXml sortXml = sortJson(sortResult, sortJson);
                            attachSortSource(sourceKey, sortXml);
                            if (sortXml != null && Hawk.get(HawkConfig.HOME_REC, HawkConfig.DEFAULT_HOME_REC) == 1) {
                                AbsXml absXml = json(null, sortJson, sourceBean.getKey());
                                if (absXml != null && absXml.movie != null && absXml.movie.videoList != null && absXml.movie.videoList.size() > 0) {
                                    sortXml.videoList = absXml.movie.videoList;
                                    postSortResult(sourceKey, sortXml, requestSeq);
                                    cacheSort(sourceKey, sortXml);
                                } else {
                                    getHomeRecList(sourceBean, null, new HomeRecCallback() {
                                        @Override
                                        public void done(List<Movie.Video> videos) {
                                            sortXml.videoList = videos;
                                            postSortResult(sourceKey, sortXml, requestSeq);
                                            cacheSort(sourceKey, sortXml);
                                        }
                                    });
                                }
                            } else {
                                postSortResult(sourceKey, sortXml, requestSeq);
                                cacheSort(sourceKey, sortXml);
                            }
                        }
                    });
                } catch (Exception ignored) {
                    postSortResult(sourceKey, null, requestSeq);
                }
            }
        } else {
            postSortResult(sourceKey, null, requestSeq);
        }
        return requestSeq;
    }
    // categoryContent
    public int getList(MovieSort.SortData sortData, int page) {
        final int requestSeq = listRequestSeq.incrementAndGet();
        if (sortData == null) {
            LOG.i("echo-getList-sortData-null");
            listResult.postValue(createFailedXml(null, requestSeq));
            return requestSeq;
        }
        SourceBean homeSourceBean = ApiConfig.get().getHomeSourceBean();
        if (homeSourceBean == null) {
            listResult.postValue(createFailedXml(null, requestSeq));
            return requestSeq;
        }
        if (!TextUtils.isEmpty(homeSourceBean.getApi())) {
            OkGo.getInstance().cancelTag(homeSourceBean.getApi());
        }
        int type = homeSourceBean.getType();
        if (type == 3) {
            spThreadPool.execute(new Runnable() {
                @Override
                public void run() {
                    ExecutorService executor = Executors.newSingleThreadExecutor();
                    Future<String> future = executor.submit(new Callable<String>() {
                        @Override
                        public String call() throws Exception {
                            Spider sp = ApiConfig.get().getCSP(homeSourceBean);
                            return sp.categoryContent(sortData.id, page + "", true, sortData.filterSelect);
                        }
                    });
                    String json = null;
                    try {
                        json = future.get(homeSourceBean.getPlayTimeoutSeconds(), TimeUnit.SECONDS);
//                        LOG.i("echo-categoryContent:"+json);
                    } catch (TimeoutException e) {
                        LOG.i("echo--getList-timeout--" + homeSourceBean.getKey());
                        e.printStackTrace();
                        future.cancel(true);
                    } catch (InterruptedException | ExecutionException e) {
                        Throwable cause = e.getCause();
                        LOG.i("echo--getList-error--" + homeSourceBean.getKey() + "--" + e.getClass().getSimpleName() + "--" + (cause != null ? cause.getClass().getSimpleName() + ":" + cause.getMessage() : e.getMessage()));
                        e.printStackTrace();
                    } finally {
                        executor.shutdown();
                        if (json != null) {
                            json(listResult, json, homeSourceBean.getKey(), "", requestSeq);
                        } else {
                            listResult.postValue(createFailedXml(homeSourceBean.getKey(), requestSeq));
                        }
                    }
                }
            });
        } else if (type == 0 || type == 1 || type == 2) {
            final String ac = type == 0 ? "videolist" : "detail";
            final String api = homeSourceBean.getApi();
            final String sourceKey = homeSourceBean.getKey();
            // 只要用户选了任意筛选，就必须走带 filterSelect 的单请求。
            // 原先只在选中 type 子分类时才单请求，选「喜剧」这类非 type 筛选项时
            // 仍会聚合父分类+全部子分类，列表看起来像没刷新。
            if (hasActiveFilter(sortData)) {
                String typeId = sortData.filterSelect.get("type");
                String requestId = !TextUtils.isEmpty(typeId) ? typeId : sortData.id;
                requestType01List(api, sourceKey, type, ac, requestId, page, sortData.filterSelect, requestSeq);
                return requestSeq;
            }
            // 无筛选：顶级有子分类 → 聚合父分类+子分类内容（空文件夹顶级也能出列表）；否则单请求该分类
            List<String> childIds = childTypeIds(sortData);
            if (childIds == null || childIds.isEmpty()) {
                requestType01List(api, sourceKey, type, ac, sortData.id, page, sortData.filterSelect, requestSeq);
            } else {
                aggregateType01List(api, sourceKey, type, ac, sortData.id, childIds, page, requestSeq);
            }
        }else if (type == 4) {
            String ext= "";
            String extend=homeSourceBean.getExt();
            extend=getFixUrl(extend);
            if (sortData.filterSelect != null && sortData.filterSelect.size() > 0) {
                try {
                    String selectExt = new JSONObject(sortData.filterSelect).toString();
                    ext = Base64.encodeToString(selectExt.getBytes("UTF-8"), Base64.DEFAULT |  Base64.NO_WRAP);
                } catch (UnsupportedEncodingException e) {
                    e.printStackTrace();
                }
            }else {
                ext = Base64.encodeToString("{}".getBytes(), Base64.DEFAULT |  Base64.NO_WRAP);
            }

            GetRequest<String> request = OkGo.<String>get(homeSourceBean.getApi())
                    .tag(homeSourceBean.getApi())
                    .params("ac", "detail")
                    .params("filter", "true")
                    .params("t", sortData.id)
                    .params("pg", page)
                    .params("ext", ext);
            // 当 extend 不为空且非空字符串时添加参数
            if (extend != null && !extend.isEmpty()) {
                request.params("extend", extend);
            }
            request.execute(new AbsCallback<String>() {
                        @Override
                        public String convertResponse(okhttp3.Response response) throws Throwable {
                            try {
                                if (response.body() != null) {
                                    return response.body().string();
                                } else {
                                    throw new IllegalStateException("网络请求错误，response body 为 null");
                                }
                            } catch (Exception e) {
                                LOG.i("echo-list: convertResponse error"+ e.getMessage());
                                throw e;  // 重新抛出异常
                            }
                        }

                        @Override
                        public void onSuccess(Response<String> response) {
                            String json = response.body();
//                            LOG.i("echo-list: " + json);
                            json(listResult, json, homeSourceBean.getKey(), "", requestSeq);
                        }

                        @Override
                        public void onError(Response<String> response) {
                            super.onError(response);
                            listResult.postValue(createFailedXml(homeSourceBean.getKey(), requestSeq));
                        }
                    });

        } else {
            listResult.postValue(createFailedXml(homeSourceBean.getKey(), requestSeq));
        }
        return requestSeq;
    }

    /** 当前分类是否已经选中了至少一个有效筛选项。 */
    private boolean hasActiveFilter(MovieSort.SortData sortData) {
        if (sortData == null || sortData.filterSelect == null || sortData.filterSelect.isEmpty()) {
            return false;
        }
        for (String value : sortData.filterSelect.values()) {
            if (!TextUtils.isEmpty(value)) {
                return true;
            }
        }
        return false;
    }

    /** 顶级分类挂载的子分类 type_id 列表（来自“类型/地区”筛选的 values） */
    private List<String> childTypeIds(MovieSort.SortData sortData) {
        List<String> ids = new ArrayList<>();
        if (sortData == null || sortData.filters == null) return ids;
        for (MovieSort.SortFilter f : sortData.filters) {
            if ("type".equals(f.key) && f.values != null) {
                for (String v : f.values.values()) {
                    if (v != null && !v.isEmpty() && !"0".equals(v)) {
                        ids.add(v);
                    }
                }
            }
        }
        return ids;
    }

    /** 单分类请求（type 0/1）：t=分类 id */
    private void requestType01List(String api, final String sourceKey, final int type, String ac,
                                   String t, int page, HashMap<String, String> filterSelect, final int requestSeq) {
        OkGo.<String>get(api)
                .tag(api)
                .params("ac", ac)
                .params("t", t)
                .params("pg", page)
                .params(filterSelect)
                .params("f", (filterSelect == null || filterSelect.size() <= 0) ? "" : new JSONObject(filterSelect).toString())
                .execute(new AbsCallback<String>() {
                    @Override
                    public String convertResponse(okhttp3.Response response) throws Throwable {
                        if (response.body() != null) {
                            return response.body().string();
                        } else {
                            throw new IllegalStateException("网络请求错误");
                        }
                    }

                    @Override
                    public void onSuccess(Response<String> response) {
                        if (type == 0) {
                            xml(listResult, response.body(), sourceKey, "", requestSeq);
                        } else {
                            json(listResult, response.body(), sourceKey, "", requestSeq);
                        }
                    }

                    @Override
                    public void onError(Response<String> response) {
                        super.onError(response);
                        listResult.postValue(createFailedXml(sourceKey, requestSeq));
                    }
                });
    }

    /** 顶级分类聚合：父分类 + 所有子分类并发请求后按序合并（去重、取最大 pagecount） */
    private void aggregateType01List(String api, final String sourceKey, final int type, String ac,
                                     String parentId, List<String> childIds, final int page, final int requestSeq) {
        final List<String> ts = new ArrayList<>();
        ts.add(parentId);
        ts.addAll(childIds);
        final AbsXml[] parts = new AbsXml[ts.size()];
        final int[] remaining = {ts.size()};
        final boolean[] failed = {false};
        for (int i = 0; i < ts.size(); i++) {
            final int idx = i;
            final String t = ts.get(i);
            OkGo.<String>get(api)
                    .tag(api)
                    .params("ac", ac)
                    .params("t", t)
                    .params("pg", page)
                    .params("f", "")
                    .execute(new AbsCallback<String>() {
                        @Override
                        public String convertResponse(okhttp3.Response response) throws Throwable {
                            if (response.body() != null) {
                                return response.body().string();
                            } else {
                                throw new IllegalStateException("网络请求错误");
                            }
                        }

                        @Override
                        public void onSuccess(Response<String> response) {
                            AbsXml one = (type == 0)
                                    ? xml(null, response.body(), sourceKey, "", requestSeq)
                                    : json(null, response.body(), sourceKey, "", requestSeq);
                            if (one != null && one.movie != null && one.movie.videoList != null
                                    && !one.movie.videoList.isEmpty()) {
                                parts[idx] = one;
                            }
                            finishAggregate(parts, remaining, failed, page, sourceKey, requestSeq);
                        }

                        @Override
                        public void onError(Response<String> response) {
                            super.onError(response);
                            failed[0] = true;
                            finishAggregate(parts, remaining, failed, page, sourceKey, requestSeq);
                        }
                    });
        }
    }

    private void finishAggregate(AbsXml[] parts, int[] remaining, boolean[] failed, int page, String sourceKey, int requestSeq) {
        if (--remaining[0] > 0) return;
        List<Movie.Video> merged = new ArrayList<>();
        java.util.HashSet<String> seen = new java.util.HashSet<>();
        int pagecount = 1;
        String resolvedSourceKey = sourceKey;
        for (AbsXml one : parts) {
            if (one == null || one.movie == null || one.movie.videoList == null) continue;
            if (resolvedSourceKey == null) resolvedSourceKey = one.sourceKey;
            for (Movie.Video v : one.movie.videoList) {
                if (v != null && v.id != null && seen.add(v.id)) {
                    merged.add(v);
                }
            }
            if (one.movie.pagecount > pagecount) pagecount = one.movie.pagecount;
        }
        if (merged.isEmpty() && failed[0]) {
            listResult.postValue(createFailedXml(resolvedSourceKey, requestSeq));
            return;
        }
        AbsXml data = new AbsXml();
        data.sourceKey = resolvedSourceKey;
        data.requestSeq = requestSeq;
        data.failed = false;
        data.movie = new Movie();
        data.movie.videoList = merged;
        data.movie.pagecount = pagecount;
        data.movie.page = page;
        listResult.postValue(data);
    }

    interface HomeRecCallback {
        void done(List<Movie.Video> videos);
    }
//    homeVideoContent
    void getHomeRecList(SourceBean sourceBean, ArrayList<String> ids, HomeRecCallback callback) {
        int type = sourceBean.getType();
        if (type == 3) {
            Runnable waitResponse = new Runnable() {
                @Override
                public void run() {
                    ExecutorService executor = Executors.newSingleThreadExecutor();
                    Future<String> future = executor.submit(new Callable<String>() {
                        @Override
                        public String call() throws Exception {
                            Spider sp = ApiConfig.get().getCSP(sourceBean);
                            String json = sp.homeVideoContent();
//                            LOG.i("echo--getHomeRecList :" + json);
                            return json;
                        }
                    });
                    String sortJson = null;
                    try {
                        sortJson = future.get(20, TimeUnit.SECONDS);
                    } catch (TimeoutException e) {
                        e.printStackTrace();
                        future.cancel(true);
                    } catch (InterruptedException | ExecutionException e) {
                        e.printStackTrace();
                    } finally {
                        if (sortJson != null) {
                            AbsXml absXml = json(null, sortJson, sourceBean.getKey());
                            if (absXml != null && absXml.movie != null && absXml.movie.videoList != null) {
                                callback.done(absXml.movie.videoList);
                            } else {
                                callback.done(null);
                            }
                        } else {
                            callback.done(null);
                        }
                        try {
                            executor.shutdown();
                        } catch (Throwable th) {
                            th.printStackTrace();
                        }
                    }
                }
            };
            spThreadPool.execute(waitResponse);
        } else if (type == 0 || type == 1 || type == 2) {
            OkGo.<String>get(sourceBean.getApi())
                    .tag("detail")
                    .params("ac", sourceBean.getType() == 0 ? "videolist" : "detail")
                    .params("ids", TextUtils.join(",", ids))
                    .execute(new AbsCallback<String>() {

                        @Override
                        public String convertResponse(okhttp3.Response response) throws Throwable {
                            if (response.body() != null) {
                                return response.body().string();
                            } else {
                                throw new IllegalStateException("网络请求错误");
                            }
                        }

                        @Override
                        public void onSuccess(Response<String> response) {
                            AbsXml absXml;
                            if (sourceBean.getType() == 0) {
                                String xml = response.body();
                                absXml = xml(null, xml, sourceBean.getKey());
                            } else {
                                String json = response.body();
                                absXml = json(null, json, sourceBean.getKey());
                            }
                            if (absXml != null && absXml.movie != null && absXml.movie.videoList != null) {
                                callback.done(absXml.movie.videoList);
                            } else {
                                callback.done(null);
                            }
                        }

                        @Override
                        public void onError(Response<String> response) {
                            super.onError(response);
                            callback.done(null);
                        }
                    });
        } else {
            callback.done(null);
        }
    }
    // detailContent
    public int getDetail(String sourceKey, String urlid) {
        final int requestSeq = detailRequestSeq.incrementAndGet();
        OkGo.getInstance().cancelTag("detail");
        if (urlid != null && urlid.startsWith("push://") && ApiConfig.get().getSource(PUSH_AGENT) != null) {
            String pushUrl = urlid.substring(7);
            if (pushUrl.startsWith("b64:")) {
                try {
                    pushUrl = new String(Base64.decode(pushUrl.substring(4), Base64.DEFAULT | Base64.URL_SAFE | Base64.NO_WRAP), "UTF-8");
                } catch (UnsupportedEncodingException e) {
                    e.printStackTrace();
                }
            } else {
                pushUrl = URLDecoder.decode(pushUrl);
            }
            sourceKey = isCastPushUrl(pushUrl) ? PUSH_FALLBACK : PUSH_AGENT;
            urlid = pushUrl;
        } else if (PUSH_AGENT.equals(sourceKey) && isCastPushUrl(urlid)) {
            sourceKey = PUSH_FALLBACK;
        }
        final String id = urlid;
        final String resolvedKey = sourceKey;

        SourceBean sourceBean = ApiConfig.get().getSource(resolvedKey);
        if (isPushFallback(resolvedKey, sourceBean)) {
            AbsXml pushDetail = createPushDetail(id, resolvedKey);
            pushDetail.requestSeq = requestSeq;
            pushDetail.failed = false;
            detailResult.postValue(pushDetail);
            return requestSeq;
        }
        if (sourceBean == null) {
            detailResult.postValue(createFailedXml(resolvedKey, requestSeq));
            return requestSeq;
        }
        int type = sourceBean.getType();
        if (type == 3) {
            spThreadPool.execute(new Runnable() {
                @Override
                public void run() {
                    ExecutorService executor = Executors.newSingleThreadExecutor();
                    Future<String> future = executor.submit(new Callable<String>() {
                        @Override
                        public String call() {
                            Spider sp = ApiConfig.get().getCSP(sourceBean);
                            List<String> ids = new ArrayList<>();
                            ids.add(id);
                            try {
                                return sp.detailContent(ids);
                            } catch (Exception e) {
                                LOG.i("echo--getDetail--error: " + e.getMessage());
                                return "";
                            }
                        }
                    });

                    String json = null;
                    try {
                        json = future.get(30, TimeUnit.SECONDS);
//                        LOG.i("echo--getDetail--result:" + json);
                    } catch (TimeoutException e) {
                        LOG.i("echo--getDetail--timeout");
                        future.cancel(true);
                    } catch (Exception e) {
                        LOG.i("echo--getDetail--error: " + e.getMessage());
                    } finally {
                        if (!TextUtils.isEmpty(json)) {
                            json(detailResult, json, sourceBean.getKey(), "", requestSeq);
                        } else {
                            detailResult.postValue(createFailedXml(sourceBean.getKey(), requestSeq));
                        }
                        executor.shutdown();
                    }
                }
            });
        } else if (type == 0 || type == 1 || type == 2 || type == 4) {
            String extend=sourceBean.getExt();
            extend=getFixUrl(extend);

            GetRequest<String> request = OkGo.<String>get(sourceBean.getApi())
                    .tag("detail")
                    .params("ac", type == 0 ? "videolist" : "detail")
                    .params("ids", id);
            // 当 extend 不为空且非空字符串时添加参数
            if (extend != null && !extend.isEmpty()) {
                request.params("extend", extend);
            }
            request.execute(new AbsCallback<String>() {

                        @Override
                        public String convertResponse(okhttp3.Response response) throws Throwable {
                            if (response.body() != null) {
                                return response.body().string();
                            } else {
                                throw new IllegalStateException("网络请求错误");
                            }
                        }

                        @Override
                        public void onSuccess(Response<String> response) {
                            if (type == 0) {
                                String xml = response.body();
                                xml(detailResult, xml, sourceBean.getKey(), "", requestSeq);
                            } else {
                                String json = response.body();
                                LOG.i(json);
                                json(detailResult, json, sourceBean.getKey(), "", requestSeq);
                            }
                        }

                        @Override
                        public void onError(Response<String> response) {
                            super.onError(response);
                            detailResult.postValue(createFailedXml(sourceBean.getKey(), requestSeq));
                        }
                    });
        } else {
            detailResult.postValue(createFailedXml(resolvedKey, requestSeq));
        }
        return requestSeq;
    }

    public void action(String sourceKey, String action) {
        SourceBean sourceBean = ApiConfig.get().getSource(sourceKey);
        if (sourceBean == null || action == null) {
            actionResult.postValue(null);
            return;
        }
        if (sourceBean.getType() == 3) {
            spThreadPool.execute(new Runnable() {
                @Override
                public void run() {
                    try {
                        Spider sp = ApiConfig.get().getCSP(sourceBean);
                        String json = sp.action(action);
                        actionResult.postValue(TextUtils.isEmpty(json) ? null : new JSONObject(json));
                    } catch (Throwable th) {
                        th.printStackTrace();
                        actionResult.postValue(null);
                    }
                }
            });
        } else {
            actionResult.postValue(null);
        }
    }

    // searchContent
    public void getSearch(String sourceKey, String wd) {
        getSearch(sourceKey, wd, "");
    }

    public void getSearch(String sourceKey, String wd, String searchToken) {
        SourceBean sourceBean = ApiConfig.get().getSource(sourceKey);
        if (sourceBean == null) {
            postEmptySearchResult(searchResult, sourceKey, searchToken);
            return;
        }
        int type = sourceBean.getType();
        if (type == 3) {
            try {
                Spider sp = ApiConfig.get().getCSP(sourceBean);
                String search = sp.searchContent(wd, false);
                if(!TextUtils.isEmpty(search)){
                    json(searchResult, search, sourceBean.getKey(), searchToken);
                } else {
                    json(searchResult, "", sourceBean.getKey(), searchToken);
                }
            } catch (Throwable th) {
                th.printStackTrace();
                json(searchResult, "", sourceBean.getKey(), searchToken);
            }
        } else if (type == 0 || type == 1 || type == 2) {
            OkGo.<String>get(sourceBean.getApi())
                    .params("wd", wd)
                    .params(type == 0 ? null : "ac", type == 0 ? null : "detail")
                    .tag("search")
                    .execute(new AbsCallback<String>() {
                        @Override
                        public String convertResponse(okhttp3.Response response) throws Throwable {
                            if (response.body() != null) {
                                return response.body().string();
                            } else {
                                throw new IllegalStateException("网络请求错误");
                            }
                        }

                        @Override
                        public void onSuccess(Response<String> response) {
                            if (type == 0) {
                                String xml = response.body();
                                xml(searchResult, xml, sourceBean.getKey(), searchToken);
                            } else {
                                String json = response.body();
                                json(searchResult, json, sourceBean.getKey(), searchToken);
                            }
                        }

                        @Override
                        public void onError(Response<String> response) {
                            super.onError(response);
                            postEmptySearchResult(searchResult, sourceBean.getKey(), searchToken);
                        }
                    });
        }else if (type == 4) {
            final String searchWd = wd;
            httpPrepareThreadPool.execute(new Runnable() {
                @Override
                public void run() {
            String extend=sourceBean.getExt();
            extend=getFixUrlDirect(extend);
            String queryWd = searchWd;
            try {
                queryWd=URLEncoder.encode(queryWd, "UTF-8");
            } catch (UnsupportedEncodingException e) {
                e.printStackTrace();
            }

            GetRequest<String> request = OkGo.<String>get(sourceBean.getApi())
                    .tag("search")
                    .params("wd", queryWd)
                    .params("ac" ,"detail")
                    .params("quick" ,"false");
            // 当 extend 不为空且非空字符串时添加参数
            if (extend != null && !extend.isEmpty()) {
                request.params("extend", extend);
            }
            request.execute(new AbsCallback<String>() {
                    @Override
                    public String convertResponse(okhttp3.Response response) throws Throwable {
                        if (response.body() != null) {
                            return response.body().string();
                        } else {
                            LOG.i("echo-t4 search-网络请求错误");
                            throw new IllegalStateException("网络请求错误");
                        }
                    }

                    @Override
                    public void onSuccess(Response<String> response) {
                            String json = response.body();
//                            LOG.i("echo-t4 search onSuccess"+json);
                            json(searchResult, json, sourceBean.getKey(), searchToken);
                    }

                    @Override
                    public void onError(Response<String> response) {
                        LOG.i("echo-t4 search-onError");
                        super.onError(response);
                        postEmptySearchResult(searchResult, sourceBean.getKey(), searchToken);
                    }
                });
                }
            });
        } else {
            postEmptySearchResult(searchResult, sourceBean.getKey(), searchToken);
        }
    }
    // searchContent
    public void getQuickSearch(String sourceKey, String wd) {
        getQuickSearch(sourceKey, wd, "");
    }

    public void getQuickSearch(String sourceKey, String wd, String searchToken) {
        SourceBean sourceBean = ApiConfig.get().getSource(sourceKey);
        if (sourceBean == null) {
            postEmptySearchResult(quickSearchResult, sourceKey, searchToken);
            return;
        }
        int type = sourceBean.getType();
        if (type == 3) {
            try {
                Spider sp = ApiConfig.get().getCSP(sourceBean);
                json(quickSearchResult, sp.searchContent(wd, true), sourceBean.getKey(), searchToken);
            } catch (Throwable th) {
                th.printStackTrace();
                postEmptySearchResult(quickSearchResult, sourceBean.getKey(), searchToken);
            }
        } else if (type == 0 || type == 1 || type == 2) {
            OkGo.<String>get(sourceBean.getApi())
                    .params("wd", wd)
                    .params(type == 0 ? null : "ac", type == 0 ? null : "detail")
                    .tag("quick_search")
                    .execute(new AbsCallback<String>() {
                        @Override
                        public String convertResponse(okhttp3.Response response) throws Throwable {
                            if (response.body() != null) {
                                return response.body().string();
                            } else {
                                throw new IllegalStateException("网络请求错误");
                            }
                        }

                        @Override
                        public void onSuccess(Response<String> response) {
                            if (type == 0) {
                                String xml = response.body();
                                xml(quickSearchResult, xml, sourceBean.getKey(), searchToken);
                            } else {
                                String json = response.body();
                                json(quickSearchResult, json, sourceBean.getKey(), searchToken);
                            }
                        }

                        @Override
                        public void onError(Response<String> response) {
                            super.onError(response);
                            postEmptySearchResult(quickSearchResult, sourceBean.getKey(), searchToken);
                        }
                    });
        }else if (type == 4) {
            final String searchWd = wd;
            httpPrepareThreadPool.execute(new Runnable() {
                @Override
                public void run() {
            String extend=sourceBean.getExt();
            extend=getFixUrlDirect(extend);

            GetRequest<String> request = OkGo.<String>get(sourceBean.getApi())
                    .tag("search")
                    .params("wd", searchWd)
                    .params("ac" ,"detail")
                    .params("quick" ,"true");
            // 当 extend 不为空且非空字符串时添加参数
            if (extend != null && !extend.isEmpty()) {
                request.params("extend", extend);
            }
            request.execute(new AbsCallback<String>() {
                    @Override
                    public String convertResponse(okhttp3.Response response) throws Throwable {
                        if (response.body() != null) {
                            return response.body().string();
                        } else {
                            throw new IllegalStateException("网络请求错误");
                        }
                    }

                    @Override
                    public void onSuccess(Response<String> response) {
                        String json = response.body();
                        LOG.i(json);
                        json(quickSearchResult, json, sourceBean.getKey(), searchToken);
                    }

                    @Override
                    public void onError(Response<String> response) {
                        super.onError(response);
                        postEmptySearchResult(quickSearchResult, sourceBean.getKey(), searchToken);
                    }
                });
                }
            });
        } else {
            postEmptySearchResult(quickSearchResult, sourceBean.getKey(), searchToken);
        }
    }
    // playerContent
    public void getPlay(String sourceKey, String playFlag, String progressKey, String url, String subtitleKey) {
        final int requestSeq = playRequestSeq.incrementAndGet();
        SourceBean sourceBean = ApiConfig.get().getSource(sourceKey);
        boolean pushFallback = isPushFallback(sourceKey, sourceBean);
        PushUrl pushUrl = pushFallback ? parsePushUrl(url) : createPushUrl(url);
        String requestUrl = pushUrl.url;
        if (pushFallback) {
            postPlayResult(requestSeq, createPushPlayResult(url, pushUrl, progressKey, subtitleKey, playFlag));
            return;
        }
        int type = sourceBean.getType();
        if (type == 3) {
            spThreadPool.execute(new Runnable() {
                @Override
                public void run() {
                    ExecutorService executor = Executors.newSingleThreadExecutor();
                    Future<String> future = executor.submit(new Callable<String>() {
                        @Override
                        public String call() throws Exception {
                            Spider sp = ApiConfig.get().getCSP(sourceBean);
                            if (TextUtils.isEmpty(requestUrl)) return "";
                            try {
                                return sp.playerContent(playFlag, requestUrl, ApiConfig.get().getVipParseFlags());
                            } catch (Exception e) {
                                LOG.i("echo--getPlay--error: " + e.getMessage());
                                return "";
                            }
                        }
                    });

                    try {
                        String json = future.get(sourceBean.getPlayTimeoutSeconds(), TimeUnit.SECONDS);
                        LOG.i("echo--getPlay--result:" + json);
                        // 处理返回的 JSON
                        if (!TextUtils.isEmpty(json)) {
                            JSONObject result = normalizePlayerResult(new JSONObject(json));
                            result.put("key", url);
                            mergePushHeaders(result, pushUrl);
                            result.put("proKey", progressKey);
                            result.put("subtKey", subtitleKey);
                            if (!result.has("flag"))
                                result.put("flag", playFlag);
                            if (TextUtils.isEmpty(result.optString("url", "")) && shouldDirectPlay(sourceBean, requestUrl)) {
                                postPlayResult(requestSeq, createDirectPlayResult(url, pushUrl, progressKey, subtitleKey, playFlag));
                            } else {
                                postPlayResult(requestSeq, result);
                            }
                        } else {
                            postPlayResult(requestSeq, null);
                        }
                    } catch (TimeoutException e) {
                        // 如果超时了，处理超时逻辑
                        LOG.i("echo--getPlay--timeout");
                        future.cancel(true);
                        postPlayResult(requestSeq, null);
                    } catch (Exception e) {
                        // 捕获其他异常
                        LOG.i("echo--getPlay--error: " + e.getMessage());
                        postPlayResult(requestSeq, null);
                    } finally {
                        executor.shutdown();
                    }
                }
            });
        } else if (type == 0 || type == 1 || type == 2) {
            JSONObject result = new JSONObject();
            try {
                result.put("key", url);
                String playUrl = sourceBean.getPlayerUrl().trim();
                if (DefaultConfig.isVideoFormat(requestUrl) && playUrl.isEmpty()) {
                    result.put("parse", 0);
                    result.put("url", requestUrl);
                } else {
                    result.put("parse", 1);
                    result.put("url", requestUrl);
                }
                mergePushHeaders(result, pushUrl);
                result.put("proKey", progressKey);
                result.put("subtKey", subtitleKey);
                result.put("playUrl", playUrl);
                result.put("flag", playFlag);
                postPlayResult(requestSeq, result);
            } catch (Throwable th) {
                th.printStackTrace();
                postPlayResult(requestSeq, null);
            }
        } else if (type == 4) {
            String extend=sourceBean.getExt();
            extend=getFixUrl(extend);

            GetRequest<String> request = OkGo.<String>get(sourceBean.getApi())
                    .tag("play")
                    .params("play", requestUrl)
                    .params("flag" ,playFlag);
            // 当 extend 不为空且非空字符串时添加参数
            if (extend != null && !extend.isEmpty()) {
                request.params("extend", extend);
            }
            request.execute(new AbsCallback<String>() {
                    @Override
                    public String convertResponse(okhttp3.Response response) throws Throwable {
                        if (response.body() != null) {
                            return response.body().string();
                        } else {
                            throw new IllegalStateException("网络请求错误");
                        }
                    }

                    @Override
                    public void onSuccess(Response<String> response) {
                        String json = response.body();
                        LOG.i(json);
                        try {
                            JSONObject result = normalizePlayerResult(new JSONObject(json));
                            result.put("key", url);
                            mergePushHeaders(result, pushUrl);
                            result.put("proKey", progressKey);
                            result.put("subtKey", subtitleKey);
                            if (!result.has("flag"))
                                result.put("flag", playFlag);
                            postPlayResult(requestSeq, result);
                        } catch (Throwable th) {
                            th.printStackTrace();
                            postPlayResult(requestSeq, null);
                        }
                    }

                    @Override
                    public void onError(Response<String> response) {
                        super.onError(response);
                        postPlayResult(requestSeq, null);
                    }
                });
        }else {
            postPlayResult(requestSeq, null);
        }
    }

    public void cancelPlayRequest() {
        playRequestSeq.incrementAndGet();
    }

    private boolean shouldDirectPlay(SourceBean sourceBean, String requestUrl) {
        return sourceBean != null
                && !TextUtils.isEmpty(requestUrl)
                && (requestUrl.startsWith("http://") || requestUrl.startsWith("https://"));
    }

    private JSONObject createDirectPlayResult(String rawUrl, PushUrl pushUrl, String progressKey, String subtitleKey, String playFlag) {
        try {
            JSONObject result = new JSONObject();
            result.put("key", rawUrl);
            result.put("proKey", progressKey);
            result.put("subtKey", subtitleKey);
            result.put("flag", playFlag);
            result.put("parse", 0);
            result.put("jx", 0);
            result.put("url", pushUrl.url);
            mergePushHeaders(result, pushUrl);
            LOG.i("echo--getPlay--direct:" + pushUrl.url);
            return result;
        } catch (Throwable th) {
            th.printStackTrace();
            return null;
        }
    }

    private JSONObject normalizePlayerResult(JSONObject result) {
        if (result == null) return null;
        try {
            String playUrl = result.optString("playUrl", "");
            String url = result.optString("url", "");
            if (TextUtils.isEmpty(url)) return result;
            if (url.startsWith("[") && url.endsWith("]")) {
                JSONArray array = new JSONArray(url);
                for (int i = 0; i < array.length(); i++) {
                    Object item = array.get(i);
                    if (item instanceof String) {
                        String str = (String) item;
                        if (str.startsWith("proxy://")) {
                            str = DefaultConfig.checkReplaceProxy(str);
                            array.put(i, str);
                        } else if (str.startsWith("video://")) {
                            str = str.substring(8);
                            array.put(i, str);
                        }
                    }
                }
                result.put("url", array.toString());
                result.put("parse", 0);
                return result;
            }
            if (url.startsWith("video://")) {
                url = url.substring(8);
                result.put("url", url);
                result.put("parse", 1);
            } else if (url.startsWith("proxy://")) {
                url = DefaultConfig.checkReplaceProxy(url);
                result.put("url", url);
                result.put("parse", 0);
            } else if (playUrl.length() == 0
                    && DefaultConfig.isVideoFormat(url)
                    && !result.has("parse")
                    && !result.has("jx")) {
                result.put("parse", 0);
            }
        } catch (Throwable th) {
            th.printStackTrace();
        }
        return result;
    }

    private boolean isPushFallback(String sourceKey, SourceBean sourceBean) {
        return PUSH_FALLBACK.equals(sourceKey) || (sourceBean != null && PUSH_AGENT.equals(sourceBean.getKey()) && sourceBean.getType() == -1);
    }

    private boolean isCastPushUrl(String url) {
        return !TextUtils.isEmpty(url) && url.contains(PUSH_HEADERS_MARKER);
    }

    private AbsXml createFailedXml(String sourceKey, int requestSeq) {
        AbsXml data = new AbsXml();
        data.sourceKey = sourceKey;
        data.requestSeq = requestSeq;
        data.failed = true;
        return data;
    }

    private AbsXml createPushDetail(String url, String sourceKey) {
        AbsXml data = new AbsXml();
        data.sourceKey = sourceKey;
        data.failed = false;
        Movie movie = new Movie();
        movie.videoList = new ArrayList<>();
        Movie.Video video = new Movie.Video();
        video.id = url;
        video.name = url;
        video.type = "推送";
        video.sourceKey = sourceKey;
        video.urlBean = new Movie.Video.UrlBean();
        video.urlBean.infoList = new ArrayList<>();
        Movie.Video.UrlBean.UrlInfo urlInfo = new Movie.Video.UrlBean.UrlInfo();
        urlInfo.flag = "推送";
        urlInfo.urls = "播放$" + url;
        urlInfo.beanList = new ArrayList<>();
        urlInfo.beanList.add(new Movie.Video.UrlBean.UrlInfo.InfoBean("播放", url));
        video.urlBean.infoList.add(urlInfo);
        movie.videoList.add(video);
        data.movie = movie;
        return data;
    }

    private JSONObject createPushPlayResult(String rawUrl, PushUrl pushUrl, String progressKey, String subtitleKey, String playFlag) {
        try {
            JSONObject result = new JSONObject();
            result.put("key", rawUrl);
            result.put("proKey", progressKey);
            result.put("subtKey", subtitleKey);
            result.put("flag", playFlag);
            result.put("parse", 0);
            result.put("url", pushUrl.url);
            mergePushHeaders(result, pushUrl);
            return result;
        } catch (Throwable th) {
            th.printStackTrace();
            return null;
        }
    }

    private void mergePushHeaders(JSONObject result, PushUrl pushUrl) {
        if (result == null || pushUrl == null || pushUrl.headers.isEmpty()) return;
        try {
            JSONObject header = result.optJSONObject("header");
            if (header == null) header = result.optJSONObject("headers");
            if (header == null) header = new JSONObject();
            for (String key : pushUrl.headers.keySet()) {
                header.put(key, pushUrl.headers.get(key));
            }
            result.put("header", header);
        } catch (Throwable ignored) {
        }
    }

    private PushUrl createPushUrl(String rawUrl) {
        PushUrl pushUrl = new PushUrl();
        pushUrl.url = rawUrl == null ? "" : rawUrl;
        return pushUrl;
    }

    private PushUrl parsePushUrl(String rawUrl) {
        PushUrl pushUrl = createPushUrl(rawUrl);
        parseMarkedHeaders(pushUrl);
        return pushUrl;
    }

    private boolean parseMarkedHeaders(PushUrl pushUrl) {
        String marker = PUSH_HEADERS_MARKER;
        int start = pushUrl.url.indexOf(marker);
        if (start < 0) return false;
        int valueStart = start + marker.length();
        int end = pushUrl.url.indexOf('@', valueStart);
        if (end < 0) return false;
        try {
            String text = URLDecoder.decode(pushUrl.url.substring(valueStart, end), "UTF-8");
            JSONObject json = new JSONObject(text);
            Iterator<String> keys = json.keys();
            while (keys.hasNext()) {
                String key = keys.next();
                String value = json.optString(key, "");
                if (!TextUtils.isEmpty(key)) pushUrl.headers.put(key, value);
            }
            pushUrl.url = pushUrl.url.substring(0, start) + pushUrl.url.substring(end + 1);
            return true;
        } catch (Throwable ignored) {
            return false;
        }
    }

    private static class PushUrl {
        String url = "";
        HashMap<String, String> headers = new HashMap<>();
    }

    private void postPlayResult(int requestSeq, JSONObject result) {
        mainHandler.post(new Runnable() {
            @Override
            public void run() {
                if (requestSeq != playRequestSeq.get()) {
                    LOG.i("echo--getPlay--ignore stale result");
                    return;
                }
                playResult.setValue(result);
            }
        });
    }

    private static final ConcurrentHashMap<String, String> extendCache = new ConcurrentHashMap<>();

    private String getFixUrl(final String extend) {
        if (TextUtils.isEmpty(extend)) return "";
        if(!extend.startsWith("http"))return extend;
        final String key = MD5.string2MD5(extend);
        if (extendCache.containsKey(key)) {
            LOG.i("echo-getFixUrl Cache");
            return extendCache.get(key);
        }
        Future<String> future = spThreadPool.submit(new Callable<String>() {
            @Override
            public String call() {
                String result = extend;
                if (extend.startsWith("http://127.0.0.1")) {
                    String path = extend.replaceAll("^http.+/file/", FileUtils.getRootPath() + "/");
                    path = path.replaceAll("localhost/", "/");
                    result = FileUtils.readFileToString(path, "UTF-8");
                    result = tryMinifyJson(result);
                    extendCache.putIfAbsent(key, result);
                } else if (extend.startsWith("http")) {
                    result = OkHttp.string(extend, null);
                    if (!result.isEmpty()) {
                        result = tryMinifyJson(result);
                        if(result.length()>2500)result = extend;
                        extendCache.putIfAbsent(key, result);
                    }
                }
                return result;
            }
        });

        try {
            return future.get(20, TimeUnit.SECONDS);
        } catch (TimeoutException te) {
            te.printStackTrace();
            future.cancel(true);
            return extend;
        } catch (Exception e) {
            e.printStackTrace();
            return extend;
        }
    }

    private String tryMinifyJson(String raw) {
        try {
            raw = raw.trim();
            JsonElement jsonElement = JsonParser.parseString(raw);
            return gson.toJson(jsonElement);
        } catch (Exception e) {
            return raw;
        }
    }

    private MovieSort.SortFilter getSortFilter(JsonObject obj) {
        String key = obj.get("key").getAsString();
        String name = obj.get("name").getAsString();
        JsonArray kv = obj.getAsJsonArray("value");
        LinkedHashMap<String, String> values = new LinkedHashMap<>();
        for (JsonElement ele : kv) {
            JsonObject ele_obj = ele.getAsJsonObject();
            String values_key=ele_obj.has("n")?ele_obj.get("n").getAsString():"";
            String values_value=ele_obj.has("v")?ele_obj.get("v").getAsString():"";
            values.put(values_key, values_value);
        }
        MovieSort.SortFilter filter = new MovieSort.SortFilter();
        filter.key = key;
        filter.name = name;
        filter.values = values;
        return filter;
    }

    private AbsSortXml sortJson(MutableLiveData<AbsSortXml> result, String json) {
        try {
            if (TextUtils.isEmpty(json)) {
                return new AbsSortJson().toAbsSortXml();
            }
            JsonObject obj = JsonParser.parseString(json).getAsJsonObject();
            AbsSortJson sortJson = gson.fromJson(obj, new TypeToken<AbsSortJson>() {
            }.getType());
            AbsSortXml data = sortJson.toAbsSortXml();
            try {
                if (obj.has("filters")) {
                    LinkedHashMap<String, ArrayList<MovieSort.SortFilter>> sortFilters = new LinkedHashMap<>();
                    JsonObject filters = obj.getAsJsonObject("filters");
                    for (String key : filters.keySet()) {
                        ArrayList<MovieSort.SortFilter> sortFilter = new ArrayList<>();
                        JsonElement one = filters.get(key);
                        if (one.isJsonObject()) {
                            sortFilter.add(getSortFilter(one.getAsJsonObject()));
                        } else {
                            for (JsonElement ele : one.getAsJsonArray()) {
                                sortFilter.add(getSortFilter(ele.getAsJsonObject()));
                            }
                        }
                        sortFilters.put(key, sortFilter);
                    }
                    if (data.classes != null && data.classes.sortList != null) {
                        for (MovieSort.SortData sort : data.classes.sortList) {
                            if (sortFilters.containsKey(sort.id) && sortFilters.get(sort.id) != null) {
                                sort.filters = sortFilters.get(sort.id);
                            }
                        }
                    }
                }
            } catch (Throwable th) {

            }
            return data;
        } catch (Exception e) {
            LOG.i("echo--sortJson-err--" + (e == null ? "null" : (e.getClass().getSimpleName() + ":" + e.getMessage())));
            return null;
        }
    }

    private AbsSortXml sortXml(MutableLiveData<AbsSortXml> result, String xml) {
        try {
            XStream xstream = new XStream(new DomDriver());//创建Xstram对象
            xstream.autodetectAnnotations(true);
            xstream.processAnnotations(AbsSortXml.class);
            xstream.ignoreUnknownElements();
            AbsSortXml data = (AbsSortXml) xstream.fromXML(xml);
            for (MovieSort.SortData sort : data.classes.sortList) {
                if (sort.filters == null) {
                    sort.filters = new ArrayList<>();
                }
            }
            return data;
        } catch (Exception e) {
            return null;
        }
    }

    private void absXml(AbsXml data, String sourceKey) {
        absXml(data, sourceKey, "");
    }

    private void absXml(AbsXml data, String sourceKey, String searchToken) {
        data.sourceKey = sourceKey;
        data.searchToken = searchToken;
        if (data.movie != null && data.movie.videoList != null) {
            for (Movie.Video video : data.movie.videoList) {
                if (video.urlBean != null && video.urlBean.infoList != null) {
                    for (Movie.Video.UrlBean.UrlInfo urlInfo : video.urlBean.infoList) {
                        String[] str = null;
                        if (urlInfo.urls.contains("#")) {
                            str = urlInfo.urls.split("#");
                        } else {
                            str = new String[]{urlInfo.urls};
                        }
                        List<Movie.Video.UrlBean.UrlInfo.InfoBean> infoBeanList = new ArrayList<>();
//                        for (String s : str) {
//                            if (s.contains("$")) {
//                                String[] ss = s.split("\\$");
//                                if (ss.length >= 2) {
//                                    infoBeanList.add(new Movie.Video.UrlBean.UrlInfo.InfoBean(ss[0], ss[1]));
//                                }
//                                //infoBeanList.add(new Movie.Video.UrlBean.UrlInfo.InfoBean(s.substring(0, s.indexOf("$")), s.substring(s.indexOf("$") + 1)));
//                            }
//                        }
                        for (String s : str) {
                            String[] ss = s.split("\\$", 2);
                            if (ss.length > 0) {
                                if (ss.length >= 2) {
                                    infoBeanList.add(new Movie.Video.UrlBean.UrlInfo.InfoBean(ss[0], ss[1]));
                                } else {
                                    infoBeanList.add(new Movie.Video.UrlBean.UrlInfo.InfoBean((infoBeanList.size() + 1) + "", ss[0]));
                                }
                            }
                        }
                        urlInfo.beanList = infoBeanList;
                    }
                }
                video.sourceKey = sourceKey;
            }
        }
    }

    private AbsXml checkPush(AbsXml data) {
        if (data.movie != null && data.movie.videoList != null && data.movie.videoList.size() > 0) {
            Movie.Video video = data.movie.videoList.get(0);
            if (video != null && video.urlBean != null && video.urlBean.infoList != null && video.urlBean.infoList.size() > 0) {
                for (int i = 0; i < video.urlBean.infoList.size(); i++) {
                    Movie.Video.UrlBean.UrlInfo urlinfo = video.urlBean.infoList.get(i);
                    if (urlinfo != null && urlinfo.beanList != null && !urlinfo.beanList.isEmpty()) {
                        for (Movie.Video.UrlBean.UrlInfo.InfoBean infoBean : urlinfo.beanList) {
                            if (infoBean.url.startsWith("push://")) {
                                String pushUrl = infoBean.url.substring(7);
                                if (pushUrl.startsWith("b64:")) {
                                    try {
                                        pushUrl = new String(Base64.decode(pushUrl.substring(4), Base64.DEFAULT | Base64.URL_SAFE | Base64.NO_WRAP), "UTF-8");
                                    } catch (UnsupportedEncodingException e) {
                                        e.printStackTrace();
                                    }
                                } else {
                                    pushUrl = URLDecoder.decode(pushUrl);
                                }

                                final AbsXml[] resData = {null};

                                final CountDownLatch countDownLatch = new CountDownLatch(1);
                                ExecutorService threadPool = Executors.newSingleThreadExecutor();
                                String finalPushUrl = pushUrl;
                                threadPool.execute(new Runnable() {
                                    @Override
                                    public void run() {
                                        SourceBean sb = ApiConfig.get().getSource("push_agent");
                                        if (sb == null) {
                                            countDownLatch.countDown();
                                            return;
                                        }
                                        if (sb.getType() == 4) {
                                            OkGo.<String>get(sb.getApi())
                                                    .tag("detail")
                                                    .params("ac","detail")
                                                    .params("ids", finalPushUrl)
                                                    .execute(new AbsCallback<String>() {
                                                        @Override
                                                        public String convertResponse(okhttp3.Response response) throws Throwable {
                                                            if (response.body() != null) {
                                                                return response.body().string();
                                                            } else {
                                                                return "";
                                                            }
                                                        }

                                                        @Override
                                                        public void onSuccess(Response<String> response) {
                                                            String res = response.body();
                                                            if (!TextUtils.isEmpty(res)) {
                                                                try {
                                                                    AbsJson absJson = gson.fromJson(res, new TypeToken<AbsJson>() {
                                                                    }.getType());
                                                                    resData[0] = absJson.toAbsXml();
                                                                    absXml(resData[0], sb.getKey());
                                                                } catch (Exception e) {
                                                                    e.printStackTrace();
                                                                }
                                                            }
                                                            countDownLatch.countDown();
                                                        }

                                                        @Override
                                                        public void onError(Response<String> response) {
                                                            super.onError(response);
                                                            countDownLatch.countDown();
                                                        }
                                                    });
                                        } else {
                                            try {
                                                Spider sp = ApiConfig.get().getCSP(sb);
                                             //   ApiConfig.get().setPlayJarKey(sb.getJar());
                                                List<String> ids = new ArrayList<>();
                                                ids.add(finalPushUrl);
                                                String res = sp.detailContent(ids);
                                                if (!TextUtils.isEmpty(res)) {
                                                    try {
                                                        AbsJson absJson = gson.fromJson(res, new TypeToken<AbsJson>() {}.getType());
                                                        resData[0] = absJson.toAbsXml();
                                                        absXml(resData[0], sb.getKey());
                                                    } catch (Exception e) {
                                                        e.printStackTrace();
                                                    }
                                                }
                                            } catch (Throwable th) {
                                                th.printStackTrace();
                                            }
                                            countDownLatch.countDown();
                                        }
                                    }
                                });
                                try {
                                    countDownLatch.await(15, TimeUnit.SECONDS);
                                    threadPool.shutdown();
                                } catch (InterruptedException e) {
                                    e.printStackTrace();
                                }
                                if (resData[0] != null) {
                                    AbsXml res = resData[0];
                                    if (res.movie != null && res.movie.videoList != null && res.movie.videoList.size() > 0) {
                                        Movie.Video resVideo = res.movie.videoList.get(0);
                                        if (resVideo != null && resVideo.urlBean != null && resVideo.urlBean.infoList != null && resVideo.urlBean.infoList.size() > 0) {
                                            if (urlinfo.beanList.size() == 1) {
                                                video.urlBean.infoList.remove(i);
                                            } else {
                                                urlinfo.beanList.remove(infoBean);
                                            }
                                            for (Movie.Video.UrlBean.UrlInfo resUrlinfo : resVideo.urlBean.infoList) {
                                                if (resUrlinfo != null && resUrlinfo.beanList != null && !resUrlinfo.beanList.isEmpty()) {
                                                    video.urlBean.infoList.add(resUrlinfo);
                                                }
                                            }
                                            video.sourceKey = "push_agent";
                                            return data;
                                        }
                                    }
                                }
                                infoBean.name = "解析失败 >>> " + infoBean.name;
                            }
                        }
                    }
                }
            }
        }
        return data;
    }

    public void checkThunder(AbsXml data, int index) {
        boolean thunderParse = false;
        if (data.movie != null && data.movie.videoList != null && data.movie.videoList.size() == 1) {
            Movie.Video video = data.movie.videoList.get(0);
            if (video != null && video.urlBean != null && video.urlBean.infoList != null) {
                boolean hasThunder=false;
                thunderLoop:
                for (int idx=0;idx<video.urlBean.infoList.size();idx++) {
                    Movie.Video.UrlBean.UrlInfo urlInfo = video.urlBean.infoList.get(idx);
                    for (Movie.Video.UrlBean.UrlInfo.InfoBean infoBean : urlInfo.beanList) {
                        if(Thunder.isSupportUrl(infoBean.url)){
                            hasThunder=true;
                            break thunderLoop;
                        }
                    }
                }
                if (hasThunder) {
                    thunderParse = true;
                    Thunder.parse(App.getInstance(), video.urlBean, new Thunder.ThunderCallback() {
                        @Override
                        public void status(int code, String info) {
                            if (code >= 0) {
                                LOG.i(info);
                            } else {
                                video.urlBean.infoList.get(0).beanList.get(0).name = info;
                                detailResult.postValue(data);
                            }
                        }

                        @Override
                        public void list(Map<Integer, String> urlMap) {
                            for (int key : urlMap.keySet()) {
                                String playList=urlMap.get(key);
                                video.urlBean.infoList.get(key).urls = playList;
                                String[] str = playList.split("#");
                                List<Movie.Video.UrlBean.UrlInfo.InfoBean> infoBeanList = new ArrayList<>();
                                for (String s : str) {
                                    if (s.contains("$")) {
                                        String[] ss = s.split("\\$", 2);

                                        if (ss.length > 0) {
                                            if (ss.length >= 2) {
                                                infoBeanList.add(new Movie.Video.UrlBean.UrlInfo.InfoBean(ss[0], ss[1]));
                                            } else {
                                                infoBeanList.add(new Movie.Video.UrlBean.UrlInfo.InfoBean((infoBeanList.size() + 1) + "", ss[0]));
                                            }
                                        }
                                    }
                                }
                                video.urlBean.infoList.get(key).beanList = infoBeanList;
                            }
                            detailResult.postValue(data);
                        }

                        @Override
                        public void play(String url) {

                        }
                    });
                }
            }
        }
        if (!thunderParse && index==0) {
            detailResult.postValue(data);
        }
    }

    private AbsXml xml(MutableLiveData<AbsXml> result, String xml, String sourceKey) {
        return xml(result, xml, sourceKey, "", 0);
    }

    private AbsXml xml(MutableLiveData<AbsXml> result, String xml, String sourceKey, String searchToken) {
        return xml(result, xml, sourceKey, searchToken, 0);
    }

    private AbsXml xml(MutableLiveData<AbsXml> result, String xml, String sourceKey, String searchToken, int requestSeq) {
        try {
            XStream xstream = new XStream(new DomDriver());//创建Xstram对象
            xstream.autodetectAnnotations(true);
            xstream.processAnnotations(AbsXml.class);
            xstream.ignoreUnknownElements();
            if (xml.contains("<year></year>")) {
                xml = xml.replace("<year></year>", "<year>0</year>");
            }
            if (xml.contains("<state></state>")) {
                xml = xml.replace("<state></state>", "<state>0</state>");
            }
            AbsXml data = (AbsXml) xstream.fromXML(xml);
            absXml(data, sourceKey, searchToken);
            data.requestSeq = requestSeq;
            data.failed = false;
            if (searchResult == result) {
                EventBus.getDefault().post(new RefreshEvent(RefreshEvent.TYPE_SEARCH_RESULT, data));
            } else if (quickSearchResult == result) {
                EventBus.getDefault().post(new RefreshEvent(RefreshEvent.TYPE_QUICK_SEARCH_RESULT, data));
            } else if (result != null) {
                if (result == detailResult) {
                	data = checkPush(data);
                    checkThunder(data,0);
                }else {
                    result.postValue(data);
                }
            }
            return data;
        } catch (Exception e) {
            if (searchResult == result || quickSearchResult == result) {
                postEmptySearchResult(result, sourceKey, searchToken);
            } else if (result != null) {
                result.postValue(createFailedXml(sourceKey, requestSeq));
            }
            return null;
        }
    }

    private AbsXml json(MutableLiveData<AbsXml> result, String json, String sourceKey) {
        return json(result, json, sourceKey, "", 0);
    }

    private AbsXml json(MutableLiveData<AbsXml> result, String json, String sourceKey, String searchToken) {
        return json(result, json, sourceKey, searchToken, 0);
    }

    private AbsXml json(MutableLiveData<AbsXml> result, String json, String sourceKey, String searchToken, int requestSeq) {
        try {
            // 测试数据
//            json = "{\n" +
//                    "\t\"list\": [{\n" +
//                    "\t\t\"vod_id\": \"137133\",\n" +
//                    "\t\t\"vod_name\": \"磁力测试\",\n" +
//                    "\t\t\"vod_pic\": \"https:/img9.doubanio.com/view/photo/s_ratio_poster/public/p2656327176.webp\",\n" +
//                    "\t\t\"type_name\": \"剧情 / 爱情 / 古装\",\n" +
//                    "\t\t\"vod_year\": \"2022\",\n" +
//                    "\t\t\"vod_area\": \"中国大陆\",\n" +
//                    "\t\t\"vod_remarks\": \"40集全\",\n" +
//                    "\t\t\"vod_actor\": \"刘亦菲\",\n" +
//                    "\t\t\"vod_director\": \"杨阳\",\n" +
//                    "\t\t\"vod_content\": \"　　在钱塘开茶铺的赵盼儿（刘亦菲 饰）惊闻未婚夫、新科探花欧阳旭（徐海乔 饰）要另娶当朝高官之女，不甘命运的她誓要上京讨个公道。在途中她遇到了出自权门但生性正直的皇城司指挥顾千帆（陈晓 饰），并卷入江南一场大案，两人不打不相识从而结缘。赵盼儿凭借智慧解救了被骗婚而惨遭虐待的“江南第一琵琶高手”宋引章（林允 饰）与被苛刻家人逼得离家出走的豪爽厨娘孙三娘（柳岩 饰），三位姐妹从此结伴同行，终抵汴京，见识世间繁华。为了不被另攀高枝的欧阳旭从东京赶走，赵盼儿与宋引章、孙三娘一起历经艰辛，将小小茶坊一步步发展为汴京最大的酒楼，揭露了负心人的真面目，收获了各自的真挚感情和人生感悟，也为无数平凡女子推开了一扇平等救赎之门。\",\n" +
//                    "\t\t\"vod_play_from\": \"磁力测试\",\n" +
//                    "\t\t\"vod_play_url\": \"0$magnet:?xt=urn:btih:e398ca38fb9d64897ed19b4d16efeea11af4d03b\"\n" +
//                    "\t}]\n" +
//                    "}";
            AbsJson absJson = gson.fromJson(json, new TypeToken<AbsJson>() {
            }.getType());
            AbsXml data = absJson.toAbsXml();
            absXml(data, sourceKey, searchToken);
            data.requestSeq = requestSeq;
            data.failed = false;
            if (searchResult == result) {
                EventBus.getDefault().post(new RefreshEvent(RefreshEvent.TYPE_SEARCH_RESULT, data));
            } else if (quickSearchResult == result) {
                EventBus.getDefault().post(new RefreshEvent(RefreshEvent.TYPE_QUICK_SEARCH_RESULT, data));
            } else if (result != null) {
                if (result == detailResult) {
                	data = checkPush(data);
                    checkThunder(data,0);
                }else {
                    result.postValue(data);
                }
            }
            return data;
        } catch (Exception e) {
            if (searchResult == result || quickSearchResult == result) {
                postEmptySearchResult(result, sourceKey, searchToken);
            } else if (result != null) {
                result.postValue(createFailedXml(sourceKey, requestSeq));
            }
            return null;
        }
    }

    private String getFixUrlDirect(final String extend) {
        if (TextUtils.isEmpty(extend)) return "";
        if (!extend.startsWith("http")) return extend;
        final String key = MD5.string2MD5(extend);
        if (extendCache.containsKey(key)) {
            return extendCache.get(key);
        }
        String result = extend;
        try {
            if (extend.startsWith("http://127.0.0.1")) {
                String path = extend.replaceAll("^http.+/file/", FileUtils.getRootPath() + "/");
                path = path.replaceAll("localhost/", "/");
                result = FileUtils.readFileToString(path, "UTF-8");
                result = tryMinifyJson(result);
                extendCache.putIfAbsent(key, result);
            } else {
                result = OkHttp.string(extend, null);
                if (!TextUtils.isEmpty(result)) {
                    result = tryMinifyJson(result);
                    if (result.length() > 2500) result = extend;
                    extendCache.putIfAbsent(key, result);
                }
            }
        } catch (Throwable th) {
            th.printStackTrace();
            return extend;
        }
        return result;
    }

    private void postEmptySearchResult(MutableLiveData<AbsXml> result, String sourceKey) {
        postEmptySearchResult(result, sourceKey, "");
    }

    private void postEmptySearchResult(MutableLiveData<AbsXml> result, String sourceKey, String searchToken) {
        AbsXml data = new AbsXml();
        data.sourceKey = sourceKey;
        data.searchToken = searchToken;
        if (searchResult == result) {
            EventBus.getDefault().post(new RefreshEvent(RefreshEvent.TYPE_SEARCH_RESULT, data));
        } else if (quickSearchResult == result) {
            EventBus.getDefault().post(new RefreshEvent(RefreshEvent.TYPE_QUICK_SEARCH_RESULT, data));
        } else if (result != null) {
            result.postValue(data);
        }
    }

    @Override
    protected void onCleared() {
        super.onCleared();
    }
}
