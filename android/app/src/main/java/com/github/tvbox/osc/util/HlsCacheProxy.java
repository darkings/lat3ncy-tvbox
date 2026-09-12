package com.github.tvbox.osc.util;

import android.text.TextUtils;

import com.github.catvod.net.OkHttp;
import com.orhanobut.hawk.Hawk;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.net.URLEncoder;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

import okhttp3.Request;
import okhttp3.Response;

/**
 * 点播 HLS 缓存加速代理：
 * - 播放器把 m3u8 交给本代理（/hls?url=...），代理拉取播放列表并把分片/密钥/子播放列表
 *   的 URI 全部改写回本代理，保证所有分片请求都经过本代理。
 * - 分片首次命中时下载并落盘缓存；同时后台并发预取后续分片
 *   （直播 LIVE_PREFETCH_AHEAD=2，点播 VOD_PREFETCH_AHEAD=4），
 *   把「播放器串行拉取」提升为「代理并发提前下载」，显著提高慢源的可用吞吐。
 * - 命中缓存直接回放，二次观看/拖动进度条免网络。
 */
public class HlsCacheProxy {

    private static final String TAG = "HlsCacheProxy";
    // 直播窗口只预取后续 2 片，避免和正在播的分片抢带宽。
    // 点播没有滑动窗口，预取 4 片才能把 IJK 的 high-water-mark 喂饱，减少卡顿。
    private static final int LIVE_PREFETCH_AHEAD = 2;
    private static final int VOD_PREFETCH_AHEAD = 4;

    /**
     * 直播窗口窄，多预取会和当前片抢带宽；
     * 点播没有滑动窗口，要把 IJK high-water-mark 喂饱。
     */
    private static int prefetchAhead() {
        return Hawk.get(HawkConfig.PLAYER_IS_LIVE, false) ? LIVE_PREFETCH_AHEAD : VOD_PREFETCH_AHEAD;
    }
    // 仅直播窗口使用：播放器最多看到最近已缓存分片，用来攒缓冲
    private static final int LIVE_KEEP = 8;
    // 仅直播窗口使用：首播从直播边缘后退，避免一上来就追最新未缓存分片
    private static final int LIVE_BEHIND = 3;
    private static final Set<String> polling = ConcurrentHashMap.newKeySet();
    // 分片下载超时（慢分片快速失败，避免占满预取线程池）
    private static final long SEGMENT_TIMEOUT_MS = 15000L;
    // 主分片/播放列表下载超时（源挂起时快速失败返回，不让播放器卡死等 30s）
    private static final long SERVE_TIMEOUT_MS = 20000L;
    private static final long CACHE_MAX_BYTES = 512L * 1024 * 1024;
    private static final String UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36";

    private static final ExecutorService prefetchPool = Executors.newFixedThreadPool(3);
    // 播放列表地址 -> 有序分片地址（已绝对化，未编码）
    private static final ConcurrentHashMap<String, List<String>> playlists = new ConcurrentHashMap<>();
    // 源端原始播放列表文本，刷新时优先本地秒回，避免和分片下载抢连接
    private static final ConcurrentHashMap<String, String> liveRawPlaylists = new ConcurrentHashMap<>();
    // 分片地址 -> 所在播放列表地址 + 序号（用于预取后续分片）
    private static final ConcurrentHashMap<String, SegRef> segIndex = new ConcurrentHashMap<>();
    // 已入缓存的文件（分片地址 -> 缓存文件）
    private static final ConcurrentHashMap<String, File> cacheIndex = new ConcurrentHashMap<>();
    // 正在下载的分片（去重：同一分片不重复提交下载）
    private static final Set<String> downloading = ConcurrentHashMap.newKeySet();
    // 每个直播播放列表钉死的起播分片，刷新列表时不能跟着直播边缘跑
    private static final ConcurrentHashMap<String, String> livePins = new ConcurrentHashMap<>();
    // 钉住分片对应的 MEDIA-SEQUENCE，后续本地窗口用它算序号，避免 IJK 看到序号乱跳
    private static final ConcurrentHashMap<String, Long> livePinSeq = new ConcurrentHashMap<>();
    // 从钉住分片开始的本地历史窗口。源端只有 5 片，旧钉滑出后必须靠这里续播
    private static final ConcurrentHashMap<String, List<LiveSeg>> liveHistory = new ConcurrentHashMap<>();
    // 直播分片下载锁池：按 URL 隔离，不同分片并行下载，同分片串行去重
    private static final ConcurrentHashMap<String, Object> LIVE_DL_LOCKS = new ConcurrentHashMap<>();
    // 分片下载失败计数：URL -> 连续失败次数
    private static final ConcurrentHashMap<String, Integer> FAIL_COUNTS = new ConcurrentHashMap<>();
    // 分片下载黑名单：URL -> 拉黑截止时间戳（毫秒）
    private static final ConcurrentHashMap<String, Long> BLACKLIST = new ConcurrentHashMap<>();
    // 黑名单阈值：连续失败 3 次拉黑 60 秒
    private static final int FAIL_THRESHOLD = 3;
    private static final long BLACKLIST_MS = 60_000L;
    private static volatile long cacheBytes = 0L;

