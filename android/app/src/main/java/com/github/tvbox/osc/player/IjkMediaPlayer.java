package com.github.tvbox.osc.player;

import android.content.Context;
import android.text.TextUtils;

import com.github.tvbox.osc.api.ApiConfig;
import com.github.tvbox.osc.bean.IJKCode;
import com.github.tvbox.osc.server.ControlManager;
import com.github.tvbox.osc.util.AudioTrackMemory;
import com.github.tvbox.osc.util.FileUtils;
import com.github.tvbox.osc.util.HawkConfig;
import com.github.tvbox.osc.util.LOG;
import com.github.tvbox.osc.util.MD5;
import com.orhanobut.hawk.Hawk;

import java.io.File;
import java.net.URI;
import java.net.URLEncoder;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.Map;

import tv.danmaku.ijk.media.player.IMediaPlayer;
import tv.danmaku.ijk.media.player.IjkMediaMeta;
import tv.danmaku.ijk.media.player.misc.IMediaFormat;
import tv.danmaku.ijk.media.player.misc.ITrackInfo;
import tv.danmaku.ijk.media.player.misc.IjkTrackInfo;
import xyz.doikki.videoplayer.exo.ExoMediaSourceHelper;
import xyz.doikki.videoplayer.ijk.IjkPlayer;

public class IjkMediaPlayer extends IjkPlayer {

    private IJKCode codec = null;
    protected String currentPlayPath;
    private static AudioTrackMemory memory;
    private static final String DEFAULT_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36";
    private static final String DEFAULT_ACCEPT = "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/json;q=0.9";

    public IjkMediaPlayer(Context context, IJKCode codec) {
        super(context);
        this.codec = codec;
        memory = AudioTrackMemory.getInstance(context);
    }

