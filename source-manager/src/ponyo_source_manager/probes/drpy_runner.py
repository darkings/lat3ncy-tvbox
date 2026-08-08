#!/usr/bin/env python3
"""drpy2 业务功能测试：通过 subprocess 调用 drpy2 执行搜索/详情/选集/播放解析。

设计决策：
- drpy2 通过 Node.js 子进程调用，接口为 JSON stdin/stdout
- 所有 I/O 可注入，便于 mock 测试
- 测试结果写入 drpy_test_result 表
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import subprocess
import time
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from ponyo_source_manager.core.common import (
    CONFIG_DIR,
    DATA_DIR,
    PONYO_HOME,
    REPORT_DIR,
)
from ponyo_source_manager.discovery.audit_types import audit_source
from ponyo_source_manager.discovery.path_resolver import resolve_source_assets


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


PLATFORM_PAGE_HOSTS = {
    "iqiyi.com",
    "www.iqiyi.com",
    "v.qq.com",
    "youku.com",
    "www.youku.com",
    "mgtv.com",
    "www.mgtv.com",
    "bilibili.com",
    "www.bilibili.com",
}

DRPY_EXECUTION_ROUTE = "drpy_vod"

DEFAULT_KEYWORD_PROFILES = {
    "general": ["庆余年", "长相思", "流浪地球"],
    "children": ["熊出没", "小猪佩奇", "汪汪队立大功"],
    "animation": ["名侦探柯南", "斗罗大陆", "海贼王"],
    # 实测短剧源对具体剧名几乎全空，通用题材词（逆袭/重生/闪婚）稳定有结果
    "short_drama": ["逆袭", "重生", "闪婚"],
    "books_audio": ["斗破苍穹", "凡人修仙传", "诡秘之主"],
    # 部分听书源对「周杰伦」常空，歌名词覆盖更稳
    "audio_music": ["海阔天空", "后来", "夜曲"],
    "documentary": ["蓝色星球", "航拍中国", "地球脉动"],
}


def classify_content_lane(source: dict, audited: dict | None = None) -> str:
    """Assign a search profile without changing source quota or pass gates."""
    audited = audited or audit_source(source)
    roles = set(audited.get("content_roles") or [])
    text = " ".join(str(source.get(key) or "") for key in ("name", "site_key")).lower()

    if "children" in roles:
        return "children"
    if any(marker in text for marker in ("短剧", "短視頻", "短视频", "微短")):
        return "short_drama"
    if any(
        marker in text
        for marker in ("小说", "聽書", "听书", "有声", "有聲", "[书]", "┃书")
    ):
        return "books_audio"
    if any(
        marker in text for marker in ("动漫", "動漫", "动画", "動畫", "番剧", "二次元")
    ):
        return "animation"
    if any(marker in text for marker in ("纪录", "紀錄", "documentary")):
        return "documentary"
    if any(
        marker in text for marker in ("[听]", "┃听", "音乐", "音樂", "ktv", "mv", "dj")
    ):
        return "audio_music"
    return "general"


def load_keyword_profiles(path: str | Path) -> dict[str, list[str]]:
    """Load three distinct mandatory keywords per content lane."""
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(document, list):
        configured = {"general": document}
    elif isinstance(document, dict) and isinstance(document.get("profiles"), dict):
        configured = document["profiles"]
    else:
        raise ValueError("test keyword config must be a list or contain profiles")

    profiles = {}
    for lane, defaults in DEFAULT_KEYWORD_PROFILES.items():
        values = configured.get(lane, defaults)
        if not isinstance(values, list):
            raise ValueError(f"keyword profile {lane} must be a list")
        keywords = [str(value).strip() for value in values if str(value).strip()]
        if len(keywords) < 3 or len(set(keywords[:3])) != 3:
            raise ValueError(f"keyword profile {lane} needs three distinct keywords")
        profiles[lane] = keywords[:3]
    return profiles


def classify_drpy_route(source: dict) -> dict:
    """Route one source to its owning probe without treating skips as passes."""
    audited = audit_source(source)
    tags = set(audited.get("runtime_tags") or [])
    roles = set(audited.get("content_roles") or [])

    if source.get("type") == 4 and "drpys" not in tags:
        route = "invalid_drpy_endpoint"
    elif "drpys" in tags:
        if roles & {"settings", "tool", "local"}:
            route = "excluded_tool"
        elif "live" in roles:
            route = "live_manager"
        elif "cloud_drive" in roles:
            route = "cloud_adapter"
        elif audited.get("testability") == "testable_now":
            route = DRPY_EXECUTION_ROUTE
        else:
            route = "invalid_drpy_endpoint"
    elif "drpy2" in tags:
        # The scheduler imports the trusted drpy-node config before this probe.
        # Raw engine+rule pairs are shadows; only their generated type-4 /api
        # endpoint is executable by the HTTP adapter.
        route = "drpy2_shadow_needs_endpoint"
    elif "maccms" in tags:
        route = "maccms_probe"
    elif tags & {"jar_csp", "xbpq", "python", "catvod"}:
        route = "unsupported_adapter"
    else:
        route = "unsupported_other"

    return {
        "route": route,
        "content_lane": classify_content_lane(source, audited),
        "runtime_type": audited.get("runtime_type"),
        "runtime_tags": sorted(tags),
        "content_roles": sorted(roles),
        "testability": audited.get("testability"),
    }


def _adapter_version() -> str:
    explicit = os.environ.get("DRPY2_ADAPTER_VERSION", "").strip()
    if explicit:
        return explicit[:120]
    adapter = os.environ.get("DRPY2_ADAPTER", "").strip()
    return Path(adapter).name[:120] if adapter else "drpy-runner-v2"


def _is_platform_page(url: str) -> bool:
    try:
        host = (urlsplit(url).hostname or "").lower()
    except ValueError:
        return False
    return host in PLATFORM_PAGE_HOSTS


def classify_failure_stage(result: dict, test_type: str | None = None) -> dict:
    """Attach one stable failure stage without weakening media acceptance."""
    stage_type = test_type or str(result.get("test_type", "unknown"))
    error = str(result.get("error") or "").lower()
    if stage_type == "playurl" and _is_platform_page(str(result.get("play_url") or "")):
        result["success"] = 0
        result["error"] = "platform webpage rejected"
        result["failure_stage"] = "platform_page"
        result["failure_signature"] = "platform_page"
        result["failure_disposition"] = "non_media_url"
        return result
    if result.get("success") in (1, True):
        result["failure_stage"] = None
        return result
    if "timeout" in error or "timed out" in error:
        stage = f"{stage_type}_timeout"
    elif "placeholder" in error:
        stage = "placeholder_response"
    elif stage_type == "search" and not result.get("result_count"):
        stage = "search_empty" if not error else "search_runtime_error"
    elif stage_type == "detail" and not result.get("result_count"):
        stage = "detail_empty" if not error else "detail_runtime_error"
    elif stage_type == "episode" and not result.get("result_count"):
        stage = "episode_empty" if not error else "episode_runtime_error"
    elif stage_type == "playurl" and not result.get("play_url"):
        stage = "playurl_empty" if not error else "playurl_runtime_error"
    elif stage_type == "playback":
        if "non-media payload" in error:
            stage = "non_media_payload"
        elif "m3u8" in error and ("fetch" in error or "invalid" in error):
            stage = "media_manifest_failed"
        elif "no segments" in error:
            stage = "media_no_segments"
        elif result.get("segments_checked") and not result.get("segments_ok"):
            stage = "media_segment_failed"
        else:
            stage = "media_playback_failed"
    elif stage_type == "ffprobe":
        stage = (
            "duration_gate_failed"
            if result.get("ffprobe_success") and not result.get("duration_pass")
            else "ffprobe_failed"
        )
    else:
        stage = f"{stage_type}_failed"
    result["failure_stage"] = stage
    signature, disposition = classify_failure_signature(result, stage_type)
    result["failure_signature"] = signature
    result["failure_disposition"] = disposition
    return result


def classify_failure_signature(
    result: dict, test_type: str | None = None
) -> tuple[str, str]:
    """Return a stable second-level reason without changing pass/fail gates.

    The signature is deliberately based on bounded error markers instead of the
    complete error text, so reports remain aggregatable and do not persist URLs,
    tokens, or other upstream response details.
    """
    stage_type = test_type or str(result.get("test_type", "unknown"))
    error = str(result.get("error") or "").lower()

    if "drpy-node /api/:module endpoint" in error:
        return "drpy_endpoint_required", "configuration"
    if "invalid url" in error:
        return "invalid_url", "configuration"
    if stage_type == "search" and "t4 search returned an empty list" in error:
        return "t4_search_empty", "upstream_empty"
    if "t4 http 500" in error:
        return "t4_http_500", "upstream_server"
    if "timeout" in error or "timed out" in error:
        return "timeout", "transient_network"
    if "placeholder" in error:
        return "placeholder_response", "configuration"
    if not error:
        return f"{stage_type}_empty", "empty_result"
    return f"{stage_type}_runtime_other", "unknown"


def _evidence_json(result: dict) -> str:
    allowed = (
        "m3u8_ok",
        "segments_total",
        "segments_checked",
        "segments_ok",
        "segment_error_types",
        "ffprobe_valid",
        "ffprobe_success",
        "duration_pass",
        "duration_s",
        "quality_tier",
        "content_type",
        "latency_ms",
        "result_count",
        "failure_signature",
        "failure_disposition",
    )
    evidence = {key: result.get(key) for key in allowed if key in result}
    if str(result.get("test_type") or "") == "playurl":
        from ponyo_source_manager.probes.playback_audit import sanitize_playurl_evidence

        evidence.update(sanitize_playurl_evidence(result))
    return json.dumps(evidence, ensure_ascii=False, sort_keys=True)


def _rule_string(value) -> str:
    if not isinstance(value, str):
        return ""
    text = value.strip()
    if not text:
        return ""
    try:
        decoded = json.loads(text)
    except (TypeError, ValueError):
        return text
    return decoded.strip() if isinstance(decoded, str) else text


def select_rule_path(api, ext, origin="") -> str:
    """Select the executable rule, resolving drpy2's engine/rule pair by origin."""
    resolved = resolve_source_assets(str(origin or ""), api, ext, None)
    effective_api = _rule_string(resolved.get("effective_api"))
    effective_ext = _rule_string(resolved.get("effective_ext"))
    api_lower = effective_api.lower().split("?", 1)[0]
    if effective_ext and re.search(r"(?:^|/)drpy2(?:\.min)?\.js$", api_lower):
        return effective_ext
    return effective_api or effective_ext


