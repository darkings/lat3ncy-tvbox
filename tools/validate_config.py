#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
validate_config.py —— TVBox 配置文件发布前校验
用法: python validate_config.py <config.json>
返回: 0=通过, 1=存在错误（阻断发布）
"""
import json
import sys
import io

# Windows 控制台默认 GBK，强制 UTF-8 输出避免中文乱码
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# site 必填字段：缺失任一项都会导致客户端解析异常
REQUIRED_SITE_FIELDS = ["key", "name", "type", "api"]

# type 合法取值：0=XML采集 1=JSON采集 3=爬虫(csp_*) 4=JSONP
VALID_TYPES = {0, 1, 3, 4}


def validate(path: str) -> int:
    """校验配置文件，返回错误数量。"""
    try:
        with open(path, encoding="utf-8") as f:
            cfg = json.load(f)
    except json.JSONDecodeError as e:
        print(f"[FATAL] JSON 语法错误: {e}")
        return 1
    except FileNotFoundError:
        print(f"[FATAL] 文件不存在: {path}")
        return 1

    errors = 0
    sites = cfg.get("sites", [])
    print(f"共 {len(sites)} 个源，开始校验...")

    seen_keys = set()  # 用于检测 key 重复
    for idx, site in enumerate(sites):
        site_id = f"sites[{idx}] (key={site.get('key', '?')})"

        # 检查必填字段
        for field in REQUIRED_SITE_FIELDS:
            if field not in site:
                print(f"[ERROR] {site_id} 缺少必填字段: {field}")
                errors += 1

        # 检查 key 重复
        key = site.get("key")
        if key:
            if key in seen_keys:
                print(f"[ERROR] {site_id} key 重复: {key}")
                errors += 1
            seen_keys.add(key)

        # 检查 type 合法性
        stype = site.get("type")
        if stype is not None and stype not in VALID_TYPES:
            print(f"[WARN] {site_id} type={stype} 非常见取值，请确认")

        # csp_ 开头的 api 必须是 type=3
        api = site.get("api", "")
        if api.startswith("csp_") and stype != 3:
            print(f"[ERROR] {site_id} api 为 {api}（csp_*）但 type={stype}，应为 3")
            errors += 1

    print(f"校验完成，共 {errors} 个错误")
    return errors


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python validate_config.py <config.json>")
        sys.exit(1)
    sys.exit(1 if validate(sys.argv[1]) > 0 else 0)

