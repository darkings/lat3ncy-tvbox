#!/usr/bin/env python3
"""自动化发布脚本：强制校验 -> 原子替换 -> (可选) Git 提交。"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

from ponyo_source_manager.core.common import PONYO_ROOT, classify


def _calc_sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


EXEMPT_KEYS = {
    "drpy_js_豆瓣",
    "配置中心",
    "本地",
    "Douban",
    "LocalPlay",
    "ConfigCenter",
    "AliDrive",
    "QuarkDrive",
}

# A10/A23: 29个普通源的分类配额（影视让出 1 名给听书短剧）
CATEGORY_QUOTA = {"影视": 20, "动漫": 4, "纪录": 2, "综艺": 2, "听书短剧": 1}
# A23: 禁止进入正式订阅的分类
FORBIDDEN_CATEGORIES = {"戏曲", "成人", "广场舞", "纯测试"}


def validate_before_publish(sub_dir: Path) -> tuple[bool, list[str]]:
    errors = []
    lite_file = sub_dir / "ponyo-lite.json"
    manifest_file = sub_dir / "manifest.json"

    # 1. 文件存在校验
    for fname in [
        "ponyo-lite.json",
        "ponyo-full.json",
        "ponyo-live.json",
        "ponyo-children.json",
        "manifest.json",
    ]:
        if not (sub_dir / fname).exists():
            errors.append(f"{fname} 不存在")

    if errors:
        return False, errors

    # 2. JSON Schema & 计数
    try:
        data_bytes = lite_file.read_bytes()
        data = json.loads(data_bytes.decode("utf-8"))
        sites = data.get("sites", [])
        lives = data.get("lives", [])

        children_sites = [s for s in sites if s.get("key") == "Ponyo_Children"]
        exempt_sites = [s for s in sites if s.get("key") in EXEMPT_KEYS]
        normal_sites = [
            s
            for s in sites
            if s.get("key") != "Ponyo_Children" and s.get("key") not in EXEMPT_KEYS
        ]

        if len(children_sites) != 1:
            errors.append(f"儿童聚合源数量 {len(children_sites)} 不等于 1")
        if len(normal_sites) != 29:
            errors.append(
                f"普通精选点播数量 {len(normal_sites)} 不等于 29 (必须严格等于29)"
            )
        if len(lives) != 1:
            errors.append(f"正式直播源数量 {len(lives)} 不等于 1")

        counted_vod_sources = len(normal_sites) + len(children_sites)
        if counted_vod_sources != 30:
            errors.append(
                f"计入指标的 VOD 源数量 {counted_vod_sources} 不等于 30 (必须严格等于30)"
            )

        keys = set()
        for s in sites:
            k = s.get("key", "")
            if k in keys:
                errors.append(f"存在重复站点 Key: {k}")
            keys.add(k)

        # A10/A23: 分类子配额校验 20/4/2/2/1
        if len(normal_sites) == 29:
            cat_counts = {"影视": 0, "动漫": 0, "纪录": 0, "综艺": 0, "听书短剧": 0}
            forbidden_found = []

            policy_path = (
                PONYO_ROOT / "src" / "ponyo_source_manager" / "config" / "policy.json"
            )
            policy = (
                json.loads(policy_path.read_text(encoding="utf-8"))
                if policy_path.exists()
                else {
                    "categories": {},
                    "category_order": [],
                    "default_category": "未分类",
                }
            )

            for s in normal_sites:
                name = s.get("name", "")
                cat = classify(name, policy)
                if cat in FORBIDDEN_CATEGORIES:
                    forbidden_found.append(f"{name}({cat})")
                elif cat in cat_counts:
                    cat_counts[cat] += 1
                else:
                    cat_counts["影视"] += 1  # 未分类默认归入影视

            for cat, expected in CATEGORY_QUOTA.items():
                actual = cat_counts.get(cat, 0)
                if actual != expected:
                    errors.append(f"A23: 分类配额 {cat} 实际={actual} 要求={expected}")

            if forbidden_found:
                errors.append(
                    f"A23: 禁止分类源进入正式订阅: {', '.join(forbidden_found)}"
                )

        # 3. Manifest 校验
        man_data = json.loads(manifest_file.read_text(encoding="utf-8"))
        for fname in [
            "ponyo-lite.json",
            "ponyo-full.json",
            "ponyo-live.json",
            "ponyo-children.json",
        ]:
            file_bytes = (sub_dir / fname).read_bytes()
            expected_hash = man_data.get("files", {}).get(fname, {}).get("sha256")
            actual_hash = _calc_sha256(file_bytes)
            if expected_hash and expected_hash != actual_hash:
                errors.append(
                    f"{fname} Hash 不匹配: expected {expected_hash}, got {actual_hash}"
                )

    except Exception as e:
        errors.append(f"文件解析或校验失败: {e}")

    return len(errors) == 0, errors


def publish_release(
    staging_dir: Path, publish_dir: Path, *, git_commit: bool = False
) -> dict:
    valid, errors = validate_before_publish(staging_dir)
    if not valid:
        print(f"Validation failed: {errors}")
        return {"success": False, "errors": errors}

    # A14: 原子替换 — 使用临时目录 + rename，中断时可回滚
    import os
    import tempfile

    publish_parent = publish_dir.parent
    publish_parent.mkdir(parents=True, exist_ok=True)
    backup_dir = None
    temp_dir = None

    try:
        # 1. 准备临时目录，写入所有文件
        temp_dir = Path(
            tempfile.mkdtemp(dir=str(publish_parent), prefix=".publish_tmp_")
        )
        publish_files = [
            "ponyo-lite.json",
            "ponyo-full.json",
            "ponyo-live.json",
            "ponyo-children.json",
            "manifest.json",
        ]
        for fname in publish_files:
            src = staging_dir / fname
            dst = temp_dir / fname
            if src.exists():
                shutil.copy2(src, dst)
            else:
                raise FileNotFoundError(f"staging 缺少文件: {fname}")

        # 2. 验证临时目录中的文件完整性
        for fname in publish_files:
            src_hash = _calc_sha256((staging_dir / fname).read_bytes())
            dst_hash = _calc_sha256((temp_dir / fname).read_bytes())
            if src_hash != dst_hash:
                raise RuntimeError(f"文件复制校验失败: {fname}")

        # 3. 备份旧的 publish_dir（如果存在）
        if publish_dir.exists():
            backup_dir = Path(
                tempfile.mkdtemp(dir=str(publish_parent), prefix=".publish_bak_")
            )
            for fname in publish_files:
                old_file = publish_dir / fname
                if old_file.exists():
                    shutil.copy2(old_file, backup_dir / fname)

        # 4. 原子替换：版本目录加 current 符号链接
        publish_dir.mkdir(parents=True, exist_ok=True)

        # 复制文件到版本专属的子目录中
        version_dir = publish_dir / staging_dir.name
        version_dir.mkdir(parents=True, exist_ok=True)
        for fname in publish_files:
            shutil.copy2(temp_dir / fname, version_dir / fname)

        # 原子切换 current 符号链接
        current_link = publish_dir / "current"
        tmp_link = publish_dir / f"current_tmp_{staging_dir.name}"

        # 创建临时符号链接指向真正的版本目录
        # 注意: 符号链接目标最好是相对路径，避免跨容器/主机路径问题
        os.symlink(staging_dir.name, str(tmp_link))

        # os.replace 可以原子地将一个符号链接覆盖到另一个符号链接上
        os.replace(str(tmp_link), str(current_link))

        # 清理过期的版本目录，只保留最近 7 个
        try:
            # 找到所有形如 20* 的版本目录
            version_dirs = sorted(
                [
                    d
                    for d in publish_dir.iterdir()
                    if d.is_dir() and d.name.startswith("20")
                ]
            )
            if len(version_dirs) > 7:
                for old_dir in version_dirs[:-7]:
                    shutil.rmtree(old_dir, ignore_errors=True)
        except Exception as e:
            print(f"[Warning] Failed to cleanup old versions: {e}")

    except Exception as e:
        return {"success": False, "errors": [f"发布失败: {e}"]}
    finally:
        # 清理临时目录和备份
        if temp_dir and temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)
        if backup_dir and backup_dir.exists():
            shutil.rmtree(backup_dir, ignore_errors=True)

    # A14: 原子 Git 提交
    if git_commit:
        try:
            subprocess.run(["git", "add", str(publish_dir)], check=True, cwd=PONYO_ROOT)
            r = subprocess.run(["git", "diff-index", "--quiet", "HEAD"], cwd=PONYO_ROOT)
            if r.returncode != 0:
                subprocess.run(
                    ["git", "commit", "-m", "auto: update ponyo subscription release"],
                    check=True,
                    cwd=PONYO_ROOT,
                )
                subprocess.run(["git", "push"], check=True, cwd=PONYO_ROOT)
        except Exception as e:
            return {"success": False, "errors": [f"Git 操作失败: {e}"]}

    return {"success": True, "published_dir": str(publish_dir)}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--staging", required=True)
    p.add_argument("--publish", default=str(PONYO_ROOT / "subscription"))
    p.add_argument("--commit", action="store_true", help="是否自动 git commit & push")
    args = p.parse_args()

    res = publish_release(
        Path(args.staging), Path(args.publish), git_commit=args.commit
    )
    print(json.dumps(res, ensure_ascii=False))
    if not res.get("success"):
        sys.exit(1)


if __name__ == "__main__":
    main()