def _run_drpy(
    rule_path: str,
    action: str,
    params: dict,
    *,
    runner_cmd="node",
    drpy_entry=None,
    timeout=15,
) -> dict:
    """调用 drpy2 Node 进程，返回解析后的 JSON 结果。

    可通过替换此函数实现 mock 测试。
    """
    drpy_entry = drpy_entry or os.environ.get("DRPY2_ENTRY", "drpy2/index.js")
    payload = json.dumps(
        {
            "rule": rule_path,
            "action": action,
            "params": params,
        },
        ensure_ascii=False,
    )
    try:
        result = subprocess.run(
            [runner_cmd, drpy_entry],
            input=payload,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode != 0:
            return {"success": False, "error": result.stderr.strip()[:500]}
        response = json.loads(result.stdout)
        serialized = json.dumps(response, ensure_ascii=False).lower()
        if "example.com/mock.m3u8" in serialized:
            return {
                "success": False,
                "error": "placeholder drpy2 response rejected in production",
            }
        return response
    except subprocess.TimeoutExpired:
        return {"success": False, "error": f"timeout after {timeout}s"}
    except (json.JSONDecodeError, Exception) as e:
        return {"success": False, "error": str(e)[:500]}


def run_drpy_search(rule_path: str, keyword: str, *, runner=_run_drpy) -> dict:
    """搜索测试：返回结果数和延迟。"""
    t0 = time.monotonic()
    result = runner(rule_path, "search", {"keyword": keyword})
    latency = int((time.monotonic() - t0) * 1000)
    items = result.get("list", [])
    return {
        "test_type": "search",
        "keyword": keyword,
        "success": 1 if (isinstance(items, list) and len(items) > 0) else 0,
        "result_count": len(items) if isinstance(items, list) else 0,
        "latency_ms": latency,
        "error": result.get("error"),
        "items": items,  # 供后续 detail 测试使用
    }


def run_drpy_detail(rule_path: str, item_id: str, *, runner=_run_drpy) -> dict:
    """详情测试：获取内容详情页。"""
    t0 = time.monotonic()
    result = runner(rule_path, "detail", {"id": item_id})
    latency = int((time.monotonic() - t0) * 1000)
    has_detail = bool(result.get("title") or result.get("vod_name"))
    return {
        "test_type": "detail",
        "keyword": item_id,
        "success": 1 if has_detail else 0,
        "result_count": 1 if has_detail else 0,
        "latency_ms": latency,
        "error": result.get("error"),
        "detail": result,
    }


def run_drpy_episode(rule_path: str, item_id: str, *, runner=_run_drpy) -> dict:
    """选集测试：获取播放集数列表。"""
    t0 = time.monotonic()
    result = runner(rule_path, "episode", {"id": item_id})
    latency = int((time.monotonic() - t0) * 1000)
    episodes = result.get("list", result.get("episodes", []))
    return {
        "test_type": "episode",
        "keyword": item_id,
        "success": 1 if (isinstance(episodes, list) and len(episodes) > 0) else 0,
        "result_count": len(episodes) if isinstance(episodes, list) else 0,
        "latency_ms": latency,
        "error": result.get("error"),
        "episodes": episodes,
    }


def run_drpy_playurl(rule_path: str, episode_flag: str, *, runner=_run_drpy) -> dict:
    """播放地址解析测试。"""
    t0 = time.monotonic()
    result = runner(rule_path, "play", {"flag": episode_flag})
    latency = int((time.monotonic() - t0) * 1000)
    play_url = result.get("url", result.get("play_url", ""))
    return {
        "test_type": "playurl",
        "keyword": episode_flag,
        "success": 1 if play_url else 0,
        "result_count": 1 if play_url else 0,
        "latency_ms": latency,
        "error": result.get("error"),
        "play_url": play_url,
        "header": result.get("header", result.get("headers", {})),
    }


import random

from ponyo_source_manager.probes import media_quality, playback


def run_full_chain(
    rule_path: str, keyword: str, db_path: str = "", fp: str = "", *, runner=_run_drpy
) -> list[dict]:
    """完整功能链测试：搜索 → 详情 → 选集 → 播放地址 → HLS验证 → ffprobe。
    任一环节失败即停止后续测试。
    """
    results = []

    # 1. 搜索
    search = classify_failure_stage(run_drpy_search(rule_path, keyword, runner=runner))
    results.append(search)
    if not search["success"]:
        return results

    # 随机抽取1个内容
    items = search["items"]
    if not items:
        return results
    item = random.choice(items) if len(items) > 1 else items[0]
    item_id = item.get("id", item.get("vod_id", ""))
    if not item_id:
        return results

    # 2. 详情
    detail = classify_failure_stage(run_drpy_detail(rule_path, item_id, runner=runner))
    results.append(detail)
    if not detail["success"]:
        return results

    # 3. 选集
    episode = classify_failure_stage(
        run_drpy_episode(rule_path, item_id, runner=runner)
    )
    results.append(episode)
    if not episode["success"]:
        return results

    # 随机抽取1集，或者最新/旧集
    episodes_list = episode["episodes"]
    if not episodes_list:
        return results
    ep = random.choice(episodes_list)
    ep_flag = ep.get("url", ep.get("flag", ""))
    if not ep_flag:
        return results

    # 4. 播放地址
    playurl = classify_failure_stage(
        run_drpy_playurl(rule_path, ep_flag, runner=runner)
    )
    results.append(playurl)

    url = playurl.get("play_url", "")
    if not playurl["success"] or not url:
        return results

    # 5. 真实播放测试
    t0 = time.monotonic()
    ext_str = item.get("ext", "")
    if not isinstance(ext_str, str):
        ext_str = json.dumps(ext_str)
    play_headers = playurl.get("header", {})
    if isinstance(play_headers, dict) and play_headers:
        try:
            ext_data = json.loads(ext_str) if ext_str.startswith("{") else {}
        except json.JSONDecodeError:
            ext_data = {}
        ext_data["header"] = {**ext_data.get("header", {}), **play_headers}
        ext_str = json.dumps(ext_data, ensure_ascii=False)
    pb_res = playback.verify_playback(url, mode="deep", ext_str=ext_str)
    pb_res["test_type"] = "playback"
    pb_res["keyword"] = keyword
    classify_failure_stage(pb_res)
    results.append(pb_res)

    # 6. ffprobe 媒体质量测试
    if pb_res["success"] and db_path and fp:
        type_info = media_quality.infer_content_type(
            item.get("vod_name", item.get("name", keyword)),
            detail.get("detail", {}),
            episode_count=len(episodes_list),
            source_hint=rule_path,
        )
        mq = media_quality.probe_and_save(
            db_path,
            fp,
            url,
            keyword,
            request_headers=play_headers if isinstance(play_headers, dict) else None,
            content_type=type_info["content_type"],
        )
        mq["content_type_confidence"] = type_info["confidence"]
        mq["content_type_evidence"] = type_info["evidence"]
        mq["test_type"] = "ffprobe"
        mq["keyword"] = keyword
        classify_failure_stage(mq)
        results.append(mq)

    return results


def save_results(
    db_path: str,
    fingerprint: str,
    results: list[dict],
    now: str | None = None,
    *,
    run_id: str | None = None,
    adapter_version: str | None = None,
) -> int:
    """将测试结果写入 drpy_test_result 表。"""
    now = now or _now()
    con = sqlite3.connect(str(db_path))
    columns = {row[1] for row in con.execute("PRAGMA table_info(drpy_test_result)")}
    extended = {
        "failure_stage",
        "run_id",
        "adapter_version",
        "evidence_json",
    } <= columns
    count = 0
    for r in results:
        if extended:
            con.execute(
                "INSERT INTO drpy_test_result"
                "(fingerprint,test_type,keyword,success,result_count,latency_ms,error,tested_at,"
                "failure_stage,run_id,adapter_version,evidence_json)"
                " VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    fingerprint,
                    r["test_type"],
                    r.get("keyword"),
                    r["success"],
                    r.get("result_count"),
                    r.get("latency_ms"),
                    r.get("error"),
                    now,
                    r.get("failure_stage"),
                    run_id,
                    adapter_version,
                    _evidence_json(r),
                ),
            )
        else:
            con.execute(
                "INSERT INTO drpy_test_result"
                "(fingerprint,test_type,keyword,success,result_count,latency_ms,error,tested_at)"
                " VALUES(?,?,?,?,?,?,?,?)",
                (
                    fingerprint,
                    r["test_type"],
                    r.get("keyword"),
                    r["success"],
                    r.get("result_count"),
                    r.get("latency_ms"),
                    r.get("error"),
                    now,
                ),
            )
        count += 1
    con.commit()
    con.close()
    return count


