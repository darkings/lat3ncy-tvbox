#!/usr/bin/env python3
"""VIP 解析服务：过短点播应丢弃，让后续解析结果顶上。"""
from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "jx_parse_server.py"


def _load_jx():
    spec = importlib.util.spec_from_file_location("jx_parse_server", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_media_usable_rejects_short_vod(monkeypatch):
    jx = _load_jx()

    def fake_inspect(url, **_kwargs):
        if "short" in url:
            return {
                "ok": False,
                "duration_s": 90.0,
                "is_vod": True,
                "reason": "short vod 90.0s < 180s",
            }
        return {"ok": True, "duration_s": 1200.0, "is_vod": True, "reason": "ok"}

    monkeypatch.setattr(
        "ponyo_source_manager.probes.playback.inspect_hls_duration",
        fake_inspect,
    )
    assert jx._media_usable("https://cdn.test/short.m3u8") is False
    assert jx._media_usable("https://cdn.test/full.m3u8") is True
    # mp4 / ts 不走 HLS 时长探测，避免把直链当播放列表去拉
    assert jx._media_usable("https://cdn.test/clip.mp4") is True


def test_first_usable_skips_preview_and_returns_next(monkeypatch):
    jx = _load_jx()

    def fake_usable(url: str) -> bool:
        return "full" in url

    monkeypatch.setattr(jx, "_media_usable", fake_usable)
    found = [
        "https://cdn.test/preview.m3u8",
        "https://cdn.test/full.m3u8",
    ]
    checked: set[str] = set()
    got = asyncio.run(jx._first_usable(found, checked))
    assert got == "https://cdn.test/full.m3u8"
    assert checked == set(found)


def test_first_usable_returns_none_when_all_short(monkeypatch):
    jx = _load_jx()
    monkeypatch.setattr(jx, "_media_usable", lambda _url: False)
    found = ["https://cdn.test/a.m3u8", "https://cdn.test/b.m3u8"]
    checked: set[str] = set()
    assert asyncio.run(jx._first_usable(found, checked)) is None
    assert checked == set(found)
