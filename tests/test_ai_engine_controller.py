import unittest
from unittest.mock import patch

from PySide6.QtCore import QCoreApplication

from ui.ai_engine_controller import AIEngineController


class FakeClaudeClient:
    """替身：只实现控制器真正会调的两个方法。

    引擎已从 dsh 换成 claude（见 core/claude_client.py），
    原来这里是 use_isolated_workspace()，现在控制器改成把工作目录
    指到仓库根——所以替身也跟着换成 set_working_directory()。
    """

    created = []

    def __init__(self, **kwargs):
        self.options = kwargs
        self.cleaned = False
        self.working_directory = None
        self.created.append(self)

    def set_working_directory(self, directory):
        self.working_directory = directory

    def cleanup(self):
        self.cleaned = True


class AIEngineControllerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def setUp(self) -> None:
        FakeClaudeClient.created.clear()

    def test_running_task_defers_old_client_cleanup(self) -> None:
        running = [False]
        with patch("ui.ai_engine_controller.ClaudeClient", FakeClaudeClient):
            controller = AIEngineController({"ai_command": "claude"}, lambda: running[0])
            first = controller.client
            self.assertIsNotNone(first)
            self.assertIsNotNone(first.working_directory)

            running[0] = True
            second = controller.configure({"ai_command": "claude-new"})

            self.assertIsNot(first, second)
            self.assertFalse(first.cleaned)
            controller.cleanup_retired()
            self.assertTrue(first.cleaned)
            self.assertFalse(second.cleaned)

            controller.cleanup()
            self.assertTrue(second.cleaned)
            self.assertIsNone(controller.client)

    def test_idle_reconfiguration_cleans_old_client_immediately(self) -> None:
        with patch("ui.ai_engine_controller.ClaudeClient", FakeClaudeClient):
            controller = AIEngineController({"ai_command": "claude"}, lambda: False)
            first = controller.client
            controller.configure({"ai_command": "claude-new"})
            self.assertTrue(first.cleaned)