    @Override
    public void setOptions() {
        super.setOptions();
        IJKCode codecTmp = this.codec == null ? ApiConfig.get().getCurrentIJKCode() : this.codec;
        LinkedHashMap<String, String> options = codecTmp.getOption();
        if (options != null) {
            for (String key : options.keySet()) {
                String value = options.get(key);
                String[] opt = key.split("\\|");
                int category = Integer.parseInt(opt[0].trim());
                String name = opt[1].trim();
                try {
                    assert value != null;
                    long valLong = Long.parseLong(value);
                    mMediaPlayer.setOption(category, name, valLong);
                } catch (Exception e) {
                    mMediaPlayer.setOption(category, name, value);
                }
            }
        }
        // L01: 只在订阅未显式配置 max-fps 时才用 30 兜底，避免覆盖订阅中的高帧率配置
        boolean hasMaxFps = false;
        if (options != null) {
            for (String key : options.keySet()) {
                if (key != null && key.endsWith("|max-fps")) {
                    hasMaxFps = true;
                    break;
                }
            }
        }
        if (!hasMaxFps) {
            mMediaPlayer.setOption(tv.danmaku.ijk.media.player.IjkMediaPlayer.OPT_CATEGORY_PLAYER, "max-fps", 30);
        }

        // 设置视频流格式
//        mMediaPlayer.setOption(tv.danmaku.ijk.media.player.IjkMediaPlayer.OPT_CATEGORY_PLAYER, "overlay-format", tv.danmaku.ijk.media.player.IjkMediaPlayer.SDL_FCC_RV32);

        //开启内置字幕
        mMediaPlayer.setOption(tv.danmaku.ijk.media.player.IjkMediaPlayer.OPT_CATEGORY_PLAYER, "subtitle", 1);
        mMediaPlayer.setOption(tv.danmaku.ijk.media.player.IjkMediaPlayer.OPT_CATEGORY_FORMAT, "dns_cache_clear", 1);
        mMediaPlayer.setOption(tv.danmaku.ijk.media.player.IjkMediaPlayer.OPT_CATEGORY_FORMAT, "dns_cache_timeout", -1);
        mMediaPlayer.setOption(tv.danmaku.ijk.media.player.IjkMediaPlayer.OPT_CATEGORY_FORMAT,"safe",0);

        if(Hawk.get(HawkConfig.PLAYER_IS_LIVE, false)){
            LOG.i("echo-type-直播");
            boolean hlsProxy = Hawk.get(HawkConfig.LIVE_HLS_PROXY, false);
            // 进台时等音画都就绪再起播，避免刚进频道口型对不上
            mMediaPlayer.setOption(tv.danmaku.ijk.media.player.IjkMediaPlayer.OPT_CATEGORY_PLAYER, "sync-av-start", 1);
            mMediaPlayer.setOption(tv.danmaku.ijk.media.player.IjkMediaPlayer.OPT_CATEGORY_FORMAT, "reconnect", 1);
            mMediaPlayer.setOption(tv.danmaku.ijk.media.player.IjkMediaPlayer.OPT_CATEGORY_CODEC, "threads", "auto");
            mMediaPlayer.setOption(tv.danmaku.ijk.media.player.IjkMediaPlayer.OPT_CATEGORY_PLAYER, "soundtouch", 0);
            // 默认 AudioTrack 更稳，OpenSLES 在部分真机会把声音一起卡住
            mMediaPlayer.setOption(tv.danmaku.ijk.media.player.IjkMediaPlayer.OPT_CATEGORY_PLAYER, "opensles", 0);
            if (hlsProxy) {
                // 本地整片代理已经在攒缓冲，IJK 再开 packet-buffering 会双重等待
                LOG.i("echo-live-ijk-opts proxy=on");
                mMediaPlayer.setOption(tv.danmaku.ijk.media.player.IjkMediaPlayer.OPT_CATEGORY_PLAYER, "packet-buffering", 0);
                mMediaPlayer.setOption(tv.danmaku.ijk.media.player.IjkMediaPlayer.OPT_CATEGORY_PLAYER, "infbuf", 1);
                mMediaPlayer.setOption(tv.danmaku.ijk.media.player.IjkMediaPlayer.OPT_CATEGORY_PLAYER, "max_cached_duration", 300);
                mMediaPlayer.setOption(tv.danmaku.ijk.media.player.IjkMediaPlayer.OPT_CATEGORY_PLAYER, "min-frames", 1);
                mMediaPlayer.setOption(tv.danmaku.ijk.media.player.IjkMediaPlayer.OPT_CATEGORY_PLAYER, "framedrop", 1);
                mMediaPlayer.setOption(tv.danmaku.ijk.media.player.IjkMediaPlayer.OPT_CATEGORY_FORMAT, "flush_packets", 1);
            } else {
                // 直连 HLS：音画不同步只发生在刚进台（视频先出、音频后到）。
                // 用 first-high-water-mark 等够音画数据再起播。
                // infbuf 必须关，否则 IJK 会跳过 high-water-mark。
                // 不要用 max_cached_duration 当水位：它是缓存上限，满了就停读，
                // 播空再填会变成「播几秒卡几秒」。
                // 探测窗口从 2s/1MB 收到 0.8s/512KB：够识别音视频轨，少等一轮空等。
                LOG.i("echo-live-ijk-opts proxy=off packet-buffering=1 first-hwm=1500");
                mMediaPlayer.setOption(tv.danmaku.ijk.media.player.IjkMediaPlayer.OPT_CATEGORY_PLAYER, "packet-buffering", 1);
                mMediaPlayer.setOption(tv.danmaku.ijk.media.player.IjkMediaPlayer.OPT_CATEGORY_PLAYER, "infbuf", 0);
                mMediaPlayer.setOption(tv.danmaku.ijk.media.player.IjkMediaPlayer.OPT_CATEGORY_PLAYER, "max_cached_duration", 0);
                mMediaPlayer.setOption(tv.danmaku.ijk.media.player.IjkMediaPlayer.OPT_CATEGORY_PLAYER, "max-buffer-size", 15 * 1024 * 1024);
                mMediaPlayer.setOption(tv.danmaku.ijk.media.player.IjkMediaPlayer.OPT_CATEGORY_PLAYER, "first-high-water-mark-ms", 1500);
                mMediaPlayer.setOption(tv.danmaku.ijk.media.player.IjkMediaPlayer.OPT_CATEGORY_PLAYER, "next-high-water-mark-ms", 2500);
                mMediaPlayer.setOption(tv.danmaku.ijk.media.player.IjkMediaPlayer.OPT_CATEGORY_PLAYER, "last-high-water-mark-ms", 4000);
                mMediaPlayer.setOption(tv.danmaku.ijk.media.player.IjkMediaPlayer.OPT_CATEGORY_PLAYER, "min-frames", 10);
                mMediaPlayer.setOption(tv.danmaku.ijk.media.player.IjkMediaPlayer.OPT_CATEGORY_PLAYER, "framedrop", 1);
                mMediaPlayer.setOption(tv.danmaku.ijk.media.player.IjkMediaPlayer.OPT_CATEGORY_FORMAT, "flush_packets", 0);
                mMediaPlayer.setOption(tv.danmaku.ijk.media.player.IjkMediaPlayer.OPT_CATEGORY_FORMAT, "analyzeduration", 800 * 1000);
                mMediaPlayer.setOption(tv.danmaku.ijk.media.player.IjkMediaPlayer.OPT_CATEGORY_FORMAT, "probesize", 512 * 1024);
                // timeout / rw_timeout 单位是微秒。
                // 30s：本地 HLS 代理冷启动时上游 TLS 握手可达 7-10s（跨境 CDN），
                // 加一级/二级 m3u8 串行拉取，10s 会误杀慢源（实测 lzcdn31 首开 -10000）。
                mMediaPlayer.setOption(tv.danmaku.ijk.media.player.IjkMediaPlayer.OPT_CATEGORY_FORMAT, "timeout", 30 * 1000 * 1000);
                mMediaPlayer.setOption(tv.danmaku.ijk.media.player.IjkMediaPlayer.OPT_CATEGORY_FORMAT, "rw_timeout", 35 * 1000 * 1000);
                mMediaPlayer.setOption(tv.danmaku.ijk.media.player.IjkMediaPlayer.OPT_CATEGORY_FORMAT, "http-detect-range-support", 0);
            }
        }else{
            LOG.i("echo-type-点播");
            // 点播不要设 max_cached_duration：它是缓存上限，满了就停读，
            // 播空再填会变成「播几秒卡几秒」。水位只用 high-water-mark。
            // infbuf 属于 PLAYER，写到 FORMAT 不会生效。
            mMediaPlayer.setOption(tv.danmaku.ijk.media.player.IjkMediaPlayer.OPT_CATEGORY_PLAYER, "packet-buffering", 1);
            mMediaPlayer.setOption(tv.danmaku.ijk.media.player.IjkMediaPlayer.OPT_CATEGORY_PLAYER, "infbuf", 0);
            mMediaPlayer.setOption(tv.danmaku.ijk.media.player.IjkMediaPlayer.OPT_CATEGORY_PLAYER, "max_cached_duration", 0);
            mMediaPlayer.setOption(tv.danmaku.ijk.media.player.IjkMediaPlayer.OPT_CATEGORY_PLAYER, "max-buffer-size", 15 * 1024 * 1024);
            mMediaPlayer.setOption(tv.danmaku.ijk.media.player.IjkMediaPlayer.OPT_CATEGORY_PLAYER, "min-frames", 10);
            mMediaPlayer.setOption(tv.danmaku.ijk.media.player.IjkMediaPlayer.OPT_CATEGORY_CODEC, "threads", "2");
            mMediaPlayer.setOption(tv.danmaku.ijk.media.player.IjkMediaPlayer.OPT_CATEGORY_FORMAT, "reconnect", 1);
            mMediaPlayer.setOption(tv.danmaku.ijk.media.player.IjkMediaPlayer.OPT_CATEGORY_FORMAT, "analyzeduration", 800 * 1000);
            mMediaPlayer.setOption(tv.danmaku.ijk.media.player.IjkMediaPlayer.OPT_CATEGORY_FORMAT, "probesize", 512 * 1024);
            mMediaPlayer.setOption(tv.danmaku.ijk.media.player.IjkMediaPlayer.OPT_CATEGORY_PLAYER, "first-high-water-mark-ms", 1200);
            mMediaPlayer.setOption(tv.danmaku.ijk.media.player.IjkMediaPlayer.OPT_CATEGORY_PLAYER, "next-high-water-mark-ms", 2500);
            mMediaPlayer.setOption(tv.danmaku.ijk.media.player.IjkMediaPlayer.OPT_CATEGORY_PLAYER, "last-high-water-mark-ms", 4000);
            // 30s：点播同样可能走本地代理冷启动（上游 TLS 7-10s），10s 会误杀（lzcdn31 实测 -10000）。
            mMediaPlayer.setOption(tv.danmaku.ijk.media.player.IjkMediaPlayer.OPT_CATEGORY_FORMAT, "timeout", 30 * 1000 * 1000);
            mMediaPlayer.setOption(tv.danmaku.ijk.media.player.IjkMediaPlayer.OPT_CATEGORY_FORMAT, "rw_timeout", 35 * 1000 * 1000);
//        mMediaPlayer.setOption(tv.danmaku.ijk.media.player.IjkMediaPlayer.OPT_CATEGORY_PLAYER, "sync-av-start", 1);//强制音画同步
        }
    }

