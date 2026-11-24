"""
heroLogo.py - Full-bleed Moxie wordmark for the guest home page.

A QLabel subclass that owns a source pixmap and rescales it to fit its
own current size on every resize event. Aspect ratio is preserved and
the image is centered, so the logo grows to fill whatever box the
layout gives it (the hero section, in this case).

Usage:
    logo = HeroLogo()
    logo.set_source(QPixmap(theme.asset("logoFullDark.png")))
"""

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QLabel, QSizePolicy


class HeroLogo(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._source = QPixmap()
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Expanding)
        self.setMinimumHeight(220)

    def set_source(self, pixmap: QPixmap):
        """Hand it the full-resolution pixmap; it handles the rest."""
        self._source = pixmap
        self._rescale()

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        self._rescale()

    def _rescale(self):
        if self._source.isNull():
            return
        w, h = self.width(), self.height()
        if w <= 0 or h <= 0:
            return
        scaled = self._source.scaled(
            w, h,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.setPixmap(scaled)
