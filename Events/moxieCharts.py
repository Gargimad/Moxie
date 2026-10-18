"""
moxieCharts.py — Hand-painted chart widgets for Moxie dashboards.

All widgets are QWidget subclasses that draw themselves with QPainter.
No external dependencies. Colors follow the theme palette via
QPalette, so charts re-tint automatically when light / dark toggles.
"""
from PyQt6.QtCore import Qt, QRectF, QPointF
from PyQt6.QtGui import (
    QColor, QPainter, QPainterPath, QPen, QBrush, QLinearGradient,
    QFont, QPalette,
)
from PyQt6.QtWidgets import (
    QWidget, QFrame, QVBoxLayout, QHBoxLayout, QLabel,
)


# ── Palette helpers ───────────────────────────────────────────────────
def is_dark(widget):
    return widget.palette().color(
        QPalette.ColorRole.Window
    ).lightness() < 128


def moxie_colors(widget):
    """Brand chart colors for the current theme."""
    if is_dark(widget):
        return {
            "text": QColor("#EDE6F2"),
            "subtext": QColor("#9C8EA9"),
            "muted": QColor("#4A3A54"),
            "grid": QColor(179, 156, 219, 45),
            "brand": QColor("#B39CDB"),
            "accent": QColor("#7B8BE0"),
            "pos": QColor("#7B8BE0"),
            "neg": QColor("#E74C3C"),
            "series": [
                QColor("#B39CDB"), QColor("#7B8BE0"), QColor("#93A2F0"),
                QColor("#C9B4EC"), QColor("#9C8EA9"), QColor("#4A3A54"),
            ],
        }
    return {
        "text": QColor("#2D1A3E"),
        "subtext": QColor("#6B5B77"),
        "muted": QColor("#BFAFB3"),
        "grid": QColor(45, 26, 62, 25),
        "brand": QColor("#2D1A3E"),
        "accent": QColor("#3D4BA8"),
        "pos": QColor("#3D4BA8"),
        "neg": QColor("#C0392B"),
        "series": [
            QColor("#2D1A3E"), QColor("#3D4BA8"), QColor("#6B5B77"),
            QColor("#47305C"), QColor("#2F3B8A"), QColor("#BFAFB3"),
        ],
    }


# ── KPI tile ──────────────────────────────────────────────────────────
class KpiTile(QFrame):
    """Big number + caption + optional delta arrow."""

    def __init__(self, caption, value="-", delta=None, parent=None):
        super().__init__(parent)
        self.setObjectName("MoxieKpiTile")
        self.setMinimumHeight(110)
        v = QVBoxLayout(self)
        v.setContentsMargins(18, 14, 18, 14)
        v.setSpacing(4)

        top = QHBoxLayout()
        top.setSpacing(6)
        self.value_lbl = QLabel(str(value))
        self.value_lbl.setObjectName("MoxieKpiValue")
        top.addWidget(self.value_lbl)
        top.addStretch(1)
        self.delta_lbl = QLabel("")
        self.delta_lbl.setObjectName("MoxieKpiDelta")
        top.addWidget(self.delta_lbl)
        v.addLayout(top)

        self.caption_lbl = QLabel(caption)
        self.caption_lbl.setObjectName("MoxieKpiCaption")
        self.caption_lbl.setWordWrap(True)
        v.addWidget(self.caption_lbl)

        self.set_delta(delta)

    def set_value(self, value):
        self.value_lbl.setText(str(value))

    def set_delta(self, delta):
        if delta is None:
            self.delta_lbl.setText("")
            self.delta_lbl.setProperty("trend", "")
        else:
            arrow = "▲" if delta > 0 else ("▼" if delta < 0 else "—")
            sign = "+" if delta > 0 else ""
            self.delta_lbl.setText(f"{arrow} {sign}{delta}%")
            trend = "up" if delta > 0 else ("down" if delta < 0 else "flat")
            self.delta_lbl.setProperty("trend", trend)
        self.delta_lbl.style().unpolish(self.delta_lbl)
        self.delta_lbl.style().polish(self.delta_lbl)