    private static boolean isBlacklisted(String url) {
        Long until = BLACKLIST.get(url);
        if (until == null) return false;
        if (System.currentTimeMillis() > until) {
            BLACKLIST.remove(url);
            FAIL_COUNTS.remove(url);
            return false;
        }
        return true;
    }

    private static void addFailCount(String url) {
        int count = FAIL_COUNTS.getOrDefault(url, 0) + 1;
        FAIL_COUNTS.put(url, count);
        if (count >= FAIL_THRESHOLD) {
            BLACKLIST.put(url, System.currentTimeMillis() + BLACKLIST_MS);
            LOG.e("echo-hls-blacklist-add " + url.substring(url.lastIndexOf('/') + 1) + " fails=" + count);
        }
    }

    private static void clearFailCount(String url) {
        FAIL_COUNTS.remove(url);
        BLACKLIST.remove(url);
    }

    private static final class SegRef {
        final String playlist;
        final int index;

        SegRef(String playlist, int index) {
            this.playlist = playlist;
            this.index = index;
        }
    }

    /** 直播分片：绝对 URL + 原始 #EXTINF，用来在源窗口滑走后本地重写播放列表。 */
    private static final class LiveSeg {
        final String url;
        final String inf;

        LiveSeg(String url, String inf) {
            this.url = url;
            this.inf = (inf == null || inf.isEmpty()) ? "#EXTINF:10.000," : inf;
        }
    }

    /** 把 m3u8 播放地址包装成本地代理地址（携带源要求的请求头）。 */
    public static String wrap(String url, Map<String, String> headers) {
        if (url == null || url.isEmpty() || !url.startsWith("http")) return url;
        if (url.contains("/hls?url=")) return url;
        StringBuilder sb = new StringBuilder("http://127.0.0.1:")
                .append(com.github.tvbox.osc.server.RemoteServer.serverPort)
                .append("/hls?url=").append(enc(url));
        appendHeader(sb, headers, "User-Agent", "ua");
        appendHeader(sb, headers, "Referer", "referer");
        appendHeader(sb, headers, "Origin", "origin");
        appendHeader(sb, headers, "Cookie", "cookie");
        // 预热：后台先拉一次上游 m3u8，提前完成 TLS 握手与 OkHttp 连接池热身。
        // 播放器随后请求本地代理时上游连接已复用，避免冷启动 7-10s TLS 导致 ijk -10000。
        // 仅预热不缓存内容（列表本身很小），失败静默——真正播放时 serve() 会再拉。
        final String upstream = url;
        final Map<String, String> upHeaders = headers;
        prefetchPool.execute(new Runnable() {
            @Override
            public void run() {
                try {
                    Request.Builder rb = new Request.Builder().url(upstream);
                    String ua = upHeaders == null ? null : upHeaders.get("User-Agent");
                    rb.header("User-Agent", TextUtils.isEmpty(ua) ? UA : ua);
                    String ref = upHeaders == null ? null : upHeaders.get("Referer");
                    if (!TextUtils.isEmpty(ref)) rb.header("Referer", ref);
                    // 只取响应头不读 body 也能完成握手，但读 body 才能确保连接完整可用；
                    // 列表很小（几 KB），直接读完丢弃。
                    Response resp = OkHttp.client(SERVE_TIMEOUT_MS).newCall(rb.build()).execute();
                    try {
                        if (resp.isSuccessful() && resp.body() != null) {
                            resp.body().string();
                            LOG.i("echo-hls-warm " + upstream.substring(upstream.lastIndexOf('/') + 1));
                        }
                    } finally {
                        resp.close();
                    }
                } catch (Throwable t) {
                    // 预热失败静默：真正播放时 serve() 会重试
                }
            }
        });
        return sb.toString();
    }

    private static void appendHeader(StringBuilder sb, Map<String, String> headers, String from, String to) {
        if (headers == null) return;
        String v = headers.get(from);
        if (TextUtils.isEmpty(v)) return;
        sb.append('&').append(to).append('=').append(enc(v));
    }

    private static String enc(String s) {
        try {
            return URLEncoder.encode(s, "UTF-8");
        } catch (Throwable t) {
            return "";
        }
    }

