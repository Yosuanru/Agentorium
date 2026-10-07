import unittest
from unittest.mock import patch

from PySide6.QtCore import QCoreApplication

from core.api_client import ApiClient
from core.claude_client import ClaudeClient
from core.engine import create_engine, engine_kind
from ui.ai_engine_controller import AIEngineController


class FakeEngineClient:
    """替身：只实现控制器真正会调的方法（建、用、收）。"""

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


def _fake_factory(_config=None, **_kwargs):
    """假装是 `create_engine`：每调一次给一个新替身。"""
    client = FakeEngineClient()
    client.set_working_directory("<workspace>")
    return client


class AIEngineControllerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def setUp(self) -> None:
        FakeEngineClient.created.clear()

    def test_running_task_defers_old_client_cleanup(self) -> None:
        running = [False]
        with patch("ui.ai_engine_controller.create_engine", _fake_factory):
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
        with patch("ui.ai_engine_controller.create_engine", _fake_factory):
            controller = AIEngineController({"ai_command": "claude"}, lambda: False)
            first = controller.client
            controller.configure({"ai_command": "claude-new"})
            self.assertTrue(first.cleaned)


class EngineFactoryTests(unittest.TestCase):
    """`core/engine.py` 按设置挑后端——挑错了整块 AI 就用不了。"""

    def test_default_engine_is_the_command_line_one(self) -> None:
        client = create_engine({})
        self.assertIsInstance(client, ClaudeClient)
        # 命令行那个是 agent，要有个工作目录可读；直连那个没有这回事。
        self.assertIsNotNone(client.working_directory)

    def test_api_engine_is_selected_by_the_setting(self) -> None:
        client = create_engine({
            "ai_engine": "api",
            "api_base_url": "https://api.deepseek.com/anthropic",
            "api_key": "PLACEHOLDER",
            "api_model": "deepseek-v4-flash",
        })
        self.assertIsInstance(client, ApiClient)
        self.assertEqual(client.base_url, "https://api.deepseek.com/anthropic")
        self.assertEqual(client.model, "deepseek-v4-flash")

    def test_unknown_engine_falls_back_to_the_command_line_one(self) -> None:
        self.assertEqual(engine_kind({"ai_engine": "什么鬼"}), "cli")
        self.assertEqual(engine_kind({}), "cli")
        self.assertEqual(engine_kind({"ai_engine": "API"}), "api")

    def test_timeout_override_is_honoured(self) -> None:
        client = create_engine({"ai_timeout": 900}, timeout=15)
        self.assertEqual(client.timeout, 15)
        self.assertEqual(create_engine({"ai_timeout": 900}).timeout, 900)
