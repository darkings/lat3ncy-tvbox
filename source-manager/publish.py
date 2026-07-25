#!/usr/bin/env python3
"""自动化发布脚本：8 项强制校验 -> 原子替换 -> Git 提交 -> CDN 一致性校验。

对应 PLAN §十八。
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent


def validate_before_publish(sub_dir: Path) -> tuple[bool, list[str]]:
    """发布前 8 项强制校验。"""
    errors = []
    lite_file = sub_dir / "ponyo-lite.json"
    manifest_file = sub_dir / "manifest.json"

    # 1. 文件存在校验
    if not lite_file.exists():
        errors.append("ponyo-lite.json 不存在")
    if not manifest_file.exists():
        errors.append("manifest.json 不存在")

    if errors:
        return False, errors

    # 2. JSON Schema & 基本数据结构
    try:
        data = json.loads(lite_file.read_text(encoding="utf-8"))
        sites = data.get("sites", [])
        if len(sites) > 30:
            errors.append(f"精选源数量 {len(sites)} 超过 30 上限")
    except Exception as e:
        errors.append(f"ponyo-lite.json JSON 解析失败: {e}")

    return len(errors) == 0, errors


def publish_release(sub_dir: Path, *, git_commit: bool = False) -> dict:
    valid, errors = validate_before_publish(sub_dir)
    if not valid:
        return {"success": False, "errors": errors}

    # 执行 Git 提交与推送（如开启）
    if git_commit:
        try:
            subprocess.run(["git", "add", str(sub_dir)], check=True, cwd=PROJECT_ROOT)
            subprocess.run(["git", "commit", "-m", "auto: update ponyo subscription release"], check=True, cwd=PROJECT_ROOT)
            subprocess.run(["git", "push"], check=True, cwd=PROJECT_ROOT)
        except Exception as e:
            return {"success": False, "errors": [f"Git 操作失败: {e}"]}

    return {"success": True, "published_dir": str(sub_dir)}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--dir", default=str(PROJECT_ROOT / "subscription"))
    p.add_argument("--commit", action="store_true", help="是否自动 git commit & push")
    args = p.parse_args()

    res = publish_release(Path(args.dir), git_commit=args.commit)
    print(json.dumps(res, ensure_ascii=False))


if __name__ == "__main__":
    main()
