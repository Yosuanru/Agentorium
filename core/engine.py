"""按设置挑一个 AI 引擎客户端 —— **两个后端，一套接口**。

| 引擎 | 是什么 | 需要什么 |
|---|---|---|
| `cli`（默认） | 调本机的 `claude` 命令 | 装一次 Claude Code（`npm i -g @anthropic-ai/claude-code`） |
| `api` | 直接打 Anthropic 兼容的 HTTP 端点 | **只要有地址和 key**，什么都不用装 |

两个都实现 `generate` / `generate_json`，所以上层（扩写 / 检查 / 记忆 / 对话）
一行都不用改。

⚠️ 差别只有一个：**`cli` 那个是 agent**（能读写文件、能派子代理），
`api` 那个只会一问一答。面板里唯一用得上"读写文件"的是**对话栏**——
它会在直连模式下退化成"给你一段改稿，你点一下应用到正文"。
其余功能（扩写 / 一致性检查 / 更新记忆）**本来就把上下文内联在提示词里，不吃工具**，
所以直连模式全都能用。
"""

from __future__ import annotations

from .api_client import ApiClient
from .claude_client import ClaudeClient
from .config import normalize_config
from .paths import workspace_root

# 两个后端共用这个类型名：上层只认接口，不认具体是哪一个。
EngineClient = ClaudeClient | ApiClient

ENGINE_CLI = "cli"
ENGINE_API = "api"
VALID_ENGINES = (ENGINE_CLI, ENGINE_API)


def engine_kind(config: dict | None) -> str:
    """读出当前选的是哪个引擎；认不出来就退回 `cli`。"""
    normalized = normalize_config(config or {})
    kind = str(normalized.get("ai_engine") or ENGINE_CLI).strip().casefold()
    return kind if kind in VALID_ENGINES else ENGINE_CLI


def create_engine(config: dict | None, *, timeout: int | None = None):
    """建一个引擎客户端，并把工作目录也配好。

    `timeout` 用来把"测试连接"那一下压短（别让作者干等十分钟）。
    """
    normalized = normalize_config(config or {})
    limit = int(normalized["ai_timeout"] if timeout is None else timeout)

    if engine_kind(normalized) == ENGINE_API:
        return ApiClient(
            base_url=normalized["api_base_url"],
            api_key=normalized["api_key"],
            model=normalized["api_model"],
            timeout=limit,
        )

    client = ClaudeClient(
        command=normalized["ai_command"],
        launcher_args=normalized["ai_launcher_args"],
        timeout=limit,
        extra_args=normalized["ai_extra_args"],
        api_base_url=normalized["api_base_url"],
        api_key=normalized["api_key"],
        api_model=normalized["api_model"],
    )
    # 不给它空目录——空目录会让它去找文件而不是读内联上下文。
    # 指向工作区根，它才读得到素材库那些真东西。
    client.set_working_directory(workspace_root())
    return client