    @Override
    public void initPlayer() {
        super.initPlayer();
        // 【诊断】包装监听器，监控播放器内部事件，定位卡碟原因
        mMediaPlayer.setOnInfoListener(new tv.danmaku.ijk.media.player.IMediaPlayer.OnInfoListener() {
            @Override
            public boolean onInfo(tv.danmaku.ijk.media.player.IMediaPlayer mp, int what, int extra) {
                String msg = "echo-ijk-onInfo what:" + what + " extra:" + extra;
                switch (what) {
                    case tv.danmaku.ijk.media.player.IMediaPlayer.MEDIA_INFO_VIDEO_RENDERING_START:
                        msg = "echo-ijk-video-render-start";
                        break;
                    case tv.danmaku.ijk.media.player.IMediaPlayer.MEDIA_INFO_AUDIO_RENDERING_START:
                        msg = "echo-ijk-audio-render-start";
                        break;
                    case tv.danmaku.ijk.media.player.IMediaPlayer.MEDIA_INFO_BUFFERING_START:
                        msg = "echo-ijk-buffering-start extra:" + extra;
                        break;
                    case tv.danmaku.ijk.media.player.IMediaPlayer.MEDIA_INFO_BUFFERING_END:
                        msg = "echo-ijk-buffering-end extra:" + extra;
                        break;
                    case tv.danmaku.ijk.media.player.IMediaPlayer.MEDIA_INFO_NETWORK_BANDWIDTH:
                        msg = "echo-ijk-bandwidth:" + extra;
                        break;
                    case 20001:
                        msg = "echo-ijk-video-rotation-changed:" + extra;
                        break;
                    case 20002:
                        msg = "echo-ijk-audio-decoded-start";
                        break;
                    case 20003:
                        msg = "echo-ijk-video-decoded-start";
                        break;
                    case 20004:
                        msg = "echo-ijk-open-input";
                        break;
                    case 20005:
                        msg = "echo-ijk-find-stream-info";
                        break;
                    case 20006:
                        msg = "echo-ijk-component-open";
                        break;
                    case 20010:
                        msg = "echo-ijk-video-track-lagging";
                        break;
                }
                LOG.i(msg);
                return IjkMediaPlayer.super.onInfo(mp, what, extra);
            }
        });
        mMediaPlayer.setOnErrorListener(new tv.danmaku.ijk.media.player.IMediaPlayer.OnErrorListener() {
            @Override
            public boolean onError(tv.danmaku.ijk.media.player.IMediaPlayer mp, int what, int extra) {
                LOG.i("echo-ijk-onError what:" + what + " extra:" + extra);
                return IjkMediaPlayer.super.onError(mp, what, extra);
            }
        });
        mMediaPlayer.setOnPreparedListener(new tv.danmaku.ijk.media.player.IMediaPlayer.OnPreparedListener() {
            @Override
            public void onPrepared(tv.danmaku.ijk.media.player.IMediaPlayer mp) {
                LOG.i("echo-ijk-onPrepared duration:" + mp.getDuration() + " videoWidth:" + mp.getVideoWidth() + " videoHeight:" + mp.getVideoHeight());
                IjkMediaPlayer.super.onPrepared(mp);
            }
        });
        mMediaPlayer.setOnCompletionListener(new tv.danmaku.ijk.media.player.IMediaPlayer.OnCompletionListener() {
            @Override
            public void onCompletion(tv.danmaku.ijk.media.player.IMediaPlayer mp) {
                LOG.i("echo-ijk-onCompletion");
                IjkMediaPlayer.super.onCompletion(mp);
            }
        });
        mMediaPlayer.setOnVideoSizeChangedListener(new tv.danmaku.ijk.media.player.IMediaPlayer.OnVideoSizeChangedListener() {
            @Override
            public void onVideoSizeChanged(tv.danmaku.ijk.media.player.IMediaPlayer mp, int width, int height, int sar_num, int sar_den) {
                LOG.i("echo-ijk-video-size-changed w:" + width + " h:" + height + " sar:" + sar_num + "/" + sar_den);
                IjkMediaPlayer.super.onVideoSizeChanged(mp, width, height, sar_num, sar_den);
            }
        });
    }

