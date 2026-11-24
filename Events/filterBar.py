"""filterBar.py — Search + Georgia city + ZIP code + career clusters
(shown to users as "Causes") + school + date range.

The filter dict emitted through `filtersChanged` looks like:

{
    "keyword": str,
    "type": "All" | "In-person" | "Remote",
    "location": str,             # reserved / unused now
    "zipcode": str,              # optional 5-digit GA ZIP
    "cluster_list": [str, ...],  # zero or more career cluster names
    "city": str,                 # Georgia city, or "All cities"
    "high_school": str,          # narrowed by city
    "date_enabled": bool,
    "date_from": "YYYY-MM-DD" | "",
    "date_to": "YYYY-MM-DD" | "",
}
"""
from PyQt6.QtCore import QDate, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QCursor
from PyQt6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

import Events.theme as theme
from Events.careerClusters import CAREER_CLUSTERS
from Events.gaLocations import (
    ALL_CITIES,
    ALL_SCHOOLS,
    ga_cities,
    schools_for_city,
)
from Events.multiSelectCauses import MultiSelectCauses


class FilterBar(QWidget):
    filters_changed = pyqtSignal(dict)

    TYPE_OPTIONS = ["All", "In-person", "Remote"]
    DATE_PRESETS = ["Any date", "Next 7 days", "Next 30 days",
                    "Custom range"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName(theme.FILTER_BAR)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 10, 20, 10)
        outer.setSpacing(8)

        # ── Row 1: keyword / type / city / zip / more / clear ────────
        row1 = QHBoxLayout()
        row1.setSpacing(10)

        self.search_input = QLineEdit()
        self.search_input.setObjectName(theme.FILTER_searchInput)
        self.search_input.setPlaceholderText(
            "Search by keyword, organization, or event name..."
        )

        self.type_combo = QComboBox()
        self.type_combo.setObjectName(theme.FILTER_COMBO)
        self.type_combo.addItems(self.TYPE_OPTIONS)

        self.city_combo = QComboBox()
        self.city_combo.setObjectName(theme.FILTER_COMBO)
        self.city_combo.addItem(ALL_CITIES)
        for c in ga_cities:
            self.city_combo.addItem(c)

        self.zipcode_input = QLineEdit()
        self.zipcode_input.setObjectName(theme.FILTER_LOCATION_INPUT)
        self.zipcode_input.setPlaceholderText("ZIP code")
        self.zipcode_input.setMaxLength(10)
        self.zipcode_input.setFixedWidth(110)

        self.more_btn = QPushButton("More filters")
        self.more_btn.setObjectName(theme.FILTER_MORE_BTN)
        self.more_btn.setCheckable(True)
        self.more_btn.setCursor(
            QCursor(Qt.CursorShape.PointingHandCursor)
        )

        self.clear_btn = QPushButton("Clear filters")
        self.clear_btn.setObjectName(theme.FILTER_CLEAR_BTN)
        self.clear_btn.setCursor(
            QCursor(Qt.CursorShape.PointingHandCursor)
        )
        self.clear_btn.clicked.connect(self.clear_filters)

        row1.addWidget(self.search_input, 3)
        row1.addWidget(self.type_combo, 1)
        row1.addWidget(self.city_combo, 2)
        row1.addWidget(self.zipcode_input)
        row1.addWidget(self.more_btn)
        row1.addWidget(self.clear_btn)

        # ── Row 2 (collapsible): causes / school / date range ────────
        self.more_row = QWidget()
        self.more_row.setObjectName(theme.FILTER_MORE_ROW)
        row2 = QHBoxLayout(self.more_row)
        row2.setContentsMargins(0, 0, 0, 0)
        row2.setSpacing(10)

        # Career clusters presented to the user as "Causes".
        # Multi-select: check as many as you want.
        self.causes_multi = MultiSelectCauses("All Causes")
        self.causes_multi.set_items(CAREER_CLUSTERS)
        self.causes_multi.setMinimumWidth(220)

        self.school_combo = QComboBox()
        self.school_combo.setObjectName(theme.FILTER_COMBO)
        self.school_combo.addItem(ALL_SCHOOLS)

        self.date_preset = QComboBox()
        self.date_preset.setObjectName(theme.FILTER_COMBO)
        self.date_preset.addItems(self.DATE_PRESETS)

        self.date_from = QDateEdit()
        self.date_from.setObjectName(theme.FILTER_DATE)
        self.date_from.setCalendarPopup(True)
        self.date_from.setDate(QDate.currentDate())
        self.date_from.setDisplayFormat("yyyy-MM-dd")

        self.date_to = QDateEdit()
        self.date_to.setObjectName(theme.FILTER_DATE)
        self.date_to.setCalendarPopup(True)
        self.date_to.setDate(QDate.currentDate().addMonths(6))
        self.date_to.setDisplayFormat("yyyy-MM-dd")

        self.arrow_lbl = QLabel("→")
        self.arrow_lbl.setObjectName(theme.FILTER_LABEL)

        causes_lbl = QLabel("Causes")
        causes_lbl.setObjectName(theme.FILTER_LABEL)
        school_lbl = QLabel("School")
        school_lbl.setObjectName(theme.FILTER_LABEL)
        date_lbl = QLabel("Date")
        date_lbl.setObjectName(theme.FILTER_LABEL)

        row2.addWidget(causes_lbl)
        row2.addWidget(self.causes_multi, 2)
        row2.addWidget(school_lbl)
        row2.addWidget(self.school_combo, 2)
        row2.addWidget(date_lbl)
        row2.addWidget(self.date_preset, 1)
        row2.addWidget(self.date_from)
        row2.addWidget(self.arrow_lbl)
        row2.addWidget(self.date_to)
        row2.addStretch(1)

        outer.addLayout(row1)
        outer.addWidget(self.more_row)

        # ── Debounce for text inputs ─────────────────────────────────
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(250)
        self._debounce.timeout.connect(self._emit)

        # ── Wiring ────────────────────────────────────────────────────
        self.search_input.textChanged.connect(
            lambda _t: self._debounce.start()
        )
        self.zipcode_input.textChanged.connect(
            lambda _t: self._debounce.start()
        )
        self.type_combo.currentTextChanged.connect(self._emit)
        self.city_combo.currentTextChanged.connect(self._on_city_changed)
        self.school_combo.currentTextChanged.connect(self._emit)
        self.causes_multi.selection_changed.connect(
            lambda _items: self._emit()
        )
        self.date_preset.currentTextChanged.connect(self._on_preset_changed)
        self.date_from.dateChanged.connect(self._emit)
        self.date_to.dateChanged.connect(self._emit)
        self.more_btn.toggled.connect(self._toggle_more)

        self._toggle_more(False)
        self._on_preset_changed("Any date")

    # ── City → schools ────────────────────────────────────────────────
    def _on_city_changed(self, city):
        self.school_combo.blockSignals(True)
        self.school_combo.clear()
        self.school_combo.addItem(ALL_SCHOOLS)
        for s in schools_for_city(city):
            self.school_combo.addItem(s)
        self.school_combo.blockSignals(False)
        self._emit()

    # ── Advanced row toggle ───────────────────────────────────────────
    def _toggle_more(self, expanded):
        self.more_row.setVisible(expanded)
        self._update_more_label()

    def _on_preset_changed(self, preset):
        custom = (preset == "Custom range")
        self.date_from.setVisible(custom)
        self.date_to.setVisible(custom)
        self.arrow_lbl.setVisible(custom)
        self._emit()

    def _advanced_active(self):
        return (
            bool(self.causes_multi.checked_items()) or
            self.school_combo.currentIndex() > 0 or
            self.date_preset.currentIndex() > 0
        )

    def _update_more_label(self):
        arrow = "▲" if self.more_btn.isChecked() else "▼"
        dot = " ●" if self._advanced_active() else ""
        self.more_btn.setText(f"More filters{dot} {arrow}")

    # ── Clear ─────────────────────────────────────────────────────────
    def clear_filters(self):
        widgets = (
            self.search_input, self.zipcode_input,
            self.type_combo, self.city_combo,
            self.school_combo, self.date_preset,
        )
        for w in widgets:
            w.blockSignals(True)
        self.search_input.clear()
        self.zipcode_input.clear()
        self.type_combo.setCurrentIndex(0)
        self.city_combo.setCurrentIndex(0)
        self.school_combo.setCurrentIndex(0)
        self.date_preset.setCurrentIndex(0)
        for w in widgets:
            w.blockSignals(False)
        self.causes_multi.clear_selection()
        self._on_city_changed(ALL_CITIES)

    # ── Emit ──────────────────────────────────────────────────────────
    def _date_range(self):
        preset = self.date_preset.currentText()
        today = QDate.currentDate()
        fmt = "yyyy-MM-dd"
        if preset == "Next 7 days":
            return True, today.toString(fmt), today.addDays(7).toString(fmt)
        if preset == "Next 30 days":
            return (True, today.toString(fmt),
                    today.addDays(30).toString(fmt))
        if preset == "Custom range":
            return (True,
                    self.date_from.date().toString(fmt),
                    self.date_to.date().toString(fmt))
        return False, "", ""

    def _emit(self, *_args):
        enabled, d_from, d_to = self._date_range()
        filters = {
            "keyword": self.search_input.text().strip(),
            "type": self.type_combo.currentText(),
            "location": "",
            "zipcode": self.zipcode_input.text().strip(),
            "cluster_list": self.causes_multi.checked_items(),
            "city": self.city_combo.currentText(),
            "high_school": self.school_combo.currentText(),
            "date_enabled": enabled,
            "date_from": d_from,
            "date_to": d_to,
        }
        self._update_more_label()
        self.filters_changed.emit(filters)

    # ── External setters (used by landing.handle_search) ──────────────
    def set_search_text(self, text):
        self.search_input.setText(text)

    def set_type_filter(self, value):
        legacy = {"Events": "In-person", "Organizations": "All"}
        value = legacy.get(value, value)
        idx = self.type_combo.findText(value)
        if idx >= 0:
            self.type_combo.setCurrentIndex(idx)
    filtersChanged = property(lambda self: self.filters_changed)  # noqa: N815