    /** 处理 /hls 请求，返回 {status, mime, InputStream}。 */
    public static Object[] serve(Map<String, String> params) {
        String url = params == null ? null : params.get("url");
        if (TextUtils.isEmpty(url)) return null;
        try {
            Request.Builder rb = new Request.Builder().url(url);
            String v = params.get("ua");
            rb.header("User-Agent", TextUtils.isEmpty(v) ? UA : v);
            for (String[] pair : new String[][]{{"referer", "Referer"}, {"origin", "Origin"}, {"cookie", "Cookie"}}) {
                String val = params.get(pair[0]);
                if (!TextUtils.isEmpty(val)) rb.header(pair[1], val);
            }
            String lower = url.toLowerCase();
            boolean maybeM3u8 = lower.contains(".m3u8");
            if (!maybeM3u8) {
                Object[] streamed = serveLiveSegment(url);
                if (streamed != null) return streamed;
                return new Object[]{502, "text/plain", new ByteArrayInputStream(new byte[0])};
            }
            // 只有真正进过直播 pin 的播放列表才走本地窗口，点播不得误用。
            if (livePins.containsKey(url)) {
                String cachedPlaylist = serveLivePlaylistFromHistory(url, params);
                if (cachedPlaylist != null) {
                    LOG.i("echo-hls-playlist-local " + url.substring(url.lastIndexOf('/') + 1));
                    return new Object[]{200, "application/vnd.apple.mpegurl", new ByteArrayInputStream(cachedPlaylist.getBytes("UTF-8"))};
                }
            }
            Response resp = OkHttp.client(SERVE_TIMEOUT_MS).newCall(rb.build()).execute();
            if (!resp.isSuccessful() || resp.body() == null) {
                int code = resp.code();
                resp.close();
                return new Object[]{code, "text/plain", new ByteArrayInputStream(new byte[0])};
            }
            try {
                String content = resp.body().string();
                String rewritten = rewriteM3u8(url, content, params);
                LOG.i("echo-hls-playlist " + url.substring(url.lastIndexOf('/') + 1));
                return new Object[]{200, "application/vnd.apple.mpegurl", new ByteArrayInputStream(rewritten.getBytes("UTF-8"))};
            } finally {
                resp.close();
            }
        } catch (Throwable t) {
            LOG.e("echo-hls-serve-error " + t.getMessage());
            return null;
        }
    }

    private static String rewriteM3u8(String baseUrl, String content, Map<String, String> params) {
        String[] lines = content.replace("\r\n", "\n").replace('\r', '\n').split("\n", -1);
        List<String> segs = new ArrayList<>();
        StringBuilder out = new StringBuilder();
        boolean isMaster = false;
        for (String line : lines) {
            String item = line.trim();
            if (item.isEmpty() || item.startsWith("#")) {
                // 处理 #EXT-X-KEY 的 URI 属性
                if (item.startsWith("#EXT-X-KEY") || item.startsWith("#EXT-X-SESSION-KEY")) {
                    out.append(rewriteUriAttr(baseUrl, line, params)).append('\n');
                } else {
                    if (item.startsWith("#EXT-X-STREAM-INF")) isMaster = true;
                    out.append(line).append('\n');
                }
            } else {
                String abs = absUrl(baseUrl, item);
                String proxied = proxied(abs, params);
                out.append(proxied).append('\n');
                if (isMaster || abs.toLowerCase().contains(".m3u8")) {
                    // 子播放列表：也要走代理（递归时记录）
                } else {
                    segs.add(abs);
                }
            }
        }
        if (!segs.isEmpty()) {
            // 本播放列表的分片顺序记录下来，供后续分片请求触发预取
            playlists.put(baseUrl, segs);
            for (int i = 0; i < segs.size(); i++) {
                segIndex.put(segs.get(i), new SegRef(baseUrl, i));
            }
            // 点播缺 ENDLIST 时绝不能进直播 pin/history，否则会裁窗口、钉分片。
            boolean live = !content.contains("#EXT-X-ENDLIST")
                    && Hawk.get(HawkConfig.PLAYER_IS_LIVE, false);
            if (live && !segs.isEmpty()) {
                liveRawPlaylists.put(baseUrl, content);
                mergeLiveHistory(baseUrl, content, segs);
                List<LiveSeg> history = liveHistory.get(baseUrl);
                if (history == null || history.isEmpty()) history = toLiveSegs(content, segs);
                List<String> histUrls = urlsOf(history);
                playlists.put(baseUrl, histUrls);
                for (int i = 0; i < histUrls.size(); i++) {
                    segIndex.put(histUrls.get(i), new SegRef(baseUrl, i));
                }
                String pin = livePins.get(baseUrl);
                int pinIndex = pin == null ? -1 : histUrls.indexOf(pin);
                if (pinIndex < 0) {
                    // 钉在直播边缘后 1 片。后续即使源窗口滑走，也继续用本地历史续播，绝不重钉到最新片。
                    pinIndex = Math.max(0, histUrls.size() - 1 - LIVE_BEHIND);
                    pin = histUrls.get(pinIndex);
                    livePins.put(baseUrl, pin);
                    livePinSeq.put(baseUrl, parseMediaSequence(content) + pinIndex);
                    LOG.i("echo-hls-live-pin " + pin.substring(pin.lastIndexOf('/') + 1)
                            + " idx=" + pinIndex + "/" + histUrls.size());
                }
                if (!cacheIndex.containsKey(pin)) {
                    prefetchRange(baseUrl, pinIndex, pinIndex + 1);
                }
                int lastCached = -1;
                if (cacheIndex.containsKey(pin)) {
                    lastCached = pinIndex;
                    for (int i = pinIndex + 1; i < histUrls.size(); i++) {
                        if (!cacheIndex.containsKey(histUrls.get(i))) break;
                        lastCached = i;
                    }
                }
                int keepFrom;
                int keepTo;
                if (lastCached < 0) {
                    keepFrom = pinIndex;
                    keepTo = pinIndex + 1;
                } else {
                    keepTo = lastCached + 1;
                    keepFrom = Math.max(pinIndex, lastCached + 1 - LIVE_KEEP);
                    prefetchRange(baseUrl, lastCached + 1, lastCached + 1 + prefetchAhead());
                }
                long pinSeq = livePinSeq.get(baseUrl) == null ? 0L : livePinSeq.get(baseUrl);
                String sliced = buildLivePlaylist(content, history, keepFrom, keepTo, pinSeq + (keepFrom - pinIndex), params);
                LOG.i("echo-hls-live-window from=" + keepFrom + " to=" + keepTo
                        + " lastCached=" + lastCached + " hist=" + histUrls.size()
                        + " keep=" + histUrls.get(keepFrom).substring(histUrls.get(keepFrom).lastIndexOf('/') + 1));
                startLivePoll(baseUrl, params);
                return sliced;
            }
        }
        return out.toString();
    }

