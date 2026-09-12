#!/usr/bin/env python3
import pytest
from urllib.error import URLError
from ponyo_source_manager.probes.playback import (
    classify_direct_sample,
    inspect_hls_duration,
    is_short_vod_media,
    parse_m3u8,
    resolve_hls_child_url,
    sniff_media_url,
    verify_playback,
)


def test_parse_m3u8_media():
    content = """#EXTM3U
#EXT-X-TARGETDURATION:10
#EXTINF:9.009,
http://example.com/seg1.ts
#EXTINF:9.009,
http://example.com/seg2.ts
"""
    res = parse_m3u8(content)
    assert res["valid"] is True
    assert res["is_master"] is False
    assert len(res["segments"]) == 2
    assert res["duration_s"] == 18.018
    assert res["has_endlist"] is False


def test_parse_m3u8_master():
    content = """#EXTM3U
#EXT-X-STREAM-INF:BANDWIDTH=1280000,RESOLUTION=720x480
http://example.com/low.m3u8
#EXT-X-STREAM-INF:BANDWIDTH=2560000,RESOLUTION=1080x720
http://example.com/mid.m3u8
"""
    res = parse_m3u8(content)
    assert res["valid"] is True
    assert res["is_master"] is True
    assert len(res["variants"]) == 2


def test_verify_playback_mock(monkeypatch):
    def mock_fetch(url, headers, is_bytes=False, max_bytes=0, timeout=8):
        if is_bytes:
            return b"fake_ts_data"
        return """#EXTM3U
#EXTINF:5.0,
seg1.ts
#EXTINF:5.0,
seg2.ts
"""
    monkeypatch.setattr("ponyo_source_manager.probes.playback.fetch_with_headers", mock_fetch)
    res = verify_playback("http://example.com/test.m3u8", mode="deep")
    assert res["success"] == 1
    assert res["m3u8_ok"] == 1
    assert res["segments_ok"] == 2


def test_direct_sample_rejects_webpages_and_accepts_media_magic(monkeypatch):
    monkeypatch.setattr(
        "ponyo_source_manager.probes.playback.fetch_direct_sample",
        lambda *_args, **_kwargs: {
            "data": b"<!doctype html><html>player page</html>",
            "content_type": "text/html",
            "final_url": "https://video.test/watch.html",
        },
    )
    rejected = verify_playback("https://video.test/watch")
    assert rejected["success"] == 0
    assert rejected["error"] == "webpage/non-media payload rejected"
    assert classify_direct_sample(
        b"\x00\x00\x00\x18ftypmp42", "application/octet-stream"
    ) == "media"


def test_sniff_media_url_extracts_and_prioritizes_m3u8():
    html = (
        b'<html><video src="/hls/low.m3u8"></video>'
        b'<a href="https://x.test/v.mp4"></a></html>'
    )
    assert sniff_media_url(html, "https://page.test/watch") == (
        "https://page.test/hls/low.m3u8"
    )


def test_webpage_sniffing_fallback(monkeypatch):
    """网页里嵌了 m3u8 时，应嗅探后重验证并成功。"""
    def fake_fetch_direct_sample(url, headers, **kw):
        return {
            "data": b'<html><video src="https://media.test/hls/index.m3u8"></video></html>',
            "content_type": "text/html",
            "final_url": "https://video.test/watch.html",
        }

    def fake_fetch_with_headers(url, headers, is_bytes=False, **kw):
        if is_bytes:
            return b"\x47" + b"x" * 187 + b"\x47"
        return "#EXTM3U\n#EXTINF:5.0,\nseg1.ts\n"

    monkeypatch.setattr(
        "ponyo_source_manager.probes.playback.fetch_direct_sample",
        fake_fetch_direct_sample,
    )
    monkeypatch.setattr(
        "ponyo_source_manager.probes.playback.fetch_with_headers",
        fake_fetch_with_headers,
    )
    res = verify_playback("https://video.test/watch", mode="fast")
    assert res["success"] == 1
    assert res.get("sniffed_url") == "https://media.test/hls/index.m3u8"


def test_extensionless_hls_manifest_enters_segment_validation(monkeypatch):
    manifest = b"#EXTM3U\n#EXTINF:5.0,\nseg1.ts\n#EXTINF:5.0,\nseg2.ts\n"
    monkeypatch.setattr(
        "ponyo_source_manager.probes.playback.fetch_direct_sample",
        lambda *_args, **_kwargs: {
            "data": manifest,
            "content_type": "application/vnd.apple.mpegurl",
            "final_url": "https://video.test/live/channel",
        },
    )
    monkeypatch.setattr(
        "ponyo_source_manager.probes.playback.fetch_with_headers",
        lambda *_args, **_kwargs: b"\x47" + b"x" * 187 + b"\x47",
    )
    result = verify_playback("https://video.test/live/channel", mode="fast")
    assert result["success"] == 1
    assert result["m3u8_ok"] == 1
    assert result["segments_ok"] == 1


def test_fetch_encodes_unicode_iri_and_retries_transient_error(monkeypatch):
    from ponyo_source_manager.probes import playback

    requested = []

    class Response:
        headers = {"Content-Type": "application/vnd.apple.mpegurl"}

        def read(self, _max_bytes):
            return b"#EXTM3U\n"

        def info(self):
            return self.headers

        def close(self):
            pass

    def open_response(request, timeout):
        requested.append(request.full_url)
        if len(requested) == 1:
            raise URLError("temporary dns failure")
        return Response()

    monkeypatch.setattr(playback.net._ssrf_opener, "open", open_response)
    text = playback.fetch_with_headers(
        "https://media.test/中文/第一集.m3u8", {}, timeout=1
    )
    assert text.startswith("#EXTM3U")
    assert len(requested) == 2
    assert "%E4%B8%AD%E6%96%87" in requested[-1]


