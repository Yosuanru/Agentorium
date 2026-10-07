"""会话结束（关机 / 注销）探测。

**为什么要有这个文件（2026-10-06 现场）**

Windows 关机时向每个顶层窗口发 WM_QUERYENDSESSION，Qt 把它变成 `closeEvent`——
面板因此在**会话正在拆除**的那一刻跑了退出钩子。钩子里的 `git` 子进程这时候连
DLL 都初始化不完，直接 0xc0000142；Windows 于是弹一个模态框：

    git.exe - Application Error: 应用程序无法正常启动(0xc0000142)

而模态框会**顶住注销**（系统日志：事件 26 弹框 + 事件 1073「关闭计算机失败」）。
那个框是加载器/CSRSS 弹的，Python 的 `try/except` 拦不到。

所以唯一有效的办法是：**关机时根本不启动 git**（见 `core/autocommit.py` 的待提交条子）。
本文件只负责回答一个问题——这次关闭是不是关机引起的。

非 Windows 平台恒为 False，装了也白装。
"""
from __future__ import annotations

import sys

WM_QUERYENDSESSION = 0x0011
WM_ENDSESSION = 0x0012

_ending = False

# 必须留一份引用：PySide6 不接管过滤器对象的所有权，装完就撒手的话
# Python 这边一回收，Qt 那边就再也叫不到它了——过滤器会**静默失效**（实测过）。
_filter = None


def session_ending() -> bool:
    """True = 本次关闭由系统关机/注销触发，不是用户点 X。"""
    return _ending


def _make_filter():
    """延迟构造过滤器：PySide6 / ctypes 出问题也不该影响模块被 import。"""
    import ctypes
    from ctypes import wintypes

    from PySide6.QtCore import QAbstractNativeEventFilter

    class _SessionEndFilter(QAbstractNativeEventFilter):
        def nativeEventFilter(self, eventType, message):
            global _ending
            try:
                # PySide6 给 QByteArray，别的绑定可能直接给 bytes。
                name = eventType.data() if hasattr(eventType, "data") else eventType
                if name == b"windows_generic_MSG":
                    msg = ctypes.cast(
                        int(message), ctypes.POINTER(wintypes.MSG)
                    ).contents
                    if msg.message == WM_QUERYENDSESSION:
                        _ending = True
                    elif msg.message == WM_ENDSESSION:
                        # wParam=0 表示这次关机被别的程序取消了，标记别留着，
                        # 否则之后正常点 X 关窗也会被误判成关机。
                        _ending = bool(msg.wParam)
            except Exception:  # noqa: BLE001 - 探测失灵绝不能拦住消息循环
                pass
            return False, 0

    return _SessionEndFilter()


def install(app) -> None:
    """把过滤器挂到 QApplication 上。挂不上就静默跳过，行为退化成改之前那样。"""
    global _filter
    if sys.platform != "win32" or _filter is not None:
        return
    try:
        _filter = _make_filter()
        app.installNativeEventFilter(_filter)
    except Exception:  # noqa: BLE001 - 探测失灵也不能影响启动
        _filter = None