    private static String rewriteUriAttr(String base, String line, Map<String, String> params) {
        java.util.regex.Matcher m = java.util.regex.Pattern.compile("URI=\"([^\"]+)\"").matcher(line);
        StringBuffer sb = new StringBuffer();
        while (m.find()) {
            String abs = absUrl(base, m.group(1));
            m.appendReplacement(sb, java.util.regex.Matcher.quoteReplacement("URI=\"" + proxied(abs, params) + "\""));
        }
        m.appendTail(sb);
        return sb.toString();
    }

    private static String absUrl(String base, String url) {
        if (url == null) return "";
        if (url.startsWith("http://") || url.startsWith("https://")) return url;
        try {
            return new java.net.URI(base).resolve(url).toString();
        } catch (Throwable t) {
            int slash = base.lastIndexOf('/');
            return base.substring(0, slash + 1) + url;
        }
    }

    private static String proxied(String absUrl, Map<String, String> params) {
        StringBuilder sb = new StringBuilder("http://127.0.0.1:")
                .append(com.github.tvbox.osc.server.RemoteServer.serverPort)
                .append("/hls?url=").append(enc(absUrl));
        for (String[] pair : new String[][]{{"ua", "ua"}, {"referer", "referer"}, {"origin", "origin"}, {"cookie", "cookie"}}) {
            String v = params.get(pair[0]);
            if (!TextUtils.isEmpty(v)) sb.append('&').append(pair[1]).append('=').append(enc(v));
        }
        return sb.toString();
    }

    private static List<LiveSeg> toLiveSegs(String content, List<String> segs) {
        List<String> infs = parseExtInf(content);
        List<LiveSeg> out = new ArrayList<>();
        for (int i = 0; i < segs.size(); i++) {
            String inf = i < infs.size() ? infs.get(i) : "#EXTINF:10.000,";
            out.add(new LiveSeg(segs.get(i), inf));
        }
        return out;
    }

    private static List<String> parseExtInf(String content) {
        List<String> infs = new ArrayList<>();
        for (String line : content.replace("\r\n", "\n").replace('\r', '\n').split("\n", -1)) {
            if (line.trim().startsWith("#EXTINF")) infs.add(line.trim());
        }
        return infs;
    }

    private static long parseMediaSequence(String content) {
        for (String line : content.replace("\r\n", "\n").replace('\r', '\n').split("\n", -1)) {
            String item = line.trim();
            if (item.startsWith("#EXT-X-MEDIA-SEQUENCE:")) {
                try {
                    return Long.parseLong(item.substring(item.indexOf(':') + 1).trim());
                } catch (Exception ignored) {
                    return 0L;
                }
            }
        }
        return 0L;
    }

