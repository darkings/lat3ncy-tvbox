#!/usr/bin/env python3
"""HLS 播放验证：支持快速检测和深度检测。支持 TVBox 请求头。
"""
from __future__ import annotations

import re
import time
import json
import urllib.request
from urllib.error import HTTPError, URLError
import subprocess
import tempfile
import os
from urllib.parse import urljoin, urlsplit

from ponyo_source_manager.core import net
from ponyo_source_manager.core.common import iri_to_uri


def parse_tvbox_headers(ext_str: str) -> dict:
    """解析 ext 字符串中的 header（例如 JSON 或 url#header 格式）。"""
    headers = {"User-Agent": "ponyo-source-manager/1.0"}
    if not ext_str:
        return headers
    
    # 尝试 JSON
    try:
        if ext_str.startswith("{"):
            data = json.loads(ext_str)
            if "header" in data:
                headers.update(data["header"])
            return headers
    except Exception:
        pass

    # 尝试 url#key=value;key=value
    if "#" in ext_str:
        parts = ext_str.split("#", 1)[1].split(";")
        for part in parts:
            if "=" in part:
                k, v = part.split("=", 1)
                headers[k.strip()] = v.strip()
    return headers


def parse_m3u8(content: str) -> dict:
    """解析 m3u8 播放列表。"""
    lines = content.strip().splitlines()
    if not lines or "#EXTM3U" not in lines[0]:
        return {"valid": False, "error": "not a valid m3u8"}

    is_master = any("#EXT-X-STREAM-INF" in line for line in lines)
    playlist_type = ""
    has_endlist = False
    for line in lines:
        stripped = line.strip()
        if stripped == "#EXT-X-ENDLIST":
            has_endlist = True
        elif stripped.startswith("#EXT-X-PLAYLIST-TYPE:"):
            playlist_type = stripped.split(":", 1)[1].strip().upper()

    result: dict = {
        "valid": True,
        "is_master": is_master,
        "has_endlist": has_endlist,
        "playlist_type": playlist_type,
        "duration_s": None,
    }

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
        result["duration_s"] = round(sum(s["duration"] for s in segments), 3)

    return result


def resolve_hls_child_url(manifest_url: str, child_url: str) -> str:
    """Resolve HLS children against an upstream URL embedded in a local proxy."""
    child_url = str(child_url or "").strip()
    if child_url.startswith(("http://", "https://")):
        return child_url
    try:
        host = (urlsplit(manifest_url).hostname or "").lower()
    except ValueError:
        host = ""
    base_url = manifest_url
    if host in {"127.0.0.1", "localhost"}:
        matches = list(re.finditer(r"https?://", manifest_url, flags=re.IGNORECASE))
        if len(matches) >= 2:
            base_url = manifest_url[matches[1].start():]
    return urljoin(base_url, child_url)


# VIP 解析出的正片（电影/剧集）不应短于 3 分钟。
# 1～2 分钟且带 ENDLIST 的点播，基本是解析器试看片/广告，应丢弃。
# 直播滑动窗口通常也只有几十秒，但没有 ENDLIST / PLAYLIST-TYPE:VOD，不能按短时长误杀。
MIN_ACCEPTABLE_VOD_DURATION_S = 180.0
_HLS_DURATION_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36"
)


