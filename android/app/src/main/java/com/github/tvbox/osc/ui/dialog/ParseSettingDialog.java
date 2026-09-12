package com.github.tvbox.osc.ui.dialog;

import android.content.Context;
import android.os.Bundle;
import android.view.View;

import androidx.annotation.NonNull;

import com.github.tvbox.osc.R;
import com.github.tvbox.osc.api.ApiConfig;
import com.github.tvbox.osc.bean.ParseBean;
import com.github.tvbox.osc.ui.adapter.ParseSettingAdapter;
import com.github.tvbox.osc.util.HawkConfig;
import com.owen.tvrecyclerview.widget.TvRecyclerView;
import com.orhanobut.hawk.Hawk;

import org.jetbrains.annotations.NotNull;

import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

/**
 * 解析器设置对话框：默认解析器（单选）+ 启用解析器（多选）。
 * 选择/勾选即保存：DEFAULT_PARSE 存默认解析器名，PARSE_ENABLED 存启用列表（逗号分隔）。
 */
public class ParseSettingDialog extends BaseDialog {

    public interface OnChangedListener {
        void onChanged();
    }

    private OnChangedListener changedListener;

    public ParseSettingDialog(@NonNull @NotNull Context context) {
        super(context);
        setContentView(R.layout.dialog_parse_setting);
    }

    public void setOnChangedListener(OnChangedListener listener) {
        this.changedListener = listener;
    }

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        final List<ParseBean> parsers = new ArrayList<>(ApiConfig.get().getParseBeanList());
        if (parsers.isEmpty()) {
            dismiss();
            return;
        }
        final Set<String> enabled = new HashSet<>(ApiConfig.get().getEnabledParserSet());
        final ParseSettingAdapter adapter = new ParseSettingAdapter(enabled, null);
        adapter.setListener(new ParseSettingAdapter.OnChangedListener() {
            @Override
            public void onChanged() {
                // 默认解析器
                String defName = adapter.getCurrentDefault();
                if (defName != null) {
                    for (ParseBean pb : parsers) {
                        if (pb.getName().equals(defName)) {
                            ApiConfig.get().setDefaultParse(pb);
                            break;
                        }
                    }
                }
                // 启用列表
                Hawk.put(HawkConfig.PARSE_ENABLED, join(enabled));
                if (changedListener != null) changedListener.onChanged();
            }
        });
        TvRecyclerView list = findViewById(R.id.list);
        list.setAdapter(adapter);
        String currentDefault = ApiConfig.get().getDefaultParse() != null
                ? ApiConfig.get().getDefaultParse().getName() : "";
        adapter.setData(parsers, currentDefault);
        int firstItem = 1; // 跳过 "默认解析器" 标题
        list.setSelectedPosition(firstItem);
        list.post(new Runnable() {
            @Override
            public void run() {
                View v = list.getLayoutManager() != null
                        ? list.getLayoutManager().findViewByPosition(firstItem) : null;
                if (v != null) {
                    v.setFocusable(true);
                    v.requestFocus();
                    v.requestFocusFromTouch();
                }
            }
        });
    }

    private static String join(Set<String> set) {
        StringBuilder sb = new StringBuilder();
        for (String s : set) {
            if (sb.length() > 0) sb.append(",");
            sb.append(s);
        }
        return sb.toString();
    }
}