    private static List<String> urlsOf(List<LiveSeg> segs) {
        List<String> urls = new ArrayList<>();
        for (LiveSeg seg : segs) urls.add(seg.url);
        return urls;
    }

    /**
     * 把源端新窗口接到本地历史后面。源只有 5 片，旧钉滑出后必须靠这里续播。
     */
    private static void mergeLiveHistory(String playlistUrl, String content, List<String> fresh) {
        List<LiveSeg> incoming = toLiveSegs(content, fresh);
        List<LiveSeg> hist = liveHistory.get(playlistUrl);
        if (hist == null || hist.isEmpty()) {
            liveHistory.put(playlistUrl, new ArrayList<>(incoming));
            return;
        }
        Set<String> seen = new HashSet<>();
        for (LiveSeg seg : hist) seen.add(seg.url);
        for (LiveSeg seg : incoming) {
            if (seen.add(seg.url)) hist.add(seg);
        }
        String pin = livePins.get(playlistUrl);
        int pinIndex = pin == null ? 0 : urlsOf(hist).indexOf(pin);
        if (pinIndex < 0) pinIndex = 0;
        int drop = Math.max(0, pinIndex - 2);
        if (drop > 0) {
            hist.subList(0, drop).clear();
        }
        liveHistory.put(playlistUrl, hist);
    }

    /** 用本地历史窗口重写播放列表，只暴露已缓存/钉住的分片。 */
    private static String buildLivePlaylist(String original, List<LiveSeg> history, int keepFrom, int keepTo, long mediaSeq, Map<String, String> params) {
        StringBuilder out = new StringBuilder();
        out.append("#EXTM3U\n");
        String target = "#EXT-X-TARGETDURATION:10";
        for (String line : original.replace("\r\n", "\n").replace('\r', '\n').split("\n", -1)) {
            String item = line.trim();
            if (item.startsWith("#EXT-X-TARGETDURATION")) {
                target = item;
                break;
            }
        }
        out.append(target).append('\n');
        out.append("#EXT-X-VERSION:3\n");
        out.append("#EXT-X-MEDIA-SEQUENCE:").append(Math.max(0L, mediaSeq)).append('\n');
        int from = Math.max(0, keepFrom);
        int to = Math.min(history.size(), Math.max(from + 1, keepTo));
        for (int i = from; i < to; i++) {
            LiveSeg seg = history.get(i);
            out.append(seg.inf).append('\n');
            out.append(proxied(seg.url, params == null ? Collections.emptyMap() : params)).append('\n');
        }
        return out.toString();
    }

    /**
     * 只保留 [keepFrom, keepTo) 这段分片。
     * 旧实现按 drop 裁掉开头后仍会把后面未缓存的新片留给 IJK。
     */
    private static String sliceLivePlaylist(String playlist, int keepFrom, int keepTo) {
        String[] lines = playlist.replace("\r\n", "\n").replace('\r', '\n').split("\n", -1);
        StringBuilder out = new StringBuilder();
        int segIdx = 0;
        int kept = 0;
        int need = Math.max(0, keepTo - keepFrom);
        boolean skipSeg = false;
        for (String line : lines) {
            String item = line.trim();
            if (item.startsWith("#EXT-X-MEDIA-SEQUENCE:")) {
                try {
                    long seq = Long.parseLong(item.substring(item.indexOf(':') + 1).trim());
                    out.append("#EXT-X-MEDIA-SEQUENCE:").append(seq + keepFrom).append('\n');
                } catch (Exception e) {
                    out.append(line).append('\n');
                }
                continue;
            }
            boolean segTag = item.startsWith("#EXTINF")
                    || item.startsWith("#EXT-X-BYTERANGE")
                    || item.startsWith("#EXT-X-PROGRAM-DATE-TIME")
                    || item.startsWith("#EXT-X-DISCONTINUITY");
            if (segTag) {
                skipSeg = segIdx < keepFrom || kept >= need;
                if (skipSeg) continue;
            }
            if (!item.isEmpty() && !item.startsWith("#")) {
                if (segIdx < keepFrom || kept >= need) {
                    segIdx++;
                    skipSeg = false;
                    continue;
                }
                kept++;
                segIdx++;
                skipSeg = false;
                out.append(line).append('\n');
                continue;
            }
            if (skipSeg) continue;
            out.append(line).append('\n');
        }
        return out.toString();
    }