def inspect_hls_duration(
    url: str,
    *,
    min_vod_s: float = MIN_ACCEPTABLE_VOD_DURATION_S,
    timeout: float = 6.0,
    headers: dict | None = None,
    fetch=None,
    max_depth: int = 2,
    _depth: int = 0,
) -> dict:
    """读取 HLS 播放列表，判断是否为过短点播。

    测不到时长、直播/EVENT 窗口、非 m3u8 都放行（ok=True），避免误杀。
    只有明确 VOD（ENDLIST 或 PLAYLIST-TYPE:VOD）且总时长低于门槛才拒绝。
    """
    headers = headers or {"User-Agent": _HLS_DURATION_UA}
    fetch_fn = fetch
    if fetch_fn is None:
        def fetch_fn(fetch_url, fetch_headers):
            return fetch_with_headers(
                fetch_url, fetch_headers, timeout=timeout, is_bytes=False
            )
    try:
        text = fetch_fn(url, headers)
    except Exception as exc:
        return {
            "ok": True,
            "duration_s": None,
            "is_vod": False,
            "reason": f"duration fetch failed: {exc}",
        }

    parsed = parse_m3u8(text if isinstance(text, str) else "")
    if not parsed.get("valid"):
        return {
            "ok": True,
            "duration_s": None,
            "is_vod": False,
            "reason": parsed.get("error") or "not a valid m3u8",
        }

    if parsed.get("is_master"):
        if _depth >= max_depth:
            return {
                "ok": True,
                "duration_s": None,
                "is_vod": False,
                "reason": "master playlist depth exceeded",
            }
        variants = parsed.get("variants") or []
        if not variants:
            return {
                "ok": True,
                "duration_s": None,
                "is_vod": False,
                "reason": "master m3u8 has no variants",
            }
        best = max(variants, key=lambda item: item.get("bandwidth", 0))
        child = resolve_hls_child_url(url, best.get("url") or "")
        return inspect_hls_duration(
            child,
            min_vod_s=min_vod_s,
            timeout=timeout,
            headers=headers,
            fetch=fetch,
            max_depth=max_depth,
            _depth=_depth + 1,
        )

    duration = parsed.get("duration_s")
    if duration is None:
        duration = sum(
            float(seg.get("duration") or 0) for seg in (parsed.get("segments") or [])
        )
    is_vod = bool(parsed.get("has_endlist") or parsed.get("playlist_type") == "VOD")
    if is_vod and duration < min_vod_s:
        return {
            "ok": False,
            "duration_s": duration,
            "is_vod": True,
            "reason": f"short vod {duration:.1f}s < {min_vod_s:.0f}s",
        }
    return {
        "ok": True,
        "duration_s": duration,
        "is_vod": is_vod,
        "reason": "ok",
    }


def is_short_vod_media(
    url: str,
    *,
    min_vod_s: float = MIN_ACCEPTABLE_VOD_DURATION_S,
    fetch=None,
) -> bool:
    """VIP 解析结果是否应丢弃：明确过短的点播 m3u8 返回 True。

    非 m3u8、直播窗口、拉不到播放列表时返回 False（放行）。
    """
    if not url:
        return False
    lowered = str(url).lower()
    path = lowered.split("?", 1)[0]
    if not (path.endswith((".m3u8", ".m3u")) or ".m3u8" in lowered):
        return False
    info = inspect_hls_duration(url, min_vod_s=min_vod_s, fetch=fetch)
    return not bool(info.get("ok", True))


def fetch_with_headers(url: str, headers: dict, timeout: float = 8.0, is_bytes=False, max_bytes=8388608):
    last_error = None
    for attempt in range(2):
        try:
            req = urllib.request.Request(iri_to_uri(url), headers=headers)
            resp = net._ssrf_opener.open(req, timeout=timeout)
            try:
                data = net._read_and_decompress(resp, max_bytes)
                if not is_bytes:
                    return data.decode("utf-8", errors="replace")
                return data
            finally:
                getattr(resp, "close", lambda: None)()
        except HTTPError:
            raise
        except (URLError, TimeoutError, OSError) as exc:
            last_error = exc
            if attempt == 1:
                raise
    raise last_error  # pragma: no cover


def fetch_direct_sample(url: str, headers: dict, timeout: float = 8.0,
                        max_bytes: int = 65536) -> dict:
    """Fetch a bounded sample together with non-secret response metadata."""
    last_error = None
    for attempt in range(2):
        try:
            req = urllib.request.Request(iri_to_uri(url), headers=headers)
            resp = net._ssrf_opener.open(req, timeout=timeout)
            try:
                data = net._read_and_decompress(resp, max_bytes)
                return {
                    "data": data,
                    "content_type": str(resp.headers.get("Content-Type", "")).split(";", 1)[0].lower(),
                    "final_url": str(getattr(resp, "geturl", lambda: url)()),
                }
            finally:
                getattr(resp, "close", lambda: None)()
        except HTTPError:
            raise
        except (URLError, TimeoutError, OSError) as exc:
            last_error = exc
            if attempt == 1:
                raise
    raise last_error  # pragma: no cover


