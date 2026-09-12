package com.github.tvbox.osc.ui.fragment;

import android.content.DialogInterface;
import android.content.Intent;
import android.database.Cursor;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Environment;
import android.provider.DocumentsContract;
import android.provider.OpenableColumns;
import android.os.Handler;
import android.view.View;
import android.view.ViewGroup;
import android.view.ViewTreeObserver;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

import androidx.annotation.NonNull;
import androidx.appcompat.widget.SwitchCompat;
import androidx.recyclerview.widget.DiffUtil;

import com.github.tvbox.osc.R;
import com.github.tvbox.osc.api.ApiConfig;
import com.github.tvbox.osc.api.DanmakuApi;
import com.github.tvbox.osc.base.BaseActivity;
import com.github.tvbox.osc.base.BaseLazyFragment;
import com.github.tvbox.osc.bean.IJKCode;
import com.github.tvbox.osc.bean.ParseBean;
import com.github.tvbox.osc.bean.SourceBean;
import com.github.tvbox.osc.event.RefreshEvent;
import com.github.tvbox.osc.player.thirdparty.RemoteTVBox;
import com.github.tvbox.osc.ui.activity.LocalFileActivity;
import com.github.tvbox.osc.ui.activity.SettingActivity;
import com.github.tvbox.osc.ui.adapter.ApiHistoryDialogAdapter;
import com.github.tvbox.osc.ui.adapter.SelectDialogAdapter;
import com.github.tvbox.osc.ui.dialog.AboutDialog;
import com.github.tvbox.osc.ui.dialog.ApiDialog;
import com.github.tvbox.osc.ui.dialog.ApiHistoryDialog;
import com.github.tvbox.osc.ui.dialog.BackupDialog;
import com.github.tvbox.osc.ui.dialog.DanmuApiDialog;
import com.github.tvbox.osc.ui.dialog.ParseSettingDialog;
import com.github.tvbox.osc.ui.dialog.SearchRemoteTvDialog;
import com.github.tvbox.osc.ui.dialog.SelectDialog;
import com.github.tvbox.osc.ui.dialog.XWalkInitDialog;
import com.github.tvbox.osc.util.DanmuHelper;
import com.github.tvbox.osc.util.FastClickCheckUtil;
import com.github.tvbox.osc.util.FileUtils;
import com.github.tvbox.osc.util.HawkConfig;
import com.github.tvbox.osc.util.HistoryHelper;
import com.github.tvbox.osc.util.LOG;
import com.github.tvbox.osc.util.OkGoHelper;
import com.github.tvbox.osc.util.PlayerHelper;
import com.github.tvbox.osc.viewmodel.SourceViewModel;
import com.lzy.okgo.OkGo;
import com.lzy.okgo.callback.FileCallback;
import com.lzy.okgo.model.Progress;
import com.lzy.okgo.model.Response;
import com.orhanobut.hawk.Hawk;
import com.hjq.permissions.OnPermissionCallback;
import com.hjq.permissions.Permission;
import com.hjq.permissions.XXPermissions;

import org.greenrobot.eventbus.EventBus;
import org.jetbrains.annotations.NotNull;

import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.util.ArrayList;
import java.util.List;

import okhttp3.HttpUrl;
import tv.danmaku.ijk.media.player.IjkMediaPlayer;
import com.github.tvbox.osc.util.ToastUtil;

/**
 * @author pj567
 * @date :2020/12/23
 * @description:
 */
public class ModelSettingFragment extends BaseLazyFragment {
    private static final int REQUEST_LOCAL_CONFIG = 1001;
    private TextView tvDebugOpen;
    private TextView tvMediaCodec;
    private TextView tvParseWebView;
    private TextView tvParseSetting;
    private TextView tvPlay;
    private TextView tvRender;
    private TextView tvScale;
    private TextView tvApi;
    private TextView tvApiLine;
    private View llApi;
    private View llApiHistory;
    private View llApiLine;
    private TextView tvHomeApi;
    private TextView tvDns;
    private TextView tvHomeRec;
    private TextView tvHistoryNum;
    private TextView tvSearchView;
    private SwitchCompat tvShowPreviewText;
    private SwitchCompat tvFastSearchText;
    private SwitchCompat tvm3u8AdText;
    private SwitchCompat tvAutoSwitchLineText;
    private SwitchCompat tvRecStyleText;
    private SwitchCompat tvIjkCachePlay;
    private SwitchCompat tvLiveHlsProxy; // 直播HLS整片代理开关
    private TextView tvHomeDefaultShow;
    private ApiDialog apiDialog;
    private boolean selectLocalLive;
    private SwitchCompat tvDanmuOpenText;
    private TextView tvDanmuApiText;
    private ScrollView settingScrollView;
    private int lastFocusedViewId = View.NO_ID;
    private int lastScrollY;
    private ViewTreeObserver.OnGlobalFocusChangeListener focusMemoryListener;

    public static ModelSettingFragment newInstance() {
        return new ModelSettingFragment().setArguments();
    }

    /** 按分组创建（0=通用 1=内容 2=播放 3=网络 4=外观 5=数据与关于） */
    public static ModelSettingFragment newInstance(int group) {
        ModelSettingFragment f = new ModelSettingFragment();
        Bundle b = new Bundle();
        b.putInt("group", group);
        f.setArguments(b);
        return f;
    }

    public ModelSettingFragment setArguments() {
        return this;
    }

    /** 隐藏非本组行（行容器 android:tag="group_xxx"） */
    private void applyGroupVisibility() {
        View root = getView();
        if (!(root instanceof ViewGroup)) {
            android.util.Log.i("ModelSetting", "root null or not ViewGroup: " + root);
            return;
        }
        int group = getArguments() != null ? getArguments().getInt("group", 0) : 0;
        final String[] groups = {
                "group_general", "group_content", "group_player",
                "group_network", "group_appearance", "group_data"
        };
        if (group < 0 || group >= groups.length) group = 0;
        String target = groups[group];
        ViewGroup list = null;
        // 根布局 FrameLayout -> ScrollView -> LinearLayout(vertical)
        ViewGroup frame = (ViewGroup) root;
        for (int i = 0; i < frame.getChildCount(); i++) {
            View c = frame.getChildAt(i);
            if (c instanceof ScrollView && ((ScrollView) c).getChildCount() > 0
                    && ((ScrollView) c).getChildAt(0) instanceof ViewGroup) {
                list = (ViewGroup) ((ScrollView) c).getChildAt(0);
                break;
            }
        }
        if (list == null) {
            android.util.Log.i("ModelSetting", "list null, frame children=" + frame.getChildCount());
            return;
        }
        android.util.Log.i("ModelSetting", "group=" + group + " target=" + target + " rows=" + list.getChildCount());
        int shown = 0;
        for (int i = 0; i < list.getChildCount(); i++) {
            View child = list.getChildAt(i);
            Object tag = child.getTag();
            if (tag == null || !target.equals(tag)) {
                child.setVisibility(View.GONE);
            } else {
                shown++;
                android.util.Log.i("ModelSetting", "show row " + i + " tag=" + tag);
            }
        }
        android.util.Log.i("ModelSetting", "shown rows=" + shown);
    }

