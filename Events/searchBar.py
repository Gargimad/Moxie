"""
searchBar.py — Thin bar under the nav bar. Only visible on the guest
home page. Emits `searchRequested(filters)` with a dict shaped exactly
like VolunteerPage.filter_bar expects, plus the new keys:

    cluster_list : list of career cluster names (shown as "Causes")
    zipcode      : str
    city         : str (Georgia city or "All cities")
    high_school  : str
"""
import os

from PyQt6.QtCore import QPoint, Qt, pyqtSignal
from PyQt6.QtGui import (
    QAction,
    QCursor,
    QIcon,
    QKeySequence,
    QShortcut,
)
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QStyle,
    QWidget,
)

import Events.theme as theme
from Events.careerClusters import CAREER_CLUSTERS
from Events.gaLocations import ALL_CITIES, ga_cities
from Events.multiSelectCauses import MultiSelectCauses
from Guest.micAttachment import attach_mic_to_line_edit

MAX_RECENTS = 6


class SearchBar(QWidget):
    search_requested = pyqtSignal(dict)

    TYPE_OPTIONS = ["All", "In-person", "Remote"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName(theme.SEARCH_BAR)
        self._recent_searches = []

        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 10, 20, 10)
        layout.setSpacing(10)

        # ── Causes (career clusters, multi-select) ───────────────────
        self.causes_multi = MultiSelectCauses("All Causes")
        self.causes_multi.set_items(CAREER_CLUSTERS)
        self.causes_multi.setFixedWidth(190)

        # ── Type ──────────────────────────────────────────────────────
        self.typeCombo = QComboBox()
        self.typeCombo.setObjectName(theme.SEARCH_CATEGORY)
        self.typeCombo.addItems(self.TYPE_OPTIONS)
        self.typeCombo.setFixedWidth(110)
        self.typeCombo.setCursor(
            QCursor(Qt.CursorShape.PointingHandCursor)
        )

        # ── City ──────────────────────────────────────────────────────
        self.cityCombo = QComboBox()
        self.cityCombo.setObjectName(theme.SEARCH_CATEGORY)
        self.cityCombo.addItem(ALL_CITIES)
        for c in ga_cities:
            self.cityCombo.addItem(c)
        self.cityCombo.setFixedWidth(150)
        self.cityCombo.setCursor(
            QCursor(Qt.CursorShape.PointingHandCursor)
        )

        # ── ZIP code ──────────────────────────────────────────────────
        self.zipcodeInput = QLineEdit()
        self.zipcodeInput.setObjectName(theme.SEARCH_INPUT)
        self.zipcodeInput.setPlaceholderText("ZIP")
        self.zipcodeInput.setMaxLength(10)
        self.zipcodeInput.setFixedWidth(90)
        self.zipcodeInput.returnPressed.connect(self._emit_search)

        # ── Keyword ───────────────────────────────────────────────────
        self.SEARCH_INPUT = QLineEdit()
        self.SEARCH_INPUT.setObjectName(theme.SEARCH_INPUT)
        self.SEARCH_INPUT.setPlaceholderText(
            "Search organizations, opportunities, or events...")
        self.SEARCH_INPUT.setClearButtonEnabled(False)
        self.SEARCH_INPUT.returnPressed.connect(self._emit_search)
        self.SEARCH_INPUT.textChanged.connect(self._on_text_changed)
        attach_mic_to_line_edit(self.SEARCH_INPUT)

        icon_path = theme.asset("search.svg")
        if os.path.exists(icon_path):
            icon_action = QAction(
                QIcon(icon_path), "", self.SEARCH_INPUT
            )
            icon_action.setEnabled(False)
            self.SEARCH_INPUT.addAction(
                icon_action, QLineEdit.ActionPosition.LeadingPosition
            )

        self.clear_action = QAction(
            QApplication.style().standardIcon(
                QStyle.StandardPixmap.SP_LineEditClearButton
            ),
            "Clear", self.SEARCH_INPUT,
        )
        self.clear_action.setVisible(False)
        self.clear_action.triggered.connect(self.SEARCH_INPUT.clear)
        self.SEARCH_INPUT.addAction(
            self.clear_action, QLineEdit.ActionPosition.TrailingPosition
        )

        # ── Search button ─────────────────────────────────────────────
        self.SEARCH_BTN = QPushButton("Search")
        self.SEARCH_BTN.setObjectName(theme.SEARCH_BTN)
        self.SEARCH_BTN.setCursor(
            QCursor(Qt.CursorShape.PointingHandCursor)
        )
        self.SEARCH_BTN.clicked.connect(self._emit_search)

        layout.addWidget(self.SEARCH_INPUT, 1)
        layout.addWidget(self.causes_multi)
        layout.addWidget(self.typeCombo)
        layout.addWidget(self.cityCombo)
        layout.addWidget(self.zipcodeInput)
        layout.addWidget(self.SEARCH_BTN)

        # ── Recent-searches popup ─────────────────────────────────────
        self.suggestions = QListWidget()
        self.suggestions.setObjectName("SearchSuggestions")
        self.suggestions.setWindowFlags(
            Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint
        )
        self.suggestions.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.suggestions.setVisible(False)
        self.suggestions.itemClicked.connect(self._pick_suggestion)

        QShortcut(
            QKeySequence("Ctrl+K"), self, activated=self.focus_input
        )

    # ── Public API ────────────────────────────────────────────────────
    def focus_input(self):
        self.SEARCH_INPUT.setFocus()
        self.SEARCH_INPUT.selectAll()
        self._maybe_show_suggestions()

    def set_keyword(self, text):
        self.SEARCH_INPUT.setText(text)

    def set_category(self, category):
        """Kept for caller compatibility — routes into causes list."""
        if category and category != "All Causes":
            self.causes_multi.set_checked([category])

    def populate_categories(self, categories):
        """
        Legacy hook — the SearchBar no longer sources categories from
        the DB. Career clusters are fixed, so we ignore the argument.
        """
        return

    # ── Input events ──────────────────────────────────────────────────
    def _on_text_changed(self, text):
        if hasattr(self, "clear_action"):
            self.clear_action.setVisible(bool(text))
        if text:
            self.suggestions.setVisible(False)

    # ── Emit ──────────────────────────────────────────────────────────
    def _emit_search(self):
        keyword = self.SEARCH_INPUT.text().strip()
        zipcode = self.zipcodeInput.text().strip()
        type_ = self.typeCombo.currentText()
        city = self.cityCombo.currentText()
        causes = self.causes_multi.checked_items()

        # Nothing meaningful — do nothing.
        if (not keyword and not zipcode and
                type_ == "All" and
                city == ALL_CITIES and
                not causes):
            return

        if keyword:
            if keyword in self._recent_searches:
                self._recent_searches.remove(keyword)
            self._recent_searches.insert(0, keyword)
            self._recent_searches = self._recent_searches[:MAX_RECENTS]

        self.suggestions.setVisible(False)
        self.search_requested.emit({
            "keyword": keyword,
            "location": "",
            "zipcode": zipcode,
            "type": type_,
            "city": city,
            "high_school": "",
            "cluster_list": causes,
            "date_enabled": False,
            "date_from": "",
            "date_to": "",
        })

    # ── Suggestions popup ─────────────────────────────────────────────
    def _maybe_show_suggestions(self):
        if not self._recent_searches:
            return
        if self.SEARCH_INPUT.text().strip():
            return
        self._populate_suggestions()
        self._position_suggestions()

    def _populate_suggestions(self):
        self.suggestions.clear()
        for s in self._recent_searches:
            item = QListWidgetItem(s)
            item.setData(Qt.ItemDataRole.UserRole, s)
            self.suggestions.addItem(item)

    def _position_suggestions(self):
        top_left = self.SEARCH_INPUT.mapToGlobal(
            QPoint(0, self.SEARCH_INPUT.height())
        )
        self.suggestions.move(top_left)
        self.suggestions.setFixedWidth(self.SEARCH_INPUT.width())
        count = self.suggestions.count()
        row_h = self.suggestions.sizeHintForRow(0) if count else 24
        self.suggestions.setFixedHeight(min(count * row_h + 8, 220))
        self.suggestions.show()
        self.suggestions.raise_()

    def _pick_suggestion(self, item):
        text = item.data(Qt.ItemDataRole.UserRole) or item.text()
        self.SEARCH_INPUT.setText(text)
        self.suggestions.setVisible(False)
        self._emit_search()

    def hideEvent(self, event):  # noqa: N802
        self.suggestions.setVisible(False)
        super().hideEvent(event)
    searchRequested = property(lambda self: self.search_requested)  # noqa: N815