    /** 已有本地历史时，刷新播放列表不再打源站，避免和分片下载抢连接。 */
    private static String serveLivePlaylistFromHistory(String playlistUrl, Map<String, String> params) {
        List<LiveSeg> history = liveHistory.get(playlistUrl);
        if (history == null || history.isEmpty()) return null;
        String pin = livePins.get(playlistUrl);
        if (TextUtils.isEmpty(pin)) return null;
        List<String> histUrls = urlsOf(history);
        int pinIndex = histUrls.indexOf(pin);
        if (pinIndex < 0) return null;
        int lastCached = -1;
        if (cacheIndex.containsKey(pin)) {
            lastCached = pinIndex;
            for (int i = pinIndex + 1; i < histUrls.size(); i++) {
                if (!cacheIndex.containsKey(histUrls.get(i))) break;
                lastCached = i;
            }
        }
        int keepFrom = lastCached < 0 ? pinIndex : Math.max(pinIndex, lastCached + 1 - LIVE_KEEP);
        int keepTo = lastCached < 0 ? pinIndex + 1 : lastCached + 1;
        long pinSeq = livePinSeq.get(playlistUrl) == null ? 0L : livePinSeq.get(playlistUrl);
        String original = liveRawPlaylists.get(playlistUrl);
        if (original == null) original = "#EXTM3U\n#EXT-X-TARGETDURATION:10\n";
        LOG.i("echo-hls-live-window-local from=" + keepFrom + " to=" + keepTo
                + " lastCached=" + lastCached + " hist=" + histUrls.size()
                + " keep=" + histUrls.get(keepFrom).substring(histUrls.get(keepFrom).lastIndexOf('/') + 1));
        return buildLivePlaylist(original, history, keepFrom, keepTo, pinSeq + (keepFrom - pinIndex), params);
    }

    /**
     * 直播分片：已缓存直接回；正在下则边下边吐；都没有才新开一条流。
     * 不能再等整片 11MB 下完，否则播放器必然一卡一开。
     */
    private static Object[] serveLiveSegment(String url) {
        byte[] cached = readCache(url);
        if (cached != null) {
            LOG.i("echo-hls-hit " + url.substring(url.lastIndexOf('/') + 1));
            prefetchAfter(url);
            return new Object[]{200, "video/mp2t", new ByteArrayInputStream(cached)};
        }
        if (downloading.contains(url)) {
            LOG.i("echo-hls-stream-wait " + url.substring(url.lastIndexOf('/') + 1));
            InputStream stream = streamPrefetch(url);
            if (stream != null) return new Object[]{200, "video/mp2t", stream};
        }
        try {
            Request.Builder rb = new Request.Builder().url(url).header("User-Agent", UA);
            Response resp = OkHttp.client(SEGMENT_TIMEOUT_MS).newCall(rb.build()).execute();
            if (!resp.isSuccessful() || resp.body() == null) {
                if (resp != null) resp.close();
                return null;
            }
            LOG.i("echo-hls-stream-open " + url.substring(url.lastIndexOf('/') + 1));
            prefetchAfter(url);
            return new Object[]{200, "video/mp2t", streamAndCache(resp, url)};
        } catch (Throwable t) {
            LOG.e("echo-hls-stream-error " + t.getMessage());
            return null;
        }
    }

    private static InputStream streamPrefetch(final String url) {
        final File[] holder = new File[1];
        for (int i = 0; i < 80; i++) {
            File f = cacheIndex.get(url);
            if (f != null && f.isFile() && f.length() > 0) {
                holder[0] = f;
                break;
            }
            if (!downloading.contains(url) && cacheIndex.get(url) == null) return null;
            try {
                Thread.sleep(50);
            } catch (InterruptedException e) {
                return null;
            }
        }
        if (holder[0] == null) {
            byte[] cached = readCache(url);
            return cached == null ? null : new ByteArrayInputStream(cached);
        }
        try {
            return new FileInputStream(holder[0]);
        } catch (Throwable t) {
            return null;
        }
    }

    private static byte[] serveCachedSegment(String url) {
        byte[] cached = readCache(url);
        if (cached != null) {
            LOG.i("echo-hls-hit " + url.substring(url.lastIndexOf('/') + 1));
            prefetchAfter(url);
            return cached;
        }
        cached = waitForPrefetch(url);
        if (cached != null) {
            LOG.i("echo-hls-wait-hit " + url.substring(url.lastIndexOf('/') + 1));
            prefetchAfter(url);
            return cached;
        }
        LOG.i("echo-hls-sync-fetch " + url.substring(url.lastIndexOf('/') + 1));
        fetchAndCache(url);
        cached = readCache(url);
        if (cached != null) prefetchAfter(url);
        return cached;
    }

