"""常驻对话面板 —— 和 AI 边聊边改的那一栏。

和 Inspector 里另外三页不同：那三页是只读的展示，这一页是干活的地方。
只负责收发和显示，**不知道故事上下文怎么拼**——那是 MainWindow 的事，
这样以后换上下文策略不用动界面。
"""

from __future__ import annotations

import html
import re
import time

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QPlainTextEdit,
                               QPushButton, QTextBrowser, QVBoxLayout, QWidget)

from core import voice
from core.text_stats import body_char_count
from ui.ai_task_runner import DSHTask
from ui.theme import chat_css

# AI 要给"改后的正文"时，按约定装进 ```正文 … ``` 块。
# 不要用"出现任意代码块就当正文"——它回答问题也会用代码块，那会误伤。
_CANDIDATE_RE = re.compile(r"```+[ \t]*正文[ \t]*\n(.*?)\n?```+", re.S)


def split_candidate(text: str) -> tuple[str, str | None]:
    """把 AI 回复里的 ``正文`` 块抽出来。

    返回（显示给作者的文字，可应用的正文或 None）。
    正文动辄几千字，整段铺在窄栏的对话里没法看——换成一行提示，
    真正的正文留给「应用到正文」按钮。
    """
    match = _CANDIDATE_RE.search(text)
    if not match:
        return text, None
    body = match.group(1).strip()
    if not body:
        return text, None
    note = "\n（改后正文 %d 字，点下面的按钮写进正文）" % body_char_count(body)
    shown = (text[: match.start()] + note + text[match.end():]).strip()
    return shown, (body or None)


class ChatInput(QPlainTextEdit):
    """回车发送、Shift+回车换行。"""

    submitted = Signal()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802 (Qt 命名)
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                super().keyPressEvent(event)
            else:
                self.submitted.emit()
            return
        super().keyPressEvent(event)


def ask_in_panel(panel, title: str, body: str) -> bool:
    """在对话栏里出稿子、等作者点「确认写入 / 不要」，返回他点了哪个。

    用它替掉 QMessageBox：作者的原话是「点了之后再给我弹个 window 的提示，
    那样的话太丑了，不如直接在侧栏旁边生成一份文稿，然后我再点一下确认」。
    """
    from PySide6.QtCore import QEventLoop

    # ⚠️ 重入闸门：确认提示挂在那儿的时候（非模态），作者完全可以再点一次
    # 「接着写 / 更新记忆 / 检查设定」。两个 ask_in_panel 嵌套、两个回调同时挂在
    # confirm_clicked 上 —— 点一次确认会**把同一个付费任务跑两遍**。
    if getattr(panel, "_confirm_open", False):
        return False
    panel._confirm_open = True

    loop = QEventLoop()
    answer = {"ok": False}

    def _got(ok: bool) -> None:
        answer["ok"] = bool(ok)
        loop.quit()

    panel.confirm_clicked.connect(_got)
    # 保险丝：万一按钮没画出来（侧栏收起、或提示被清掉），
    # 无限等下去会把所有 AI 操作都卡死——超时就当"不要"。
    _timer = QTimer(panel)
    _timer.setSingleShot(True)
    _timer.setInterval(120_000)
    _timer.timeout.connect(loop.quit)
    _timer.start()
    panel.ask_confirm(title, body)
    try:
        loop.exec()
    finally:
        _timer.stop()
        _timer.deleteLater()
        # 无论正常点完、超时、还是中途抛异常，都要把闸门放开、把提示清掉——
        # 不清的话它会一直留在对话栏，而且再点也没反应（信号已经断了）。
        panel._confirm_open = False
        panel._pending_confirm = None
        panel._render()
        try:
            panel.confirm_clicked.disconnect(_got)
        except (RuntimeError, TypeError):
            pass
    return answer["ok"]


