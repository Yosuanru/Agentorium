"""工作区根目录 —— **源码运行、打包、以及"面板单独放在一个仓库里"三种情况都要找得对。**

以前这里的写法是写死一个绝对路径，或者 `Path(__file__).resolve().parents[2]`：

    · 写死绝对路径 → 换台机器就废；
    · `parents[2]`  → 只有当面板装在 `<工作区>/panel/` 底下时才对，
                       别人把整个仓库拉下来单独跑，它指到上一层去了。

所以现在**不猜层级，去认地标**：往上走，找到同时有 `core/` 和 `ui/` 的那一层
（= 程序自己所在的根）；再看它外面那一层像不像"工作区"（有 `style/技法样本/`
或 `拆文库/`）——像就用外面那层，不像就用程序自己那层。

    <工作区>/panel/core/paths.py   → <工作区>      （面板装在 panel/ 子目录里）
    <仓库根>/core/paths.py         → <仓库根>      （面板就是仓库本身）

取不到就退回脚本所在目录——**宁可指错也不要抛异常**：面板至少得能开。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# 工作区里这两样，是判断"外面那一层是不是工作区"的地标。
_WORKSPACE_MARKERS = (("style", "技法样本"), ("拆文库",))


def _app_root() -> Path | None:
    """往上找，直到看见同时有 `core/` 和 `ui/` 的那一层——程序自己所在的根。"""
    for parent in Path(__file__).resolve().parents:
        if (parent / "core").is_dir() and (parent / "ui").is_dir():
            return parent
    return None


def _looks_like_workspace(path: Path) -> bool:
    return any(path.joinpath(*parts).is_dir() for parts in _WORKSPACE_MARKERS)


def app_home() -> Path:
    """**程序自己住的那个目录**——里面有 `core/` 和 `ui/` 的那一层。

    项目、备份、自动提交的暂存文件都挂在它下面。

    ⚠️ **不假设它叫 `panel/`。** 面板装在 `<工作区>/panel/` 底下时它是 `panel/`；
    别人把仓库单独拉下来跑时，它就是仓库根。以前这几处写死了
    `workspace_root() / "panel" / ...`，换个布局就全指到不存在的地方去。
    """
    return _app_root() or Path(__file__).resolve().parent.parent


def workspace_root() -> Path:
    override = os.environ.get("AGENTORIUM_WORKSPACE")
    if override:
        candidate = Path(override)
        if candidate.is_dir():
            return candidate

    if getattr(sys, "frozen", False):
        # 打包成 exe：就是 exe 旁边那个目录。
        return Path(sys.executable).resolve().parent

    app_root = _app_root()
    if app_root is None:
        return Path(__file__).resolve().parent.parent

    # 面板装在 `<工作区>/panel/` 里 → 工作区是外面那一层。
    outer = app_root.parent
    if outer != app_root and _looks_like_workspace(outer):
        return outer
    return app_root
