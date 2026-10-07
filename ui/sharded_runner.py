"""分片并发 —— 把一件大活切成几片，几片同时跑。

面板原来一次只起一个 AI 任务（`AITaskRunner` 里就一个 `_thread`）。
拆书流程（`style/技法样本/_拆书流程.md` 第 3 步）写的是「一个专题一个代理、可以并行」，
单进程跑 363 章要跑到天荒地老。

**为什么不让原来的 runner 也并发**：写稿这类活必须串行——同一份稿不能两个进程同时改。
只有「天然可分割、各片写不同产物」的活才走这里（拆书、扫榜、批量摘要）。

⚠️ **写并发的红线：两片绝不能写同一个文件。**
   分片时要保证产物不重叠，否则就是几条进程抢一个文件——这台机器上反复出过的故障源。
   拆书的分法：每片只写自己的逐章摘要 + 自己的中间条目文件；
   把条目「并进 style/技法样本 那几册」是**最后单独一步**，不在分片里做。
"""
from __future__ import annotations

from threading import Event
from typing import Callable

from PySide6.QtCore import QObject, Signal

from ui.ai_task_runner import DSHTask


class ShardedTask(QObject):
    """几片同时跑；每片一个线程，各自调 worker(shard, cancel_event)。

    信号都在主线程收（Qt 跨线程信号自动排队），所以下面的计数器不用加锁。
    """

    progress = Signal(int, int, str)      # 已完成片数, 总片数, 说明
    succeeded = Signal(list, list)        # [结果...], [错误...]
    finished = Signal()

    def __init__(self, shards: list, worker: Callable, parent=None):
        super().__init__(parent)
        self._shards = list(shards)
        self._worker = worker
        self._cancel = Event()
        self._threads: list[DSHTask] = []
        self._results: list = []
        self._errors: list[str] = []
        self._done = 0

    def start(self) -> None:
        if not self._shards:
            self.succeeded.emit([], [])
            self.finished.emit()
            return
        for shard in self._shards:
            thread = DSHTask(
                lambda cancel, s=shard: self._worker(s, cancel), self._cancel, self)
            thread.success.connect(lambda result: self._one(result, None))
            thread.failed.connect(lambda message: self._one(None, message))
            thread.cancelled.connect(lambda: self._one(None, "已取消"))
            # 跑完就回收，不然每拆一次书都留着几段线程对象不放。
            thread.finished.connect(thread.deleteLater)
            self._threads.append(thread)
            thread.start()

    def cancel(self) -> None:
        self._cancel.set()

    def is_running(self) -> bool:
        return any(thread.isRunning() for thread in self._threads)

    def _one(self, result, error) -> None:
        if error:
            self._errors.append(str(error))
        else:
            self._results.append(result)
        self._done += 1
        self.progress.emit(self._done, len(self._shards), "")
        if self._done >= len(self._shards):
            self.succeeded.emit(self._results, self._errors)
            self.finished.emit()


def shard_ranges(start: int, end: int, size: int) -> list[tuple[int, int]]:
    """把 [start, end] 按 size 切段。最后一段不满也留着。"""
    start = max(1, int(start))
    end = max(start, int(end))
    size = max(1, int(size))
    out = []
    lo = start
    while lo <= end:
        hi = min(lo + size - 1, end)
        out.append((lo, hi))
        lo = hi + 1
    return out
