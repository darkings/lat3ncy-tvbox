#!/usr/bin/env python3
import pytest
from test_playback import parse_m3u8, verify_playback


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


def test_verify_playback_mock():
    def mock_fetch_text(url):
        return """#EXTM3U
#EXTINF:5.0,
seg1.ts
#EXTINF:5.0,
seg2.ts
"""
    def mock_fetch_bytes(url, max_bytes=65536):
        return b"fake_ts_data"

    res = verify_playback("http://example.com/test.m3u8",
                          fetch_text=mock_fetch_text,
                          fetch_bytes=mock_fetch_bytes)
    assert res["success"] == 1
    assert res["m3u8_ok"] == 1
    assert res["segments_ok"] == 2