def run_batch_test(
    db_path, keywords_path, *, runner=_run_drpy, report_path=None, now=None
) -> dict:
    """对数据库中所有活跃源执行批量功能链测试。"""
    now = now or _now()
    run_id = f"drpy-{uuid.uuid4().hex}"
    adapter_version = _adapter_version()
    keyword_profiles = load_keyword_profiles(keywords_path)
    con = sqlite3.connect(str(db_path))

    discovered_rows = con.execute("""
        SELECT DISTINCT n.fingerprint, r.api, r.ext, r.name, r.origin,
                        r.id, r.site_key, r.type, r.raw_json
        FROM norm_source n
        JOIN raw_source r ON n.raw_id = r.id
        LEFT JOIN list_state ls ON n.fingerprint = ls.fingerprint
        WHERE COALESCE(ls.state, 'candidate') != 'deny'
    """).fetchall()
    con.close()

    routing_counts: Counter[str] = Counter()
    keyword_profile_counts: Counter[str] = Counter()
    routing_samples: dict[str, list[str]] = {}
    rows = []
    for row in discovered_rows:
        fp, api, ext, name, origin, raw_id, site_key, source_type, raw_json = row
        routing = classify_drpy_route(
            {
                "id": raw_id,
                "origin": origin,
                "site_key": site_key,
                "name": name,
                "type": source_type,
                "api": api,
                "ext": ext,
                "raw_json": raw_json,
            }
        )
        route = routing["route"]
        routing_counts[route] += 1
        samples = routing_samples.setdefault(route, [])
        if len(samples) < 5:
            samples.append(str(name or site_key or fp[:12]))
        if route == DRPY_EXECUTION_ROUTE:
            content_lane = routing["content_lane"]
            keyword_profile_counts[content_lane] += 1
            rows.append((fp, api, ext, name, origin, content_lane))

    summary = {
        "run_id": run_id,
        "adapter_version": adapter_version,
        "discovered_sources": len(discovered_rows),
        "total_sources": len(rows),
        "tested": 0,
        "passed": 0,
        "failed": 0,
        "routed_out": len(discovered_rows) - len(rows),
        "routing_counts": dict(sorted(routing_counts.items())),
        "keyword_profile_counts": dict(sorted(keyword_profile_counts.items())),
        "failure_stages": {},
        "failure_signatures": {},
    }
    failure_counts: Counter[str] = Counter()
    failure_signature_counts: Counter[str] = Counter()
    with sqlite3.connect(str(db_path)) as run_con:
        has_run_table = run_con.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='drpy_run'"
        ).fetchone()
        if has_run_table:
            run_con.execute(
                "INSERT INTO drpy_run"
                "(run_id,adapter_version,started_at,total_sources,"
                "discovered_sources,routing_counts_json,"
                "keyword_profile_counts_json) VALUES(?,?,?,?,?,?,?)",
                (
                    run_id,
                    adapter_version,
                    now,
                    len(rows),
                    len(discovered_rows),
                    json.dumps(summary["routing_counts"], ensure_ascii=False),
                    json.dumps(summary["keyword_profile_counts"], ensure_ascii=False),
                ),
            )
    all_results = []

    for fp, api, ext, name, origin, content_lane in rows:
        rule_path = select_rule_path(api, ext, origin)
        if not rule_path:
            missing = classify_failure_stage(
                {
                    "test_type": "resolve",
                    "keyword": None,
                    "success": 0,
                    "result_count": 0,
                    "latency_ms": 0,
                    "error": "no executable rule path",
                }
            )
            save_results(
                db_path,
                fp,
                [missing],
                now=now,
                run_id=run_id,
                adapter_version=adapter_version,
            )
            failure_counts[missing["failure_stage"]] += 1
            failure_signature_counts[missing["failure_signature"]] += 1
            summary["tested"] += 1
            summary["failed"] += 1
            all_results.append(
                {
                    "fingerprint": fp,
                    "name": name,
                    "content_lane": content_lane,
                    "results": [missing],
                }
            )
            continue
        test_keywords = keyword_profiles.get(content_lane, keyword_profiles["general"])
        all_chain_results = []
        source_success = True

        for kw in test_keywords:
            chain_results = run_full_chain(rule_path, kw, db_path, fp, runner=runner)
            save_results(
                db_path,
                fp,
                chain_results,
                now=now,
                run_id=run_id,
                adapter_version=adapter_version,
            )
            all_chain_results.extend(chain_results)
            for chain_result in chain_results:
                if chain_result.get("success") not in (1, True):
                    failure_counts[
                        chain_result.get("failure_stage") or "unclassified"
                    ] += 1
                    failure_signature_counts[
                        chain_result.get("failure_signature") or "unclassified"
                    ] += 1
            if not chain_results or not all(r["success"] for r in chain_results):
                source_success = False

        summary["tested"] += 1
        if source_success:
            summary["passed"] += 1
        else:
            summary["failed"] += 1

        all_results.append(
            {
                "fingerprint": fp,
                "name": name,
                "content_lane": content_lane,
                "results": [
                    {
                        k: v
                        for k, v in r.items()
                        if k not in ("items", "detail", "episodes")
                    }
                    for r in all_chain_results
                ],
            }
        )

    summary["failure_stages"] = dict(sorted(failure_counts.items()))
    summary["failure_signatures"] = dict(sorted(failure_signature_counts.items()))
    finished_at = _now()
    with sqlite3.connect(str(db_path)) as run_con:
        has_run_table = run_con.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='drpy_run'"
        ).fetchone()
        if has_run_table:
            run_con.execute(
                "UPDATE drpy_run SET finished_at=?,tested_sources=?,passed_sources=?,"
                "failed_sources=?,failure_counts_json=? WHERE run_id=?",
                (
                    finished_at,
                    summary["tested"],
                    summary["passed"],
                    summary["failed"],
                    json.dumps(summary["failure_stages"], ensure_ascii=False),
                    run_id,
                ),
            )

    if report_path:
        report = {
            "summary": summary,
            "generated_at": now,
            "routing_samples": routing_samples,
            "sources": all_results,
        }
        Path(report_path).parent.mkdir(parents=True, exist_ok=True)
        Path(report_path).write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    return summary


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--db", default=str(DATA_DIR / "sources.db"))
    p.add_argument("--keywords", default=str(CONFIG_DIR / "test_keywords.json"))
    p.add_argument("--report", default=str(REPORT_DIR / "drpy-test-report.json"))
    args = p.parse_args()
    result = run_batch_test(args.db, args.keywords, report_path=args.report)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