def classify_direct_sample(data: bytes, content_type: str = "") -> str:
    """Classify a bounded direct response without trusting URL extensions."""
    sample = bytes(data or b"")
    lowered = sample[:4096].lstrip().lower()
    content_type = str(content_type or "").lower()
    if (
        content_type in {"text/html", "application/xhtml+xml", "application/json"}
        or lowered.startswith((b"<!doctype html", b"<html", b"<script", b"{"))
    ):
        return "webpage"
    if lowered.startswith(b"#extm3u") or content_type in {
        "application/vnd.apple.mpegurl", "application/x-mpegurl",
    }:
        return "hls_manifest"
    media_magic = (
        len(sample) >= 12 and sample[4:12].startswith(b"ftyp"),
        sample.startswith(b"\x1aE\xdf\xa3"),
        sample.startswith((b"FLV", b"OggS", b"RIFF", b"ID3")),
        len(sample) >= 189 and sample[0] == 0x47 and sample[188] == 0x47,
        len(sample) >= 2 and sample[0] == 0xFF and (sample[1] & 0xF0) == 0xF0,
    )
    if content_type.startswith(("video/", "audio/")) or any(media_magic):
        return "media"
    return "unknown"


_MEDIA_URL_RE = re.compile(
    r"""https?://[^\s"'<>\\]+?\.(?:m3u8|m3u|mp4|m4a|mp3)(?:\?[^\s"'<>\\]*)?|"""
    r"""[./][^\s"'<>\\]+?\.(?:m3u8|m3u|mp4|m4a|mp3)(?:\?[^\s"'<>\\]*)?|"""
    r"""[A-Za-z0-9_-]+\.(?:m3u8|m3u|mp4|m4a|mp3)(?:\?[^\s"'<>\\]*)?""",
    re.IGNORECASE,
)


def sniff_media_url(html: bytes, base_url: str) -> str:
    """从网页/JSON 文本里嗅探 m3u8/mp4/m4a/mp3 媒体地址（一次回退）。

    只做静态正则提取，不执行 JS；用于把「播放地址其实是网页/接口响应」的源
    救回真实媒体直链。m3u8 优先，其次 mp4/m4a/mp3。
    """
    if not html:
        return ""
    try:
        text = html.decode("utf-8", errors="replace")
    except Exception:
        return ""
    # 解码 JSON 转义斜杠，便于匹配 API 返回的 url 字段
    text = text.replace("\\/", "/")
    candidates: list[str] = []
    for m in _MEDIA_URL_RE.finditer(text):
        u = m.group(0)
        if not u.startswith(("http://", "https://")):
            if u.startswith("//"):
                u = "https:" + u
            else:
                u = urljoin(base_url, u)
        candidates.append(u)
    # 去重，m3u8 优先
    seen: set[str] = set()
    ordered: list[str] = []
    for u in candidates:
        if u in seen:
            continue
        seen.add(u)
        ordered.append(u)
    ordered.sort(key=lambda u: (0 if u.lower().endswith((".m3u8", ".m3u")) else 1))
    return ordered[0] if ordered else ""


def check_media_with_ffprobe(data: bytes) -> dict:
    """使用 ffprobe 验证切片数据是否为有效媒体。"""
    if not data:
        return {"valid": False, "error": "empty data"}
    
    with tempfile.NamedTemporaryFile(delete=False) as f:
        f.write(data)
        tmp_path = f.name
        
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,width,height", "-of", "json", tmp_path],
            capture_output=True, text=True, timeout=5
        )
        if r.returncode != 0:
            return {"valid": False, "error": "ffprobe failed"}
        info = json.loads(r.stdout)
        streams = info.get("streams", [])
        if any(s.get("codec_type") in ("video", "audio") for s in streams):
            return {"valid": True, "info": streams}
        return {"valid": False, "error": "no audio/video stream found"}
    except Exception as e:
        return {"valid": False, "error": str(e)}
    finally:
        os.unlink(tmp_path)


