#!/usr/bin/env python3
import pytest
from media_quality import classify_quality, analyze_stream


def test_classify_quality():
    assert classify_quality(2160, 12_000_000) == "uhd"
    assert classify_quality(1080, 4_000_000) == "fhd"
    assert classify_quality(720, 2_000_000) == "hd"
    assert classify_quality(480, 800_000) == "sd"


def test_analyze_stream():
    mock_ffprobe_res = {
        "success": True,
        "streams": [
            {"codec_type": "video", "width": 1920, "height": 1080, "codec_name": "h264", "bit_rate": "3500000", "r_frame_rate": "30/1"},
            {"codec_type": "audio", "codec_name": "aac"}
        ],
        "format": {"duration": "120.5"}
    }
    info = analyze_stream(mock_ffprobe_res)
    assert info["success"] == 1
    assert info["height"] == 1080
    assert info["quality_tier"] == "fhd"
    assert info["video_codec"] == "h264"
    assert info["frame_rate"] == 30.0
