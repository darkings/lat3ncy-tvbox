# -*- coding: utf-8 -*-
"""每日订阅自动更新（本地定时任务，服务器生成 -> 拉回 -> 发布）。

流程：
1. 查询服务器最新库的 allow+hard_pass 点播源数量
2. 数量 < 29：临时版（limit=95，allow/hard_pass 全收 + 候选高分补足）
   数量 >= 29：正式版（limit=29，全部为通过验证的源）
3. 服务器生成订阅 -> scp 拉回 -> 结构校验
4. git 提交并推送到 GitHub（jsDelivr CDN 生效，地址不变）
5. 追加日志

用法：
    python subscription_daily_update.py [--push] [--no-push]
"""

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

SSH_HOST = "jie"
REMOTE_DIR = "/opt/ponyo-source-manager"
REMOTE_SCRIPT = "scripts/generate_temp_subscription.py"
REMOTE_OUT = "subscription/ponyo-temp.json"

REPO = Path(r"C:/Users/Jie/Projects/lat3ncy-tvbox")
LOCAL_SUB = REPO / "subscription"
LOCAL_OUT = LOCAL_SUB / "ponyo-temp.json"
TARGET = LOCAL_SUB / "ponyo.json"
LOG_FILE = LOCAL_SUB / "update-log.txt"

# 点播源数量达到该值即切换正式版（工具源不计入；正式配额 29 点播）
TARGET_VOD = 29
# 临时版点播源上限（用户放宽到 95）
TEMP_LIMIT = 95

COUNT_CODE = """import sqlite3
con = sqlite3.connect('data/sources.db')
n = con.execute(
    "SELECT COUNT(*) FROM list_state WHERE state IN ('allow','hard_pass')"
).fetchone()[0]
print(n)
"""


def sh(argv: list, timeout: int = 300) -> str:
    # Windows 下默认 GBK 解码会破坏 UTF-8 输出（如 git commit message）
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


def count_approved_vod() -> int:
    # 代码经 stdin 传入远端 python，避免 shell 引号嵌套
    r = subprocess.run(
        ["ssh", SSH_HOST, f"cd {REMOTE_DIR} && .venv/bin/python -"],
        input=COUNT_CODE.encode("utf-8"),
        capture_output=True,
        timeout=300,
    )
    if r.returncode != 0:
        raise RuntimeError(f"命令失败: ssh {SSH_HOST}\n{r.stderr[-2000:]}")
    return int(r.stdout.strip().splitlines()[-1])


def generate_remote(limit: int) -> None:
    sh(
        [
            "ssh",
            SSH_HOST,
            f"cd {REMOTE_DIR} && .venv/bin/python {REMOTE_SCRIPT} "
            f"--db data/sources.db --template ponyo-template.json "
            f"--output {REMOTE_OUT} --limit {limit}",
        ]
    )


def pull() -> None:
    sh(["scp", f"{SSH_HOST}:{REMOTE_DIR}/{REMOTE_OUT}", str(LOCAL_OUT)])


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


def publish(limit: int, summary: str, do_push: bool) -> None:
    data = json.loads(LOCAL_OUT.read_text(encoding="utf-8"))
    desc = validate(data)
    TARGET.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    sh(["git", "-C", str(REPO), "add", "subscription/ponyo.json"])
    changed = sh(["git", "-C", str(REPO), "diff", "--cached", "--name-only"]).strip()
    if not changed:
        # 内容与上次发布一致：幂等跳过，不产生空提交
        print("订阅内容无变化，跳过提交/推送")
        log(limit, desc, False, changed=False)
        return
    msg = f"订阅日更：{desc}（limit={limit}）\n\n{summary}"
    sh(["git", "-C", str(REPO), "commit", "-m", msg])
    if do_push:
        sh(["git", "-C", str(REPO), "push", "origin", "main"])
    log(limit, desc, do_push, changed=True)


def log(limit: int, desc: str, pushed: bool, changed: bool) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    line = f"{ts} limit={limit} {desc} pushed={pushed} changed={changed}\n"
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--push", action="store_true", help="生成后自动 git push")
    p.add_argument("--no-push", action="store_true")
    args = p.parse_args()
    do_push = args.push and not args.no_push

    t0 = time.time()
    n = count_approved_vod()
    limit = TARGET_VOD if n >= TARGET_VOD else TEMP_LIMIT
    mode = "正式版" if limit == TARGET_VOD else "临时版"
    print(
        f"[{datetime.now().isoformat()}] 已通过验证点播源: {n} -> {mode} (limit={limit})"
    )

    generate_remote(limit)
    pull()
    publish(limit, f"已通过源 {n}，采用{mode}（limit={limit}）", do_push)
    print(
        f"完成，耗时 {time.time() - t0:.1f}s；{'已推送' if do_push else '未推送（--push 可推送）'}"
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