    private static final String ITV_TARGET_DOMAIN = "gslbserv.itv.cmvideo.cn";
    @Override
    public void setDataSource(String path, Map<String, String> headers) {
        try {
            switch (getStreamType(path)) {
                case RTSP_UDP_RTP:
                    mMediaPlayer.setOption(tv.danmaku.ijk.media.player.IjkMediaPlayer.OPT_CATEGORY_FORMAT, "infbuf", 1);
                    mMediaPlayer.setOption(tv.danmaku.ijk.media.player.IjkMediaPlayer.OPT_CATEGORY_FORMAT, "rtsp_transport", "tcp");
                    mMediaPlayer.setOption(tv.danmaku.ijk.media.player.IjkMediaPlayer.OPT_CATEGORY_FORMAT, "rtsp_flags", "prefer_tcp");
                    mMediaPlayer.setOption(tv.danmaku.ijk.media.player.IjkMediaPlayer.OPT_CATEGORY_FORMAT, "probesize", 512 * 1000);
                    mMediaPlayer.setOption(tv.danmaku.ijk.media.player.IjkMediaPlayer.OPT_CATEGORY_FORMAT, "analyzeduration", 2 * 1000 * 1000);
                    break;

                case CACHE_VIDEO:
                    if (Hawk.get(HawkConfig.IJK_CACHE_PLAY, false)) {
                        String cachePath = FileUtils.getCachePath() + "/ijkcaches/";
                        File cacheFile = new File(cachePath);
                        if (!cacheFile.exists()) cacheFile.mkdirs();
                        String tmpMd5 = MD5.string2MD5(path);
                        String cacheFilePath = cachePath + tmpMd5 + ".file";
                        String cacheMapPath = cachePath + tmpMd5 + ".map";

                        mMediaPlayer.setOption(tv.danmaku.ijk.media.player.IjkMediaPlayer.OPT_CATEGORY_FORMAT, "cache_file_path", cacheFilePath);
                        mMediaPlayer.setOption(tv.danmaku.ijk.media.player.IjkMediaPlayer.OPT_CATEGORY_FORMAT, "cache_map_path", cacheMapPath);
                        mMediaPlayer.setOption(tv.danmaku.ijk.media.player.IjkMediaPlayer.OPT_CATEGORY_FORMAT, "parse_cache_map", 1);
                        mMediaPlayer.setOption(tv.danmaku.ijk.media.player.IjkMediaPlayer.OPT_CATEGORY_FORMAT, "auto_save_map", 1);
                        mMediaPlayer.setOption(tv.danmaku.ijk.media.player.IjkMediaPlayer.OPT_CATEGORY_FORMAT, "cache_max_capacity", 60 * 1024 * 1024);
                        path = "ijkio:cache:ffio:" + path;
                    }
                    break;

                case M3U8:
                    // 直播且是ijk的时候自动自动走代理解决DNS
                    if (Hawk.get(HawkConfig.PLAYER_IS_LIVE, false) ) {
                        URI uri = new URI(path);
                        String host = uri.getHost();
                        if(ITV_TARGET_DOMAIN.equalsIgnoreCase(host))path = ControlManager.get().getAddress(true) + "proxy?go=live&type=m3u8&url="+ URLEncoder.encode(path,"UTF-8");
                    }
                    break;

                default:
                    break;
            }
        } catch (Exception e) {
            e.printStackTrace();
        }
        setDataSourceHeader(headers);
        mMediaPlayer.setOption(tv.danmaku.ijk.media.player.IjkMediaPlayer.OPT_CATEGORY_FORMAT, "protocol_whitelist", "ijkio,ffio,async,cache,crypto,file,dash,http,https,ijkhttphook,ijkinject,ijklivehook,ijklongurl,ijksegment,ijktcphook,pipe,rtp,tcp,tls,udp,ijkurlhook,data");
        currentPlayPath = path;
        super.setDataSource(path, null);
    }

