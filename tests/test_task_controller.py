from threading import Event
import subprocess
from unittest import TestCase
from unittest.mock import patch

from core.claude_client import ClaudeClient
from core.task_controller import AITaskCancelled, AITaskController, AITaskState


class AITaskControllerTests(TestCase):
    def test_only_one_running_task_is_allowed_and_finished_task_can_be_replaced(self) -> None:
        controller = AITaskController()
        first = controller.start("expand", "chapter_01")
        self.assertIsNotNone(first)
        self.assertIsNone(controller.start("check", "chapter_01"))

        self.assertTrue(controller.request_cancel(first))
        self.assertEqual(first.state, AITaskState.CANCEL_REQUESTED)
        self.assertTrue(first.cancel_event.is_set())
        self.assertIsNone(controller.start("memory", "chapter_01"))

        self.assertTrue(controller.finish(first))
        second = controller.start("memory", "chapter_01")
        self.assertIsNotNone(second)
        self.assertFalse(controller.is_current(first))
        self.assertTrue(controller.is_current(second))

    def test_cancel_request_is_idempotently_rejected_after_finish(self) -> None:
        controller = AITaskController()
        token = controller.start("check", "chapter_01")
        self.assertTrue(controller.finish(token))
        self.assertFalse(controller.request_cancel(token))


class _FakeStdin:
    def write(self, _text):
        return len(_text)

    def close(self):
        pass


class CancellableClientTests(TestCase):
    """取消那条路：**已经取消的不许起进程；跑到一半取消的要把进程收掉。**"""

    def test_already_cancelled_task_does_not_start_a_process(self) -> None:
        event = Event()
        event.set()
        client = ClaudeClient("claude")
        with patch("core.claude_client.subprocess.Popen") as popen:
            with self.assertRaises(AITaskCancelled):
                client.generate("system", "user", cancel_event=event)
        popen.assert_not_called()

    def test_cancelled_process_is_killed_and_not_reported_as_failure(self) -> None:
        event = Event()

        class FakeProcess:
            def __init__(self) -> None:
                self.returncode = None
                self.killed = False
                self.stdin = _FakeStdin()
                self.communicate_calls = 0

            def poll(self):
                return self.returncode

            def communicate(self, timeout=None):
                self.communicate_calls += 1
                if not self.killed:
                    event.set()
                    raise subprocess.TimeoutExpired("claude", timeout)
                self.returncode = -9
                return "", ""

            def kill(self):
                self.killed = True

        process = FakeProcess()
        client = ClaudeClient("claude")
        with patch("core.claude_client.subprocess.Popen", return_value=process):
            with self.assertRaises(AITaskCancelled):
                client.generate("system", "user", cancel_event=event)
        self.assertTrue(process.killed)

    def test_kill_tree_is_safe_without_a_pid(self) -> None:
        """没有 pid（假进程、或拿不到 pid）时不能抛，得退回 proc.kill()。"""

        class NoPidProcess:
            pid = None

            def __init__(self) -> None:
                self.killed = False

            def kill(self):
                self.killed = True

        process = NoPidProcess()
        ClaudeClient._kill_tree(process)
        self.assertTrue(process.killed)
