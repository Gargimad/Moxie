"""
orgBrowsePage.py — Public organization directory.

Used by:
  • Guests browsing the guest home page (view-only; a Join click
    prompts them to log in).
  • Logged-in volunteers (Join actually works).

Signals:
  loginRequested — a guest tried to interact but isn't logged in.
                   landing.py should route to the login page.
"""
# ── Color helper (kept local to avoid a heavy import chain) ───────────
import zlib

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QCursor
from PyQt6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

import Events.theme as theme
from Events.careerClusters import CAREER_CLUSTERS
from Events.gaLocations import ALL_CITIES, ga_cities
from Events.multiSelectCauses import MultiSelectCauses

_ORG_PALETTE = [
    "#2E86DE", "#E67E22", "#27AE60", "#C0392B", "#8E44AD",
    "#16A085", "#D4AC0D", "#E84393", "#5D6D7E", "#00A8CC",
]
_INDEPENDENT_COLOR = "#7F8C8D"


def _org_color(name):
    if not name:
        return _INDEPENDENT_COLOR
    return _ORG_PALETTE[
        zlib.crc32(name.encode("utf-8")) % len(_ORG_PALETTE)
    ]


class OrgBrowsePage(QWidget):
    login_requested = pyqtSignal()

    def __init__(self, db, on_back_click=None, parent=None):
        super().__init__(parent)
        self.setObjectName(theme.VOLUNTEER_PAGE)
        self.db = db
        self.on_back_click = on_back_click
        self.current_volunteer_id = None
        self._rows = []
        self._joined_ids = set()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        outer.addWidget(self._build_header())
        outer.addWidget(self._build_filters())
        outer.addWidget(self._build_results_count())
        outer.addWidget(self._build_scroll(), 1)
        outer.addWidget(self._build_empty_state())

        self.refresh()

    # ── Header ────────────────────────────────────────────────────────
    def _build_header(self):
        header = QWidget()
        header.setObjectName(theme.VOLUNTEER_HEADER)
        layout = QHBoxLayout(header)
        layout.setContentsMargins(20, 12, 20, 12)

        back_btn = QPushButton("← Back")
        back_btn.setObjectName(theme.BACK_BTN)
        back_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        if self.on_back_click:
            back_btn.clicked.connect(self.on_back_click)

        self.title_lbl = QLabel("Organizations")
        self.title_lbl.setObjectName(theme.VOLUNTEER_TITLE)

        layout.addWidget(back_btn)
        layout.addWidget(self.title_lbl)
        layout.addStretch(1)
        return header

    # ── Filters ───────────────────────────────────────────────────────
    def _build_filters(self):
        bar = QWidget()
        bar.setObjectName(theme.FILTER_BAR)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(20, 10, 20, 10)
        layout.setSpacing(10)

        self.search_input = QLineEdit()
        self.search_input.setObjectName(theme.FILTER_searchInput)
        self.search_input.setPlaceholderText(
            "Search by name, mission, or cause..."
        )
        layout.addWidget(self.search_input, 3)

        self.city_combo = QComboBox()
        self.city_combo.setObjectName(theme.FILTER_COMBO)
        self.city_combo.addItem(ALL_CITIES)
        for c in ga_cities:
            self.city_combo.addItem(c)
        layout.addWidget(self.city_combo, 1)

        self.causes_multi = MultiSelectCauses("All Causes")
        self.causes_multi.set_items(CAREER_CLUSTERS)
        self.causes_multi.setMinimumWidth(200)
        layout.addWidget(self.causes_multi, 2)

        self.clear_btn = QPushButton("Clear filters")
        self.clear_btn.setObjectName(theme.FILTER_CLEAR_BTN)
        self.clear_btn.setCursor(
            QCursor(Qt.CursorShape.PointingHandCursor)
        )
        self.clear_btn.clicked.connect(self._clear_filters)
        layout.addWidget(self.clear_btn)

        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(250)
        self._debounce.timeout.connect(self.refresh)

        self.search_input.textChanged.connect(
            lambda _t: self._debounce.start()
        )
        self.city_combo.currentTextChanged.connect(self.refresh)
        self.causes_multi.selection_changed.connect(
            lambda _items: self.refresh()
        )

        return bar

    def _build_results_count(self):
        wrap = QWidget()
        layout = QHBoxLayout(wrap)
        layout.setContentsMargins(20, 2, 20, 2)
        self.results_lbl = QLabel("")
        self.results_lbl.setObjectName(theme.VOLUNTEER_RESULTS_COUNT)
        layout.addWidget(self.results_lbl)
        layout.addStretch()
        return wrap

    # ── Scroll container ──────────────────────────────────────────────
    def _build_scroll(self):
        self.scroll = QScrollArea()
        self.scroll.setObjectName(theme.VOLUNTEER_SCROLL)
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.scroll.setFrameShape(QScrollArea.Shape.NoFrame)

        content = QWidget()
        content.setObjectName(theme.VOLUNTEER_LIST_CONTAINER)
        self.list_layout = QVBoxLayout(content)
        self.list_layout.setContentsMargins(20, 10, 20, 30)
        self.list_layout.setSpacing(12)
        self.list_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.scroll.setWidget(content)
        return self.scroll

    def _build_empty_state(self):
        self.empty_wrap = QWidget()
        self.empty_wrap.setObjectName(theme.VOLUNTEER_EMPTY_WRAP)
        layout = QVBoxLayout(self.empty_wrap)
        layout.setContentsMargins(20, 40, 20, 40)
        layout.setSpacing(14)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.empty_lbl = QLabel(
            "No organizations match your filters yet."
        )
        self.empty_lbl.setObjectName(theme.VOLUNTEER_EMPTY)
        self.empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        btn = QPushButton("Clear filters")
        btn.setObjectName(theme.VOLUNTEER_EMPTY_BTN)
        btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn.clicked.connect(self._clear_filters)

        layout.addWidget(self.empty_lbl)
        layout.addWidget(btn, 0, Qt.AlignmentFlag.AlignCenter)
        self.empty_wrap.setVisible(False)
        return self.empty_wrap

    # ── External API ──────────────────────────────────────────────────
    def set_current_volunteer(self, volunteer_id):
        """Called when login state changes (also on logout with None)."""
        self.current_volunteer_id = volunteer_id
        self._joined_ids = set()
        if volunteer_id:
            try:
                rows = self.db.get_organizations(volunteer_id) or []
                self._joined_ids = {
                    r["organizationID"] for r in rows
                    if r["is_member"]
                }
            except Exception:
                pass
        self.refresh()

    def _clear_filters(self):
        for w in (self.search_input, self.city_combo):
            w.blockSignals(True)
        self.search_input.clear()
        self.city_combo.setCurrentIndex(0)
        for w in (self.search_input, self.city_combo):
            w.blockSignals(False)
        self.causes_multi.clear_selection()
        self.refresh()

    # ── Data ──────────────────────────────────────────────────────────
    def refresh(self):
        keyword = self.search_input.text().strip()
        city = self.city_combo.currentText()
        clusters = self.causes_multi.checked_items()

        try:
            rows = self.db.search_organizations(
                keyword=keyword,
                city=city,
                cluster_list=clusters,
                limit=500,
            )
        except Exception as e:
            print("OrgBrowsePage query error:", e)
            rows = []

        self._rows = rows
        self._render()

    def _render(self):
        while self.list_layout.count():
            item = self.list_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        n = len(self._rows)
        self.results_lbl.setText(
            f"{n} organization{'s' if n != 1 else ''}"
        )

        if not self._rows:
            self.scroll.setVisible(False)
            self.empty_wrap.setVisible(True)
            return

        self.scroll.setVisible(True)
        self.empty_wrap.setVisible(False)
        for row in self._rows:
            self.list_layout.addWidget(self._make_org_card(row))

    # ── Card ──────────────────────────────────────────────────────────
    @staticmethod
    def _swatch(color, size=14):
        s = QLabel()
        s.setFixedSize(size, size)
        s.setStyleSheet(
            f"background-color: {color}; "
            f"border-radius: {size // 2}px;"
        )
        return s

    def _make_org_card(self, row):
        org_id = row["orgID"]
        name = row["org_name"] or "Unnamed organization"
        is_member = org_id in self._joined_ids

        card = QFrame()
        card.setObjectName(theme.EVENT_CARD)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(6)

        # Header: swatch + name + verified pill
        head = QHBoxLayout()
        head.setSpacing(10)
        head.addWidget(self._swatch(_org_color(name)))
        title = QLabel(name)
        title.setObjectName(theme.EVENT_TITLE_LIST)
        head.addWidget(title)
        if row["is_moxie_org"]:
            pill = QLabel("Verified on Moxie")
            pill.setObjectName(theme.EVENT_SOURCE_MOXIE)
            head.addWidget(pill)
        head.addStretch(1)

        # Meta line: city, service area, remote-friendly
        meta_bits = []
        if row["city"]:
            meta_bits.append(f"{row['city']}, GA")
        if row["service_area"]:
            meta_bits.append(row["service_area"])
        if row["remote_friendly"]:
            meta_bits.append("Remote-friendly")
        if meta_bits:
            meta = QLabel(" · ".join(meta_bits))
            meta.setObjectName(theme.EVENT_META_VALUE)
            meta.setWordWrap(True)
            head.addWidget(meta)
        lay.addLayout(head)

        # Description
        if row["description"]:
            desc = QLabel(row["description"])
            desc.setObjectName(theme.EVENT_DESCRIPTION)
            desc.setWordWrap(True)
            lay.addWidget(desc)

        # Clusters shown as causes
        clusters = self.db.get_organization_clusters(org_id) or []
        if clusters:
            cl = QLabel(" · ".join(clusters))
            cl.setObjectName(theme.EVENT_META_VALUE)
            cl.setWordWrap(True)
            lay.addWidget(cl)

        # Footer: count + action button
        foot = QHBoxLayout()
        n_opps = int(row["active_opportunities"] or 0)
        opps = QLabel(
            f"{n_opps} active "
            f"{'opportunity' if n_opps == 1 else 'opportunities'}"
        )
        opps.setObjectName(theme.EVENT_META_VALUE)
        foot.addWidget(opps)
        foot.addStretch(1)

        if is_member:
            joined = QPushButton("Joined ✓")
            joined.setObjectName(theme.SECONDARY_BTN)
            joined.setEnabled(False)
            foot.addWidget(joined)
        else:
            join_btn = QPushButton("Join")
            join_btn.setObjectName(theme.PRIMARY_BTN)
            join_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            join_btn.clicked.connect(
                lambda _, oid=org_id: self._on_join(oid)
            )
            foot.addWidget(join_btn)

        lay.addLayout(foot)
        return card

    # ── Actions ───────────────────────────────────────────────────────
    def _on_join(self, org_id):
        if not self.current_volunteer_id:
            self.login_requested.emit()
            return
        if not self.db.join_organization(
                self.current_volunteer_id, org_id):
            QMessageBox.warning(
                self, "Join failed",
                "Could not join this organization right now."
            )
            return
        try:
            self.db.add_notification(
                self.current_volunteer_id,
                "You joined a new organization.",
                "join_org", None,
            )
        except Exception:
            pass
        self._joined_ids.add(org_id)
        self._render()
    loginRequested = property(lambda self: self.login_requested)  # noqa: N815