def verify_playback(play_url: str, mode: str = "fast", ext_str: str = "", _sniff_depth: int = 0) -> dict:
    """完整播放验证流程。mode 可选 'fast' 或 'deep'。

    当直链返回网页/非媒体时，尝试一次静态嗅探回退（提取 m3u8/mp4 等媒体地址），
    避免把「播放地址是网页/接口响应」的源直接判死。
    """
    result = {
        "success": 0, "m3u8_ok": 0, "segments_total": 0, "segments_checked": 0,
        "segments_ok": 0, "latency_ms": 0, "first_frame_ms": 0, "throughput_kbps": 0,
        "error": None, "ffprobe_valid": 0
        , "segment_error_types": []
    }
    t0 = time.monotonic()
    
    headers = parse_tvbox_headers(ext_str)

    if not play_url:
        result["error"] = "empty play url"
        return result

    is_hls = play_url.split("?")[0].endswith((".m3u8", ".m3u")) or "m3u8" in play_url

    preloaded_m3u8 = None
    if not is_hls:
        try:
            sample = fetch_direct_sample(play_url, headers)
            data = sample["data"]
            sample_type = classify_direct_sample(data, sample.get("content_type", ""))
            result["latency_ms"] = int((time.monotonic() - t0) * 1000)
            if sample_type == "hls_manifest":
                is_hls = True
                preloaded_m3u8 = data.decode("utf-8", errors="replace")
                play_url = sample.get("final_url") or play_url
            elif sample_type == "media":
                result["success"] = 1
                return result
            elif sample_type == "webpage":
                if _sniff_depth < 1:
                    sniffed = sniff_media_url(
                        data, sample.get("final_url") or play_url
                    )
                    if sniffed:
                        sub = verify_playback(
                            sniffed,
                            mode=mode,
                            ext_str=ext_str,
                            _sniff_depth=_sniff_depth + 1,
                        )
                        sub["sniffed_from"] = play_url
                        sub["sniffed_url"] = sniffed
                        return sub
                result["error"] = "webpage/non-media payload rejected"
                return result
            else:
                result["error"] = "unknown non-media payload rejected"
                return result
        except Exception as e:
            result["error"] = str(e)[:300]
            result["latency_ms"] = int((time.monotonic() - t0) * 1000)
            return result

    # HLS 流
    if preloaded_m3u8 is not None:
        m3u8_text = preloaded_m3u8
    else:
        try:
            m3u8_text = fetch_with_headers(play_url, headers, is_bytes=False)
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

    if parsed.get("is_master"):
        variants = parsed.get("variants", [])
        if not variants:
            result["error"] = "master m3u8 has no variants"
            result["latency_ms"] = int((time.monotonic() - t0) * 1000)
            return result
        best = max(variants, key=lambda v: v.get("bandwidth", 0))
        variant_url = best["url"]
        variant_url = resolve_hls_child_url(play_url, variant_url)
        try:
            m3u8_text = fetch_with_headers(variant_url, headers, is_bytes=False)
        except Exception as e:
            result["error"] = f"variant m3u8 fetch failed: {e}"
            result["latency_ms"] = int((time.monotonic() - t0) * 1000)
            return result
        parsed = parse_m3u8(m3u8_text)
        if not parsed.get("valid"):
            result["error"] = "variant m3u8 invalid"
            result["latency_ms"] = int((time.monotonic() - t0) * 1000)
            return result
        play_url = variant_url

    segments = parsed.get("segments", [])
    result["segments_total"] = len(segments)

    if not segments:
        result["error"] = "m3u8 has no segments"
        result["latency_ms"] = int((time.monotonic() - t0) * 1000)
        return result

    # fast: 1 fragment, deep: 3 fragments
    max_segments = 1 if mode == "fast" else 3
    to_check = segments[:max_segments]
    result["segments_checked"] = len(to_check)
    
    total_bytes = 0
    t_start_dl = time.monotonic()
    
    for i, seg in enumerate(to_check):
        seg_url = seg["url"]
        seg_url = resolve_hls_child_url(play_url, seg_url)
        try:
            t_seg = time.monotonic()
            data = fetch_with_headers(seg_url, headers, is_bytes=True, max_bytes=5242880) # 5MB max per seg
            if len(data) > 0:
                result["segments_ok"] += 1
                total_bytes += len(data)
                
                # fast 模式下测第一帧 latency，同时深度检测下验证 codec
                if i == 0:
                    result["first_frame_ms"] = int((time.monotonic() - t_seg) * 1000)
                    if mode == "deep":
                        ff_res = check_media_with_ffprobe(data)
                        if ff_res.get("valid"):
                            result["ffprobe_valid"] = 1
        except Exception as e:
            error_type = type(e).__name__
            if isinstance(e, HTTPError):
                error_type = f"HTTP_{e.code}"
            if error_type not in result["segment_error_types"]:
                result["segment_error_types"].append(error_type)

    t_end_dl = time.monotonic()
    result["latency_ms"] = int((t_end_dl - t0) * 1000)
    
    if total_bytes > 0 and (t_end_dl - t_start_dl) > 0:
        result["throughput_kbps"] = int((total_bytes * 8 / 1000) / (t_end_dl - t_start_dl))
        
    required_ok = 1 if mode == "fast" else min(2, len(to_check))
    result["success"] = 1 if result["segments_ok"] >= required_ok else 0
    
    if not result["success"] and not result["error"]:
        result["error"] = (f"only {result['segments_ok']}/{result['segments_checked']} segments readable")
        
    return result
