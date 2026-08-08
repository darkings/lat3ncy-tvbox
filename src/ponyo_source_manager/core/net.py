#!/usr/bin/env python3
"""网络 I/O 唯一出口：URL 分类 + 分层探测 + 文本下载（可注入，便于 mock 测试）。"""

from __future__ import annotations

import gzip
import io
import ipaddress
import os
import socket
import ssl
import threading
import time
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from ponyo_source_manager.core.common import iri_to_uri

# 兜底：进程内所有裸 socket 操作（含连接建立）强制限时，
# 防止特定目标 IP 无响应时进程无限期挂起（曾观察到 SYN-SENT 卡 2h+）。
socket.setdefaulttimeout(15.0)

_USER_AGENT = "ponyo-source-manager/1.0"


class RateLimiter:
    """A24: per-connector rate limiting with 429 Retry-After."""

    def __init__(
        self,
        max_per_window: int = 60,
        window_seconds: float = 60.0,
        max_retries: int = 3,
    ):
        self._lock = threading.Lock()
        self._counts: dict[str, list[float]] = defaultdict(list)
        self.max_per_window = max_per_window
        self.window_seconds = window_seconds
        self.max_retries = max_retries

    def check(self, host: str) -> bool:
        now = time.monotonic()
        with self._lock:
            self._counts[host] = [
                t for t in self._counts[host] if now - t < self.window_seconds
            ]
            if len(self._counts[host]) >= self.max_per_window:
                return False
            self._counts[host].append(now)
            return True

    def handle_429(self, retry_after: str | None) -> float:
        try:
            wait = float(retry_after) if retry_after else 5.0
        except (ValueError, TypeError):
            wait = 5.0
        return min(wait, 60.0)


_default_limiter = RateLimiter()


def disable_proxies():
    for k in list(os.environ.keys()):
        if k.lower().endswith("_proxy"):
            del os.environ[k]


disable_proxies()


def _is_local(ip_str: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_str)
        return (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_unspecified
            or str(ip) == "169.254.169.254"
        )
    except ValueError:
        return False


def check_proxy_env():
    return True


def classify_url(url: str) -> str:
    url = iri_to_uri(url)
    if "{" in url or "}" in url:
        return "template"
    return (
        "local"
        if (urlsplit(url).hostname and urlsplit(url).hostname.lower() == "localhost")
        else "probe"
    )


def _getaddrinfo(host: str, timeout: float) -> bool:
    # SSRF protection: resolve host and check if it resolves to a local IP
    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
        for info in infos:
            ip = info[4][0]
            if _is_local(ip):
                raise ValueError(f"SSRF blocked: {host} resolves to {ip}")
        return True
    except (socket.gaierror, socket.timeout, OSError):
        # DNS 解析失败/超时均视为不可达，由调用方记录 err 继续，不中断整轮探测。
        return False


class SSRFRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        host = urlsplit(newurl).hostname
        if host:
            _getaddrinfo(host, 10.0)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_ssrf_opener = build_opener(SSRFRedirectHandler())


def _opener_with_range(url: str, timeout: float):
    # Used for probe to save bandwidth
    host = urlsplit(url).hostname
    if host:
        _getaddrinfo(host, timeout)
    req = Request(url, headers={"Range": "bytes=0-0", "User-Agent": _USER_AGENT})
    return _ssrf_opener.open(req, timeout=timeout)


