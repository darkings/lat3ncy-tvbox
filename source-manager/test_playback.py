#!/usr/bin/env python3
"""HLS 播放验证：不只检查 HTTP 200，要下载 m3u8 → 解析 → 读取分片 → 验证。

对应 PLAN §六 第 5 层。
"""
from __future__ import annotations

import re
import time
from urllib.parse import urljoin

import net


def parse_m3u8(content: str) -> dict:
    """解析 m3u8 播放列表。

    返回：
    - is_master: 是否为多清晰度主列表
    - variants: [{url, bandwidth, resolution}]  (master)
    - segments: [{url, duration}]  (media)
    """
    lines = content.strip().splitlines()
    if not lines or "#EXTM3U" not in lines[0]:
        return {"valid": False, "error": "not a valid m3u8"}

    is_master = any("#EXT-X-STREAM-INF" in line for line in lines)
    result: dict = {"valid": True, "is_master": is_master}

    if is_master:
        variants = []
        for i, line in enumerate(lines):
            if "#EXT-X-STREAM-INF" in line:
                attrs = line.split(":", 1)[1] if ":" in line else ""
                bw_m = re.search(r"BANDWIDTH=(\d+)", attrs)
                res_m = re.search(r"RESOLUTION=(\d+x\d+)", attrs)
                url = lines[i + 1].strip() if i + 1 < len(lines) else ""
                if url and not url.startswith("#"):
                    variants.append({
                        "url": url,
                        "bandwidth": int(bw_m.group(1)) if bw_m else 0,
                        "resolution": res_m.group(1) if res_m else "",
                    })
        result["variants"] = variants
    else:
        segments = []
        for i, line in enumerate(lines):
            if "#EXTINF:" in line:
                dur_m = re.search(r"#EXTINF:([\d.]+)", line)
                url = lines[i + 1].strip() if i + 1 < len(lines) else ""
                if url and not url.startswith("#"):
                    segments.append({
                        "url": url,
                        "duration": float(dur_m.group(1)) if dur_m else 0,
                    })
        result["segments"] = segments

    return result


def verify_playback(play_url: str, *, fetch_text=net.fetch_text,
                    fetch_bytes=net.fetch_bytes, max_segments=3,
                    headers=None) -> dict:
    """完整播放验证流程：

    1. 下载 m3u8 播放列表
    2. 解析（支持 master → 选最高清 → 再下载 media m3u8）
    3. 连续读取 2-3 个分片，验证非空
    4. 检查分片真实存在且可读取

    返回 {success, m3u8_ok, segments_total, segments_checked,
          segments_ok, latency_ms, error}
    """
    result = {
        "success": 0, "m3u8_ok": 0,
        "segments_total": 0, "segments_checked": 0, "segments_ok": 0,
        "latency_ms": 0, "error": None,
    }
    t0 = time.monotonic()

    # 非 m3u8 地址（mp4 直链等），只检查可达性
    if not play_url:
        result["error"] = "empty play url"
        return result

    is_hls = play_url.endswith((".m3u8", ".m3u")) or "m3u8" in play_url

    if not is_hls:
        # 直链，尝试 range 请求前几个字节
        try:
            data = fetch_bytes(play_url, max_bytes=4096)
            result["success"] = 1 if len(data) > 0 else 0
            result["latency_ms"] = int((time.monotonic() - t0) * 1000)
            if not data:
                result["error"] = "empty response for direct url"
        except Exception as e:
            result["error"] = str(e)[:300]
            result["latency_ms"] = int((time.monotonic() - t0) * 1000)
        return result

    # HLS 流
    try:
        m3u8_text = fetch_text(play_url)
    except Exception as e:
        result["error"] = f"m3u8 fetch failed: {e}"
        result["latency_ms"] = int((time.monotonic() - t0) * 1000)
        return result

    parsed = parse_m3u8(m3u8_text)
    if not parsed.get("valid"):
        result["error"] = parsed.get("error", "invalid m3u8")
        result["latency_ms"] = int((time.monotonic() - t0) * 1000)
        return result

    result["m3u8_ok"] = 1

    # 如果是 master 列表，选最高带宽的 variant
    if parsed.get("is_master"):
        variants = parsed.get("variants", [])
        if not variants:
            result["error"] = "master m3u8 has no variants"
            result["latency_ms"] = int((time.monotonic() - t0) * 1000)
            return result
        best = max(variants, key=lambda v: v.get("bandwidth", 0))
        variant_url = best["url"]
        if not variant_url.startswith("http"):
            variant_url = urljoin(play_url, variant_url)
        try:
            m3u8_text = fetch_text(variant_url)
        except Exception as e:
            result["error"] = f"variant m3u8 fetch failed: {e}"
            result["latency_ms"] = int((time.monotonic() - t0) * 1000)
            return result
        parsed = parse_m3u8(m3u8_text)
        if not parsed.get("valid"):
            result["error"] = "variant m3u8 invalid"
            result["latency_ms"] = int((time.monotonic() - t0) * 1000)
            return result
        play_url = variant_url  # 更新 base URL 用于相对路径

    segments = parsed.get("segments", [])
    result["segments_total"] = len(segments)

    if not segments:
        result["error"] = "m3u8 has no segments"
        result["latency_ms"] = int((time.monotonic() - t0) * 1000)
        return result

    # 连续读取前几个分片
    to_check = segments[:max_segments]
    result["segments_checked"] = len(to_check)

    for seg in to_check:
        seg_url = seg["url"]
        if not seg_url.startswith("http"):
            seg_url = urljoin(play_url, seg_url)
        try:
            data = fetch_bytes(seg_url, max_bytes=65536)
            if len(data) > 0:
                result["segments_ok"] += 1
        except Exception:
            pass

    result["latency_ms"] = int((time.monotonic() - t0) * 1000)
    result["success"] = 1 if result["segments_ok"] >= min(2, len(to_check)) else 0
    if not result["success"] and not result["error"]:
        result["error"] = (f"only {result['segments_ok']}/{result['segments_checked']}"
                          " segments readable")
    return result
