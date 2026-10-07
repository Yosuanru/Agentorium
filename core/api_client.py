"""直连 API 的引擎适配层 —— **不装任何命令行工具，填个地址和 key 就能用**。

和 `claude_client.py` 是**同一套接口**（`generate` / `generate_json`），
所以上层（扩写 / 一致性检查 / 更新记忆 / 对话）一行都不用改，只是换了个后端。

**为什么能这么简单**：面板的 AI 任务**不需要工具调用**——它把当前章节、大纲、
角色卡、伏笔这些全部**内联进提示词**，模型只要回文本或 JSON 就行。
（唯一需要工具的是对话栏里"直接改文件"那条路；直连模式下它会退化成
"给你一段改稿，你点一下应用到正文"，功能不丢，只是少一只手。）

**只依赖标准库**（`urllib`）：不引第三方 HTTP 库，别人 clone 下来就能跑。
"""

from __future__ import annotations

import json
import threading
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .json_utils import JSONExtractionError, extract_json
from .task_controller import AITaskCancelled

# 一次请求最多要多少 token。整章正文 + 上下文都在提示词里，
# 输出也要一整章，所以给得比默认宽。
DEFAULT_MAX_TOKENS = 8192

# 网络层的兜底读法：分块读，好让"取消"能插进来。
_CHUNK = 8192


class ApiClient:
    """直接打 Anthropic 兼容的 `/v1/messages` 端点，取回纯文本。

    ⚠️ **它是 `ClaudeClient` 的替身，不是补充**：两个都实现同一套接口，
    由 `AIEngineController` 按设置里的「引擎」二选一。
    """

    def __init__(
        self,
        base_url: str = "",
        api_key: str = "",
        model: str = "",
        timeout: int = 600,
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ):
        self.base_url = (base_url or "").strip().rstrip("/")
        self.api_key = (api_key or "").strip()
        self.model = (model or "").strip()
        self.timeout = max(1, int(timeout))
        self.max_tokens = max(1, int(max_tokens))

    # ── 与 ClaudeClient 同名同义，方便互换 ──────────────────────
    def set_working_directory(self, directory=None) -> None:
        """直连模式不落盘、没有工作目录——接口留着，好让两者可互换。"""

    def use_isolated_workspace(self) -> None:
        """同上：直连模式没有"它去翻文件"这回事。"""

    def cleanup(self) -> None:
        """同上：没有临时目录要收。"""

    # ── 核心 ───────────────────────────────────────────────────
    def _endpoint(self) -> str:
        base = self.base_url
        if not base:
            raise RuntimeError(
                "还没填接口地址。打开「设置 → AI 引擎」，填上服务商的地址和密钥。"
            )
        # 用户可能填到 `/v1`，也可能只填域名——两种都认。
        if base.endswith("/v1/messages"):
            return base
        if base.endswith("/v1"):
            return base + "/messages"
        return base + "/v1/messages"

    def _headers(self) -> dict[str, str]:
        headers = {
            "content-type": "application/json",
            "anthropic-version": "2023-06-01",
            "accept": "application/json",
        }
        if self.api_key:
            # 两套都带：官方认 x-api-key，第三方兼容端点（DeepSeek 等）认 Bearer。
            headers["x-api-key"] = self.api_key
            headers["authorization"] = "Bearer " + self.api_key
        return headers

    def _payload(self, system_prompt: str, user_prompt: str) -> bytes:
        body: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": [{"role": "user", "content": str(user_prompt or "")}],
        }
        system = str(system_prompt or "").strip()
        if system:
            body["system"] = system
        return json.dumps(body, ensure_ascii=False).encode("utf-8")

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        session_id: str | None = None,
        *,
        timeout_override: int | None = None,
        cancel_event: threading.Event | None = None,
    ) -> str:
        """发一次请求，取回模型正文。

        `session_id` 在直连模式下没有意义（每次都是独立请求）——
        参数留着，是为了跟 `ClaudeClient` 可互换。
        """
        if not self.model:
            raise RuntimeError(
                "还没填模型名。打开「设置 → AI 引擎」，填上服务商给的模型名。"
            )
        if cancel_event is not None and cancel_event.is_set():
            raise AITaskCancelled()

        limit = max(1, int(timeout_override if timeout_override is not None else self.timeout))
        request = Request(
            self._endpoint(),
            data=self._payload(system_prompt, user_prompt),
            headers=self._headers(),
            method="POST",
        )
        try:
            with urlopen(request, timeout=limit) as response:  # noqa: S310 (地址由用户自己填)
                raw = self._read_cancellable(response, limit, cancel_event)
        except AITaskCancelled:
            raise
        except HTTPError as exc:
            raise RuntimeError(self._http_error_message(exc)) from None
        except URLError as exc:
            raise RuntimeError(f"连不上接口地址（{self.base_url}）：{exc.reason}") from None
        except TimeoutError:
            raise RuntimeError(f"接口调用超时（>{limit} 秒）。") from None
        return self._extract_text(raw)

    def generate_json(self, system_prompt, user_prompt, session_id=None, **kwargs) -> Any:
        text = self.generate(system_prompt, user_prompt, session_id, **kwargs)
        try:
            return extract_json(text)
        except JSONExtractionError as exc:
            raise RuntimeError(
                "接口返回的内容不是合法 JSON：\n%s" % str(text)[:500]) from exc

    # ── 内部 ───────────────────────────────────────────────────
    @staticmethod
    def _read_cancellable(response, limit: int, cancel_event) -> bytes:
        """分块读，好让"取消"能插进来——`urlopen` 本身没法中途打断。"""
        deadline = time.monotonic() + limit
        chunks: list[bytes] = []
        while True:
            if cancel_event is not None and cancel_event.is_set():
                raise AITaskCancelled()
            if time.monotonic() > deadline:
                raise TimeoutError
            chunk = response.read(_CHUNK)
            if not chunk:
                break
            chunks.append(chunk)
        return b"".join(chunks)

    @staticmethod
    def _extract_text(raw: bytes) -> str:
        try:
            data = json.loads((raw or b"").decode("utf-8", errors="replace"))
        except ValueError as exc:
            raise RuntimeError("接口返回的不是 JSON，拿不到正文。") from exc
        if not isinstance(data, dict):
            raise RuntimeError("接口返回的 JSON 结构不对，拿不到正文。")
        if data.get("type") == "error" or isinstance(data.get("error"), dict):
            detail = data.get("error") if isinstance(data.get("error"), dict) else data
            raise RuntimeError(
                "接口报错：%s" % str(detail.get("message") or detail)[:300])
        blocks = data.get("content")
        if isinstance(blocks, list):
            parts = [
                str(block.get("text") or "")
                for block in blocks
                if isinstance(block, dict) and block.get("type") == "text"
            ]
            text = "".join(parts).strip()
            if text:
                return text
        raise RuntimeError("接口返回里没有正文内容。")

    @staticmethod
    def _http_error_message(exc: HTTPError) -> str:
        """把 HTTP 错误翻成人能照着排查的一句。"""
        try:
            detail = exc.read().decode("utf-8", errors="replace")[:300]
        except Exception:  # noqa: BLE001 - 读不到就算了，别让报错再报错
            detail = ""
        hint = {
            401: "密钥不对，或者这个 key 没有权限。",
            403: "密钥没通过校验，或者没有额度。",
            404: "接口地址大概率写错了——很多服务商要求带 /anthropic 之类的后缀。",
            429: "被限流了，等一会儿再试。",
        }.get(exc.code, "")
        head = f"接口返回 HTTP {exc.code}。" + (hint or "")
        return head + (("\n" + detail) if detail else "")
