#!/usr/bin/env python3
"""Import the local drpy-node generated TVBox config through a narrow trust boundary."""
from __future__ import annotations

import argparse
import json
import os
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

from ponyo_source_manager.core.common import CONFIG_DIR, DATA_DIR
from ponyo_source_manager.discovery.discover_sources import DiscoveryEngine, _now

DEFAULT_CONFIG_URL = "http://127.0.0.1:5757/config/1?pwd=ponyo-local-drpy"


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("trusted drpy config redirects are forbidden")


def validate_config_url(url: str) -> str:
    parts = urlsplit(url)
    if (
        parts.scheme != "http"
        or parts.hostname not in {"127.0.0.1", "::1"}
        or parts.port != 5757
        or parts.path != "/config/1"
        or parts.query != "pwd=ponyo-local-drpy"
        or parts.username
        or parts.password
        or parts.fragment
    ):
        raise ValueError("DRPY2_CONFIG_URL must be exactly loopback:5757/config/1")
    return url


def fetch_trusted_config(url: str, *, timeout: float = 20.0, opener=None) -> str:
    validate_config_url(url)
    opener = opener or urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())
    request = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "ponyo-source-manager/1.0"})
    with opener.open(request, timeout=timeout) as response:
        body = response.read(4_194_305)
    if len(body) > 4_194_304:
        raise ValueError("drpy config exceeds 4 MiB")
    text = body.decode("utf-8")
    document = json.loads(text)
    if not isinstance(document, dict) or not isinstance(document.get("sites"), list):
        raise ValueError("drpy config must contain a sites array")
    sites = []
    for site in document["sites"]:
        if not isinstance(site, dict) or site.get("type") != 4:
            continue
        api = urlsplit(str(site.get("api", "")))
        if not (
            api.scheme == "http"
            and api.hostname in {"127.0.0.1", "::1"}
            and api.port == 5757
            and api.path.startswith("/api/")
            and api.query == "pwd=ponyo-local-drpy"
        ):
            continue
        sites.append(site)
    if not sites:
        raise ValueError("drpy config contains no trusted local T4 sites")
    sites.sort(key=lambda item: (str(item.get("key", "")), str(item.get("api", ""))))
    return json.dumps({"sites": sites}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def import_drpy_config(
    db_path: str,
    policy_path: str,
    *,
    url: str = DEFAULT_CONFIG_URL,
    fetch_fn=fetch_trusted_config,
    now: str | None = None,
) -> dict:
    validate_config_url(url)
    now = now or _now()
    engine = DiscoveryEngine(db_path, policy_path)
    batch_id = engine.start_batch("trusted_drpy_node", query=url)
    try:
        result = engine.process_url_source(
            url,
            "trusted_drpy_node",
            batch_id,
            source_type="trusted_local_config",
            fetch_fn=fetch_fn,
            now=now,
            trusted_local=True,
        )
        engine.finish_batch(batch_id, "success" if not result["errors"] else "failed", result["requested"], result["errors"])
    except Exception:
        engine.finish_batch(batch_id, "failed", 1, 1)
        raise
    return {"batch_id": batch_id, **result}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=str(DATA_DIR / "sources.db"))
    parser.add_argument("--policy", default=str(CONFIG_DIR / "policy.json"))
    parser.add_argument("--url", default=os.environ.get("DRPY2_CONFIG_URL", DEFAULT_CONFIG_URL))
    args = parser.parse_args()
    print(json.dumps(import_drpy_config(args.db, args.policy, url=args.url), ensure_ascii=False))


if __name__ == "__main__":
    main()