    private static void startLivePoll(final String playlistUrl, final Map<String, String> params) {
        if (!polling.add(playlistUrl)) return;
        prefetchPool.execute(new Runnable() {
            @Override
            public void run() {
                try {
                    for (int i = 0; i < 80; i++) {
                        try {
                            Thread.sleep(2000);
                        } catch (InterruptedException e) {
                            return;
                        }
                        try {
                            Request.Builder rb = new Request.Builder().url(playlistUrl);
                            String ua = params.get("ua");
                            rb.header("User-Agent", TextUtils.isEmpty(ua) ? UA : ua);
                            try (Response resp = OkHttp.client(8000L).newCall(rb.build()).execute()) {
                                if (!resp.isSuccessful() || resp.body() == null) continue;
                                String body = resp.body().string();
                                List<String> segs = new ArrayList<>();
                                for (String line : body.replace("\r\n", "\n").replace('\r', '\n').split("\n", -1)) {
                                    String item = line.trim();
                                    if (item.isEmpty() || item.startsWith("#")) continue;
                                    String abs = absUrl(playlistUrl, item);
                                    if (!abs.toLowerCase().contains(".m3u8")) segs.add(abs);
                                }
                                if (segs.isEmpty()) continue;
                                playlists.put(playlistUrl, segs);
                                for (int s = 0; s < segs.size(); s++) {
                                    segIndex.put(segs.get(s), new SegRef(playlistUrl, s));
                                }
                                liveRawPlaylists.put(playlistUrl, body);
                                mergeLiveHistory(playlistUrl, body, segs);
                                List<LiveSeg> history = liveHistory.get(playlistUrl);
                                List<String> histUrls = history == null ? segs : urlsOf(history);
                                playlists.put(playlistUrl, histUrls);
                                for (int s = 0; s < histUrls.size(); s++) {
                                    segIndex.put(histUrls.get(s), new SegRef(playlistUrl, s));
                                }
                                String pin = livePins.get(playlistUrl);
                                int pinIndex = pin == null ? -1 : histUrls.indexOf(pin);
                                int lastCached = -1;
                                if (pinIndex >= 0 && cacheIndex.containsKey(pin)) {
                                    lastCached = pinIndex;
                                    for (int s = pinIndex + 1; s < histUrls.size(); s++) {
                                        if (!cacheIndex.containsKey(histUrls.get(s))) break;
                                        lastCached = s;
                                    }
                                }
                                String target;
                                if (pinIndex >= 0 && !cacheIndex.containsKey(pin)) {
                                    target = pin;
                                } else if (lastCached >= 0 && lastCached + 1 < histUrls.size()) {
                                    target = histUrls.get(lastCached + 1);
                                } else {
                                    continue;
                                }
                                if (cacheIndex.containsKey(target) || downloading.contains(target)) continue;
                                if (isBlacklisted(target)) {
                                    LOG.i("echo-hls-poll-blacklist " + target.substring(target.lastIndexOf('/') + 1));
                                    continue;
                                }
                                LOG.i("echo-hls-poll-prefetch " + target.substring(target.lastIndexOf('/') + 1));
                                fetchAndCache(target);
                            }
                        } catch (Throwable ignored) {
                        }
                    }
                } finally {
                    polling.remove(playlistUrl);
                }
            }
        });
    }

    private static byte[] waitForPrefetch(String url) {
        if (!downloading.contains(url)) return null;
        LOG.i("echo-hls-wait " + url.substring(url.lastIndexOf('/') + 1));
        for (int i = 0; i < 200; i++) {
            byte[] cached = readCache(url);
            if (cached != null) return cached;
            if (!downloading.contains(url)) return readCache(url);
            try {
                Thread.sleep(200);
            } catch (InterruptedException e) {
                return null;
            }
        }
        return readCache(url);
    }

    private static InputStream streamAndCache(final Response resp, final String url) {
        final InputStream in = resp.body().byteStream();
        final ByteArrayOutputStream acc = new ByteArrayOutputStream();
        downloading.add(url);
        return new InputStream() {
            private boolean done;

            @Override
            public int read() throws IOException {
                byte[] one = new byte[1];
                int n = read(one, 0, 1);
                return n < 0 ? -1 : (one[0] & 0xff);
            }

            @Override
            public int read(byte[] b, int off, int len) throws IOException {
                int n = in.read(b, off, len);
                if (n > 0) {
                    acc.write(b, off, n);
                } else if (n < 0) {
                    finish(true);
                }
                return n;
            }

            @Override
            public void close() {
                finish(false);
            }

            private void finish(boolean complete) {
                if (done) return;
                done = true;
                try {
                    in.close();
                } catch (Throwable ignored) {
                }
                try {
                    resp.close();
                } catch (Throwable ignored) {
                }
                if (complete) writeCache(url, acc.toByteArray());
                downloading.remove(url);
            }
        };
    }