def test_local_proxy_hls_children_resolve_against_embedded_upstream():
    manifest = (
        "http://127.0.0.1:5757/proxy/央视大全/"
        "https://media.example/hls/channel/master.m3u8"
    )
    assert resolve_hls_child_url(manifest, "segment-1.ts") == (
        "https://media.example/hls/channel/segment-1.ts"
    )


def _vod_playlist(total_s: float, *, endlist: bool = True, playlist_type: str = "VOD") -> str:
    """构造指定总时长的点播 m3u8，默认带 ENDLIST。"""
    # 用 10 秒切片拼出目标时长，最后一片补余数
    segs = []
    remain = float(total_s)
    while remain > 0:
        dur = 10.0 if remain > 10 else remain
        segs.append(f"#EXTINF:{dur:.3f},\nseg{len(segs)}.ts")
        remain -= dur
    header = "#EXTM3U\n#EXT-X-TARGETDURATION:10\n"
    if playlist_type:
        header += f"#EXT-X-PLAYLIST-TYPE:{playlist_type}\n"
    footer = "\n#EXT-X-ENDLIST\n" if endlist else "\n"
    return header + "\n".join(segs) + footer


def test_inspect_hls_duration_rejects_one_to_two_minute_vod():
    """1～2 分钟且带 ENDLIST 的点播应判为试看片。"""
    playlists = {
        "https://cdn.test/90s.m3u8": _vod_playlist(90),
        "https://cdn.test/120s.m3u8": _vod_playlist(120),
        "https://cdn.test/179s.m3u8": _vod_playlist(179),
    }

    def fake_fetch(url, _headers):
        return playlists[url]

    for url, expected in (
        ("https://cdn.test/90s.m3u8", 90.0),
        ("https://cdn.test/120s.m3u8", 120.0),
        ("https://cdn.test/179s.m3u8", 179.0),
    ):
        info = inspect_hls_duration(url, fetch=fake_fetch)
        assert info["ok"] is False
        assert info["is_vod"] is True
        assert info["duration_s"] == expected
        assert is_short_vod_media(url, fetch=fake_fetch) is True


def test_inspect_hls_duration_keeps_normal_episode_and_live_window():
    """正常 20 分钟点播应保留；无 ENDLIST 的直播短窗口不能当试看片误杀。"""
    playlists = {
        "https://cdn.test/20min.m3u8": _vod_playlist(20 * 60),
        "https://cdn.test/live.m3u8": _vod_playlist(30, endlist=False, playlist_type=""),
        "https://cdn.test/event.m3u8": _vod_playlist(45, endlist=False, playlist_type="EVENT"),
    }

    def fake_fetch(url, _headers):
        return playlists[url]

    long_vod = inspect_hls_duration("https://cdn.test/20min.m3u8", fetch=fake_fetch)
    assert long_vod["ok"] is True
    assert long_vod["duration_s"] == 1200.0
    assert is_short_vod_media("https://cdn.test/20min.m3u8", fetch=fake_fetch) is False

    live = inspect_hls_duration("https://cdn.test/live.m3u8", fetch=fake_fetch)
    assert live["ok"] is True
    assert live["is_vod"] is False
    assert is_short_vod_media("https://cdn.test/live.m3u8", fetch=fake_fetch) is False

    event = inspect_hls_duration("https://cdn.test/event.m3u8", fetch=fake_fetch)
    assert event["ok"] is True
    assert event["is_vod"] is False


def test_inspect_hls_duration_follows_master_playlist():
    """master playlist 应跟随最高带宽变体，再按媒体列表时长判断。"""
    playlists = {
        "https://cdn.test/master.m3u8": (
            "#EXTM3U\n"
            "#EXT-X-STREAM-INF:BANDWIDTH=800000,RESOLUTION=640x360\n"
            "low.m3u8\n"
            "#EXT-X-STREAM-INF:BANDWIDTH=2500000,RESOLUTION=1280x720\n"
            "high.m3u8\n"
        ),
        "https://cdn.test/high.m3u8": _vod_playlist(90),
        "https://cdn.test/low.m3u8": _vod_playlist(1200),
    }

    def fake_fetch(url, _headers):
        return playlists[url]

    info = inspect_hls_duration("https://cdn.test/master.m3u8", fetch=fake_fetch)
    assert info["ok"] is False
    assert info["duration_s"] == 90.0
    assert is_short_vod_media("https://cdn.test/master.m3u8", fetch=fake_fetch) is True


def test_inspect_hls_duration_allows_unreadable_or_non_hls():
    """拉不到播放列表、非 m3u8 都应放行，避免把解析结果整条打死。"""

    def boom(_url, _headers):
        raise TimeoutError("cdn timeout")

    info = inspect_hls_duration("https://cdn.test/timeout.m3u8", fetch=boom)
    assert info["ok"] is True
    assert info["duration_s"] is None
    assert is_short_vod_media("https://cdn.test/timeout.m3u8", fetch=boom) is False
    assert is_short_vod_media("https://cdn.test/clip.mp4") is False
    assert is_short_vod_media("") is False