    /**
     * 解析 URL
     */
    private static final int RTSP_UDP_RTP = 1;
    private static final int CACHE_VIDEO = 2;
    private static final int M3U8 = 3;
    private static final int OTHER = 0;

    private int getStreamType(String path) {
        if (TextUtils.isEmpty(path)) {
            return OTHER;
        }
        // 低成本检查 RTSP/UDP/RTP 类型
        String lowerPath = path.toLowerCase();
        if (lowerPath.startsWith("rtsp://") || lowerPath.startsWith("udp://") || lowerPath.startsWith("rtp://")) {
            return RTSP_UDP_RTP;
        }
        String cleanUrl = path.split("\\?")[0];
        if (cleanUrl.endsWith(".m3u8")) {
            return M3U8;
        }
        if (cleanUrl.endsWith(".mp4") || cleanUrl.endsWith(".mkv") || cleanUrl.endsWith(".avi")) {
            return CACHE_VIDEO;
        }
        return OTHER;
    }

    private void setDataSourceHeader(Map<String, String> headers) {
        LinkedHashMap<String, String> playHeaders = new LinkedHashMap<>();
        String userAgent = null;
        boolean hasAccept = false;
        if (headers != null && !headers.isEmpty()) {
            for (Map.Entry<String, String> entry : headers.entrySet()) {
                String key = entry.getKey();
                String value = entry.getValue();
                if (TextUtils.isEmpty(key) || TextUtils.isEmpty(value)) {
                    continue;
                }
                if (ExoMediaSourceHelper.HEADER_FORMAT.equalsIgnoreCase(key)) {
                    continue;
                }
                if ("User-Agent".equalsIgnoreCase(key)) {
                    userAgent = value.trim();
                } else {
                    if ("Accept".equalsIgnoreCase(key)) {
                        hasAccept = true;
                    }
                    playHeaders.put(key, value.trim());
                }
            }
        }
        if (TextUtils.isEmpty(userAgent)) {
            userAgent = DEFAULT_USER_AGENT;
        }
        if (!hasAccept) {
            playHeaders.put("Accept", DEFAULT_ACCEPT);
        }
        if (!TextUtils.isEmpty(userAgent)) {
            mMediaPlayer.setOption(tv.danmaku.ijk.media.player.IjkMediaPlayer.OPT_CATEGORY_FORMAT, "user_agent", userAgent);
        }
        if (playHeaders.size() > 0) {
            StringBuilder sb = new StringBuilder();
            for (Map.Entry<String, String> entry : playHeaders.entrySet()) {
                sb.append(entry.getKey());
                sb.append(": ");
                sb.append(entry.getValue());
                sb.append("\r\n");
            }
            mMediaPlayer.setOption(tv.danmaku.ijk.media.player.IjkMediaPlayer.OPT_CATEGORY_FORMAT, "headers", sb.toString());
        }
    }