class ChatPanel(QWidget):
    """对话记录 + 输入框。只发信号，不自己调 AI。"""

    send_requested = Signal(str)
    apply_requested = Signal(str)      # AI 改好的正文，交给 MainWindow 写进编辑器
    confirm_clicked = Signal(bool)     # 对话栏里的「确认写入 / 不要」

    def __init__(self, parent=None):
        super().__init__(parent)
        self._messages: list[tuple[str, str]] = []   # 本次会话（前端显示）
        self._history: list[tuple[str, str]] = []    # 从文件读回的历史（只喂 AI，不上屏）
        self._busy = False
        self._listening = False

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        self.transcript = QTextBrowser()
        self.transcript.setObjectName("chatTranscript")
        self.transcript.setOpenExternalLinks(False)
        # 「应用到正文」是页内锚点，别让 QTextBrowser 自己去导航，交给我们处理。
        self.transcript.setOpenLinks(False)
        self.transcript.anchorClicked.connect(self._on_anchor)
        root.addWidget(self.transcript, 1)

        bar = QFrame()
        bar_layout = QHBoxLayout(bar)
        bar_layout.setContentsMargins(0, 0, 0, 0)
        bar_layout.setSpacing(6)
        self.status = QLabel("可以说话了")
        self.status.setObjectName("chatStatus")
        bar_layout.addWidget(self.status, 1)
        self.clear_btn = QPushButton("清空")
        self.clear_btn.setObjectName("chatClear")
        self.clear_btn.clicked.connect(self.clear)
        bar_layout.addWidget(self.clear_btn)
        root.addWidget(bar)

        self.editor = ChatInput()
        self.editor.setObjectName("chatInput")
        self.editor.setPlaceholderText("在这里打字…回车发送，Shift+回车换行")
        self.editor.setFixedHeight(84)
        self.editor.submitted.connect(self._submit)
        root.addWidget(self.editor)

        actions = QHBoxLayout()
        actions.setSpacing(6)
        self.mic_btn = QPushButton("说")
        self.mic_btn.setObjectName("chatMic")
        self.mic_btn.setFixedWidth(64)
        self.mic_btn.setToolTip("按一下开始听，说完自动停（Windows 自带识别，不用装东西）")
        self.mic_btn.clicked.connect(self._start_voice)
        actions.addWidget(self.mic_btn)
        actions.addStretch(1)
        self.send_btn = QPushButton("发送")
        self.send_btn.setObjectName("chatSend")
        self.send_btn.clicked.connect(self._submit)
        actions.addWidget(self.send_btn)
        root.addLayout(actions)

        self.set_theme({"theme": "light"})

    # ── 语音 ────────────────────────────────────────────────
    def _start_voice(self) -> None:
        if self._busy or self._listening:
            return
        self._listening = True
        self.mic_btn.setEnabled(False)
        self.mic_btn.setText("听…")
        self.status.setText("在听——说完停两秒")
        task = DSHTask(lambda cancel: voice.listen(10), parent=self)
        task.success.connect(self._voice_done)
        task.failed.connect(self._voice_failed)
        # 不接 finished 的话，每点一次「说」就在面板下挂一个走不掉的线程对象。
        task.finished.connect(task.deleteLater)
        self._voice_task = task
        task.start()

    def _voice_done(self, text: str) -> None:
        self._listening = False
        self.mic_btn.setEnabled(True)
        self.mic_btn.setText("说")
        if not text:
            self.status.setText("没听清，再说一次")
            return
        cur = self.editor.toPlainText().strip()
        self.editor.setPlainText((cur + " " + text).strip() if cur else text)
        self.editor.setFocus()
        self.status.setText("听到了，改完按回车")

    def _voice_failed(self, err: str) -> None:
        self._listening = False
        self.mic_btn.setEnabled(True)
        self.mic_btn.setText("说")
        self.status.setText(str(err)[:60])

    # ── 对外 ────────────────────────────────────────────────
    def append(self, who: str, text: str) -> None:
        self._messages.append((who, text))
        self._append_log(who, str(text))     # 顺手存进项目的对话记录
        self._render()

    def set_busy(self, busy: bool, note: str = "") -> None:
        self._busy = busy
        self.send_btn.setEnabled(not busy)
        self.editor.setReadOnly(busy)
        self.status.setText(note or ("它正在想…" if busy else "可以说话了"))

    def ask_confirm(self, title: str, body: str) -> None:
        """在对话栏里出一份稿子，让作者点「确认写入」或「不要」。

        替代以前那个 QMessageBox——作者原话：「点了之后再给我弹个 window 的提示，
        那样的话太丑了，不如直接在侧栏旁边生成一份文稿，然后我再点一下确认」。
        """
        self._pending_confirm = {"title": str(title), "body": str(body)}
        self._render()

    def _take_confirm(self) -> bool:
        pending = getattr(self, "_pending_confirm", None)
        self._pending_confirm = None
        self._render()
        return bool(pending)

    # ── 对话记录的持久化 ────────────────────────────────────
    # 作者的原话：「保持前面对话记录的内容……不然每次重新写章，它会割裂的吧？
    # 就像你一样有个长期固化的记忆。」
    # 所以对话**按项目存**，打开项目就接上，不是每次都从空白开始。
    def attach_project(self, project_root) -> None:
        """切到某个项目：把对话记录读到**后台**，前端保持干净。

        作者的原话：「每次打开的时候是清了才对，然后重新加载最近的 30 条对话记录，
        但是在后台，不在我的前端啊。」

        —— 前端（他眼睛看的这块）每次打开都是空的，只显示**这次**聊的；
        历史 30 条进 `_history`，由 `_build_chat_system` 喂给 AI。
        这样界面不背着几百条旧消息，AI 该知道的又一条不少。
        """
        from pathlib import Path
        self._log_path = Path(project_root) / "memory" / "对话记录.md" if project_root else None
        self._messages.clear()          # 前端：清空
        self._history.clear()           # 后台：重读
        if self._log_path is not None and self._log_path.exists():
            try:
                self._history.extend(
                    _parse_log(self._log_path.read_text(encoding="utf-8")))
            except (OSError, UnicodeError):
                pass
        self._render()

    def history_digest(self, limit: int | None = None) -> str:
        """把后台那 30 条压成一段给 AI 看的「上次聊到哪」。没有就返回空串。"""
        rows = self._history[-(limit or self.LOG_KEEP):]
        if not rows:
            return ""
        lines = []
        for who, text in rows:
            body = " ".join(str(text).split())
            lines.append("- %s：%s" % ("作者" if who == "你" else "你", body[:150]))
        return "\n".join(lines)

    def _append_log(self, who: str, text: str) -> None:
        """每说一句就追加一行进项目里的对话记录。失败不该惊动人。"""
        path = getattr(self, "_log_path", None)
        if path is None:
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            stamp = time.strftime("%Y-%m-%d %H:%M")
            with path.open("a", encoding="utf-8", newline="\n") as fh:
                fh.write("\n## %s · %s\n\n%s\n" % (who, stamp, text.strip()))
        except OSError:
            pass

    def clear(self) -> None:
        self._messages.clear()
        self._render()

    def set_theme(self, config: dict | None = None) -> None:
        # 对话用 chat_css（黑体），不用 document_css（宋体）——
        # 宋体是给正文长句读的，落在窄栏的对话里看着笨重。
        self.transcript.document().setDefaultStyleSheet(chat_css(config))
        self._render()

    # ── 内部 ────────────────────────────────────────────────
    def _submit(self) -> None:
        if self._busy:
            return
        text = self.editor.toPlainText().strip()
        if not text:
            return
        self.editor.clear()
        self.send_requested.emit(text)

    def _render(self) -> None:
        pending = getattr(self, "_pending_confirm", None)
        if not self._messages and not pending:
            self.transcript.setHtml(
                "<div class='eyebrow'>对话</div>"
                "<p class='muted'>在这里跟它说话——改稿、问设定、让它接着写。"
                "它会带上当前章节的上下文。</p>"
            )
            return
        if pending:
            escaped = html.escape(pending["body"]).replace("\n", "<br>")
            parts = [
                "<div class='msg-ai'>"
                "<div class='who'>待你确认</div>"
                "<div class='body'><b>%s</b><br><br>%s</div>"
                "<div class='applyRow'>"
                "<a class='applyLink' href='confirm:yes'>✓ 确认写入</a>&nbsp;&nbsp;"
                "<a class='applyLink' href='confirm:no'>不要</a>"
                "</div></div>" % (html.escape(pending["title"]), escaped)
            ]
        else:
            parts = []
        for index, (who, text) in enumerate(self._messages):
            cls = "msg-user" if who == "你" else "msg-ai"
            shown, candidate = (text, None) if who == "你" else split_candidate(text)
            body = html.escape(shown).replace("\n", "<br>")
            apply_link = ""
            if candidate:
                apply_link = (
                    "<div class='applyRow'>"
                    "<a class='applyLink' href='apply:%d'>↳ 应用到正文</a></div>" % index
                )
            parts.append(
                f"<div class='{cls}'>"
                f"<div class='who'>{html.escape(who)}</div>"
                f"<div class='body'>{body}</div>{apply_link}</div>"
            )
        self.transcript.setHtml("".join(parts))
        self.transcript.verticalScrollBar().setValue(
            self.transcript.verticalScrollBar().maximum()
        )

    def _on_anchor(self, url) -> None:
        """对话栏里的锚点：应用到正文 / 确认写入。"""
        if url.scheme() == "confirm":
            self._pending_confirm = None
            self._render()
            self.confirm_clicked.emit(url.path() == "yes")
            return
        if url.scheme() != "apply":
            return
        try:
            index = int(url.path() or "-1")
        except ValueError:
            return
        if not 0 <= index < len(self._messages):
            return
        _, candidate = split_candidate(self._messages[index][1])
        if candidate:
            self.apply_requested.emit(candidate)


def _parse_log(raw: str) -> list[tuple[str, str]]:
    """把 `## 谁 · 时间` + 正文的 markdown 解析回 (谁, 内容) 列表。

    只取最近 `ChatPanel.LOG_KEEP` 条——记录是长期累积的，全读回来会把窄栏塞爆，
    也没人往上翻那么远。写文件那边不截断，只影响界面上显示多少。
    """
    out: list[tuple[str, str]] = []
    who: str | None = None
    body: list[str] = []
    for line in str(raw or "").splitlines():
        if line.startswith("## ") and " · " in line:
            if who is not None:
                text = "\n".join(body).strip()
                if text:
                    out.append((who, text))
            who = line[3:].split(" · ")[0].strip()
            body = []
        elif who is not None:
            body.append(line)
    if who is not None:
        text = "\n".join(body).strip()
        if text:
            out.append((who, text))
    return out[-ChatPanel.LOG_KEEP:]


# 界面上最多回溯多少条（文件里全都在）
ChatPanel.LOG_KEEP = 30
