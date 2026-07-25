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
import sqlite3
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _run_drpy(rule_path: str, action: str, params: dict, *,
              runner_cmd="node", drpy_entry="drpy2/index.js",
              timeout=15) -> dict:
    """调用 drpy2 Node 进程，返回解析后的 JSON 结果。

    可通过替换此函数实现 mock 测试。
    """
    payload = json.dumps({
        "rule": rule_path,
        "action": action,
        "params": params,
    }, ensure_ascii=False)
    try:
        result = subprocess.run(
            [runner_cmd, drpy_entry],
            input=payload, capture_output=True, text=True,
            timeout=timeout,
        )
        if result.returncode != 0:
            return {"success": False, "error": result.stderr.strip()[:500]}
        return json.loads(result.stdout)
    except subprocess.TimeoutExpired:
        return {"success": False, "error": f"timeout after {timeout}s"}
    except (json.JSONDecodeError, Exception) as e:
        return {"success": False, "error": str(e)[:500]}


def run_drpy_search(rule_path: str, keyword: str, *,
                    runner=_run_drpy) -> dict:
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


def run_drpy_detail(rule_path: str, item_id: str, *,
                    runner=_run_drpy) -> dict:
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


def run_drpy_episode(rule_path: str, item_id: str, *,
                     runner=_run_drpy) -> dict:
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


def run_drpy_playurl(rule_path: str, episode_flag: str, *,
                     runner=_run_drpy) -> dict:
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
    }


def run_full_chain(rule_path: str, keyword: str, *,
                   runner=_run_drpy) -> list[dict]:
    """完整功能链测试：搜索 → 详情 → 选集 → 播放地址。
    任一环节失败即停止后续测试。
    """
    results = []

    # 1. 搜索
    search = run_drpy_search(rule_path, keyword, runner=runner)
    results.append(search)
    if not search["success"]:
        return results

    # 2. 详情（取第一个搜索结果）
    first_item = search["items"][0] if search["items"] else {}
    item_id = first_item.get("id", first_item.get("vod_id", ""))
    if not item_id:
        return results

    detail = run_drpy_detail(rule_path, item_id, runner=runner)
    results.append(detail)
    if not detail["success"]:
        return results

    # 3. 选集
    episode = run_drpy_episode(rule_path, item_id, runner=runner)
    results.append(episode)
    if not episode["success"]:
        return results

    # 4. 播放地址（取第一集）
    first_ep = episode["episodes"][0] if episode["episodes"] else {}
    ep_flag = first_ep.get("url", first_ep.get("flag", ""))
    if not ep_flag:
        return results

    playurl = run_drpy_playurl(rule_path, ep_flag, runner=runner)
    results.append(playurl)
    return results


def save_results(db_path: str, fingerprint: str, results: list[dict],
                 now: str | None = None) -> int:
    """将测试结果写入 drpy_test_result 表。"""
    now = now or _now()
    con = sqlite3.connect(str(db_path))
    count = 0
    for r in results:
        con.execute(
            "INSERT INTO drpy_test_result"
            "(fingerprint,test_type,keyword,success,result_count,latency_ms,error,tested_at)"
            " VALUES(?,?,?,?,?,?,?,?)",
            (fingerprint, r["test_type"], r.get("keyword"), r["success"],
             r.get("result_count"), r.get("latency_ms"), r.get("error"), now))
        count += 1
    con.commit()
    con.close()
    return count


def run_batch_test(db_path, keywords_path, *, runner=_run_drpy,
                   report_path=None, now=None) -> dict:
    """对数据库中所有活跃源执行批量功能链测试。"""
    now = now or _now()
    keywords = json.loads(Path(keywords_path).read_text(encoding="utf-8"))
    con = sqlite3.connect(str(db_path))

    rows = con.execute("""
        SELECT DISTINCT n.fingerprint, r.api, r.ext, r.name
        FROM norm_source n
        JOIN raw_source r ON n.raw_id = r.id
        LEFT JOIN list_state ls ON n.fingerprint = ls.fingerprint
        WHERE COALESCE(ls.state, 'candidate') != 'deny'
    """).fetchall()
    con.close()

    summary = {"total_sources": len(rows), "tested": 0, "passed": 0, "failed": 0}
    all_results = []

    for fp, api, ext, name in rows:
        rule_path = api or ext or ""
        if not rule_path:
            continue
        # 使用第一个关键词进行测试
        kw = keywords[0] if keywords else "功夫熊猫"
        chain_results = run_full_chain(rule_path, kw, runner=runner)
        save_results(db_path, fp, chain_results, now=now)
        summary["tested"] += 1
        if chain_results and all(r["success"] for r in chain_results):
            summary["passed"] += 1
        else:
            summary["failed"] += 1
        all_results.append({
            "fingerprint": fp, "name": name,
            "results": [{k: v for k, v in r.items()
                        if k not in ("items", "detail", "episodes")}
                       for r in chain_results],
        })

    if report_path:
        report = {"summary": summary, "generated_at": now, "sources": all_results}
        Path(report_path).parent.mkdir(parents=True, exist_ok=True)
        Path(report_path).write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    return summary


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--db", default=str(HERE / "data" / "sources.db"))
    p.add_argument("--keywords", default=str(HERE / "config" / "test_keywords.json"))
    p.add_argument("--report", default=str(HERE / "reports" / "drpy-test-report.json"))
    args = p.parse_args()
    result = run_batch_test(args.db, args.keywords, report_path=args.report)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
