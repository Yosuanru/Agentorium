"""框架图（泳道图）：**把整卷的线铺在同一条时间轴上**。

数据从 `outline/swimlanes.json` 来（见 `core/swimlanes.py`）。
跟「关系图」是一对：关系图画**人跟人的网**，这张图画**线跟时间的路**——
一条线什么时候起、什么时候暗下去、在哪一章又咬回来，一眼看得全。

**只读**：要改，改 json，不在这里拖。点块 → 跳到那一章的第一章。
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (QGraphicsRectItem, QGraphicsScene,
                               QGraphicsSimpleTextItem, QGraphicsView, QLabel,
                               QVBoxLayout, QWidget)

from core.swimlanes import load_swimlanes, swimlanes_path
from ui.theme import colors_for

PAD = 18.0            # 画布四周留白
NAME_W = 156.0        # 左边"线名"那一列的宽（要放得下最长的线名，见下面的缩字号）
NAME_GAP = 10.0       # 线名右端到刻度区起点之间的空
NAME_PT = 9.0         # 线名字号（放不下就往下缩，最矮 NAME_MIN_PT）
NAME_MIN_PT = 6.5
HEAD_H = 32.0         # 顶部"幕带"的高
LANE_H = 38.0         # 一条线占多高
BAR_H = 22.0          # 段块的高
ROW_GAP = 6.0
AXIS_H = 24.0         # 底部刻度那一条
PX_PER_CH = 9.0       # 一章多少像素


class _Block(QGraphicsRectItem):
    """能点的段块。点一下把「从哪一章开始看」交出去。"""

    def __init__(self, rect, on_click, chapter_id: str):
        super().__init__(rect)
        self._on_click = on_click
        self._chapter_id = chapter_id
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, event):  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._on_click(self._chapter_id)
            event.accept()
            return
        super().mousePressEvent(event)


class SwimlanePage(QWidget):
    """框架图页签。"""

    chapter_requested = Signal(str)      # "chapter_42"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("pageSurface")
        self._project = None
        self._colors = colors_for(None)
        self._scene = QGraphicsScene(self)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 14, 18, 14)
        root.setSpacing(10)

        self.title = QLabel("框架图")
        self.title.setObjectName("pageTitle")
        root.addWidget(self.title)

        self.hint = QLabel("")
        self.hint.setWordWrap(True)
        self.hint.setObjectName("pageHint")
        root.addWidget(self.hint)

        self.view = QGraphicsView(self._scene)
        self.view.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self.view.setFrameShape(QGraphicsView.Shape.NoFrame)
        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.view.setBackgroundBrush(QBrush(Qt.BrushStyle.NoBrush))
        root.addWidget(self.view, 1)

    # ---- 对外 --------------------------------------------------------------

    def set_theme(self, config: dict | None = None) -> None:
        self._colors = colors_for(config)
        self._draw()

    def refresh(self, project=None) -> None:
        self._project = project
        self._draw()

    # ---- 画 ----------------------------------------------------------------

    def _path(self) -> Path | None:
        if self._project is None:
            return None
        return swimlanes_path(self._project.outline_dir)

    def _draw(self) -> None:
        self._scene.clear()
        data = load_swimlanes(self._path()) if self._path() else load_swimlanes("")

        if not data.ok:
            self.title.setText("框架图")
            self.hint.setText(
                "还没有框架图。放一份 `outline/swimlanes.json`（整卷有几条线、"
                "每条线在哪几章亮着），这一页就画出来了。"
            )
            return

        self.title.setText(data.title or "框架图")
        self.hint.setText(
            "点一段就跳到那一章。实心＝这条线正亮着 · 描边＝在暗里走 · 虚线＝断着或只剩余温。"
        )

        accent = QColor(self._colors["accent_color"])
        muted = QColor(self._colors["muted_text_color"])
        text = QColor(self._colors["text_color"]) if "text_color" in self._colors else muted

        left = PAD + NAME_W
        right = PAD + NAME_W + (data.end - data.start + 1) * PX_PER_CH

        def x_of(chapter: int) -> float:
            return left + (chapter - data.start) * PX_PER_CH

        # 顶部：幕带
        for act in data.acts:
            x1, x2 = x_of(act.start), x_of(act.end + 1)
            band = QRectF(x1, PAD, max(x2 - x1, 2.0), HEAD_H)
            item = QGraphicsRectItem(band)
            fill = QColor(accent)
            fill.setAlpha(38)
            item.setBrush(QBrush(fill))
            item.setPen(QPen(Qt.PenStyle.NoPen))
            self._scene.addItem(item)
            label = QGraphicsSimpleTextItem(act.name, parent=item)
            font = QFont()
            font.setPointSizeF(max(7.5, min(9.5, (band.width()) / max(len(act.name), 1) * 1.5)))
            font.setBold(True)
            label.setFont(font)
            label.setBrush(QBrush(accent))
            label.setPos(x1 + 6, PAD + HEAD_H / 2 - label.boundingRect().height() / 2)

        top = PAD + HEAD_H + ROW_GAP
        for lane_index, lane in enumerate(data.lanes):
            y = top + lane_index * (LANE_H + ROW_GAP)
            is_main = lane.kind in ("main", "主线")

            # 线名（左边那一列）
            #
            # ⚠️ 这一列是**右对齐**的（名字贴着刻度区那头），位置＝列右边界 − 文字宽。
            # 原来的写法没给"文字比列还宽"留余地——名字一长，x 就成了负数，
            # 字直接顶到画布外头被切掉（实测「散人（姓程的 / 祁先生）」x = −44，
            # 「体系（贺沉 / 沈知微）」x = −32）。
            # 现在：够宽就照旧，不够先**缩字号**，缩到底还放不下才让左边界兜住。
            name = QGraphicsSimpleTextItem(lane.name)
            font = QFont()
            font.setPointSizeF(NAME_PT)
            font.setBold(is_main)
            name.setFont(font)
            avail = NAME_W - NAME_GAP - 4.0
            while (font.pointSizeF() > NAME_MIN_PT
                   and name.boundingRect().width() > avail):
                font.setPointSizeF(max(NAME_MIN_PT, font.pointSizeF() - 0.5))
                name.setFont(font)
            name.setBrush(QBrush(accent if is_main else muted))
            name.setPos(
                max(PAD, PAD + NAME_W - NAME_GAP - name.boundingRect().width()),
                y + BAR_H / 2 - name.boundingRect().height() / 2)
            self._scene.addItem(name)

            # 泳道底纹（一条浅线，让人看清"这一条线一直到这儿"）
            guide = QGraphicsRectItem(QRectF(left, y + BAR_H / 2 - 0.5,
                                             right - left, 1.0))
            guide.setPen(QPen(Qt.PenStyle.NoPen))
            faint = QColor(muted)
            faint.setAlpha(45)
            guide.setBrush(QBrush(faint))
            self._scene.addItem(guide)

            for seg in lane.segments:
                x1, x2 = x_of(seg.start), x_of(seg.end + 1)
                rect = QRectF(x1 + 1.5, y, max(x2 - x1 - 3.0, 6.0), BAR_H)
                block = _Block(rect, self._jump,
                               "chapter_%02d" % seg.start)
                pen = QPen(accent if is_main else muted)
                pen.setWidthF(1.6 if is_main else 1.1)
                brush = QBrush(Qt.BrushStyle.NoBrush)
                if seg.tone == "solid":
                    fill = QColor(accent if is_main else muted)
                    fill.setAlpha(70 if is_main else 55)
                    brush = QBrush(fill)
                elif seg.tone == "faint":
                    pen.setStyle(Qt.PenStyle.DashLine)
                block.setPen(pen)
                block.setBrush(brush)
                block.setToolTip("%s · 第 %d–%d 章" % (seg.label or lane.name,
                                                      seg.start, seg.end))
                self._scene.addItem(block)

                if seg.label:
                    # ⚠️ 原来这里把标签挂成段块的**子项**，位置写的是
                    # `rect.left() - block.rect().left() + 5`——而
                    # `block.rect().left()` 就是 `rect.left()`，两项一减恒等于 5；
                    # 更要命的是**子项的坐标原点跟的是父项的 `pos()`（这里是 0,0），
                    # 不是父项 rect 的左上角**。两下一凑，**每一条段块的说明文字
                    # 全叠在画布左上角那一个点上**（看着就是一小团挤在一起的字）。
                    # 改成：不挂父项，直接放进场景、用绝对坐标。
                    caption = QGraphicsSimpleTextItem(seg.label)
                    font = QFont()
                    font.setPointSizeF(8.0)
                    caption.setFont(font)
                    caption.setBrush(QBrush(text))
                    avail = rect.width() - 10
                    while (caption.boundingRect().width() > avail
                           and len(caption.text()) > 3):
                        caption.setText(caption.text()[:-2])
                    caption.setPos(
                        rect.left() + 5,
                        rect.top() + (BAR_H - caption.boundingRect().height()) / 2)
                    self._scene.addItem(caption)

        # 底部：章号刻度
        axis_y = top + len(data.lanes) * (LANE_H + ROW_GAP) + 2
        step = 10
        chapter = data.start - (data.start - 1) % step
        while chapter <= data.end:
            if chapter >= data.start:
                x = x_of(chapter)
                tick = QGraphicsRectItem(QRectF(x, axis_y, 1.0, 5.0))
                tick.setPen(QPen(Qt.PenStyle.NoPen))
                tick.setBrush(QBrush(muted))
                self._scene.addItem(tick)
                label = QGraphicsSimpleTextItem(str(chapter))
                font = QFont()
                font.setPointSizeF(7.5)
                label.setFont(font)
                label.setBrush(QBrush(muted))
                label.setPos(x - label.boundingRect().width() / 2, axis_y + 5)
                self._scene.addItem(label)
            chapter += step

        self._scene.setSceneRect(
            QRectF(0, 0, right + PAD, axis_y + AXIS_H)
        )

    def _jump(self, chapter_id: str) -> None:
        self.chapter_requested.emit(chapter_id)