# ── Horizontal bar chart ──────────────────────────────────────────────
class HBarChart(QWidget):
    """Horizontal bars: label on the left, value on the right."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.rows = []
        self._row_h = 34
        self.setMinimumHeight(120)

    def set_data(self, rows):
        self.rows = rows
        self.setMinimumHeight(max(120, len(rows) * self._row_h + 16))
        self.update()

    def paintEvent(self, event):
        if not self.rows:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        cols = moxie_colors(self)
        w = self.width()
        label_w = 150
        value_w = 56
        bar_w = max(20, w - label_w - value_w - 20)
        max_v = max((v for _, v in self.rows), default=1) or 1

        f = QFont(); f.setPointSize(9); p.setFont(f)
        y = 6
        for i, (label, value) in enumerate(self.rows):
            colour = cols["series"][i % len(cols["series"])]
            p.setPen(cols["text"])
            p.drawText(
                QRectF(0, y, label_w - 10, self._row_h - 6),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                str(label),
            )
            p.setBrush(cols["grid"]); p.setPen(Qt.PenStyle.NoPen)
            p.drawRect(label_w, y + 10, bar_w, self._row_h - 20)
            p.setBrush(colour)
            p.drawRect(label_w, y + 10,
                       int(bar_w * (value / max_v)), self._row_h - 20)
            p.setPen(cols["subtext"])
            p.drawText(
                QRectF(label_w + bar_w + 6, y, value_w, self._row_h - 6),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                f"{value:.1f}h",
            )
            y += self._row_h
        p.end()


# ── Vertical bar chart ────────────────────────────────────────────────
class VBarChart(QWidget):
    """Vertical bars, one per label. Good for totals over time."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.points = []
        self.setMinimumHeight(200)

    def set_data(self, points):
        self.points = points
        self.update()

    def paintEvent(self, event):
        if not self.points:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        cols = moxie_colors(self)
        w, h = self.width(), self.height()
        pad_l, pad_r, pad_t, pad_b = 40, 20, 20, 36
        plot = QRectF(pad_l, pad_t, w - pad_l - pad_r, h - pad_t - pad_b)

        p.setPen(QPen(cols["grid"], 1))
        for i in range(5):
            y = plot.top() + plot.height() * i / 4
            p.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))

        max_v = max((v for _, v in self.points), default=1) or 1
        max_v *= 1.15

        n = len(self.points)
        slot = plot.width() / n
        bar_w = slot * 0.5

        for i, (label, v) in enumerate(self.points):
            bh = plot.height() * (v / max_v)
            x = plot.left() + slot * i + (slot - bar_w) / 2
            y = plot.bottom() - bh
            colour = cols["series"][i % len(cols["series"])]
            p.setBrush(colour); p.setPen(Qt.PenStyle.NoPen)
            p.drawRect(QRectF(x, y, bar_w, bh))

        f = QFont(); f.setPointSize(8); p.setFont(f)
        p.setPen(cols["subtext"])
        for i, (label, _) in enumerate(self.points):
            x = plot.left() + slot * i
            p.drawText(
                QRectF(x, plot.bottom() + 6, slot, 20),
                Qt.AlignmentFlag.AlignCenter, str(label),
            )
        p.end()


