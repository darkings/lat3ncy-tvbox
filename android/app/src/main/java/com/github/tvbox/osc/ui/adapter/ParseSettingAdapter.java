package com.github.tvbox.osc.ui.adapter;

import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.widget.TextView;

import androidx.annotation.NonNull;
import androidx.recyclerview.widget.RecyclerView;

import com.github.tvbox.osc.R;
import com.github.tvbox.osc.bean.ParseBean;
import com.github.tvbox.osc.util.FastClickCheckUtil;

import java.util.ArrayList;
import java.util.List;
import java.util.Set;

/**
 * 解析器设置列表（单列表 + 分区标题）：
 * "默认解析器"区 = 全部解析器（Ponyo解析 恒在，✓ 标记当前默认，点击即设为默认）；
 * "启用解析器"区 = type-0 解析器（✓ 标记启用，点击切换，Ponyo解析 恒启用不列出）。
 */
public class ParseSettingAdapter extends RecyclerView.Adapter<ParseSettingAdapter.VH> {

    public static final int TYPE_HEADER_DEFAULT = 0;
    public static final int TYPE_ITEM_DEFAULT = 1;
    public static final int TYPE_HEADER_ENABLE = 2;
    public static final int TYPE_ITEM_ENABLE = 3;

    public interface OnChangedListener {
        void onChanged();
    }

    static class Row {
        final int kind;
        final ParseBean pb;

        Row(int kind, ParseBean pb) {
            this.kind = kind;
            this.pb = pb;
        }
    }

    private OnChangedListener listener;
    private final List<Row> data = new ArrayList<>();
    private String currentDefault;
    private final Set<String> enabled;

    public ParseSettingAdapter(Set<String> enabled, OnChangedListener listener) {
        this.enabled = enabled;
        this.listener = listener;
    }

    public void setListener(OnChangedListener listener) {
        this.listener = listener;
    }

    public void setData(List<ParseBean> parsers, String currentDefaultName) {
        data.clear();
        currentDefault = currentDefaultName;
        data.add(new Row(TYPE_HEADER_DEFAULT, null));
        for (ParseBean pb : parsers) {
            data.add(new Row(TYPE_ITEM_DEFAULT, pb));
        }
        data.add(new Row(TYPE_HEADER_ENABLE, null));
        for (ParseBean pb : parsers) {
            if (pb.getType() != 1) {
                data.add(new Row(TYPE_ITEM_ENABLE, pb));
            }
        }
        notifyDataSetChanged();
    }

    public String getCurrentDefault() {
        return currentDefault;
    }

    static String platformTags(ParseBean pb) {
        Set<String> plats = pb.getPlatforms();
        if (plats == null || plats.isEmpty()) {
            return "全平台";
        }
        StringBuilder sb = new StringBuilder();
        for (String f : plats) {
            if (sb.length() > 0) sb.append("/");
            switch (f) {
                case "qq": sb.append("腾讯"); break;
                case "mgtv": sb.append("芒果"); break;
                case "qiyi": sb.append("爱奇艺"); break;
                case "youku": sb.append("优酷"); break;
                default: sb.append(f);
            }
        }
        return sb.toString();
    }

    @Override
    public int getItemViewType(int position) {
        return data.get(position).kind;
    }

    @NonNull
    @Override
    public VH onCreateViewHolder(@NonNull ViewGroup parent, int viewType) {
        LayoutInflater inflater = LayoutInflater.from(parent.getContext());
        if (viewType == TYPE_HEADER_DEFAULT || viewType == TYPE_HEADER_ENABLE) {
            View v = inflater.inflate(R.layout.item_parse_header, parent, false);
            return new VH(v, true);
        }
        View v = inflater.inflate(R.layout.item_parse_setting, parent, false);
        return new VH(v, false);
    }

    @Override
    public void onBindViewHolder(@NonNull VH holder, int position) {
        Row row = data.get(position);
        if (holder.isHeader) {
            holder.tvHeader.setText(row.kind == TYPE_HEADER_DEFAULT ? "默认解析器" : "启用解析器（服务器解析用，多选）");
            return;
        }
        ParseBean pb = row.pb;
        String name = pb.getName();
        if (pb.getType() == 1) {
            holder.tvName.setText("Ponyo解析（智能多解析）");
        } else {
            holder.tvName.setText(name + "  ·  " + platformTags(pb));
        }
        boolean checked = row.kind == TYPE_ITEM_DEFAULT
                ? name.equals(currentDefault)
                : enabled.isEmpty() || enabled.contains(name);
        holder.tvMark.setText(checked ? "✓" : "");
        holder.itemView.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                FastClickCheckUtil.check(v);
                if (row.kind == TYPE_ITEM_DEFAULT) {
                    currentDefault = name;
                    notifyDataSetChanged();
                } else {
                    if (enabled.contains(name)) enabled.remove(name);
                    else enabled.add(name);
                    notifyDataSetChanged();
                }
                if (listener != null) listener.onChanged();
            }
        });
    }

    @Override
    public int getItemCount() {
        return data.size();
    }

    static class VH extends RecyclerView.ViewHolder {
        final boolean isHeader;
        TextView tvHeader;
        TextView tvName;
        TextView tvMark;

        VH(@NonNull View itemView, boolean isHeader) {
            super(itemView);
            this.isHeader = isHeader;
            if (isHeader) {
                tvHeader = itemView.findViewById(R.id.tvHeader);
            } else {
                tvName = itemView.findViewById(R.id.tvName);
                tvMark = itemView.findViewById(R.id.tvMark);
            }
        }
    }
}