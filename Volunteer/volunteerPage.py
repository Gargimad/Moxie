"""volunteerPage.py — events listing with a left sidebar of filters."""
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QCursor
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QStackedWidget, QGridLayout, QButtonGroup, QMessageBox,
)

import Events.theme as theme
from Events.eventCard import EventCard
from Events.eventDetailsDialog import EventDetailsDialog
from Events.filterSidebar import FilterSidebar


class VolunteerPage(QWidget):
    openLinkRequested = pyqtSignal(str)
    rsvpSucceeded = pyqtSignal(int)

    def __init__(self, db, on_back_click=None, parent=None):
        super().__init__(parent)
        self.setObjectName(theme.VOLUNTEER_PAGE)
        self.db = db
        self.on_back_click = on_back_click
        self.current_view = "grid"
        self.current_filters = {}
        self.current_volunteer_id = None
        self._bookmarked_ids = set()
        self._grid_cards = []
        self._grid_cols = 0
        self._recommendation_cards = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        outer.addWidget(self._build_header())

        # Body: sidebar | main content
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        self.filter_sidebar = FilterSidebar()
        self.filter_sidebar.filtersChanged.connect(self.apply_filters)
        body.addWidget(self.filter_sidebar, 0)

        main = QWidget()
        main.setObjectName(theme.EVENT_MAIN_AREA)
        main_v = QVBoxLayout(main)
        main_v.setContentsMargins(0, 0, 0, 0)
        main_v.setSpacing(0)

        main_v.addWidget(self._build_results_bar())
        main_v.addWidget(self._build_scroll(), 1)
        main_v.addWidget(self._build_empty_state())

        body.addWidget(main, 1)
        outer.addLayout(body, 1)

        self.refresh()

    # ── Header ────────────────────────────────────────────────────────
    def _build_header(self):
        header = QWidget()
        header.setObjectName(theme.VOLUNTEER_HEADER)
        layout = QHBoxLayout(header)
        layout.setContentsMargins(28, 16, 28, 16)
        layout.setSpacing(12)

        back_btn = QPushButton("← Back")
        back_btn.setObjectName(theme.BACK_BTN)
        back_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        if self.on_back_click:
            back_btn.clicked.connect(self.on_back_click)

        self.title_lbl = QLabel("Explore Opportunities")
        self.title_lbl.setObjectName(theme.VOLUNTEER_TITLE)

        self.grid_btn = QPushButton("Grid")
        self.grid_btn.setObjectName(theme.VIEW_TOGGLE_BTN)
        self.grid_btn.setCheckable(True)
        self.grid_btn.setChecked(True)
        self.grid_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.grid_btn.clicked.connect(lambda: self.set_view("grid"))

        self.list_btn = QPushButton("List")
        self.list_btn.setObjectName(theme.VIEW_TOGGLE_BTN)
        self.list_btn.setCheckable(True)
        self.list_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.list_btn.clicked.connect(lambda: self.set_view("list"))

        group = QButtonGroup(self)
        group.setExclusive(True)
        group.addButton(self.grid_btn)
        group.addButton(self.list_btn)

        layout.addWidget(back_btn)
        layout.addWidget(self.title_lbl)
        layout.addStretch()
        layout.addWidget(self.grid_btn)
        layout.addWidget(self.list_btn)
        return header

    # ── Results bar ───────────────────────────────────────────────────
    def _build_results_bar(self):
        bar = QWidget()
        bar.setObjectName(theme.EVENT_MAIN_AREA)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(24, 12, 24, 4)
        self.results_lbl = QLabel("")
        self.results_lbl.setObjectName(theme.VOLUNTEER_RESULTS_COUNT)
        layout.addWidget(self.results_lbl)
        layout.addStretch()
        return bar

    # ── Scroll container ──────────────────────────────────────────────
    def _build_scroll(self):
        self.results_scroll = QScrollArea()
        self.results_scroll.setObjectName(theme.VOLUNTEER_SCROLL)
        self.results_scroll.setWidgetResizable(True)
        self.results_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.results_scroll.setFrameShape(QScrollArea.Shape.NoFrame)

        self.scroll_content = QWidget()
        scroll_layout = QVBoxLayout(self.scroll_content)
        scroll_layout.setContentsMargins(24, 8, 24, 30)
        scroll_layout.setSpacing(14)

        self.recommendations_section = QWidget()
        recommendation_layout = QVBoxLayout(
            self.recommendations_section
        )
        recommendation_layout.setContentsMargins(0, 0, 0, 0)
        recommendation_layout.setSpacing(10)

        recommendation_title = QLabel("Recommended for you")
        recommendation_title.setObjectName(theme.SECTION_TITLE)
        recommendation_layout.addWidget(recommendation_title)

        self.recommendations_layout = QVBoxLayout()
        self.recommendations_layout.setSpacing(14)
        recommendation_layout.addLayout(self.recommendations_layout)
        self.recommendations_section.setVisible(False)
        scroll_layout.addWidget(self.recommendations_section)

        all_events_title = QLabel("All opportunities")
        all_events_title.setObjectName(theme.SECTION_TITLE)
        scroll_layout.addWidget(all_events_title)

        self.content_stack = QStackedWidget()
        self.content_stack.setObjectName(theme.VOLUNTEER_CONTENT_STACK)

        self.grid_container = QWidget()
        self.grid_container.setObjectName(theme.VOLUNTEER_GRID_CONTAINER)
        self.grid_layout = QGridLayout(self.grid_container)
        self.grid_layout.setContentsMargins(24, 8, 24, 30)
        self.grid_layout.setSpacing(20)
        self.grid_layout.setAlignment(
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft
        )

        self.list_container = QWidget()
        self.list_container.setObjectName(theme.VOLUNTEER_LIST_CONTAINER)
        self.list_layout = QVBoxLayout(self.list_container)
        self.list_layout.setContentsMargins(24, 8, 24, 30)
        self.list_layout.setSpacing(14)
        self.list_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.content_stack.addWidget(self.grid_container)
        self.content_stack.addWidget(self.list_container)
        scroll_layout.addWidget(self.content_stack)
        self.results_scroll.setWidget(self.scroll_content)
        return self.results_scroll

    def _build_empty_state(self):
        self.empty_wrap = QWidget()
        self.empty_wrap.setObjectName(theme.EVENT_MAIN_AREA)
        layout = QVBoxLayout(self.empty_wrap)
        layout.setContentsMargins(40, 60, 40, 60)
        layout.setSpacing(14)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.empty_lbl = QLabel("No results match your filters.")
        self.empty_lbl.setObjectName(theme.VOLUNTEER_EMPTY)
        self.empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        btn = QPushButton("Clear filters")
        btn.setObjectName(theme.VOLUNTEER_EMPTY_BTN)
        btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn.clicked.connect(self.filter_sidebar.clear_filters)

        layout.addWidget(self.empty_lbl)
        layout.addWidget(btn, 0, Qt.AlignmentFlag.AlignCenter)
        self.empty_wrap.setVisible(False)
        return self.empty_wrap

    # ── External API ──────────────────────────────────────────────────
    def set_current_volunteer(self, volunteer_id):
        self.current_volunteer_id = volunteer_id
        self._bookmarked_ids = set()
        if volunteer_id:
            try:
                self._bookmarked_ids = self.db.getBookmarkedIDs(
                    volunteer_id
                )
            except Exception:
                pass
        self.refresh()

    def set_search_text(self, text):
        self.filter_sidebar.set_search_text(text)

    def set_type_filter(self, value):
        self.filter_sidebar.set_type_filter(value)

    def set_view(self, mode):
        self.current_view = mode
        self.grid_btn.setChecked(mode == "grid")
        self.list_btn.setChecked(mode == "list")
        self.refresh()

    def apply_filters(self, filters):
        self.current_filters = filters
        self.refresh()

    # ── Data ──────────────────────────────────────────────────────────
    def _query_db(self):
        f = self.current_filters or {}
        date_enabled = f.get("date_enabled", False)
        return self.db.searchOpportunitiesFiltered(
            keyword=f.get("keyword", ""),
            type_filter=f.get("type", "All"),
            location=f.get("location", ""),
            date_from=f.get("date_from") if date_enabled else None,
            date_to=f.get("date_to") if date_enabled else None,
            upcoming_only=True,
            limit=1000,
            clusters=f.get("cluster_list") or None,
            city=f.get("city"),
            high_school=f.get("high_school"),
            zipcode=f.get("zipcode") or None,
        )

    # ── Render ────────────────────────────────────────────────────────
    def refresh(self):
        try:
            rows = self._query_db()
        except Exception as e:
            print("VolunteerPage query error:", e)
            rows = []

        self._clear_layouts()
        self._refresh_recommendations()

        if not rows:
            self.results_lbl.setText("0 results")
            if not self.recommendations_section.isHidden():
                self.empty_wrap.setVisible(False)
                self.results_scroll.setVisible(True)
                self._show_no_filtered_results()
            else:
                self.empty_wrap.setVisible(True)
                self.results_scroll.setVisible(False)
            return

        self.empty_wrap.setVisible(False)
        self.results_scroll.setVisible(True)
        n = len(rows)
        self.results_lbl.setText(
            f"{n} result{'s' if n != 1 else ''}"
        )

        if self.current_view == "grid":
            self._populate_grid(rows)
            self.content_stack.setCurrentWidget(self.grid_container)
            self._layout_grid(force=True)
        else:
            self._populate_list(rows)
            self.content_stack.setCurrentWidget(self.list_container)

    def _show_no_filtered_results(self):
        label = QLabel("No results match your filters.")
        label.setObjectName(theme.VOLUNTEER_EMPTY)
        label.setWordWrap(True)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if self.current_view == "grid":
            self.grid_layout.addWidget(label, 0, 0)
            self.content_stack.setCurrentWidget(self.grid_container)
        else:
            self.list_layout.addWidget(label)
            self.content_stack.setCurrentWidget(self.list_container)

    def _refresh_recommendations(self):
        self._clear_recommendations()
        if not self.current_volunteer_id:
            self.recommendations_section.setVisible(False)
            return

        try:
            from Volunteer.ml_recommender import rank_opportunities

            user_profile = self.db.getUserProfile(
                self.current_volunteer_id
            )
            signup_rows = self.db.getSignupsForVolunteer(
                self.current_volunteer_id
            )
            active_signups = [
                row for row in signup_rows
                if (row["status"] or "") != "cancelled"
            ]
            joined_orgs = [
                row for row in self.db.getOrganizations(
                    self.current_volunteer_id
                )
                if row["is_member"]
            ]
            opportunities = self.db.getAllOpportunities()
            recommendations, _ = rank_opportunities(
                user_profile or {},
                active_signups,
                joined_orgs,
                list(opportunities),
                top_n=4,
            )
        except ImportError as e:
            print("VolunteerPage recommendation import error:", e)
            self._add_recommendation_message(
                "Recommendations need scikit-learn to be installed."
            )
            return
        except Exception as e:
            print("VolunteerPage recommendation error:", e)
            self._add_recommendation_message(
                "Recommendations are temporarily unavailable."
            )
            return

        if not recommendations:
            self.recommendations_section.setVisible(False)
            return

        for row in recommendations:
            card = self._make_card(row, "list")
            self._recommendation_cards.append(card)
            self.recommendations_layout.addWidget(card)
        self.recommendations_section.setVisible(True)

    def _add_recommendation_message(self, text):
        label = QLabel(text)
        label.setObjectName(theme.VOLUNTEER_EMPTY)
        label.setWordWrap(True)
        self.recommendations_layout.addWidget(label)
        self.recommendations_section.setVisible(True)

    def _clear_recommendations(self):
        self._recommendation_cards = []
        while self.recommendations_layout.count():
            item = self.recommendations_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def _make_card(self, row, view_mode):
        card = EventCard(
            row, view_mode=view_mode,
            current_volunteer_id=self.current_volunteer_id,
            bookmarked_ids=self._bookmarked_ids,
        )
        card.set_bookmark_callback(self._on_bookmark_toggled)
        card.openLinkRequested.connect(self.openLinkRequested.emit)
        card.rsvpRequested.connect(self._handle_rsvp)
        card.detailsRequested.connect(self._show_details)
        return card

    def _on_bookmark_toggled(self, opportunityID, is_bookmarked):
        if not self.current_volunteer_id:
            return
        result = self.db.toggleBookmark(
            self.current_volunteer_id, opportunityID
        )
        if result == "error":
            QMessageBox.warning(
                self, "Bookmark", "Could not save bookmark."
            )
            return
        if result == "added":
            self._bookmarked_ids.add(opportunityID)
        else:
            self._bookmarked_ids.discard(opportunityID)

    def _populate_grid(self, rows):
        self._grid_cards = [
            self._make_card(row, "grid") for row in rows
        ]
        self._grid_cols = 0

    def _populate_list(self, rows):
        for row in rows:
            self.list_layout.addWidget(self._make_card(row, "list"))

    def _clear_layouts(self):
        self._grid_cards = []
        self._grid_cols = 0
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        while self.list_layout.count():
            item = self.list_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    # ── Responsive grid ───────────────────────────────────────────────
    def _grid_columns(self):
        m = self.grid_layout.contentsMargins()
        spacing = self.grid_layout.spacing()
        avail = self.results_scroll.viewport().width() - m.left() - m.right()
        return max(
            1,
            (avail + spacing) // (EventCard.GRID_WIDTH + spacing),
        )

    def _layout_grid(self, force=False):
        if not self._grid_cards:
            return
        cols = self._grid_columns()
        if cols == self._grid_cols and not force:
            return
        self._grid_cols = cols
        while self.grid_layout.count():
            self.grid_layout.takeAt(0)
        for idx, card in enumerate(self._grid_cards):
            self.grid_layout.addWidget(card, idx // cols, idx % cols)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.current_view == "grid":
            self._layout_grid()

    def showEvent(self, event):
        super().showEvent(event)
        if self.current_view == "grid":
            self._layout_grid()

    # ── Card events ───────────────────────────────────────────────────
    def _show_details(self, card):
        EventDetailsDialog(card, self).exec()

    def apply_external_filters(self, filters: dict):
        fb = self.filter_sidebar
        fb.set_search_text(filters.get("keyword", ""))
        fb.set_type_filter(filters.get("type", "All"))
        if filters.get("zipcode"):
            fb.zipcode_input.setText(filters["zipcode"])
        if filters.get("city"):
            idx = fb.city_combo.findText(filters["city"])
            if idx >= 0:
                fb.city_combo.setCurrentIndex(idx)
        cluster_list = filters.get("cluster_list") or []
        if not cluster_list and filters.get("category") \
                and filters["category"] != "All Causes":
            cluster_list = [filters["category"]]
        if cluster_list:
            fb.set_causes(cluster_list)
        else:
            fb._emit()

    def _handle_rsvp(self, opportunity_id):
        if not self.current_volunteer_id:
            QMessageBox.information(
                self, "Login required",
                "Log in as a volunteer to RSVP.",
            )
            return
        result = self.db.registerForOpportunity(
            self.current_volunteer_id, opportunity_id
        )
        if result == "ok":
            try:
                row = self.db.getOpportunityByID(opportunity_id)
                title = row["title"] if row else "an event"
                self.db.addNotification(
                    self.current_volunteer_id,
                    f"You signed up for {title}.",
                    "rsvp", opportunity_id,
                )
            except Exception as e:
                print("addNotification failed:", e)

            QMessageBox.information(
                self, "Registered",
                "You're signed up! Taking you to My Events.",
            )
            self.refresh()
            self.rsvpSucceeded.emit(opportunity_id)
        elif result == "duplicate":
            QMessageBox.information(
                self, "Already registered",
                "You've already RSVP'd for this event.",
            )
        elif result == "full":
            QMessageBox.warning(
                self, "Event full",
                "This event has reached capacity.",
            )
        else:
            QMessageBox.warning(
                self, "Error", "Could not complete RSVP."
            )