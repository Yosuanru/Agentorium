"""Claude Code 客户端适配层 —— 把 AI 引擎从 `dsh` 换成 `claude`。

与原 `DSHClient` 保持同一套接口，所以上层（expansion / consistency /
ai_workflow / AIEngineController）一行都不用改：

    generate(system_prompt, user_prompt, session_id=None, *, timeout_override=None, cancel_event=None)
    set_working_directory() / use_isolated_workspace() / cleanup()

**三处刻意的不同（不是照抄原实现）：**

1. **提示词走 stdin，不走命令行参数。**
   原实现把整段提示词拼成命令行的最后一个参数，因此不得不去解析 npm 的
   `.cmd` shim 来绕过 Windows 约 8000 字符的命令行上限，还写了 80 行兜底。
   `claude -p` 能从标准输入收提示词——长上下文（章节正文 + 设定 + 记忆）
   因此完全没有长度问题，那 80 行也就没必要存在。

2. **没有 `--profile`。** `dsh` 需要它选入口；`claude` 用 `-p` 直接进无头模式。

3. **系统提示词优先走 `--append-system-prompt`，太长才并进 stdin。**
   系统提示词通常很短（角色设定 + 输出约束），走真正的系统通道效果更好；
   但若它本身就很长（正文内联在系统侧时），就退回合并，避免命令行超限。
"""

from __future__ import annotations

import os
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

from .json_utils import JSONExtractionError, extract_json
from .task_controller import AITaskCancelled

# 命令行里放系统提示词的安全长度。超过就并进 stdin。
SYS_PROMPT_ARG_LIMIT = 4000


