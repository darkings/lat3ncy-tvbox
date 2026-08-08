#!/usr/bin/env python3
import pytest
from urllib.error import URLError
from ponyo_source_manager.probes.playback import (
    classify_direct_sample,
    parse_m3u8,
    resolve_hls_child_url,
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
