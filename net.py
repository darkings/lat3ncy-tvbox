#!/usr/bin/env python3
"""网络 I/O 唯一出口：URL 分类 + 分层探测 + 文本下载（可注入，便于 mock 测试）。"""
from __future__ import annotations
import socket, ssl, time
from datetime import datetime, timezone
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

_LOCAL_PREFIXES = ("127.", "10.", "192.168.", "localhost")
_HDRS = {"Range": "bytes=0-0", "User-Agent": "ponyo-source-manager/1.0"}

def _is_local(host: str) -> bool:
    h = (host or "").lower()
    if h in ("localhost",) or any(h.startswith(p) for p in _LOCAL_PREFIXES):
        return True
    if h.startswith("172."):
        try:
            return 16 <= int(h.split(".")[1]) <= 31
        except (IndexError, ValueError):
            return False
    return False

def classify_url(url: str) -> str:
    if "{" in url or "}" in url:
        return "template"
    return "local" if _is_local(urlsplit(url).hostname or "") else "probe"

def _getaddrinfo(host: str, timeout: float) -> bool:
    socket.getaddrinfo(host, None)
    return True

def _urlopen(url: str, timeout: float):
    return urlopen(Request(url, headers=_HDRS), timeout=timeout)

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

def probe(url, *, now=None, resolver=_getaddrinfo, opener=_urlopen,
          timeout=8.0, retries=1) -> dict:
    parts = urlsplit(url)
    host, https = parts.hostname or "", parts.scheme == "https"
    r = {"dns_ok": 0, "tcp_ok": 0, "tls_ok": (0 if https else None),
         "http_status": None, "latency_ms": None, "ok": 0, "err": None,
         "probed_at": now or _now()}
    try:
        if not resolver(host, timeout):
            r["err"] = "dns: no address"; return r
    except Exception as e:  # gaierror 等
        r["err"] = f"dns: {e}"; return r
    r["dns_ok"] = 1
    attempt = 0
    while True:
        t0 = time.monotonic()
        try:
            resp = opener(url, timeout)
            try:
                status = getattr(resp, "status", None) or resp.getcode()
            finally:
                getattr(resp, "close", lambda: None)()
            r["tcp_ok"] = 1
            if https: r["tls_ok"] = 1
            r["http_status"] = status
            r["latency_ms"] = int((time.monotonic() - t0) * 1000)
            r["ok"] = 1 if (status is not None and status < 400) else 0
            return r
        except HTTPError as e:  # 有响应即连通，状态码照记
            r["tcp_ok"] = 1
            if https: r["tls_ok"] = 1
            r["http_status"] = e.code
            r["latency_ms"] = int((time.monotonic() - t0) * 1000)
            r["ok"] = 0
            return r
        except ssl.SSLError as e:
            r["tls_ok"] = 0; r["err"] = f"tls: {e}"; return r
        except (URLError, socket.timeout, OSError) as e:
            reason = getattr(e, "reason", e)
            if isinstance(reason, socket.gaierror):
                r["dns_ok"] = 0; r["err"] = f"dns: {reason}"; return r
            if isinstance(reason, ssl.SSLError):
                r["tls_ok"] = 0; r["err"] = f"tls: {reason}"; return r
            r["err"] = f"tcp: {reason}"
            if attempt < retries:
                attempt += 1; time.sleep(0.2); continue
            return r

def fetch_text(url, *, opener=_urlopen, timeout=8.0, max_bytes=1_048_576) -> str:
    resp = opener(url, timeout)
    try:
        return resp.read(max_bytes).decode("utf-8", errors="replace")
    finally:
        getattr(resp, "close", lambda: None)()

def fetch_bytes(url, *, opener=_urlopen, timeout=8.0, max_bytes=8_388_608) -> bytes:
    resp = opener(url, timeout)
    try:
        return resp.read(max_bytes)
    finally:
        getattr(resp, "close", lambda: None)()