    @Override
    protected int getLayoutResID() {
        return R.layout.fragment_model;
    }

    @Override
    protected void init() {
        applyGroupVisibility();
        initFocusMemory();
        tvFastSearchText = findViewById(R.id.showFastSearchText);
        tvFastSearchText.setChecked(Hawk.get(HawkConfig.FAST_SEARCH_MODE, true));
        tvm3u8AdText = findViewById(R.id.m3u8AdText);
        tvm3u8AdText.setChecked(Hawk.get(HawkConfig.M3U8_PURIFY, false));
        tvDanmuOpenText = findViewById(R.id.danmuOpenText);
        tvDanmuOpenText.setChecked(DanmuHelper.isOpen());
        tvDanmuApiText = findViewById(R.id.danmuApiText);
        refreshDanmuApiText();
        tvAutoSwitchLineText = findViewById(R.id.autoSwitchLineText);
        tvAutoSwitchLineText.setChecked(Hawk.get(HawkConfig.AUTO_SWITCH_LINE, true));
        tvRecStyleText = findViewById(R.id.showRecStyleText);
        tvRecStyleText.setChecked(Hawk.get(HawkConfig.HOME_REC_STYLE, false));
        tvShowPreviewText = findViewById(R.id.showPreviewText);
        tvShowPreviewText.setChecked(Hawk.get(HawkConfig.SHOW_PREVIEW, true));
        tvDebugOpen = findViewById(R.id.tvDebugOpen);
        tvParseWebView = findViewById(R.id.tvParseWebView);
        tvMediaCodec = findViewById(R.id.tvMediaCodec);
        tvPlay = findViewById(R.id.tvPlay);
        tvRender = findViewById(R.id.tvRenderType);
        tvScale = findViewById(R.id.tvScaleType);
        llApi = findViewById(R.id.llApi);
        llApiHistory = findViewById(R.id.llApiHistory);
        llApiLine = findViewById(R.id.llApiLine);
        tvApi = findViewById(R.id.tvApi);
        tvApiLine = findViewById(R.id.tvApiLine);
        tvHomeApi = findViewById(R.id.tvHomeApi);
        tvDns = findViewById(R.id.tvDns);
        tvHomeRec = findViewById(R.id.tvHomeRec);
        tvHistoryNum = findViewById(R.id.tvHistoryNum);
        tvSearchView = findViewById(R.id.tvSearchView);
        tvIjkCachePlay = findViewById(R.id.tvIjkCachePlay);
        tvLiveHlsProxy = findViewById(R.id.tvLiveHlsProxy); // 直播HLS代理开关view
        tvMediaCodec.setText(Hawk.get(HawkConfig.IJK_CODEC, "硬解码"));
        tvDebugOpen.setText(Hawk.get(HawkConfig.DEBUG_OPEN, false) ? "已打开" : "已关闭");
        tvParseWebView.setText(Hawk.get(HawkConfig.PARSE_WEBVIEW, true) ? "系统自带" : "XWalkView");
        bindApiSummary();
        llApi.setOnFocusChangeListener(new View.OnFocusChangeListener() {
            @Override
            public void onFocusChange(View v, boolean hasFocus) {
                bindApiSummary();
            }
        });
        refreshApiLineText();

        tvDns.setText(OkGoHelper.dnsHttpsList.get(Hawk.get(HawkConfig.DOH_URL, 0)));
        tvHomeRec.setText(getHomeRecName(Hawk.get(HawkConfig.HOME_REC, HawkConfig.DEFAULT_HOME_REC)));
        tvHistoryNum.setText(HistoryHelper.getHistoryNumName(Hawk.get(HawkConfig.HISTORY_NUM, 0)));
        tvSearchView.setText(getSearchView(Hawk.get(HawkConfig.SEARCH_VIEW, 0)));
        tvHomeApi.setText(ApiConfig.get().getHomeSourceBean().getName());
        tvScale.setText(PlayerHelper.getScaleName(Hawk.get(HawkConfig.PLAY_SCALE, 0)));
        tvPlay.setText(PlayerHelper.getPlayerName(Hawk.get(HawkConfig.PLAY_TYPE, 0)));
        tvRender.setText(PlayerHelper.getRenderName(Hawk.get(HawkConfig.PLAY_RENDER, 0)));
        tvIjkCachePlay.setChecked(Hawk.get(HawkConfig.IJK_CACHE_PLAY, false));
        tvLiveHlsProxy.setChecked(Hawk.get(HawkConfig.LIVE_HLS_PROXY, false)); // 直播HLS代理默认关
        tvHomeDefaultShow = findViewById(R.id.tvHomeText);
        tvHomeDefaultShow.setText(Hawk.get(HawkConfig.DEFAULT_LOAD_LIVE, false) ? "直播" : "点播");
        findViewById(R.id.llDebug).setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                FastClickCheckUtil.check(v);
                Hawk.put(HawkConfig.DEBUG_OPEN, !Hawk.get(HawkConfig.DEBUG_OPEN, false));
                tvDebugOpen.setText(Hawk.get(HawkConfig.DEBUG_OPEN, false) ? "已打开" : "已关闭");
            }
        });
        final SwitchCompat tvDynamicColor = findViewById(R.id.tvDynamicColor);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            tvDynamicColor.setChecked(Hawk.get(HawkConfig.DYNAMIC_COLOR, false));
            findViewById(R.id.llDynamicColor).setOnClickListener(new View.OnClickListener() {
                @Override
                public void onClick(View v) {
                    FastClickCheckUtil.check(v);
                    boolean enable = !Hawk.get(HawkConfig.DYNAMIC_COLOR, false);
                    Hawk.put(HawkConfig.DYNAMIC_COLOR, enable);
                    tvDynamicColor.setChecked(enable);
                    if (getActivity() != null) {
                        getActivity().recreate();
                    }
                }
            });
        } else {
            findViewById(R.id.llDynamicColor).setVisibility(View.GONE);
        }
        final SwitchCompat tvReduceMotion = findViewById(R.id.tvReduceMotion);
        tvReduceMotion.setChecked(Hawk.get(HawkConfig.REDUCE_MOTION, false));
        findViewById(R.id.llReduceMotion).setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                FastClickCheckUtil.check(v);
                boolean enable = !Hawk.get(HawkConfig.REDUCE_MOTION, false);
                Hawk.put(HawkConfig.REDUCE_MOTION, enable);
                tvReduceMotion.setChecked(enable);
            }
        });
        findViewById(R.id.llParseWebVew).setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                FastClickCheckUtil.check(v);
                boolean useSystem = !Hawk.get(HawkConfig.PARSE_WEBVIEW, true);
                Hawk.put(HawkConfig.PARSE_WEBVIEW, useSystem);
                tvParseWebView.setText(Hawk.get(HawkConfig.PARSE_WEBVIEW, true) ? "系统自带" : "XWalkView");
                if (!useSystem) {
                    ToastUtil.info(mContext, "注意: XWalkView只适用于部分低Android版本，Android5.0以上推荐使用系统自带", Toast.LENGTH_LONG);
                    XWalkInitDialog dialog = new XWalkInitDialog(mContext);
                    dialog.setOnListener(new XWalkInitDialog.OnListener() {
                        @Override
                        public void onchange() {
                        }
                    });
                    dialog.show();
                }
            }
        });
        findViewById(R.id.llBackup).setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                FastClickCheckUtil.check(v);
                BackupDialog dialog = new BackupDialog(mActivity);
                dialog.show();
            }
        });
        // 解析器设置：默认解析器（单选）+ 启用解析器（多选）；仅订阅含官方源时显示
        tvParseSetting = findViewById(R.id.tvParseSetting);
        findViewById(R.id.llParseSetting).setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                FastClickCheckUtil.check(v);
                ParseSettingDialog dialog = new ParseSettingDialog(mActivity);
                dialog.setOnChangedListener(new ParseSettingDialog.OnChangedListener() {
                    @Override
                    public void onChanged() {
                        refreshParseSettingSummary();
                    }
                });
                dialog.show();
            }
        });
        refreshParseSettingVisibility();
        refreshParseSettingSummary();
        findViewById(R.id.llAbout).setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                FastClickCheckUtil.check(v);
                AboutDialog dialog = new AboutDialog(mActivity);
                dialog.show();
            }
        });
        findViewById(R.id.llWp).setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                FastClickCheckUtil.check(v);
                if (!ApiConfig.get().wallpaper.isEmpty())
                    OkGo.<File>get(ApiConfig.get().wallpaper).execute(new FileCallback(requireActivity().getFilesDir().getAbsolutePath(), "wp") {
                        @Override
                        public void onSuccess(Response<File> response) {
                            ((BaseActivity) requireActivity()).changeWallpaper(true);
                        }

                        @Override
                        public void onError(Response<File> response) {
                            super.onError(response);
                        }

                        @Override
                        public void downloadProgress(Progress progress) {
                            super.downloadProgress(progress);
                        }
                    });
            }
        });
        findViewById(R.id.llWpRecovery).setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                FastClickCheckUtil.check(v);
                File wp = new File(requireActivity().getFilesDir().getAbsolutePath() + "/wp");
                if (wp.exists())
                    wp.delete();
                ((BaseActivity) requireActivity()).changeWallpaper(true);
            }
        });
        findViewById(R.id.llHomeApi).setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                FastClickCheckUtil.check(v);
                List<SourceBean> sites = ApiConfig.get().getSwitchSourceBeanList();
                if (sites.size() > 0) {
                    SelectDialog<SourceBean> dialog = new SelectDialog<>(mActivity);
                    dialog.setTip("请选择首页数据源");
                    int select = sites.indexOf(ApiConfig.get().getHomeSourceBean());
                    if (select<0) select = 0;
                    dialog.setAdapter(new SelectDialogAdapter.SelectDialogInterface<SourceBean>() {
                        @Override
                        public void click(SourceBean value, int pos) {
                            dialog.dismiss();
                            ApiConfig.get().setSourceBean(value);
                            tvHomeApi.setText(ApiConfig.get().getHomeSourceBean().getName());
                            EventBus.getDefault().post(new RefreshEvent(RefreshEvent.TYPE_HOME_SOURCE_CHANGE));
                        }

                        @Override
                        public String getDisplay(SourceBean val) {
                            return val.getName();
                        }
                    }, new DiffUtil.ItemCallback<SourceBean>() {
                        @Override
                        public boolean areItemsTheSame(@NonNull @NotNull SourceBean oldItem, @NonNull @NotNull SourceBean newItem) {
                            return oldItem == newItem;
                        }

                        @Override
                        public boolean areContentsTheSame(@NonNull @NotNull SourceBean oldItem, @NonNull @NotNull SourceBean newItem) {
                            return oldItem.getKey().equals(newItem.getKey());
                        }
                    }, sites, select);
                    dialog.show();
                }
            }
        });
        findViewById(R.id.llDns).setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                FastClickCheckUtil.check(v);
                int dohUrl = Hawk.get(HawkConfig.DOH_URL, 0);

                SelectDialog<String> dialog = new SelectDialog<>(mActivity);
                dialog.setTip("请选择安全DNS");
                dialog.setAdapter(new SelectDialogAdapter.SelectDialogInterface<String>() {
                    @Override
                    public void click(String value, int pos) {
                        tvDns.setText(OkGoHelper.dnsHttpsList.get(pos));
                        Hawk.put(HawkConfig.DOH_URL, pos);
//                        String url = OkGoHelper.getDohUrl(pos);
//                        OkGoHelper.dnsOverHttps.setUrl(url.isEmpty() ? null : HttpUrl.get(url));
                        OkGoHelper.reloadDns();
                        IjkMediaPlayer.toggleDotPort(pos > 0);
                    }

                    @Override
                    public String getDisplay(String val) {
                        return val;
                    }
                }, new DiffUtil.ItemCallback<String>() {
                    @Override
                    public boolean areItemsTheSame(@NonNull @NotNull String oldItem, @NonNull @NotNull String newItem) {
                        return oldItem.equals(newItem);
                    }

                    @Override
                    public boolean areContentsTheSame(@NonNull @NotNull String oldItem, @NonNull @NotNull String newItem) {
                        return oldItem.equals(newItem);
                    }
                }, OkGoHelper.dnsHttpsList, dohUrl);
                dialog.show();
            }
        });
        findViewById(R.id.llApi).setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                FastClickCheckUtil.check(v);
                apiDialog = new ApiDialog(mActivity);
                ApiDialog dialog = apiDialog;
                EventBus.getDefault().register(dialog);
                dialog.setOnListener(new ApiDialog.OnListener() {
                    @Override
                    public void onchange(String api) {
                        String oldApi = Hawk.get(HawkConfig.API_URL, "");
                        Hawk.put(HawkConfig.API_URL, api);
                        if (!HistoryHelper.isApiLineHistory(api)) {
                            HistoryHelper.clearApiLineList();
                        }
                        bindApiSummary();
                        refreshApiLineText();
                        if (!oldApi.equals(api)) {
                            restartAppAfterConfigChanged();
                        }
                    }

                    @Override
                    public void onLocalConfig(boolean live) {
                        openLocalConfig(live);
                    }
                });
                dialog.setOnDismissListener(new DialogInterface.OnDismissListener() {
                    @Override
                    public void onDismiss(DialogInterface dialog) {
                        ((BaseActivity) mActivity).hideSysBar();
                        EventBus.getDefault().unregister(dialog);
                        apiDialog = null;
                    }
                });
                dialog.show();
            }
        });

        findViewById(R.id.llApiHistory).setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                ArrayList<String> history = Hawk.get(HawkConfig.API_HISTORY, new ArrayList<String>());
                // FIX-07: 历史为空时给出提示，避免用户误以为按钮失效（原代码静默 return）
                if (history.isEmpty()) {
                    Toast.makeText(mContext, "暂无配置历史", Toast.LENGTH_SHORT).show();
                    return;
                }
                String current = Hawk.get(HawkConfig.API_URL, "");
                int idx = 0;
                if (history.contains(current))
                    idx = history.indexOf(current);
                ApiHistoryDialog dialog = new ApiHistoryDialog(mActivity);
                dialog.setTip("历史配置列表");
                dialog.setAdapter(new ApiHistoryDialogAdapter.SelectDialogInterface() {
                    @Override
                    public void click(String value) {
                        String oldApi = Hawk.get(HawkConfig.API_URL, "");
                        if (!HistoryHelper.isApiLineHistory(value)) {
                            HistoryHelper.clearApiLineList();
                        }
                        Hawk.put(HawkConfig.API_URL, value);
                        Hawk.put(HawkConfig.LIVE_API_URL, value);
                        HistoryHelper.setLiveApiHistory(value);
                        bindApiSummary();
                        refreshApiLineText();
                        dialog.dismiss();
                        if (!oldApi.equals(value)) {
                            restartAppAfterConfigChanged();
                        }
                    }

                    @Override
                    public void del(String value, ArrayList<String> data) {
                        Hawk.put(HawkConfig.API_HISTORY, data);
                    }
                }, history, idx);
                dialog.show();
            }
        });

        findViewById(R.id.llApiLine).setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                ArrayList<String> apiLines = Hawk.get(HawkConfig.API_LINE_LIST, new ArrayList<String>());
                if (apiLines.isEmpty()) {
                    ToastUtil.error(mContext, "线路列表为空");
                    return;
                }
                String current = Hawk.get(HawkConfig.API_URL, "");
                int idx = 0;
                for (int i = 0; i < apiLines.size(); i++) {
                    if (current.equals(HistoryHelper.getApiLineUrl(apiLines.get(i)))) {
                        idx = i;
                        break;
                    }
                }
                SelectDialog<String> dialog = new SelectDialog<>(mActivity);
                dialog.setTip("线路选择");
                dialog.setAdapter(new SelectDialogAdapter.SelectDialogInterface<String>() {
                    @Override
                    public void click(String value, int pos) {
                        String newApi = HistoryHelper.getApiLineUrl(value);
                        String oldApi = Hawk.get(HawkConfig.API_URL, "");
                        if (newApi.isEmpty()) {
                            return;
                        }
                        Hawk.put(HawkConfig.API_URL, newApi);
                        Hawk.put(HawkConfig.LIVE_API_URL, newApi);
                        HistoryHelper.setLiveApiHistory(newApi);
                        bindApiSummary();
                        refreshApiLineText();
                        dialog.dismiss();
                        if (!oldApi.equals(newApi)) {
                            restartAppAfterConfigChanged();
                        }
                    }

                    @Override
                    public String getDisplay(String val) {
                        return HistoryHelper.getApiLineName(val);
                    }
                }, SelectDialogAdapter.stringDiff, apiLines, idx);
                dialog.show();
            }
        });


        findViewById(R.id.llMediaCodec).setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                List<IJKCode> ijkCodes = ApiConfig.get().getIjkCodes();
                if (ijkCodes == null || ijkCodes.size() == 0)
                    return;
                FastClickCheckUtil.check(v);

                int defaultPos = 0;
                String ijkSel = Hawk.get(HawkConfig.IJK_CODEC, "硬解码");
                for (int j = 0; j < ijkCodes.size(); j++) {
                    if (ijkSel.equals(ijkCodes.get(j).getName())) {
                        defaultPos = j;
                        break;
                    }
                }

                SelectDialog<IJKCode> dialog = new SelectDialog<>(mActivity);
                dialog.setTip("请选择IJK解码");
                dialog.setAdapter(new SelectDialogAdapter.SelectDialogInterface<IJKCode>() {
                    @Override
                    public void click(IJKCode value, int pos) {
                        value.selected(true);
                        tvMediaCodec.setText(value.getName());
                    }

                    @Override
                    public String getDisplay(IJKCode val) {
                        return val.getName();
                    }
                }, new DiffUtil.ItemCallback<IJKCode>() {
                    @Override
                    public boolean areItemsTheSame(@NonNull @NotNull IJKCode oldItem, @NonNull @NotNull IJKCode newItem) {
                        return oldItem == newItem;
                    }

                    @Override
                    public boolean areContentsTheSame(@NonNull @NotNull IJKCode oldItem, @NonNull @NotNull IJKCode newItem) {
                        return oldItem.getName().equals(newItem.getName());
                    }
                }, ijkCodes, defaultPos);
                dialog.show();
            }
        });
        findViewById(R.id.llScale).setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                FastClickCheckUtil.check(v);
                int defaultPos = Hawk.get(HawkConfig.PLAY_SCALE, 0);
                ArrayList<Integer> players = new ArrayList<>();
                players.add(0);
                players.add(1);
                players.add(2);
                players.add(3);
                players.add(4);
                players.add(5);
                SelectDialog<Integer> dialog = new SelectDialog<>(mActivity);
                dialog.setTip("请选择默认画面缩放");
                dialog.setAdapter(new SelectDialogAdapter.SelectDialogInterface<Integer>() {
                    @Override
                    public void click(Integer value, int pos) {
                        Hawk.put(HawkConfig.PLAY_SCALE, value);
                        tvScale.setText(PlayerHelper.getScaleName(value));
                    }

                    @Override
                    public String getDisplay(Integer val) {
                        return PlayerHelper.getScaleName(val);
                    }
                }, new DiffUtil.ItemCallback<Integer>() {
                    @Override
                    public boolean areItemsTheSame(@NonNull @NotNull Integer oldItem, @NonNull @NotNull Integer newItem) {
                        return oldItem.intValue() == newItem.intValue();
                    }

                    @Override
                    public boolean areContentsTheSame(@NonNull @NotNull Integer oldItem, @NonNull @NotNull Integer newItem) {
                        return oldItem.intValue() == newItem.intValue();
                    }
                }, players, defaultPos);
                dialog.show();
            }
        });
        findViewById(R.id.llPlay).setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                FastClickCheckUtil.check(v);
                int playerType = Hawk.get(HawkConfig.PLAY_TYPE, 0);
                int defaultPos = 0;
                ArrayList<Integer> players = PlayerHelper.getExistPlayerTypes();
                ArrayList<Integer> renders = new ArrayList<>();
                for(int p = 0; p<players.size(); p++) {
                    renders.add(p);
                    if (players.get(p) == playerType) {
                        defaultPos = p;
                    }
                }
                SelectDialog<Integer> dialog = new SelectDialog<>(mActivity);
                dialog.setTip("请选择默认播放器");
                dialog.setAdapter(new SelectDialogAdapter.SelectDialogInterface<Integer>() {
                    @Override
                    public void click(Integer value, int pos) {
                        Integer thisPlayerType = players.get(pos);
                        Hawk.put(HawkConfig.PLAY_TYPE, thisPlayerType);
                        tvPlay.setText(PlayerHelper.getPlayerName(thisPlayerType));
                        PlayerHelper.init();
                    }

                    @Override
                    public String getDisplay(Integer val) {
                        Integer playerType = players.get(val);
                        return PlayerHelper.getPlayerName(playerType);
                    }
                }, new DiffUtil.ItemCallback<Integer>() {
                    @Override
                    public boolean areItemsTheSame(@NonNull @NotNull Integer oldItem, @NonNull @NotNull Integer newItem) {
                        return oldItem.intValue() == newItem.intValue();
                    }

                    @Override
                    public boolean areContentsTheSame(@NonNull @NotNull Integer oldItem, @NonNull @NotNull Integer newItem) {
                        return oldItem.intValue() == newItem.intValue();
                    }
                }, renders, defaultPos);
                dialog.show();
            }
        });
        findViewById(R.id.llRender).setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                FastClickCheckUtil.check(v);
                int defaultPos = Hawk.get(HawkConfig.PLAY_RENDER, 0);
                ArrayList<Integer> renders = new ArrayList<>();
                renders.add(0);
                renders.add(1);
                SelectDialog<Integer> dialog = new SelectDialog<>(mActivity);
                dialog.setTip("请选择默认渲染方式");
                dialog.setAdapter(new SelectDialogAdapter.SelectDialogInterface<Integer>() {
                    @Override
                    public void click(Integer value, int pos) {
                        Hawk.put(HawkConfig.PLAY_RENDER, value);
                        tvRender.setText(PlayerHelper.getRenderName(value));
                        PlayerHelper.init();
                    }

                    @Override
                    public String getDisplay(Integer val) {
                        return PlayerHelper.getRenderName(val);
                    }
                }, new DiffUtil.ItemCallback<Integer>() {
                    @Override
                    public boolean areItemsTheSame(@NonNull @NotNull Integer oldItem, @NonNull @NotNull Integer newItem) {
                        return oldItem.intValue() == newItem.intValue();
                    }

                    @Override
                    public boolean areContentsTheSame(@NonNull @NotNull Integer oldItem, @NonNull @NotNull Integer newItem) {
                        return oldItem.intValue() == newItem.intValue();
                    }
                }, renders, defaultPos);
                dialog.show();
            }
        });
        findViewById(R.id.llHomeRec).setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                FastClickCheckUtil.check(v);
                int defaultPos = Hawk.get(HawkConfig.HOME_REC, HawkConfig.DEFAULT_HOME_REC);
                ArrayList<Integer> types = new ArrayList<>();
                types.add(0);
                types.add(1);
                types.add(2);
                SelectDialog<Integer> dialog = new SelectDialog<>(mActivity);
                dialog.setTip("请选择首页列表数据");
                dialog.setAdapter(new SelectDialogAdapter.SelectDialogInterface<Integer>() {
                    @Override
                    public void click(Integer value, int pos) {
                        Hawk.put(HawkConfig.HOME_REC, value);
                        tvHomeRec.setText(getHomeRecName(value));
                    }

                    @Override
                    public String getDisplay(Integer val) {
                        return getHomeRecName(val);
                    }
                }, new DiffUtil.ItemCallback<Integer>() {
                    @Override
                    public boolean areItemsTheSame(@NonNull @NotNull Integer oldItem, @NonNull @NotNull Integer newItem) {
                        return oldItem.intValue() == newItem.intValue();
                    }

                    @Override
                    public boolean areContentsTheSame(@NonNull @NotNull Integer oldItem, @NonNull @NotNull Integer newItem) {
                        return oldItem.intValue() == newItem.intValue();
                    }
                }, types, defaultPos);
                dialog.show();
            }
        });
        findViewById(R.id.llSearchView).setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                FastClickCheckUtil.check(v);
                int defaultPos = Hawk.get(HawkConfig.SEARCH_VIEW, 0);
                ArrayList<Integer> types = new ArrayList<>();
                types.add(0);
                types.add(1);
                SelectDialog<Integer> dialog = new SelectDialog<>(mActivity);
                dialog.setTip("请选择搜索视图");
                dialog.setAdapter(new SelectDialogAdapter.SelectDialogInterface<Integer>() {
                    @Override
                    public void click(Integer value, int pos) {
                        Hawk.put(HawkConfig.SEARCH_VIEW, value);
                        tvSearchView.setText(getSearchView(value));
                    }

                    @Override
                    public String getDisplay(Integer val) {
                        return getSearchView(val);
                    }
                }, new DiffUtil.ItemCallback<Integer>() {
                    @Override
                    public boolean areItemsTheSame(@NonNull @NotNull Integer oldItem, @NonNull @NotNull Integer newItem) {
                        return oldItem.intValue() == newItem.intValue();
                    }

                    @Override
                    public boolean areContentsTheSame(@NonNull @NotNull Integer oldItem, @NonNull @NotNull Integer newItem) {
                        return oldItem.intValue() == newItem.intValue();
                    }
                }, types, defaultPos);
                dialog.show();
            }
        });
        SettingActivity.callback = new SettingActivity.DevModeCallback() {
            @Override
            public void onChange() {
                findViewById(R.id.llDebug).setVisibility(View.VISIBLE);
            }
        };

        findViewById(R.id.showPreview).setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                FastClickCheckUtil.check(v);
                Hawk.put(HawkConfig.SHOW_PREVIEW, !Hawk.get(HawkConfig.SHOW_PREVIEW, true));
                tvShowPreviewText.setChecked(Hawk.get(HawkConfig.SHOW_PREVIEW, true));
            }
        });
        findViewById(R.id.llHistoryNum).setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                FastClickCheckUtil.check(v);
                int defaultPos = Hawk.get(HawkConfig.HISTORY_NUM, 0);
                ArrayList<Integer> types = new ArrayList<>();
                types.add(0);
                types.add(1);
                types.add(2);
                SelectDialog<Integer> dialog = new SelectDialog<>(mActivity);
                dialog.setTip("保留历史记录数量");
                dialog.setAdapter(new SelectDialogAdapter.SelectDialogInterface<Integer>() {
                    @Override
                    public void click(Integer value, int pos) {
                        Hawk.put(HawkConfig.HISTORY_NUM, value);
                        tvHistoryNum.setText(HistoryHelper.getHistoryNumName(value));
                    }

                    @Override
                    public String getDisplay(Integer val) {
                        return HistoryHelper.getHistoryNumName(val);
                    }
                }, new DiffUtil.ItemCallback<Integer>() {
                    @Override
                    public boolean areItemsTheSame(@NonNull @NotNull Integer oldItem, @NonNull @NotNull Integer newItem) {
                        return oldItem.intValue() == newItem.intValue();
                    }

                    @Override
                    public boolean areContentsTheSame(@NonNull @NotNull Integer oldItem, @NonNull @NotNull Integer newItem) {
                        return oldItem.intValue() == newItem.intValue();
                    }
                }, types, defaultPos);
                dialog.show();
            }
        });
        findViewById(R.id.showFastSearch).setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                FastClickCheckUtil.check(v);
                Hawk.put(HawkConfig.FAST_SEARCH_MODE, !Hawk.get(HawkConfig.FAST_SEARCH_MODE, true));
                tvFastSearchText.setChecked(Hawk.get(HawkConfig.FAST_SEARCH_MODE, true));
            }
        });
        findViewById(R.id.m3u8Ad).setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                FastClickCheckUtil.check(v);
                boolean is_purify=Hawk.get(HawkConfig.M3U8_PURIFY, false);
                Hawk.put(HawkConfig.M3U8_PURIFY, !is_purify);
                tvm3u8AdText.setChecked(!is_purify);
            }
        });
        findViewById(R.id.danmuOpen).setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                FastClickCheckUtil.check(v);
                boolean open = !DanmuHelper.isOpen();
                DanmuHelper.setOpen(open);
                tvDanmuOpenText.setChecked(open);
            }
        });
        findViewById(R.id.danmuApi).setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                FastClickCheckUtil.check(v);
                DanmuApiDialog dialog = new DanmuApiDialog(mActivity);
                dialog.setOnListener(new DanmuApiDialog.OnListener() {
                    @Override
                    public void onChange(String api) {
                        refreshDanmuApiText();
                    }
                });
                dialog.show();
            }
        });
        findViewById(R.id.autoSwitchLine).setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                FastClickCheckUtil.check(v);
                boolean enable = !Hawk.get(HawkConfig.AUTO_SWITCH_LINE, true);
                Hawk.put(HawkConfig.AUTO_SWITCH_LINE, enable);
                tvAutoSwitchLineText.setChecked(enable);
            }
        });
        findViewById(R.id.llHomeRecStyle).setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                FastClickCheckUtil.check(v);
                Hawk.put(HawkConfig.HOME_REC_STYLE, !Hawk.get(HawkConfig.HOME_REC_STYLE, false));
                tvRecStyleText.setChecked(Hawk.get(HawkConfig.HOME_REC_STYLE, false));
            }
        });

        findViewById(R.id.llSearchTv).setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View view) {
                FastClickCheckUtil.check(view);
                loadingSearchRemoteTvDialog = new SearchRemoteTvDialog(mActivity);
                EventBus.getDefault().register(loadingSearchRemoteTvDialog);
                loadingSearchRemoteTvDialog.setTip("搜索附近TVBox");
                loadingSearchRemoteTvDialog.setOnDismissListener(new DialogInterface.OnDismissListener() {
                    @Override
                    public void onDismiss(DialogInterface dialogInterface) {
                        EventBus.getDefault().unregister(loadingSearchRemoteTvDialog);
                    }
                });
                loadingSearchRemoteTvDialog.show();

                RemoteTVBox tv = new RemoteTVBox();
                remoteTvHostList = new ArrayList<>();
                foundRemoteTv = false;
                view.postDelayed(new Runnable() {
                    @Override
                    public void run() {

                        new Thread(new Runnable() {
                            @Override
                            public void run() {
                                RemoteTVBox.searchAvalible(tv.new Callback() {
                                    @Override
                                    public void found(String viewHost, boolean end) {
                                        remoteTvHostList.add(viewHost);
                                        if (end) {
                                            foundRemoteTv = true;
                                            EventBus.getDefault().post(new RefreshEvent(RefreshEvent.TYPE_SETTING_SEARCH_TV));
                                        }
                                    }

                                    @Override
                                    public void fail(boolean all, boolean end) {
                                        if (end) {
                                            if (all) {
                                                foundRemoteTv = false;
                                            } else {
                                                foundRemoteTv = true;
                                            }
                                            EventBus.getDefault().post(new RefreshEvent(RefreshEvent.TYPE_SETTING_SEARCH_TV));
                                        }
                                    }
                                });
                            }
                        }).start();

                    }
                }, 500);


            }
        });

        //下次进入
        findViewById(R.id.tvHomeLive).setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                FastClickCheckUtil.check(v);
                Hawk.put(HawkConfig.DEFAULT_LOAD_LIVE, !Hawk.get(HawkConfig.DEFAULT_LOAD_LIVE, false));
                tvHomeDefaultShow.setText(Hawk.get(HawkConfig.DEFAULT_LOAD_LIVE, false) ? "直播" : "点播");
            }
        });

        findViewById(R.id.llIjkCachePlay).setOnClickListener((view -> onClickIjkCachePlay(view)));
        findViewById(R.id.llLiveHlsProxy).setOnClickListener((view -> onClickLiveHlsProxy(view))); // 直播HLS代理开关点击
        findViewById(R.id.llClearCache).setOnClickListener((view -> onClickClearCache(view)));
    }

    private void restartAppAfterConfigChanged() {
        ToastUtil.info(mContext, "配置已切换,即将重新加载!");
        clearConfigSwitchCache();
        new Handler().postDelayed(new Runnable() {
            @Override
            public void run() {
                if (mActivity != null && !mActivity.isFinishing()) {
                    mActivity.onBackPressed();
                }
            }
        }, 2500);
    }

    private void clearConfigSwitchCache() {
        try {
            SourceViewModel.clearRuntimeCache();
//            FileUtils.clearSpiderCacheFiles();
            LOG.i("echo-clear-config-switch-cache");
        } catch (Exception e) {
            LOG.i("echo-clear-config-switch-cache-error:" + e.getMessage());
            e.printStackTrace();
        }
    }

    private void restartAppAfterCacheCleared() {
        ToastUtil.info(mContext, "缓存已清空,即将回到主页!", Toast.LENGTH_LONG);
        new Handler().postDelayed(new Runnable() {
            @Override
            public void run() {
                restartApp();
            }
        }, 2500);
    }

    private void refreshApiLineText() {
        if (tvApiLine == null) return;
        ArrayList<String> apiLines = Hawk.get(HawkConfig.API_LINE_LIST, new ArrayList<String>());
        String current = Hawk.get(HawkConfig.API_URL, "");
        boolean showLine = HistoryHelper.isApiLineUrl(current);
        if (llApiLine != null) {
            llApiLine.setVisibility(showLine ? View.VISIBLE : View.GONE);
        }
        updateApiRowWeight(showLine);
        String lineName = "";
        if (showLine) {
            for (String apiLine : apiLines) {
                if (current.equals(HistoryHelper.getApiLineUrl(apiLine))) {
                    lineName = HistoryHelper.getApiLineName(apiLine);
                    break;
                }
            }
        }
        tvApiLine.setText(lineName);
    }

    /**
     * 分组切换后不抢左侧导航焦点；仅记录内容区状态，供右键重新进入时恢复。
     */
    private void initFocusMemory() {
        if (rootView == null) return;
        ViewGroup frame = rootView instanceof ViewGroup ? (ViewGroup) rootView : null;
        if (frame == null) return;
        for (int i = 0; i < frame.getChildCount(); i++) {
            View child = frame.getChildAt(i);
            if (child instanceof ScrollView) {
                settingScrollView = (ScrollView) child;
                break;
            }
        }
        if (settingScrollView == null || focusMemoryListener != null) return;
        focusMemoryListener = new ViewTreeObserver.OnGlobalFocusChangeListener() {
            @Override
            public void onGlobalFocusChanged(View oldFocus, View newFocus) {
                if (newFocus == null || newFocus.getId() == View.NO_ID
                        || !isDescendantOfRoot(newFocus)) return;
                lastFocusedViewId = newFocus.getId();
                newFocus.post(new Runnable() {
                    @Override
                    public void run() {
                        if (settingScrollView != null) {
                            lastScrollY = settingScrollView.getScrollY();
                        }
                    }
                });
            }
        };
        rootView.getViewTreeObserver().addOnGlobalFocusChangeListener(focusMemoryListener);
    }

    private boolean isDescendantOfRoot(View view) {
        View current = view;
        while (current != null) {
            if (current == rootView) return true;
            if (!(current.getParent() instanceof View)) return false;
            current = (View) current.getParent();
        }
        return false;
    }

    /** 由设置左栏按右键进入本组时调用。 */
    public boolean restoreLastFocus() {
        if (rootView == null || lastFocusedViewId == View.NO_ID) return false;
        final View target = rootView.findViewById(lastFocusedViewId);
        if (target == null || target.getVisibility() != View.VISIBLE || !target.isFocusable()) {
            return false;
        }
        target.requestFocus();
        if (settingScrollView != null) {
            settingScrollView.post(new Runnable() {
                @Override
                public void run() {
                    settingScrollView.scrollTo(0, lastScrollY);
                }
            });
        }
        return true;
    }

    @Override
    protected void onFragmentPause() {
        super.onFragmentPause();
        if (settingScrollView != null) {
            lastScrollY = settingScrollView.getScrollY();
        }
    }

    /** 非焦点时仅显示安全摘要；完整 URL 只在设置行获得焦点时短暂展示。 */
    private void bindApiSummary() {
        if (tvApi == null) return;
        String api = Hawk.get(HawkConfig.API_URL, "");
        if (llApi != null && llApi.hasFocus()) {
            tvApi.setText(api);
            return;
        }
        tvApi.setText(summarizeApi(api));
    }

    private String summarizeApi(String api) {
        if (api == null || api.trim().isEmpty()) return "未设置";
        try {
            HttpUrl url = HttpUrl.parse(api);
            if (url != null) {
                String host = url.host();
                String path = url.encodedPath();
                if (path == null || path.isEmpty() || "/".equals(path)) return host;
                String[] segments = path.split("/");
                String tail = segments.length > 0 ? segments[segments.length - 1] : "";
                if (tail.length() > 24) tail = tail.substring(Math.max(0, tail.length() - 24));
                return host + (tail.isEmpty() ? "" : " · " + tail);
            }
        } catch (Exception ignored) {
            // 保持设置页可用，非法旧值只显示安全的长度摘要。
        }
        String compact = api.trim();
        return compact.length() > 28 ? compact.substring(0, 12) + "…" + compact.substring(compact.length() - 12) : compact;
    }

    private void refreshDanmuApiText() {
        if (tvDanmuApiText == null) return;
        if (DanmakuApi.isUseDefault()) {
            tvDanmuApiText.setText("默认");
            return;
        }
        String custom = Hawk.get(HawkConfig.DANMU_API, "");
        if (!custom.isEmpty()) {
            tvDanmuApiText.setText("自定义");
            return;
        }
        String config = ApiConfig.get().getDanmaku();
        tvDanmuApiText.setText(config.isEmpty() ? "默认" : "接口");
    }

    private void updateApiRowWeight(boolean showLine) {
        if (llApi == null) return;
        LinearLayout.LayoutParams params = (LinearLayout.LayoutParams) llApi.getLayoutParams();
        // 设置页现在是单列结构，旧的横向权重会在垂直 ScrollView 中把地址行拉高。
        // 线路行的显隐由 refreshApiLineText() 处理，这里只清除历史权重。
        if (params.weight != 0f) {
            params.weight = 0f;
            llApi.setLayoutParams(params);
        }
        if (llApiHistory != null) {
            LinearLayout.LayoutParams historyParams = (LinearLayout.LayoutParams) llApiHistory.getLayoutParams();
            // 新结构中历史与线路纵向排列，不再需要旧横向分隔 margin。
            if (historyParams.rightMargin != 0 || historyParams.getMarginEnd() != 0) {
                historyParams.rightMargin = 0;
                historyParams.setMarginEnd(0);
                llApiHistory.setLayoutParams(historyParams);
            }
        }
    }

    private void restartApp() {
        if (mContext == null) return;
        Intent intent = mContext.getPackageManager().getLaunchIntentForPackage(mContext.getPackageName());
        if (intent != null) {
            intent.addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP);
            startActivity(intent);
            System.exit(0);
        }
    }

    private void onClickIjkCachePlay(View v) {
        FastClickCheckUtil.check(v);
        Hawk.put(HawkConfig.IJK_CACHE_PLAY, !Hawk.get(HawkConfig.IJK_CACHE_PLAY, false));
        tvIjkCachePlay.setChecked(Hawk.get(HawkConfig.IJK_CACHE_PLAY, false));
    }

    private void onClickLiveHlsProxy(View v) {
        // 直播HLS整片代理开关: 切换并立即更新UI
        FastClickCheckUtil.check(v);
        Hawk.put(HawkConfig.LIVE_HLS_PROXY, !Hawk.get(HawkConfig.LIVE_HLS_PROXY, false));
        tvLiveHlsProxy.setChecked(Hawk.get(HawkConfig.LIVE_HLS_PROXY, false));
    }

    private void openLocalConfig(boolean live) {
        selectLocalLive = live;
        if (!XXPermissions.isGranted(mContext, Permission.Group.STORAGE)) {
            ToastUtil.info(getContext(), "请选择文件前需要先授予存储权限");
            XXPermissions.with(mActivity)
                    .permission(Permission.Group.STORAGE)
                    .request(new OnPermissionCallback() {
                        @Override
                        public void onGranted(List<String> permissions, boolean all) {
                            if (all) {
                                ToastUtil.info(getContext(), "已获得存储权限");
                                openLocalFileActivity(selectLocalLive);
                            }
                        }

                        @Override
                        public void onDenied(List<String> permissions, boolean never) {
                            if (never) {
                                ToastUtil.error(getContext(), "获取存储权限失败,请在系统设置中开启");
                                XXPermissions.startPermissionActivity(mActivity, permissions);
                            } else {
                                ToastUtil.error(getContext(), "获取存储权限失败");
                            }
                        }
                    });
            return;
        }
        openLocalFileActivity(live);
    }

    private void openLocalFileActivity(boolean live) {
        Intent intent = new Intent(mContext, LocalFileActivity.class);
        intent.putExtra(LocalFileActivity.EXTRA_LIVE, live);
        startActivityForResult(intent, REQUEST_LOCAL_CONFIG);
    }

    @Override
    public void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode != REQUEST_LOCAL_CONFIG || resultCode != android.app.Activity.RESULT_OK || data == null || data.getData() == null) {
            return;
        }
        String api = localConfigToApi(data.getData());
        if (api == null || api.isEmpty()) {
            ToastUtil.error(getContext(), "读取本地配置失败");
            return;
        }
        if (apiDialog != null) {
            apiDialog.setLocalApi(api, selectLocalLive);
        }
    }

    private String localConfigToApi(Uri uri) {
        String path = getPathFromUri(uri);
        if (path == null || path.isEmpty()) {
            path = copyUriToLocalConfig(uri);
        }
        if (path == null || path.isEmpty()) {
            return "";
        }
        String storageRoot = Environment.getExternalStorageDirectory().getAbsolutePath();
        if (path.startsWith(storageRoot)) {
            return "clan://localhost/" + path.substring(storageRoot.length()).replaceFirst("^/+", "");
        }
        path = copyUriToLocalConfig(uri);
        if (path != null && path.startsWith(storageRoot)) {
            return "clan://localhost/" + path.substring(storageRoot.length()).replaceFirst("^/+", "");
        }
        return "";
    }

    private String getPathFromUri(Uri uri) {
        try {
            if ("file".equalsIgnoreCase(uri.getScheme())) {
                return uri.getPath();
            }
            if (DocumentsContract.isDocumentUri(mContext, uri)) {
                String docId = DocumentsContract.getDocumentId(uri);
                if ("com.android.externalstorage.documents".equals(uri.getAuthority())) {
                    String[] split = docId.split(":");
                    if (split.length > 1 && "primary".equalsIgnoreCase(split[0])) {
                        return Environment.getExternalStorageDirectory().getAbsolutePath() + "/" + split[1];
                    }
                }
                if ("com.android.providers.downloads.documents".equals(uri.getAuthority()) && docId.startsWith("raw:")) {
                    return docId.substring(4);
                }
            }
        } catch (Throwable ignored) {
        }
        return null;
    }

    private String copyUriToLocalConfig(Uri uri) {
        InputStream input = null;
        FileOutputStream output = null;
        try {
            input = mContext.getContentResolver().openInputStream(uri);
            if (input == null) return "";
            File dir = new File(FileUtils.getExternalCachePath(), "config");
            if (!dir.exists()) dir.mkdirs();
            File file = new File(dir, getDisplayName(uri));
            output = new FileOutputStream(file);
            byte[] buffer = new byte[8192];
            int length;
            while ((length = input.read(buffer)) != -1) {
                output.write(buffer, 0, length);
            }
            return file.getAbsolutePath();
        } catch (Throwable th) {
            th.printStackTrace();
            return "";
        } finally {
            try {
                if (output != null) output.close();
            } catch (Throwable ignored) {
            }
            try {
                if (input != null) input.close();
            } catch (Throwable ignored) {
            }
        }
    }

    private String getDisplayName(Uri uri) {
        String name = "local_config.json";
        Cursor cursor = null;
        try {
            cursor = mContext.getContentResolver().query(uri, null, null, null, null);
            if (cursor != null && cursor.moveToFirst()) {
                int index = cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME);
                if (index >= 0) {
                    String displayName = cursor.getString(index);
                    if (displayName != null && !displayName.isEmpty()) {
                        name = displayName;
                    }
                }
            }
        } catch (Throwable ignored) {
        } finally {
            if (cursor != null) cursor.close();
        }
        return name;
    }

    private void onClickClearCache(View v) {
        FastClickCheckUtil.check(v);
        String cachePath = FileUtils.getCachePath();
        File cacheDir = new File(cachePath);
        new Thread(() -> {
            try {
                ApiConfig.get().clearSpiderCache();
                if(cacheDir.exists())FileUtils.cleanDirectory(cacheDir);
                FileUtils.clearSpiderCacheFiles();
            } catch (Exception e) {
                e.printStackTrace();
            } finally {
                if (mActivity != null) {
                    mActivity.runOnUiThread(new Runnable() {
                        @Override
                        public void run() {
                            restartAppAfterCacheCleared();
                        }
                    });
                }
            }
        }).start();
    }


    public static SearchRemoteTvDialog loadingSearchRemoteTvDialog;
    public static List<String> remoteTvHostList;
    public static boolean foundRemoteTv;

    @Override
    public void onDestroyView() {
        if (rootView != null && focusMemoryListener != null
                && rootView.getViewTreeObserver().isAlive()) {
            rootView.getViewTreeObserver().removeOnGlobalFocusChangeListener(focusMemoryListener);
        }
        focusMemoryListener = null;
        settingScrollView = null;
        super.onDestroyView();
        SettingActivity.callback = null;
    }

    @Override
    public void onResume() {
        super.onResume();
        refreshParseSettingVisibility();
        refreshParseSettingSummary();
    }

    /** 解析器行：仅当前为"播放"组（group=2）且订阅含官方源（vipParseFlags 非空、存在解析器）时显示。
     * 注意：不能在非播放组的 tab 里强行 VISIBLE，否则会覆盖 applyGroupVisibility() 的组过滤，
     * 导致网络等 tab 也出现重复的解析器行。 */
    private void refreshParseSettingVisibility() {
        View row = findViewById(R.id.llParseSetting);
        if (row == null) return;
        int group = getArguments() != null ? getArguments().getInt("group", 0) : 0;
        boolean inPlayerGroup = group == 2; // groups: 通用0 内容1 播放2 网络3 外观4 数据5
        boolean hasOfficial = !ApiConfig.get().getVipParseFlags().isEmpty()
                && !ApiConfig.get().getParseBeanList().isEmpty();
        row.setVisibility(inPlayerGroup && hasOfficial ? View.VISIBLE : View.GONE);
    }

    /** 解析器行摘要：默认解析器名 + 启用个数。 */
    private void refreshParseSettingSummary() {
        if (tvParseSetting == null) return;
        ParseBean def = ApiConfig.get().getDefaultParse();
        String name;
        int total = 0;
        for (ParseBean pb : ApiConfig.get().getParseBeanList()) {
            if (pb.getType() != 1) total++;
        }
        if (def == null) {
            name = "未设置";
            tvParseSetting.setText(name);
            return;
        }
        String defName = def.getType() == 1 ? "Ponyo解析" : def.getName();
        int enabledCount = ApiConfig.get().getEnabledParserSet().size();
        if (total == 0 || enabledCount == 0 || enabledCount >= total) {
            tvParseSetting.setText(defName + "（全部启用）");
        } else {
            tvParseSetting.setText(defName + "（启用 " + enabledCount + "/" + total + "）");
        }
    }

    String getHomeRecName(int type) {
        if (type == 1) {
            return "站点推荐";
        } else if (type == 2) {
            return "观看历史";
        } else {
            return "豆瓣热播";
        }
    }

    String getSearchView(int type) {
        if (type == 0) {
            return "文字列表";
        } else {
            return "缩略图";
        }
    }
}

