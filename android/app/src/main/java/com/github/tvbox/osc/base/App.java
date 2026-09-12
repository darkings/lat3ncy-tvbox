package com.github.tvbox.osc.base;

import android.app.Activity;
import androidx.multidex.MultiDexApplication;

import com.github.tvbox.osc.bean.VodInfo;
import com.github.tvbox.osc.callback.EmptyCallback;
import com.github.tvbox.osc.callback.ErrorCallback;
import com.github.tvbox.osc.callback.LoadingCallback;
import com.github.tvbox.osc.callback.SearchLoadingCallback;
import com.github.tvbox.osc.data.AppDataManager;
import com.github.tvbox.osc.server.ControlManager;
import com.github.tvbox.osc.util.AppManager;
import com.github.tvbox.osc.util.EpgUtil;
import com.github.tvbox.osc.util.FileUtils;
import com.github.tvbox.osc.util.HawkConfig;
import com.github.tvbox.osc.util.LOG;
import com.github.tvbox.osc.util.OkGoHelper;
import com.github.tvbox.osc.util.PlayerHelper;
import com.kingja.loadsir.core.LoadSir;
import com.orhanobut.hawk.Hawk;
import com.orhanobut.hawk.NoEncryption;
import com.p2p.P2PClass;
import com.whl.quickjs.android.QuickJSLoader;
import com.github.catvod.crawler.JsLoader;

import me.jessyan.autosize.AutoSizeConfig;
import me.jessyan.autosize.unit.Subunits;

/**
 * @author pj567
 * @date :2020/12/17
 * @description:
 */
public class App extends MultiDexApplication {
    private static final String DEFAULT_SUBSCRIPTION =
            "https://api.ponyo.fun/ponyo.json";
    private static App instance;
    private static com.github.catvod.crawler.js.DrpySServer drpySServer;

    private static P2PClass p;
    public static String burl;
    private static String dashData;

    @Override
    public void onCreate() {
        super.onCreate();
        instance = this;
        // Hawk 必须先初始化：后面 DYNAMIC_COLOR 读取和默认订阅写入都依赖它。
        initParams();
        // Android 12+ 壁纸动态取色（需在 Activity 创建前调用）
        if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.S
                && Hawk.get(HawkConfig.DYNAMIC_COLOR, false)) {
            try {
                com.google.android.material.color.DynamicColors.applyToActivitiesIfAvailable(this);
            } catch (Throwable th) {
                th.printStackTrace();
            }
        }
        // OKGo
        OkGoHelper.init(); //台标获取
        EpgUtil.init();
        // 初始化Web服务器
        ControlManager.init(this);
        // 本地 drpyS 运行时：监听 127.0.0.1:5757，服务 type-4 drpyS 源
        try {
            startDrpySServer();
        } catch (Throwable th) {
            th.printStackTrace();
        }
        //初始化数据库
        AppDataManager.init();
        LoadSir.beginBuilder()
                .addCallback(new EmptyCallback())
                .addCallback(new LoadingCallback())
                .addCallback(new SearchLoadingCallback())
                .addCallback(new ErrorCallback())
                .commit();
        AutoSizeConfig.getInstance().setCustomFragment(true).getUnitsManager()
                .setSupportDP(false)
                .setSupportSP(false)
                .setSupportSubunits(Subunits.MM);
        PlayerHelper.init();
        QuickJSLoader.init();
        FileUtils.cleanPlayerCache();
    }

    private void initParams() {
        // Hawk
        // 双端兼容：安卓9 电视盒走默认 Conceal 加密；安卓15 模拟器(arm64/x86 翻译层)
        // Conceal native 初始化失败时，降级为无加密存储，保证配置可读写、App 不闪退。
        try {
            Hawk.init(this).build();
        } catch (Throwable hawkErr) {
            android.util.Log.w("App", "Hawk default build failed, fallback to NoEncryption", hawkErr);
            Hawk.init(this).setEncryption(new NoEncryption()).build();
        }
        installDefaultSubscription();
        Hawk.put(HawkConfig.DEBUG_OPEN, false);
        if (!Hawk.contains(HawkConfig.PLAY_TYPE)) {
            Hawk.put(HawkConfig.PLAY_TYPE, 1);
        }
        // 直播默认走 Exo：HLS 边下边播，比 IJK 直连大分片更不容易卡碟。
        // 用户一旦在直播设置里选过内核，Hawk 里已有 LIVE_PLAY_TYPE，这里不会覆盖。
        if (!Hawk.contains(HawkConfig.LIVE_PLAY_TYPE)) {
            Hawk.put(HawkConfig.LIVE_PLAY_TYPE, 2);
        }
    }

    private void startDrpySServer() {
        if (drpySServer != null) return;
        drpySServer = new com.github.catvod.crawler.js.DrpySServer(
                this, com.github.catvod.crawler.js.DrpySRuleManager.rulesDir());
        drpySServer.startQuietly();
    }

    private void installDefaultSubscription() {
        String currentApi = Hawk.get(HawkConfig.API_URL, "");
        // 首次安装：空地址 / 内置 assets 地址 → 写入默认服务器直连地址
        if (!Hawk.get("ponyo_remote_subscription_migrated", false)) {
            if (currentApi == null || currentApi.trim().isEmpty()
                    || "assets://ponyo.json".equals(currentApi.trim())) {
                Hawk.put(HawkConfig.API_URL, DEFAULT_SUBSCRIPTION);
            }
            Hawk.put("ponyo_remote_subscription_migrated", true);
        }
        // 一次性迁移：已装设备若仍指向旧 jsDelivr CDN（有缓存延迟），
        // 强制改写为服务器直连地址 api.ponyo.fun（即时生效，无 CDN 缓存）
        if (!Hawk.get("ponyo_api_direct_migrated", false)) {
            String api = Hawk.get(HawkConfig.API_URL, "");
            if (api != null && api.contains("cdn.jsdelivr.net")
                    && api.contains("lat3ncy-tvbox")) {
                Hawk.put(HawkConfig.API_URL, DEFAULT_SUBSCRIPTION);
            }
            Hawk.put("ponyo_api_direct_migrated", true);
        }
        if (!Hawk.get("ponyo_beauty2_home_migrated", false)) {
            Hawk.put(HawkConfig.HOME_API, "drpy_js_豆瓣");
            Hawk.put("ponyo_beauty2_home_migrated", true);
        }
    }

    public static App getInstance() {
        return instance;
    }

    @Override
    public void onTerminate() {
        super.onTerminate();
        JsLoader.destroy();
    }


    private VodInfo vodInfo;
    public void setVodInfo(VodInfo vodinfo){
        this.vodInfo = vodinfo;
    }
    public VodInfo getVodInfo(){
        return this.vodInfo;
    }

    public static P2PClass getp2p() {
        try {
            if (p == null) {
                p = new P2PClass(FileUtils.getExternalCachePath());
            }
            return p;
        } catch (Exception e) {
            LOG.e(e.toString());
            return null;
        }
    }

    public Activity getCurrentActivity() {
        return AppManager.getInstance().currentActivity();
    }

    public void setDashData(String data) {
        dashData = data;
    }
    public String getDashData() {
        return dashData;
    }
}