# ── Smooth area chart ─────────────────────────────────────────────────
class AreaChart(QWidget):
    """Smooth line with gradient fill underneath."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.points = []
        self.setMinimumHeight(220)

    def set_data(self, points):
        self.points = points
        self.update()

    def paintEvent(self, event):
        if not self.points:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        cols = moxie_colors(self)
        w, h = self.width(), self.height()
        pad_l, pad_r, pad_t, pad_b = 40, 20, 20, 36
        plot = QRectF(pad_l, pad_t, w - pad_l - pad_r, h - pad_t - pad_b)

        p.setPen(QPen(cols["grid"], 1))
        for i in range(5):
            y = plot.top() + plot.height() * i / 4
            p.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))

        max_v = max((v for _, v in self.points), default=1) or 1
        max_v *= 1.15

        n = len(self.points)
        pts = []
        for i, (label, v) in enumerate(self.points):
            x = plot.left() + plot.width() * (i / max(1, n - 1))
            y = plot.bottom() - plot.height() * (v / max_v)
            pts.append(QPointF(x, y))

        path = QPainterPath()
        path.moveTo(pts[0])
        for i in range(1, n):
            prev, cur = pts[i - 1], pts[i]
            mx = (prev.x() + cur.x()) / 2
            path.cubicTo(QPointF(mx, prev.y()),
                         QPointF(mx, cur.y()), cur)

        fill = QPainterPath(path)
        fill.lineTo(plot.right(), plot.bottom())
        fill.lineTo(plot.left(), plot.bottom())
        fill.closeSubpath()

        grad = QLinearGradient(0, plot.top(), 0, plot.bottom())
        c1 = QColor(cols["accent"]); c1.setAlpha(150)
        c2 = QColor(cols["accent"]); c2.setAlpha(0)
        grad.setColorAt(0, c1); grad.setColorAt(1, c2)
        p.setBrush(QBrush(grad)); p.setPen(Qt.PenStyle.NoPen)
        p.drawPath(fill)

        pen = QPen(cols["accent"], 3)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)

        p.setBrush(cols["brand"]); p.setPen(Qt.PenStyle.NoPen)
        for pt in pts:
            p.drawEllipse(pt, 3.5, 3.5)

        f = QFont(); f.setPointSize(8); p.setFont(f)
        p.setPen(cols["subtext"])
        for i, (label, _) in enumerate(self.points):
            x = plot.left() + plot.width() * (i / max(1, n - 1))
            p.drawText(
                QRectF(x - 30, plot.bottom() + 6, 60, 20),
                Qt.AlignmentFlag.AlignCenter, str(label),
            )
        p.end()


# ── Donut chart ───────────────────────────────────────────────────────
class DonutChart(QWidget):
    """Donut with center label and right-side legend."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.slices = []
        self.center_label = ""
        self.setMinimumHeight(220)

    def set_data(self, slices, center_label=""):
        self.slices = slices
        self.center_label = center_label
        self.update()

    def paintEvent(self, event):
        if not self.slices:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        cols = moxie_colors(self)
        w, h = self.width(), self.height()

        d = min(w * 0.55, h - 40)
        cx = 30 + d / 2
        cy = h / 2
        outer = QRectF(cx - d / 2, cy - d / 2, d, d)
        thickness = d * 0.28
        inner = outer.adjusted(thickness, thickness,
                               -thickness, -thickness)

        total = sum(v for _, v in self.slices) or 1
        start = 90 * 16
        for i, (label, value) in enumerate(self.slices):
            span = -int(360 * 16 * (value / total))
            colour = cols["series"][i % len(cols["series"])]
            p.setBrush(colour); p.setPen(Qt.PenStyle.NoPen)
            p.drawPie(outer, start, span)
            start += span

        p.setBrush(self.palette().color(QPalette.ColorRole.Window))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(inner)

        if self.center_label:
            f = QFont(); f.setPointSize(18); f.setBold(True)
            p.setFont(f); p.setPen(cols["text"])
            p.drawText(inner, Qt.AlignmentFlag.AlignCenter,
                       self.center_label)

        f = QFont(); f.setPointSize(9); p.setFont(f)
        legend_x = 30 + d + 26
        legend_y = (h - len(self.slices) * 24) / 2
        for i, (label, value) in enumerate(self.slices):
            colour = cols["series"][i % len(cols["series"])]
            p.setBrush(colour); p.setPen(Qt.PenStyle.NoPen)
            p.drawRect(QRectF(legend_x, legend_y + 4, 10, 10))
            p.setPen(cols["text"])
            pct = int(round(100 * value / total)) if total else 0
            p.drawText(
                QRectF(legend_x + 18, legend_y, w - legend_x - 26, 20),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                f"{label}   {pct}%",
            )
            legend_y += 24
        p.end()


# ── Section label ─────────────────────────────────────────────────────
def section_label(text):
    lbl = QLabel(text.upper())
    lbl.setObjectName("MoxieSectionLabel")
    return lbl