    private static void prefetchAfter(String segmentUrl) {
        SegRef ref = segIndex.get(segmentUrl);
        if (ref == null) return;
        prefetchRange(ref.playlist, ref.index + 1, ref.index + 1 + prefetchAhead());
    }

    private static void prefetchRange(final String playlist, int from, int to) {
        List<String> segs = playlists.get(playlist);
        if (segs == null) return;
        int end = Math.min(to, segs.size());
        for (int i = Math.max(0, from); i < end; i++) {
            final String seg = segs.get(i);
            if (cacheIndex.containsKey(seg) || !downloading.add(seg)) continue;
            prefetchPool.execute(new Runnable() {
                @Override
                public void run() {
                    fetchAndCache(seg);
                }
            });
        }
    }

    private static void fetchAndCache(String url) {
        if (cacheIndex.containsKey(url)) {
            downloading.remove(url);
            return;
        }
        // 失败黑名单：同一 URL 连续失败 3 次则拉黑 60 秒，避免无限重试浪费带宽
        if (isBlacklisted(url)) {
            LOG.i("echo-hls-prefetch-blacklist " + url.substring(url.lastIndexOf('/') + 1));
            return;
        }
        downloading.add(url);
        Object lock = LIVE_DL_LOCKS.computeIfAbsent(url, k -> new Object());
        synchronized (lock) {
            // 重试 2 次：网络抖动时快速重试，避免一次失败就卡顿
            for (int retry = 0; retry < 2; retry++) {
                try {
                    if (cacheIndex.containsKey(url)) {
                        clearFailCount(url);
                        return;
                    }
                    Request.Builder rb = new Request.Builder().url(url).header("User-Agent", UA);
                    if (retry > 0) LOG.i("echo-hls-prefetch-retry-" + retry + " " + url.substring(url.lastIndexOf('/') + 1));
                    else LOG.i("echo-hls-prefetch " + url.substring(url.lastIndexOf('/') + 1));
                    try (Response resp = OkHttp.client(SEGMENT_TIMEOUT_MS).newCall(rb.build()).execute()) {
                        if (resp.isSuccessful() && resp.body() != null) {
                            byte[] data = resp.body().bytes();
                            writeCache(url, data);
                            LOG.i("echo-hls-prefetch-ok " + data.length + " " + url.substring(url.lastIndexOf('/') + 1));
                            clearFailCount(url);
                            return;
                        }
                    }
                } catch (Throwable t) {
                    LOG.e("echo-hls-prefetch-error-" + retry + " " + t.getMessage());
                }
            }
            // 2 次重试都失败，计入黑名单
            addFailCount(url);
            downloading.remove(url);
        }
    }

    private static byte[] readCache(String url) {
        File f = cacheIndex.get(url);
        if (f != null && f.isFile()) {
            try (FileInputStream in = new FileInputStream(f)) {
                byte[] buf = new byte[(int) f.length()];
                int off = 0, n;
                while (off < buf.length && (n = in.read(buf, off, buf.length - off)) >= 0) off += n;
                return buf;
            } catch (Throwable ignored) {
            }
        }
        return null;
    }

    private static synchronized void writeCache(String url, byte[] data) {
        if (data == null || data.length == 0) return;
        if (cacheIndex.containsKey(url)) return;
        try {
            File dir = new File(FileUtils.getCachePath() + "/hls/");
            if (!dir.exists()) dir.mkdirs();
            File f = new File(dir, MD5.string2MD5(url) + ".ts");
            try (FileOutputStream out = new FileOutputStream(f)) {
                out.write(data);
                out.flush();
            }
            cacheIndex.put(url, f);
            cacheBytes += data.length;
            evictIfNeeded(dir);
        } catch (Throwable ignored) {
        }
    }

    private static void evictIfNeeded(File dir) {
        if (cacheBytes <= CACHE_MAX_BYTES) return;
        File[] files = dir.listFiles();
        if (files == null) return;
        Arrays.sort(files, (a, b) -> Long.compare(a.lastModified(), b.lastModified()));
        for (File f : files) {
            if (cacheBytes <= CACHE_MAX_BYTES) break;
            long len = f.length();
            if (f.delete()) cacheBytes -= len;
        }
        // 清理已删除文件的索引
        cacheIndex.entrySet().removeIf(e -> !e.getValue().exists());
    }

    public static void clear() {
        playlists.clear();
        segIndex.clear();
        cacheIndex.clear();
        livePins.clear();
        livePinSeq.clear();
        liveHistory.clear();
        liveRawPlaylists.clear();
        cacheBytes = 0L;
    }
}








