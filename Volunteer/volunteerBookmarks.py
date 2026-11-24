"""volunteerBookmarks.py — Bookmarks tab for VolunteerHome."""
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel

import Events.theme as theme
from Events.eventCard import EventCard
from Events.eventDetailsDialog import EventDetailsDialog


class VolunteerBookmarks:
    """Mixin — expects VolunteerHome helpers (_scroll_page, _clear,
    _add, _empty, _db) and self.userID / self.db."""

    def _build_bookmarks_page(self):
        page, self.bookmarks_layout, top = self._scroll_page(
            "Bookmarked Events", spacing=10
        )

        sub = QLabel(
            "Events you've saved for later. Events that have already "
            "happened are removed automatically."
        )
        sub.setObjectName(theme.EVENT_META_VALUE)
        sub.setWordWrap(True)
        top.addWidget(sub)

        self._bookmarked_ids = set()
        return page

    def _refresh_bookmarks(self):
        self._clear(self.bookmarks_layout)
        if not (self.db and self.user_id):
            return

        rows = self._db(
            "getBookmarkedOpportunities", self.user_id, default=[]
        ) or []
        self._bookmarked_ids = {r["opportunityID"] for r in rows}

        if not rows:
            self._empty(
                self.bookmarks_layout,
                "No bookmarks yet. Tap ☆ on any event to save it here.",
            )
            return

        for row in rows:
            self._add(
                self.bookmarks_layout,
                self._make_bookmark_card(row),
            )

    def _make_bookmark_card(self, row):
        card = EventCard(
            row, view_mode="list",
            current_volunteer_id=self.user_id,
            bookmarked_ids=self._bookmarked_ids,
        )
        card.set_bookmark_callback(self._on_bookmark_toggled)
        card.details_requested.connect(
            lambda c, _p=self: EventDetailsDialog(c, self).exec()
        )
        return card

    def _on_bookmark_toggled(self, opportunity_id, is_bookmarked):
        if not is_bookmarked:
            self._refresh_bookmarks()
