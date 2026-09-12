package com.github.tvbox.osc.ui.adapter;

import android.text.TextUtils;
import android.view.View;
import android.widget.FrameLayout;
import android.widget.ImageView;
import android.widget.TextView;

import com.chad.library.adapter.base.BaseQuickAdapter;
import com.chad.library.adapter.base.BaseViewHolder;
import com.github.tvbox.osc.R;
import com.github.tvbox.osc.api.ApiConfig;
import com.github.tvbox.osc.bean.SourceBean;
import com.github.tvbox.osc.bean.VodInfo;
import com.github.tvbox.osc.util.ImgUtil;
import com.github.tvbox.osc.util.PosterCardLayout;
import com.github.tvbox.osc.util.PosterMetaFormatter;

import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

import me.jessyan.autosize.utils.AutoSizeUtils;

/** History cards use the shared poster hierarchy and a primary selected outline in edit mode. */
public class HistoryAdapter extends BaseQuickAdapter<VodInfo, BaseViewHolder> {
    private static final int POSTER_WIDTH = 200;
    private static final int POSTER_HEIGHT = 300;
    private final Set<String> selectedKeys = new HashSet<>();
    private boolean editMode;

    public HistoryAdapter() {
        super(R.layout.item_grid, new ArrayList<VodInfo>());
    }

    public void setEditMode(boolean editMode) {
        this.editMode = editMode;
        if (!editMode) selectedKeys.clear();
        notifyDataSetChanged();
    }

    public boolean isEditMode() {
        return editMode;
    }

    public void toggleSelected(int position) {
        if (position < 0 || position >= getData().size()) return;
        String key = keyOf(getData().get(position));
        if (!selectedKeys.add(key)) selectedKeys.remove(key);
        notifyItemChanged(position);
    }

    public int getSelectedCount() {
        return selectedKeys.size();
    }

    public List<VodInfo> getSelectedItems() {
        List<VodInfo> result = new ArrayList<>();
        for (VodInfo item : getData()) {
            if (selectedKeys.contains(keyOf(item))) result.add(item);
        }
        return result;
    }

    public void clearSelection() {
        selectedKeys.clear();
        notifyDataSetChanged();
    }

    public String getItemKey(int position) {
        return position < 0 || position >= getData().size() ? null : keyOf(getData().get(position));
    }

    public int findPosition(String key) {
        if (key == null) return -1;
        for (int i = 0; i < getData().size(); i++) {
            if (key.equals(keyOf(getData().get(i)))) return i;
        }
        return -1;
    }

    private String keyOf(VodInfo item) {
        if (item == null) return "";
        return String.valueOf(item.sourceKey) + "\n" + String.valueOf(item.id);
    }

    @Override
    protected void convert(BaseViewHolder helper, VodInfo item) {
        boolean selected = editMode && selectedKeys.contains(keyOf(item));
        PosterMetaFormatter.Meta meta = PosterMetaFormatter.forVodInfo(item);

        helper.itemView.setContentDescription(selected
                ? meta.contentDescription + "，已选"
                : meta.contentDescription);
        helper.getView(R.id.delFrameLayout).setVisibility(selected ? View.VISIBLE : View.GONE);
        helper.getView(R.id.imageView).setVisibility(View.GONE);

        SourceBean source = item == null ? null : ApiConfig.get().getSource(item.sourceKey);
        TextView sourceView = helper.getView(R.id.tvYear);
        setOptional(sourceView, source == null ? "" : source.getName());
        helper.setVisible(R.id.tvLang, false);
        helper.setVisible(R.id.tvArea, false);
        helper.setVisible(R.id.tvActor, false);
        PosterCardLayout.apply(helper.itemView, meta);

        bindImage(helper.getView(R.id.ivThumb), item == null ? "" : item.pic, meta.title);
    }

    private void bindImage(ImageView imageView, String rawPic, String label) {
        int width = AutoSizeUtils.mm2px(mContext, POSTER_WIDTH);
        int height = AutoSizeUtils.mm2px(mContext, POSTER_HEIGHT);
        int radius = AutoSizeUtils.dp2px(mContext, 12);
        String pic = rawPic == null ? "" : rawPic.trim();
        imageView.setImageDrawable(ImgUtil.createImagePlaceholderDrawable(width, height, radius));
        if (!TextUtils.isEmpty(pic)) ImgUtil.load(pic, imageView, radius, width, height, label);
    }

    private static void setOptional(TextView view, String value) {
        if (TextUtils.isEmpty(value)) {
            view.setText("");
            view.setVisibility(View.GONE);
        } else {
            view.setText(value);
            view.setVisibility(View.VISIBLE);
        }
    }
}
