"""
filterSidebar.py — Vertical filter panel on the left of the events
listing. Sections: Search, Location, Format, Causes, When.
"""
from PyQt6.QtCore import QDate, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QCursor
from PyQt6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QFrame,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

import Events.theme as theme
from Events.careerClusters import CAREER_CLUSTERS
from Events.gaLocations import ALL_CITIES, ga_cities


class FilterSidebar(QWidget):
    filters_changed = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName(theme.FILTER_SIDEBAR)
        self.setFixedWidth(320)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setObjectName(theme.FILTER_SIDEBAR_SCROLL)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )

        content = QWidget()
        content.setObjectName(theme.FILTER_SIDEBAR_CONTENT)
        body = QVBoxLayout(content)
        body.setContentsMargins(20, 22, 20, 22)
        body.setSpacing(16)

        # ── Search ────────────────────────────────────────────────────
        body.addWidget(self._heading("Search"))
        self.search_input = QLineEdit()
        self.search_input.setObjectName(theme.FILTER_SIDEBAR_INPUT)
        self.search_input.setPlaceholderText("Keyword or organization")
        body.addWidget(self.search_input)

        # ── Location ──────────────────────────────────────────────────
        body.addWidget(self._heading("Location"))
        self.city_combo = QComboBox()
        self.city_combo.setObjectName(theme.FILTER_SIDEBAR_INPUT)
        self.city_combo.addItem(ALL_CITIES)
        for c in ga_cities:
            self.city_combo.addItem(c)
        body.addWidget(self.city_combo)

        self.zipcode_input = QLineEdit()
        self.zipcode_input.setObjectName(theme.FILTER_SIDEBAR_INPUT)
        self.zipcode_input.setPlaceholderText("ZIP code")
        self.zipcode_input.setMaxLength(10)
        body.addWidget(self.zipcode_input)

        # ── Format ────────────────────────────────────────────────────
        body.addWidget(self._heading("Format"))
        fmt_wrap = QWidget()
        fmt_v = QVBoxLayout(fmt_wrap)
        fmt_v.setContentsMargins(0, 0, 0, 0)
        fmt_v.setSpacing(4)
        self.format_group = QButtonGroup(self)
        self._format_buttons = {}
        for label in ("All", "In-person", "Remote"):
            rb = QRadioButton(label)
            rb.setObjectName(theme.FILTER_SIDEBAR_RADIO)
            rb.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            self.format_group.addButton(rb)
            self._format_buttons[label] = rb
            fmt_v.addWidget(rb)
        self._format_buttons["All"].setChecked(True)
        body.addWidget(fmt_wrap)

        # ── Causes (career clusters) ──────────────────────────────────
        body.addWidget(self._heading("Causes"))
        self._cause_checks = {}
        for name in CAREER_CLUSTERS:
            cb = QCheckBox(name)
            cb.setObjectName(theme.FILTER_SIDEBAR_CHECK)
            cb.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            # QCheckBox has no setWordWrap; long names ellipsize.
            # Tooltip carries the full text.
            cb.setToolTip(name)
            self._cause_checks[name] = cb
            body.addWidget(cb)
        # ── When ──────────────────────────────────────────────────────
        body.addWidget(self._heading("When"))
        self.date_preset = QComboBox()
        self.date_preset.setObjectName(theme.FILTER_SIDEBAR_INPUT)
        self.date_preset.addItems([
            "Any date", "Next 7 days", "Next 30 days", "Custom range",
        ])
        body.addWidget(self.date_preset)

        self.date_from = QDateEdit()
        self.date_from.setObjectName(theme.FILTER_SIDEBAR_INPUT)
        self.date_from.setCalendarPopup(True)
        self.date_from.setDate(QDate.currentDate())
        self.date_from.setDisplayFormat("yyyy-MM-dd")
        self.date_from.setVisible(False)
        body.addWidget(self.date_from)

        self.date_to = QDateEdit()
        self.date_to.setObjectName(theme.FILTER_SIDEBAR_INPUT)
        self.date_to.setCalendarPopup(True)
        self.date_to.setDate(QDate.currentDate().addMonths(1))
        self.date_to.setDisplayFormat("yyyy-MM-dd")
        self.date_to.setVisible(False)
        body.addWidget(self.date_to)

        body.addStretch(1)
        scroll.setWidget(content)
        outer.addWidget(scroll, 1)

        # ── Clear button pinned at bottom ─────────────────────────────
        self.clear_btn = QPushButton("Clear all filters")
        self.clear_btn.setObjectName(theme.FILTER_SIDEBAR_CLEAR)
        self.clear_btn.setCursor(
            QCursor(Qt.CursorShape.PointingHandCursor)
        )
        self.clear_btn.clicked.connect(self.clear_filters)
        outer.addWidget(self.clear_btn)

        # ── Debounce + wiring ─────────────────────────────────────────
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(250)
        self._debounce.timeout.connect(self._emit)

        self.search_input.textChanged.connect(
            lambda _t: self._debounce.start()
        )
        self.zipcode_input.textChanged.connect(
            lambda _t: self._debounce.start()
        )
        self.city_combo.currentTextChanged.connect(self._emit)
        self.format_group.buttonToggled.connect(lambda *_: self._emit())
        for cb in self._cause_checks.values():
            cb.toggled.connect(lambda *_: self._emit())
        self.date_preset.currentTextChanged.connect(
            self._on_preset_changed
        )
        self.date_from.dateChanged.connect(self._emit)
        self.date_to.dateChanged.connect(self._emit)

    # ── Helpers ───────────────────────────────────────────────────────
    def _heading(self, text):
        lbl = QLabel(text.upper())
        lbl.setObjectName(theme.FILTER_SIDEBAR_HEADING)
        return lbl

    def _on_preset_changed(self, preset):
        custom = (preset == "Custom range")
        self.date_from.setVisible(custom)
        self.date_to.setVisible(custom)
        self._emit()

    def _date_range(self):
        preset = self.date_preset.currentText()
        today = QDate.currentDate()
        fmt = "yyyy-MM-dd"
        if preset == "Next 7 days":
            return (True, today.toString(fmt),
                    today.addDays(7).toString(fmt))
        if preset == "Next 30 days":
            return (True, today.toString(fmt),
                    today.addDays(30).toString(fmt))
        if preset == "Custom range":
            return (True,
                    self.date_from.date().toString(fmt),
                    self.date_to.date().toString(fmt))
        return False, "", ""

    def _format(self):
        for label, rb in self._format_buttons.items():
            if rb.isChecked():
                return label
        return "All"

    def _selected_causes(self):
        return [n for n, cb in self._cause_checks.items() if cb.isChecked()]

    # ── Emit ──────────────────────────────────────────────────────────
    def _emit(self, *_args):
        enabled, d_from, d_to = self._date_range()
        self.filters_changed.emit({
            "keyword": self.search_input.text().strip(),
            "type": self._format(),
            "location": "",
            "zipcode": self.zipcode_input.text().strip(),
            "cluster_list": self._selected_causes(),
            "city": self.city_combo.currentText(),
            "high_school": "",
            "date_enabled": enabled,
            "date_from": d_from,
            "date_to": d_to,
        })

    def clear_filters(self):
        self.search_input.blockSignals(True)
        self.zipcode_input.blockSignals(True)
        self.city_combo.blockSignals(True)
        self.date_preset.blockSignals(True)
        self.search_input.clear()
        self.zipcode_input.clear()
        self.city_combo.setCurrentIndex(0)
        self.date_preset.setCurrentIndex(0)
        self.search_input.blockSignals(False)
        self.zipcode_input.blockSignals(False)
        self.city_combo.blockSignals(False)
        self.date_preset.blockSignals(False)
        self._format_buttons["All"].setChecked(True)
        for cb in self._cause_checks.values():
            cb.blockSignals(True)
            cb.setChecked(False)
            cb.blockSignals(False)
        self.date_from.setVisible(False)
        self.date_to.setVisible(False)
        self._emit()

    # ── External setters (used by landing.handle_search) ──────────────
    def set_search_text(self, text):
        self.search_input.setText(text)

    def set_type_filter(self, value):
        legacy = {"Events": "In-person", "Organizations": "All"}
        value = legacy.get(value, value)
        if value in self._format_buttons:
            self._format_buttons[value].setChecked(True)

    def set_causes(self, cluster_names):
        cluster_names = set(cluster_names or [])
        for name, cb in self._cause_checks.items():
            cb.blockSignals(True)
            cb.setChecked(name in cluster_names)
            cb.blockSignals(False)
        self._emit()
    filtersChanged = property(lambda self: self.filters_changed)  # noqa: N815
