package com.github.tvbox.osc.callback;

import com.github.tvbox.osc.R;

/**
 * 搜索页专用加载态：使用 PonyoLoading.Search 动画，
 * 避免搜索时误用换源/内容加载（PonyoLoading.Content）动画。
 */
public class SearchLoadingCallback extends LoadingCallback {

    @Override
    protected int onCreateView() {
        return R.layout.loadsir_search_loading_layout;
    }
}