    public TrackInfo getTrackInfo() {
        IjkTrackInfo[] trackInfo = mMediaPlayer.getTrackInfo();
        if (trackInfo == null) return null;
        TrackInfo data = new TrackInfo();
        int subtitleSelected = mMediaPlayer.getSelectedTrack(ITrackInfo.MEDIA_TRACK_TYPE_TIMEDTEXT);
        int audioSelected = mMediaPlayer.getSelectedTrack(ITrackInfo.MEDIA_TRACK_TYPE_AUDIO);
        int index = 0;
        for (IjkTrackInfo info : trackInfo) {
            if (info.getTrackType() == ITrackInfo.MEDIA_TRACK_TYPE_AUDIO) {//音轨信息
                TrackInfoBean a = new TrackInfoBean();
                String name = processAudioName(info.getInfoInline());
                a.language = info.getLanguage();
                if(name.startsWith("aac"))a.language="中文";
                a.name = name;
                String language = getFriendlyLanguage(a.language, info.getInfoInline());
                a.language = language;
                a.name = buildDisplayName("\u97f3\u8f68", data.getAudio().size() + 1, language, name);
                a.trackId = index;
                a.index = index;
                a.selected = index == audioSelected;
                // 如果需要，还可以检查轨道的描述或标题以获取更多信息
                data.addAudio(a);
            }
            else if (info.getTrackType() == ITrackInfo.MEDIA_TRACK_TYPE_TIMEDTEXT) {//内置字幕
                TrackInfoBean t = new TrackInfoBean();
                t.name = info.getInfoInline();
                t.language = info.getLanguage();
                String language = getFriendlyLanguage(t.language, t.name);
                t.language = language;
                t.name = buildDisplayName("\u5b57\u5e55", data.getSubtitle().size() + 1, language, "");
                t.trackId = index;
                t.index = index;
                t.selected = index == subtitleSelected;
                data.addSubtitle(t);
            }
            index++;
        }
        return data;
    }
    // 处理音轨名称格式
    private String processAudioName(String rawName) {
        if (rawName == null) return "";
        return rawName.replace("AUDIO,", "")
                .replace("N/A,", "")
                .replace(" ", "")
                .replaceAll("^,+|,+$", "")
                .replace(",", " / ");
    }
    private String getFriendlyLanguage(String language, String rawInfo) {
        String text = ((language == null ? "" : language) + " " + (rawInfo == null ? "" : rawInfo)).toLowerCase();
        if (text.contains("yue") || text.contains("cantonese") || text.contains("\u7ca4") || text.contains("\u5e7f\u4e1c")) {
            return "\u7ca4\u8bed";
        }
        if (text.contains("zh") || text.contains("chi") || text.contains("zho") || text.contains("chs")
                || text.contains("cht") || text.contains("cmn") || text.contains("\u4e2d")
                || text.contains("\u56fd\u8bed") || text.contains("\u666e\u901a\u8bdd")) {
            return "\u56fd\u8bed";
        }
        if (text.contains("en") || text.contains("eng") || text.contains("english") || text.contains("\u82f1")) {
            return "\u82f1\u8bed";
        }
        if (text.contains("ja") || text.contains("jpn") || text.contains("japanese") || text.contains("\u65e5")) {
            return "\u65e5\u8bed";
        }
        if (text.contains("ko") || text.contains("kor") || text.contains("korean") || text.contains("\u97e9")) {
            return "\u97e9\u8bed";
        }
        if (text.contains("tha") || text.contains("thai") || text.contains("th")) {
            return "\u6cf0\u8bed";
        }
        return "";
    }
    private String buildDisplayName(String prefix, int number, String language, String detail) {
        StringBuilder builder = new StringBuilder(prefix).append(" ").append(number);
        if (language != null && !language.isEmpty()) {
            builder.append(" - ").append(language);
        }
        if (detail != null && !detail.isEmpty()) {
            builder.append(" ").append(detail);
        }
        return builder.toString();
    }
    public void setTrack(int trackIndex) {
        int audioSelected = mMediaPlayer.getSelectedTrack(ITrackInfo.MEDIA_TRACK_TYPE_AUDIO);
        int subtitleSelected = mMediaPlayer.getSelectedTrack(ITrackInfo.MEDIA_TRACK_TYPE_TIMEDTEXT);
        if (trackIndex!=audioSelected && trackIndex!=subtitleSelected){
            mMediaPlayer.selectTrack(trackIndex);
        }
    }
    public void setTrack(int trackIndex,String playKey) {
        int audioSelected = mMediaPlayer.getSelectedTrack(ITrackInfo.MEDIA_TRACK_TYPE_AUDIO);
        if (trackIndex!=audioSelected){
            if (!playKey.isEmpty()) {
                memory.save(playKey, trackIndex);
            }
            mMediaPlayer.selectTrack(trackIndex);
        }
    }
    public void setOnTimedTextListener(IMediaPlayer.OnTimedTextListener listener) {
        mMediaPlayer.setOnTimedTextListener(listener);
    }
    public void loadDefaultTrack(TrackInfo trackInfo,String playKey) {
        if(trackInfo!=null && trackInfo.getAudio().size()>1){
            Integer trackIndex = memory.ijkLoad(playKey);
            if (trackIndex == -1) {
                int firsIndex=trackInfo.getAudio().get(0).index;
                setTrack(firsIndex);
                return;
            };
            setTrack(trackIndex);
        }
    }
}


