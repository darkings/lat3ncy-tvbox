#!/usr/bin/env python3
"""源码语法检查：对项目内所有标准 Python 文件做 AST 解析。

用途
----
在提交前快速发现语法错误，避免把坏文件推送到仓库。

排除规则
--------
以下路径不参与检查（它们不是标准 Python 源码）：

* ``.venv`` / ``__pycache__`` / ``.tmp`` / ``.staging``
  —— 虚拟环境与运行时缓存
* ``drpys/js``
  —— drpy/hipy 规则目录。其中的 ``.py`` 文件是 **hipy 框架规则**，
     使用 ``@header({...})`` 这类非标准装饰器语法，由 hipy 运行时
     预处理，标准 ``ast.parse`` 无法解析，属于预期行为。

退出码
------
0 = 全部通过；1 = 存在语法错误。
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

# 不参与检查的路径片段（相对 source-manager 根目录）
SKIP_PARTS = (
    ".venv",
    "__pycache__",
    ".tmp",
    ".staging",
    ".pytest_cache",
    "drpys/js",  # hipy 规则，非标准 Python
)


def iter_python_files(root: Path):
    """遍历 root 下所有应检查的 .py 文件。"""
    for path in root.rglob("*.py"):
        # 统一成 POSIX 风格，便于跨平台匹配
        rel = path.relative_to(root).as_posix()
        if any(part in rel for part in SKIP_PARTS):
            continue
        yield path, rel


def main() -> int:
    root = Path(__file__).resolve().parent.parent  # source-manager/
    checked = 0
    errors: list[tuple[str, str]] = []

    for path, rel in iter_python_files(root):
        checked += 1
        try:
            ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError as exc:
            errors.append((rel, f"line {exc.lineno}: {exc.msg}"))
        except UnicodeDecodeError as exc:
            errors.append((rel, f"编码错误: {exc}"))

    print(f"检查 {checked} 个 Python 文件")
    if errors:
        print(f"发现 {len(errors)} 个语法错误:")
        for rel, msg in errors:
            print(f"  {rel}")
            print(f"    {msg}")
        return 1

    print("全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