def _opener_full(url: str, timeout: float):
    # Standard GET
    host = urlsplit(url).hostname
    if host:
        _getaddrinfo(host, timeout)
    req = Request(url, headers={"User-Agent": _USER_AGENT, "Accept-Encoding": "gzip"})
    return _ssrf_opener.open(req, timeout=timeout)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def probe(
    url,
    *,
    now=None,
    resolver=_getaddrinfo,
    opener=_opener_with_range,
    timeout=8.0,
    retries=1,
) -> dict:
    url = iri_to_uri(url)
    parts = urlsplit(url)
    host, https = parts.hostname or "", parts.scheme == "https"
    r = {
        "dns_ok": 0,
        "tcp_ok": 0,
        "tls_ok": (0 if https else None),
        "http_status": None,
        "latency_ms": None,
        "ok": 0,
        "err": None,
        "probed_at": now or _now(),
    }
    try:
        if not resolver(host, timeout):
            r["err"] = "dns: no address"
            return r
    except Exception as e:
        r["err"] = f"dns: {e}"
        return r
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
            if https:
                r["tls_ok"] = 1
            r["http_status"] = status
            r["latency_ms"] = int((time.monotonic() - t0) * 1000)
            r["ok"] = 1 if (status is not None and status < 400) else 0
            return r
        except HTTPError as e:
            r["tcp_ok"] = 1
            if https:
                r["tls_ok"] = 1
            r["http_status"] = e.code
            r["latency_ms"] = int((time.monotonic() - t0) * 1000)
            r["ok"] = 0
            return r
        except ssl.SSLError as e:
            r["tls_ok"] = 0
            r["err"] = f"tls: {e}"
            return r
        except (URLError, socket.timeout, OSError) as e:
            reason = getattr(e, "reason", e)
            if isinstance(reason, socket.gaierror):
                r["dns_ok"] = 0
                r["err"] = f"dns: {reason}"
                return r
            if isinstance(reason, ssl.SSLError):
                r["tls_ok"] = 0
                r["err"] = f"tls: {reason}"
                return r
            r["err"] = f"tcp: {reason}"
            if attempt < retries:
                attempt += 1
                time.sleep(0.2)
                continue
            return r


def _read_and_decompress(resp, max_bytes: int) -> bytes:
    # resp.read(n) 底层只调一次 recv，大响应可能只返回一个网络分片，
    # 必须循环读取直到 EOF 或达到 max_bytes。
    chunks: list[bytes] = []
    remaining = max_bytes
    while remaining > 0:
        chunk = resp.read(min(65536, remaining))
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    data = b"".join(chunks)
    if resp.info().get("Content-Encoding") == "gzip":
        try:
            with gzip.GzipFile(fileobj=io.BytesIO(data)) as gz:
                return gz.read(max_bytes)
        except Exception:
            pass
    return data


def fetch_text(
    url,
    *,
    opener=_opener_full,
    timeout=8.0,
    max_bytes=1_048_576,
    limiter: RateLimiter | None = _default_limiter,
) -> str:
    url = iri_to_uri(url)
    host = urlsplit(url).hostname or ""
    retries = limiter.max_retries if limiter else 0
    for attempt in range(retries + 1):
        if limiter and not limiter.check(host):
            raise RuntimeError(f"A24: rate limit exceeded for {host}")
        try:
            resp = opener(url, timeout)
            try:
                data = _read_and_decompress(resp, max_bytes)
                return data.decode("utf-8", errors="replace")
            finally:
                getattr(resp, "close", lambda: None)()
        except HTTPError as e:
            if e.code == 429 and limiter and attempt < retries:
                wait = limiter.handle_429(e.headers.get("Retry-After"))
                time.sleep(wait)
                continue
            raise


def fetch_bytes(
    url,
    *,
    opener=_opener_full,
    timeout=8.0,
    max_bytes=8_388_608,
    limiter: RateLimiter | None = _default_limiter,
) -> bytes:
    url = iri_to_uri(url)
    host = urlsplit(url).hostname or ""
    retries = limiter.max_retries if limiter else 0
    for attempt in range(retries + 1):
        if limiter and not limiter.check(host):
            raise RuntimeError(f"A24: rate limit exceeded for {host}")
        try:
            resp = opener(url, timeout)
            try:
                return _read_and_decompress(resp, max_bytes)
            finally:
                getattr(resp, "close", lambda: None)()
        except HTTPError as e:
            if e.code == 429 and limiter and attempt < retries:
                wait = limiter.handle_429(e.headers.get("Retry-After"))
                time.sleep(wait)
                continue
            raise
