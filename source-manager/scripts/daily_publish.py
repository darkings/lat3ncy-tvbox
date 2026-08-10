#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""服务器每日订阅发布（云服务器 cron 运行，替代 Windows 定时任务）。

流程（全部在服务器完成）：
1. 查询生产库 allow+hard_pass 点播源数量
2. 数量 < 29：临时版（limit=95）；>= 29：正式版（limit=29）
3. 用生产环境生成订阅 -> 写入发布仓库 subscription/ponyo.json
4. git 提交并推送 GitHub（jsDelivr CDN 生效）
5. purge jsDelivr（避免 12h 缓存等待）
6. 追加日志

用法：
    python daily_publish.py [--push]
"""

import json
import sqlite3
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

SM_DIR = Path("/opt/ponyo-source-manager")
PUBLISH_REPO = Path("/opt/ponyo-publish")
TEMPLATE = SM_DIR / "ponyo-template.json"
GEN_SCRIPT = SM_DIR / "scripts" / "generate_temp_subscription.py"
DB = SM_DIR / "data" / "sources.db"
REMOTE_OUT = SM_DIR / "subscription" / "ponyo-temp.json"
# 对外服务文件（api.ponyo.fun/ponyo.json，children-api 挂载目录，发布即时生效）
SERVE_TARGET = SM_DIR / "subscription" / "ponyo.json"
# git 发布仓库文件（jsDelivr 备份地址）
GIT_TARGET = PUBLISH_REPO / "subscription" / "ponyo.json"
LOG = PUBLISH_REPO / "subscription" / "update-log.txt"

CDN_PURGE_URL = (
    "https://purge.jsdelivr.net/gh/darkings/lat3ncy-tvbox@main/subscription/ponyo.json"
)

# 点播源数量达到该值即切换正式版（工具源不计入；正式配额 29 点播）
TARGET_VOD = 29
# 临时版点播源上限（用户放宽到 95）
TEMP_LIMIT = 95


def sh(argv: list, timeout: int = 300) -> str:
    r = subprocess.run(
        argv,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    if r.returncode != 0:
        raise RuntimeError(f"命令失败: {argv}\n{r.stderr[-2000:]}")
    return r.stdout


def ensure_repo() -> None:
    """发布仓库不存在时自动重建（sparse + blob:none，避免 139MB 全量）。"""
    if (PUBLISH_REPO / ".git").exists():
        return
    sh(["rm", "-rf", str(PUBLISH_REPO)])
    sh(
        [
            "git",
            "clone",
            "--depth",
            "1",
            "--filter=blob:none",
            "--sparse",
            "git@github.com:darkings/lat3ncy-tvbox.git",
            str(PUBLISH_REPO),
        ]
    )
    sh(["git", "-C", str(PUBLISH_REPO), "sparse-checkout", "set", "subscription"])


def count_approved_vod() -> int:
    con = sqlite3.connect(DB)
    try:
        n = con.execute(
            "SELECT COUNT(*) FROM list_state WHERE state IN ('allow','hard_pass')"
        ).fetchone()[0]
    finally:
        con.close()
    return n


def validate(data: dict) -> str:
    sites = data.get("sites", [])
    if not sites:
        raise RuntimeError("订阅为空")
    for s in sites:
        jar = str(s.get("jar", "") or "")
        if "127.0.0.1" in jar or "localhost" in jar:
            raise RuntimeError(f"订阅含本机 jar: {s.get('name')}")
    tool = sum(1 for s in sites if s.get("key") in ("drpy_js_豆瓣", "配置中心", "本地"))
    vod = len(sites) - tool
    return f"总源 {len(sites)}（工具 {tool} + 点播 {vod}）"


def purge_cdn() -> int:
    """jsDelivr purge（GET 方式，CF+FY 双提供商刷新）。"""
    with urllib.request.urlopen(CDN_PURGE_URL, timeout=60) as r:
        return r.status


def log(limit: int, desc: str, pushed: bool, changed: bool) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    line = f"{ts} limit={limit} {desc} pushed={pushed} changed={changed}\n"
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line)


def main() -> None:
    do_push = "--push" in sys.argv
    t0 = time.time()
    ensure_repo()
    # 先同步远端（工作树干净时执行，避免后续 push 被拒）
    sh(["git", "-C", str(PUBLISH_REPO), "pull", "--ff-only", "origin", "main"])
    n = count_approved_vod()
    limit = TARGET_VOD if n >= TARGET_VOD else TEMP_LIMIT
    mode = "正式版" if limit == TARGET_VOD else "临时版"
    print(
        f"[{datetime.now().isoformat()}] 已通过验证点播源: {n} -> {mode} (limit={limit})"
    )

    sh(
        [
            str(SM_DIR / ".venv/bin/python"),
            str(GEN_SCRIPT),
            "--db",
            str(DB),
            "--template",
            str(TEMPLATE),
            "--output",
            str(REMOTE_OUT),
            "--limit",
            str(limit),
        ]
    )
    data = json.loads(REMOTE_OUT.read_text(encoding="utf-8"))
    desc = validate(data)
    # 同时写入对外服务文件（api.ponyo.fun 即时生效）与 git 仓库（jsDelivr 备份）
    SERVE_TARGET.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    GIT_TARGET.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    sh(["git", "-C", str(PUBLISH_REPO), "add", "subscription/ponyo.json"])
    changed = sh(
        ["git", "-C", str(PUBLISH_REPO), "diff", "--cached", "--name-only"]
    ).strip()
    if not changed:
        print("订阅内容无变化，跳过提交/推送")
        log(limit, desc, False, False)
        print(f"完成，耗时 {time.time() - t0:.1f}s")
        return

    msg = f"订阅日更：{desc}（limit={limit}）\n\n已通过源 {n}，采用{mode}（limit={limit}）"
    sh(["git", "-C", str(PUBLISH_REPO), "commit", "-m", msg])
    pushed = False
    if do_push:
        sh(["git", "-C", str(PUBLISH_REPO), "push", "origin", "main"])
        status = purge_cdn()
        print(f"CDN purge: {status}")
        pushed = True
    log(limit, desc, pushed, True)
    print(
        f"完成，耗时 {time.time() - t0:.1f}s；{'已推送+已刷新CDN' if pushed else '未推送'}"
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