class ClaudeClient:
    """调用本机 `claude` CLI 的无头模式，取回纯文本。"""

    def __init__(
        self,
        command: str = "claude",
        launcher_args: list[str] | None = None,
        timeout: int = 600,
        extra_args: list[str] | None = None,
        working_directory: str | Path | None = None,
        # 允许它写：作者要的「你写我也写、互相改」靠这个。
        # 只读模式会挡住「让它自己建项目 / 改稿」这类活。
        #
        # Task 也要给：拆书流程（style/技法样本/_拆书流程.md 第 3 步）要求
        # **一个专题一个代理、并行**，没有 Task 就只能自己串行读，那套流程走不起来。
        # 能派哪些代理由项目 .claude/agents/ 决定（story-architect、narrative-writer 等）。
        allowed_tools: str | None = "Read Glob Grep Write Edit Task",
        api_base_url: str = "",
        api_key: str = "",
        api_model: str = "",
    ):
        self.command = (command or "claude").strip()
        self.launcher_args = list(launcher_args or [])
        self.timeout = timeout
        self.extra_args = list(extra_args or [])
        self.working_directory = Path(working_directory) if working_directory else None
        self.allowed_tools = allowed_tools
        # 面板自己接的 API（留空 = 用本机 claude 那套自己的凭据）。见 `_child_env`。
        self.api_base_url = (api_base_url or "").strip()
        self.api_key = (api_key or "").strip()
        self.api_model = (api_model or "").strip()
        self._isolated_workspace: Path | None = None

    def _child_env(self) -> dict[str, str]:
        """起 claude 子进程时用的环境变量。

        **做法跟 CC Switch 一样**：`claude` 本身只是个客户端，"请求打到哪、
        用哪个模型、拿什么凭据"全看三个环境变量。面板里填了，就递给子进程。

        ⚠️ **三项都留空 → 一个都不覆盖**（照旧用本机 claude 自己的登录）。
        ⚠️ **必须从 `os.environ` 出发**——只覆盖这三项，别把 PATH 之类冲掉。
        ⚠️ **只覆盖面板自己起的子进程**，不动系统环境、不动用户的终端。
        """
        env = dict(os.environ)
        if self.api_base_url:
            env["ANTHROPIC_BASE_URL"] = self.api_base_url
        if self.api_key:
            # 两套都设：官方 API 认 x-api-key，第三方兼容端点（DeepSeek 等）认 Bearer。
            env["ANTHROPIC_API_KEY"] = self.api_key
            env["ANTHROPIC_AUTH_TOKEN"] = self.api_key
        if self.api_model:
            env["ANTHROPIC_MODEL"] = self.api_model
            # 四档一起指过去——claude 内部会按档位挑模型（子代理 / 轻任务）。
            # 只指主模型的话，第三方端点上那些档位名字是无效的。
            for _tier in ("OPUS", "SONNET", "HAIKU", "FABLE"):
                env["ANTHROPIC_DEFAULT_%s_MODEL" % _tier] = self.api_model
        return env

    # ── 与原实现同名同义，便于直接替换 ──────────────────────────
    def set_working_directory(self, directory: str | Path | None) -> None:
        self.working_directory = Path(directory) if directory else None

    def use_isolated_workspace(self) -> None:
        """在一个空的临时目录里跑，避免 agent 去翻小说文件。

        小说的上下文全部内联在提示词里，agent 不需要读到项目文件；
        给它一个空工作目录，它就没有别的东西可描述、只能老老实实做任务。
        """
        if self._isolated_workspace is None or not self._isolated_workspace.is_dir():
            import tempfile
            self._isolated_workspace = Path(tempfile.mkdtemp(prefix="agentorium-claude-"))
        self.working_directory = self._isolated_workspace

    def cleanup(self) -> None:
        workspace = self._isolated_workspace
        self._isolated_workspace = None
        if workspace is not None:
            if self.working_directory == workspace:
                self.working_directory = None
            shutil.rmtree(workspace, ignore_errors=True)

    # ── 核心 ───────────────────────────────────────────────────
    def _resolve_command(self) -> str:
        """Windows 上 claude 是 npm 的 .cmd shim，subprocess 直接调不到，包一层 cmd。"""
        found = shutil.which(self.command)
        if found:
            return found
        if os.name == "nt":
            for suffix in (".cmd", ".exe", ".bat"):
                found = shutil.which(self.command + suffix)
                if found:
                    return found
        return self.command

    def _build(self, system_prompt: str, user_prompt: str,
               session_id: str | None) -> tuple[list[str], str]:
        command = self._resolve_command()
        cmd: list[str] = [command, *self.launcher_args, "-p"]
        cmd += self.extra_args
        if session_id:
            cmd += ["--resume", session_id]
        if self.allowed_tools is not None:
            cmd += ["--allowedTools", self.allowed_tools]

        # 系统提示词一律并进 stdin，不用 --append-system-prompt。
        # 原因（实测踩到的）：Windows 上 claude 是 npm 的 .cmd shim，多行参数
        # 经 cmd.exe 传给 bat 时会被串位——模型收到的是被搅乱的文本，
        # 报出「MARKER 后面跟的是工具清单」，整段上下文等于没送到。
        stdin_text = user_prompt or ""
        system = (system_prompt or "").strip()
        if system:
            stdin_text = system + "\n\n---\n\n" + stdin_text
        return cmd, stdin_text

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        session_id: str | None = None,
        *,
        timeout_override: int | None = None,
        cancel_event: threading.Event | None = None,
    ) -> str:
        cmd, stdin_text = self._build(system_prompt, user_prompt, session_id)
        limit = max(1, int(timeout_override if timeout_override is not None else self.timeout))

        run_args: dict[str, Any] = {
            "text": True,
            "encoding": "utf-8",
            "input": stdin_text,                     # ★ 走 stdin，绕开命令行长度限制
            "capture_output": True,
            "cwd": str(self.working_directory) if self.working_directory else None,
            # 「面板自己接的 API」就是靠这几个环境变量递进去的（见 _child_env）。
            "env": self._child_env(),
        }
        if os.name == "nt":
            # 面板是 console=False 打的包。不设这个，Windows 会给**每一个** claude
            # 子进程单开一个控制台窗口——并发拆书时一次弹好几个黑窗，看着像出事。
            run_args["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)

        try:
            if cancel_event is None:
                proc = subprocess.run(cmd, timeout=limit, **run_args)
                stdout, stderr, code = proc.stdout, proc.stderr, proc.returncode
            else:
                stdout, stderr, code = self._run_cancellable(
                    cmd, run_args, limit, cancel_event, stdin_text
                )
        except FileNotFoundError:
            raise RuntimeError(
                "找不到 claude 命令。请确认 Claude Code 已安装，"
                "或在偏好设置里把命令改成完整路径。"
            ) from None
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"claude 调用超时（>{limit} 秒）。") from None

        if code != 0:
            detail = (stderr or "").strip() or (stdout or "").strip()
            raise RuntimeError("claude 调用失败。\n"
                               f"命令: {' '.join(cmd)}\n"
                               f"stderr: {detail}")
        return self._clean(stdout)

    def _run_cancellable(self, cmd, run_args, limit, cancel_event, stdin_text: str):
        # ⚠️ **先看一眼再起进程。** 任务已经取消的话，不该再去 spawn 一个 claude
        # ——白起一次、白烧一次调用。原来的实现是第一件事就 Popen，
        # 把"取消了的任务不启动"这条保证丢了。
        if cancel_event.is_set():
            raise AITaskCancelled()
        args = dict(run_args)
        # Popen 不认 run() 的这两个参数，必须摘掉再补上管道。
        args.pop("input", None)
        args.pop("capture_output", None)
        args["stdin"] = subprocess.PIPE          # 提示词仍走 stdin
        args["stdout"] = subprocess.PIPE
        args["stderr"] = subprocess.PIPE
        if os.name == "nt":
            args["creationflags"] = (
                getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                | getattr(subprocess, "CREATE_NO_WINDOW", 0))
        else:
            args["start_new_session"] = True

        proc = subprocess.Popen(cmd, **args)
        # 先把提示词喂进去再关掉 stdin，claude 才不会一直等输入。
        try:
            proc.stdin.write(stdin_text)
            proc.stdin.close()
        except (BrokenPipeError, OSError):
            pass

        deadline = time.monotonic() + limit
        try:
            while True:
                if cancel_event.is_set():
                    self._kill_tree(proc)
                    raise AITaskCancelled()
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    self._kill_tree(proc)
                    raise RuntimeError(f"claude 调用超时（>{limit} 秒）。")
                try:
                    out, err = proc.communicate(timeout=min(0.2, remaining))
                    return out, err, proc.returncode
                except subprocess.TimeoutExpired:
                    continue
        finally:
            if proc.poll() is None and cancel_event.is_set():
                self._kill_tree(proc)

    @staticmethod
    def _kill_tree(proc) -> None:
        pid = getattr(proc, "pid", None)
        if pid and os.name == "nt":
            try:
                subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               timeout=5, check=False,
                               # 取消任务时也会闪这个黑窗——和 generate 那两处同一个坑，
                               # 漏了它等于「点了取消，界面又弹一个黑框」，看着像出事。
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            except (OSError, subprocess.TimeoutExpired):
                pass
        elif pid:
            try:
                import signal as _s
                os.killpg(os.getpgid(pid), _s.SIGKILL)
            except (OSError, ProcessLookupError):
                pass
        try:
            proc.kill()
        except (OSError, ProcessLookupError):
            pass

    def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        session_id: str | None = None,
        *,
        timeout_override: int | None = None,
        cancel_event: threading.Event | None = None,
    ) -> Any:
        """要一段 JSON 并解析出来。

        ⚠️ 这个方法在 dsh→claude 迁移时**漏掉了**，而「同步上下文/更新记忆」
        「AI 修复正文」「扩写后的伏笔复核」三条路都在调它
        （core/ai_workflow.py:81、core/consistency.py:39、core/expansion.py:129）。
        漏了 = 前两条必抛 AttributeError，第三条被 `except Exception` 静默吞掉，
        作者会以为"AI 判断过了"，其实根本没跑。
        项目测试没抓到，是因为测试用的是**自己实现了 generate_json 的假 client**。
        """
        text = self.generate(system_prompt, user_prompt, session_id,
                             timeout_override=timeout_override,
                             cancel_event=cancel_event)
        return self._extract_json(text)

    @staticmethod
    def _extract_json(text: str) -> Any:
        """从回复里抠出 JSON（容忍 ``` 围栏）。"""
        try:
            return extract_json(text)
        except JSONExtractionError as exc:
            raise RuntimeError(
                "claude 返回的内容不是合法 JSON：\n%s" % str(text)[:500]) from exc

    @staticmethod
    def _clean(stdout: str) -> str:
        """去掉 CLI 自己的提示行，只留模型正文。"""
        lines = (stdout or "").splitlines()
        kept = [ln for ln in lines if not ln.startswith("[claude-code:")]
        text = "\n".join(kept).strip()
        if not text:
            raise RuntimeError("claude 返回了空内容。")
        return text
