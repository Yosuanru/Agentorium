"""人物关系图：把「人物关系.json」画成一张网。

数据从哪来：**拆书时一并产出**（`拆文库/{书名}/人物关系.json`），
或用同格式放在项目里（`{项目}/canon/relation.json`）。格式：

    {"nodes":[{"id":"a","name":"闻潮生","role":"主角"}],
     "edges":[{"from":"a","to":"b","relation":"并肩","from_chapter":"38","because":"交底"}]}

**上一版的两个毛病（作者截图指出来的）：**
1. 颜色写死成浅色那套——深色主题下黑字落黑底，名字全看不见。
   现在颜色从主题取，跟随深浅切换。
2. 节点铺得太满，边上的被裁掉、中间的重叠。
   现在按「同心圆 + 留边距」摆，标签宽度也算进去。

**只读**：关系要改，改 json，不在这里拖。
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (QComboBox, QGraphicsScene, QGraphicsView,
                               QHBoxLayout, QLabel, QVBoxLayout, QWidget)

from core.theme_tokens import DARK_COLORS, LIGHT_COLORS

from core.paths import workspace_root

WORKSPACE = workspace_root()
CORPUS = WORKSPACE / "拆文库"
PAD = 90.0          # 画布四周留白，别把标签贴在边上


class RelationPage(QWidget):
    # 一张图最多画多少个点。超了就按"关系密的先画"筛——
    # 几百个点画出来是一团线，还不如只画要紧的。
    MAX_NODES = 40

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("pageSurface")
        self._project = None
        self._dark = False

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 14, 18, 14)
        root.setSpacing(10)

        head = QHBoxLayout()
        title = QLabel("关系图")
        title.setObjectName("pageTitle")
        head.addWidget(title)
        head.addSpacing(12)
        head.addWidget(QLabel("来源："))
        self.src = QComboBox()
        self.src.setMinimumWidth(200)
        self.src.currentTextChanged.connect(lambda _: self.refresh(self._project))
        head.addWidget(self.src)
        head.addStretch(1)
        self.hint = QLabel("")
        self.hint.setObjectName("mutedLabel")
        head.addWidget(self.hint)
        root.addLayout(head)

        self.scene = QGraphicsScene(self)
        # QSS 里 `QTextBrowser#pageBrowser` 只匹配 QTextBrowser，QGraphicsView 搭不上，
        # 于是 viewport 是透明的——重画后超出场景矩形的区域没底色可擦，会留脏边。
        # 给它自己一块不透明背景。
        self._bg_brush = QColor(LIGHT_COLORS["field_color"])
        self.view = QGraphicsView(self.scene)
        self.view.setObjectName("pageBrowser")
        self.view.setBackgroundBrush(self._bg_brush)
        self.view.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self.view.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self.view, 1)

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        if not self.scene.sceneRect().isEmpty():
            self.view.fitInView(self.scene.sceneRect(),
                                Qt.AspectRatioMode.KeepAspectRatio)

    # ── 主题 ────────────────────────────────────────────────
    def set_theme(self, config=None) -> None:
        """画图用的颜色跟着主题走。

        上一版把墨黑和灰色写死，深色主题下等于在黑板写黑字。
        """
        cfg = config or {}
        self._dark = cfg.get("theme", "light") != "light"
        self._c = DARK_COLORS if self._dark else LIGHT_COLORS
        # 画布底色也跟着换，不然深色主题下留一块浅底
        self._bg_brush = QColor(self._c["field_color"])
        self.view.setBackgroundBrush(self._bg_brush)
        self.refresh(self._project)

    # ── 数据 ────────────────────────────────────────────────
    def _sources(self):
        out = []
        # ⚠️ **本项目放最前面**：打开自己带关系数据的书时，默认画的应该是自己的图。
        # 以前拆文库那本排在前面，于是进关系图先看到的是《天不应》的网，
        # 作者得手动切下拉——很容易被当成"我的数据没进来"。
        if self._project is not None:
            p = Path(self._project.root) / "canon" / "relation.json"
            if p.exists():
                out.append(("本项目 · " + self._project.name, p))
        if CORPUS.is_dir():
            for d in sorted(CORPUS.iterdir()):
                if (d / "人物关系.json").exists():
                    out.append(("拆文库 · " + d.name, d / "人物关系.json"))
        return out

    def refresh(self, project=None):
        # 换了项目就别再记着上次选的那本——不然打开自己的书，默认画的还是上一本的网。
        changed_project = project is not self._project
        self._project = project
        srcs = self._sources()
        want = "" if changed_project else self.src.currentText()
        self.src.blockSignals(True)
        self.src.clear()
        for label, p in srcs:
            self.src.addItem(label, str(p))
        if want:
            i = self.src.findText(want)
            if i >= 0:
                self.src.setCurrentIndex(i)
        self.src.blockSignals(False)

        self.scene.clear()
        if not srcs:
            self.hint.setText("还没有关系数据——拆一本书时会一并产出 人物关系.json")
            return
        path = Path(self.src.currentData())
        try:
            data = json.loads(path.read_text(encoding="utf-8") or "{}")
        except (OSError, ValueError) as exc:
            self.hint.setText("读不了：%s" % exc)
            return
        n, e = len(data.get("nodes", [])), len(data.get("edges", []))
        self.hint.setText("节点 %d · 关系 %d" % (n, e))
        self._draw(data)

    # ── 画 ─────────────────────────────────────────────────
    def _draw(self, data) -> None:
        nodes = data.get("nodes") or []
        edges = data.get("edges") or []
        if not nodes:
            return

        # 150 章 22 个点还看得清；600 章就是一团毛球。
        # 按「关系最密的先画」取前 N 个——重要的留下，边角人物先不入图。
        total_nodes = len(nodes)
        if total_nodes > self.MAX_NODES:
            degree: dict[str, int] = {}
            for edge in edges:
                for side in ("from", "to"):
                    key = str(edge.get(side) or "")
                    degree[key] = degree.get(key, 0) + 1
            nodes = sorted(
                nodes, key=lambda n: -degree.get(str(n.get("id") or ""), 0)
            )[: self.MAX_NODES]
            keep = {str(n.get("id") or "") for n in nodes}
            edges = [e for e in edges
                     if str(e.get("from") or "") in keep and str(e.get("to") or "") in keep]
            self.hint.setText(
                "人太多画不下，只画关系最密的 %d 个（一共 %d 个）"
                % (len(nodes), total_nodes))
        else:
            self.hint.setText("")
        c = getattr(self, "_c", LIGHT_COLORS)
        ink = QColor(c["text_color"])
        muted = QColor(c["muted_text_color"])
        zhu = QColor(c["accent_color"])
        line = QColor(c["border_color"])
        fill = QColor(c["panel_color"])

        # 圆心给主角；其余按同心圆铺开，环半径随人数长，保证不挤。
        mains = [n for n in nodes if str(n.get("role") or "").startswith("主角")]
        rest = [n for n in nodes if n not in mains]
        center = mains[0] if mains else nodes[0]
        others = ([n for n in mains[1:]] if mains else []) + \
                 [n for n in rest if n is not center]

        per_ring = 7
        rings = max(1, math.ceil(len(others) / per_ring))
        step = 152.0                                  # 每个节点的地盘
        outer = step * max(2.2, rings + 0.9)
        span = outer * 2 + PAD * 2

        pos = {center.get("id"): (span / 2, span / 2)}
        for i, n in enumerate(others):
            ring = i // per_ring + 1
            idx = i % per_ring
            in_ring = min(per_ring, len(others) - (ring - 1) * per_ring)
            r = (outer - PAD) * (ring / (rings + 0.7))
            a = 2 * math.pi * idx / max(1, in_ring) - math.pi / 2
            pos[n.get("id")] = (span / 2 + r * math.cos(a),
                                span / 2 + r * math.sin(a))

        by_id = {n.get("id"): n for n in nodes}

        for e in edges:
            a, b = pos.get(e.get("from")), pos.get(e.get("to"))
            if not a or not b:
                continue
            hostile = str(e.get("relation") or "") in ("仇", "敌对", "追查", "灭口名单")
            self.scene.addLine(a[0], a[1], b[0], b[1],
                               QPen(zhu if hostile else line, 1.6))
            mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
            lbl = self.scene.addText(str(e.get("relation") or ""))
            lbl.setDefaultTextColor(zhu if hostile else muted)
            lbl.setFont(QFont("Noto Sans SC", 8))
            lbl.setPos(mx - lbl.boundingRect().width() / 2, my - 8)

        for nid, (x, y) in pos.items():
            n = by_id.get(nid, {})
            is_main = nid == center.get("id")
            r = 30 if is_main else 23
            self.scene.addEllipse(x - r, y - r, r * 2, r * 2,
                                  QPen(zhu if is_main else muted, 1.8),
                                  QBrush(fill))
            t = self.scene.addText(str(n.get("name") or nid))
            t.setDefaultTextColor(ink)
            f = QFont("Noto Sans SC", 10 if is_main else 9)
            f.setBold(is_main)
            t.setFont(f)
            t.setPos(x - t.boundingRect().width() / 2, y + r + 3)

        # 场景矩形按**内容的实际边界**收，不要按布局算出来的那块大方框——
        # 否则 fitInView 会为了填满方框把图缩得很小、还偏在一边。
        bounds = self.scene.itemsBoundingRect().adjusted(-46, -30, 46, 30)
        self.scene.setSceneRect(bounds)
        self.view.fitInView(bounds, Qt.AspectRatioMode.KeepAspectRatio)
