package com.github.tvbox.osc.ui.dialog;

import android.content.Context;
import android.os.Bundle;
import android.view.View;
import android.view.ViewGroup;
import android.widget.TextView;
import android.widget.Toast;

import androidx.annotation.NonNull;
import androidx.recyclerview.widget.DiffUtil;

import com.github.tvbox.osc.R;
import com.github.tvbox.osc.callback.EmptyCallback;
import com.github.tvbox.osc.callback.LoadingCallback;
import com.github.tvbox.osc.event.RefreshEvent;
import com.github.tvbox.osc.player.thirdparty.RemoteTVBox;
import com.github.tvbox.osc.ui.adapter.SelectDialogAdapter;
import com.github.tvbox.osc.ui.fragment.ModelSettingFragment;
import com.kingja.loadsir.callback.Callback;
import com.kingja.loadsir.core.LoadService;
import com.kingja.loadsir.core.LoadSir;

import org.greenrobot.eventbus.Subscribe;
import org.greenrobot.eventbus.ThreadMode;
import org.jetbrains.annotations.NotNull;
import com.github.tvbox.osc.util.ToastUtil;


public class SearchRemoteTvDialog extends BaseDialog{


    @Subscribe(threadMode = ThreadMode.MAIN)
    public void refresh(RefreshEvent event) {
        if (event.type == RefreshEvent.TYPE_SETTING_SEARCH_TV) {
            showRemoteTvDialog(ModelSettingFragment.foundRemoteTv);
        }
    }

    public SearchRemoteTvDialog(@NonNull @NotNull Context context) {
        super(context);
        setContentView(R.layout.dialog_search_remotetv);
    }


    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
    }

    public void setTip(String tip) {
        ((TextView) findViewById(R.id.title)).setText(tip);
        setLoadSir(findViewById(R.id.list));
        showLoading();
    }

    private void showRemoteTvDialog(boolean found) {
        if (!found) {
            // 未找到设备：在搜索对话框内显示结果文案（不依赖系统 Toast，避免被吞），
            // 1.5s 后自动关闭；不再弹 EmptyCallback 面板（无设备可点，面板无意义）
            if (ModelSettingFragment.loadingSearchRemoteTvDialog != null) {
                ModelSettingFragment.loadingSearchRemoteTvDialog.showResult("未找到附近TVBox");
                ModelSettingFragment.loadingSearchRemoteTvDialog.dismissDelayed(1500);
            }
            return;
        }
        if (ModelSettingFragment.loadingSearchRemoteTvDialog != null) {
            ModelSettingFragment.loadingSearchRemoteTvDialog.dismiss();
        }
        if (ModelSettingFragment.remoteTvHostList == null) {
            return;
        }
        RemoteTVBox.setAvalible(ModelSettingFragment.remoteTvHostList.get(0));
        SelectDialog<String> dialog = new SelectDialog<>(getContext());
        dialog.setTip("附近TVBox");
        int defaultPos = 0;
        dialog.setAdapter(new SelectDialogAdapter.SelectDialogInterface<String>() {
            @Override
            public void click(String value, int pos) {
                RemoteTVBox.setAvalible(value);
                ToastUtil.info(getContext(), "设置成功");
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
        }, ModelSettingFragment.remoteTvHostList, defaultPos);
        dialog.show();
    }



    private LoadService mLoadService;

    protected void setLoadSir(View view) {
        if (mLoadService == null) {
            mLoadService = LoadSir.getDefault().register(view, new Callback.OnReloadListener() {
                @Override
                public void onReload(View v) {
                }
            });
        }
    }

    public void showLoading() {
        if (mLoadService != null) {
            mLoadService.showCallback(LoadingCallback.class);
        }
    }

    public void showEmpty() {
        if (null != mLoadService) {
            mLoadService.showCallback(EmptyCallback.class);
        }
    }

    public void showSuccess() {
        if (null != mLoadService) {
            mLoadService.showSuccess();
        }
    }

    /** 显示搜索结果的纯文案（无按钮、无空态图标），用于"未找到设备"等提示 */
    public void showResult(String tip) {
        if (mLoadService != null) {
            mLoadService.showSuccess();  // 关掉 loading spinner
        }
        ((TextView) findViewById(R.id.title)).setText(tip);
    }

    /** 延迟关闭对话框 */
    public void dismissDelayed(long delayMs) {
        if (getWindow() != null) {
            getWindow().getDecorView().postDelayed(new Runnable() {
                @Override
                public void run() {
                    dismiss();
                }
            }, delayMs);
        }
    }

}
