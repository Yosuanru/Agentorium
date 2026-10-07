import json
from threading import Event
from unittest import TestCase

from core.api_client import ApiClient
from core.task_controller import AITaskCancelled


class EndpointTests(TestCase):
    """接口地址怎么拼——**填法五花八门，两种都得认**。"""

    def test_plain_host_gets_the_full_path(self) -> None:
        client = ApiClient(base_url="https://api.deepseek.com/anthropic")
        self.assertEqual(
            client._endpoint(), "https://api.deepseek.com/anthropic/v1/messages")

    def test_trailing_slash_is_tolerated(self) -> None:
        client = ApiClient(base_url="https://api.anthropic.com/")
        self.assertEqual(client._endpoint(), "https://api.anthropic.com/v1/messages")

    def test_user_may_fill_up_to_v1(self) -> None:
        client = ApiClient(base_url="https://example.com/v1")
        self.assertEqual(client._endpoint(), "https://example.com/v1/messages")

    def test_full_endpoint_is_left_alone(self) -> None:
        url = "https://example.com/v1/messages"
        self.assertEqual(ApiClient(base_url=url)._endpoint(), url)


class ResponseParsingTests(TestCase):
    def test_normal_response_returns_the_text(self) -> None:
        raw = json.dumps({
            "content": [{"type": "text", "text": "他起的时候，天刚亮。"}],
        }).encode("utf-8")
        self.assertEqual(ApiClient._extract_text(raw), "他起的时候，天刚亮。")

    def test_multiple_text_blocks_are_joined(self) -> None:
        raw = json.dumps({
            "content": [
                {"type": "text", "text": "第一段。"},
                {"type": "thinking", "thinking": "（内心独白，不算正文）"},
                {"type": "text", "text": "第二段。"},
            ],
        }).encode("utf-8")
        self.assertEqual(ApiClient._extract_text(raw), "第一段。第二段。")

    def test_error_payload_raises_with_the_message(self) -> None:
        raw = json.dumps({
            "type": "error",
            "error": {"type": "authentication_error", "message": "invalid api key"},
        }).encode("utf-8")
        with self.assertRaises(RuntimeError) as caught:
            ApiClient._extract_text(raw)
        self.assertIn("invalid api key", str(caught.exception))

    def test_not_json_raises_a_clear_error(self) -> None:
        with self.assertRaises(RuntimeError):
            ApiClient._extract_text(b"<html>502 Bad Gateway</html>")

    def test_empty_content_raises(self) -> None:
        raw = json.dumps({"content": []}).encode("utf-8")
        with self.assertRaises(RuntimeError):
            ApiClient._extract_text(raw)


class GuardTests(TestCase):
    """缺东西的时候，报错要说人话——作者照着那句话就知道去填哪一格。"""

    def test_missing_base_url_says_where_to_fill_it(self) -> None:
        client = ApiClient(api_key="x", model="m")
        with self.assertRaises(RuntimeError) as caught:
            client.generate("s", "u")
        self.assertIn("接口地址", str(caught.exception))

    def test_missing_model_says_where_to_fill_it(self) -> None:
        client = ApiClient(base_url="https://x", api_key="k")
        with self.assertRaises(RuntimeError) as caught:
            client.generate("s", "u")
        self.assertIn("模型名", str(caught.exception))

    def test_already_cancelled_task_does_not_fire_a_request(self) -> None:
        event = Event()
        event.set()
        client = ApiClient(base_url="https://x", api_key="k", model="m")
        with self.assertRaises(AITaskCancelled):
            client.generate("s", "u", cancel_event=event)


class InterfaceParityTests(TestCase):
    """两个后端得**能互换**——上层是按同一套接口写的，少一个方法就炸。"""

    def test_api_client_implements_the_same_surface_as_the_cli_client(self) -> None:
        from core.claude_client import ClaudeClient

        for name in ("generate", "generate_json", "set_working_directory",
                     "use_isolated_workspace", "cleanup"):
            self.assertTrue(hasattr(ApiClient, name), "ApiClient 少了 " + name)
            self.assertTrue(hasattr(ClaudeClient, name), "ClaudeClient 少了 " + name)
