"""clusterSelector.py — reusable multi-select for career clusters."""
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QCursor
from PyQt6.QtWidgets import QGridLayout, QPushButton, QWidget

import Events.theme as theme
from Events.careerClusters import CAREER_CLUSTERS


class ClusterSelector(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName(theme.CLUSTER_MULTI)
        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(6)
        self._btns = {}
        for i, name in enumerate(CAREER_CLUSTERS):
            b = QPushButton(name)
            b.setObjectName(theme.CLUSTER_CHIP)
            b.setCheckable(True)
            b.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            grid.addWidget(b, i // 2, i % 2)
            self._btns[name] = b

    def selected(self):
        return [n for n, b in self._btns.items() if b.isChecked()]

    def set_selected(self, names):
        names = set(names or [])
        for n, b in self._btns.items():
            b.setChecked(n in names)
