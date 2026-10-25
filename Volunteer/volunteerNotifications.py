"""
volunteerNotifications.py — Notifications tab for VolunteerHome.

Shows ONE feed made of:
    * announcements posted by organizations the volunteer follows
      (Database.getAnnouncementsForVolunteer: orgs they've joined +
      orgs they've signed up for events with)
    * the volunteer's own activity notifications (check-in, check-out, ...)

Layout: filter pills (All / Announcements / Activity), then cards grouped
under "Pinned" and per-day headers. Each card has a coloured left edge
(the organization's colour for announcements), a title, a timestamp and
the message body.

How it plugs in (see the instructions that came with this file):
    class VolunteerHome(NotificationsMixin, QWidget): ...
and the old _build_notifications_page / _refresh_notifications methods
in VolunteerHome are deleted so the mixin's versions are used.

The mixin relies on helpers VolunteerHome already has:
    self._scroll_page, self._clear, self._add, self._empty, self._db
"""

from datetime import date, datetime, timedelta, timezone

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QButtonGroup, QFrame, QHBoxLayout, QLabel, QMessageBox, QPushButton,
    QVBoxLayout,
)

import Events.theme as theme


# Notification type -> (card title, accent colour). Anything not listed
# falls back to DEFAULT_NOTIF.
NOTIF_TYPES = {
    "check_in": ("Checked in", "#27AE60"),
    "check_out": ("Checked out", "#27AE60"),
    "cancel": ("Signup cancelled", "#7F8C8D"),
    "join_org": ("Joined an organization", "#2E86DE"),
    "leave_org": ("Left an organization", "#7F8C8D"),
    "opportunity_cancelled": ("Event cancelled", "#C0392B"),
    "event_reminder": ("Event reminder", "#E67E22"),
    "opportunity_invite": ("Opportunity invitation", "#3D4BA8"),
}
DEFAULT_NOTIF = ("Update", "#7F8C8D")

# Database.addAnnouncement() also writes a notifications row (type
# 'announcement') for every recipient. Those are skipped here because the
# real announcement is already shown with its full text.
DUPLICATE_TYPES = {"announcement"}

FILTERS = (
    ("all", "All"),
    ("announcement", "Announcements"),
    ("activity", "Activity"),
)

EMPTY_TEXT = {
    "all": "Nothing here yet. Announcements from your organizations and "
           "updates about your events will show up here.",
    "announcement": "No announcements yet from the organizations you follow.",
    "activity": "No activity yet.",
}


# ── Date helpers ──────────────────────────────────────────────────────────
def _parse_dt(value):
    """created_at columns use SQLite's CURRENT_TIMESTAMP, which is UTC.
    Return it as naive local time so "Today" and the clock are right."""
    s = str(value or "").strip()
    if not s:
        return None
    try:
        utc = datetime.fromisoformat(s.replace("T", " ")[:19])
    except ValueError:
        return None
    return utc.replace(tzinfo=timezone.utc).astimezone().replace(tzinfo=None)


def _day_label(dt):
    if dt is None:
        return "Earlier"
    today = date.today()
    d = dt.date()
    if d == today:
        return "Today"
    if d == today - timedelta(days=1):
        return "Yesterday"
    label = f"{dt:%B} {dt.day}"
    return label if d.year == today.year else f"{label}, {d.year}"


def _when_label(dt, raw=""):
    if dt is None:
        return str(raw or "")[:16]
    clock = dt.strftime("%I:%M %p").lstrip("0")
    return f"{_day_label(dt)}, {clock}"


# ── Mixin ─────────────────────────────────────────────────────────────────
class VolunteerNotifications:

    def _build_notifications_page(self):
        page, self.notif_layout, top = self._scroll_page(
            "Notifications", spacing=8
        )
        self._notif_items = []
        self._notif_filter = "all"
        self._notif_btns = {}

        bar = QHBoxLayout()
        bar.setSpacing(6)
        group = QButtonGroup(self)
        group.setExclusive(True)
        for key, text in FILTERS:
            btn = QPushButton(text)
            btn.setObjectName(theme.VIEW_TOGGLE_BTN)
            btn.setCheckable(True)
            btn.setChecked(key == "all")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _, k=key: self._set_notif_filter(k))
            group.addButton(btn)
            bar.addWidget(btn)
            self._notif_btns[key] = (btn, text)
        bar.addStretch(1)
        self._mark_all_read_btn = QPushButton("Mark all as read")
        self._mark_all_read_btn.setObjectName(theme.MARK_ALL_READ_BTN)
        self._mark_all_read_btn.setCursor(
            Qt.CursorShape.PointingHandCursor
        )
        self._mark_all_read_btn.clicked.connect(
            self._mark_all_notifications_read
        )
        bar.addWidget(self._mark_all_read_btn)
        top.addLayout(bar)
        return page

    def _set_notif_filter(self, key):
        self._notif_filter = key
        self._render_notifications()

    def _refresh_notifications(self):
        if not (self.db and self.userID):
            return
        self._notif_items = self._load_feed_items()

        n_ann = sum(1 for i in self._notif_items if i["kind"] == "announcement")
        counts = {
            "all": len(self._notif_items),
            "announcement": n_ann,
            "activity": len(self._notif_items) - n_ann,
        }
        unread_count = sum(
            item.get("read") is False for item in self._notif_items
        )
        self._mark_all_read_btn.setVisible(unread_count > 0)
        for key, (btn, text) in self._notif_btns.items():
            btn.setText(f"{text} ({counts[key]})" if counts[key] else text)

        self._render_notifications()

    def _mark_all_notifications_read(self):
        if self._db_action("markNotificationsRead", self.userID):
            self.notificationsUpdated.emit()
            self._refresh_notifications()

    # ── Data ──────────────────────────────────────────────────────────
    def _load_feed_items(self):
        """Return announcements + activity as one list, newest first."""
        # Imported here, not at the top, to avoid a circular import
        # (volunteerHome imports this module).
        from Volunteer.volunteerHome import org_color, rget

        items = []
        notifications = self._db(
            "getNotifications", self.userID, default=[]
        ) or []
        announcement_states = {}
        for n in notifications:
            ntype = str(
                rget(n, "type", "") or rget(n, "notification_type", "") or ""
            )
            if ntype == "announcement":
                announcement_states.setdefault(
                    str(rget(n, "message", "") or ""), n
                )

        # 1) Announcements from every org the volunteer has joined or
        #    signed up with (the query lives in db.py).
        anns = self._db(
            "getAnnouncementsForVolunteer", self.userID, default=[]
        ) or []
        for a in anns:
            name = str(rget(a, "org_name", "") or "")
            raw = rget(a, "created_at", "")
            dt = _parse_dt(raw)
            title = str(rget(a, "title", "") or "Announcement")
            body = str(rget(a, "body", "") or "")
            preview = body[:120] + ("…" if len(body) > 120 else "")
            status = announcement_states.get(f"{title} — {preview}")
            items.append({
                "kind": "announcement",
                "title": title,
                "body": body,
                "org": name,
                "color": org_color(name),
                "pinned": bool(rget(a, "pinned", 0)),
                "dt": dt,
                "when": _when_label(dt, raw),
                "notification_id": (
                    rget(status, "notificationID") if status else None
                ),
                "read": (
                    bool(rget(status, "read_at")) if status else None
                ),
            })

        # 2) The volunteer's own activity notifications
        for n in notifications:
            ntype = str(
                rget(n, "type", "") or rget(n, "notification_type", "") or ""
            )
            if ntype in DUPLICATE_TYPES:
                continue
            title, color = NOTIF_TYPES.get(ntype, DEFAULT_NOTIF)
            raw = rget(n, "created_at", "")
            dt = _parse_dt(raw)
            items.append({
                "kind": "activity",
                "title": title,
                "body": str(rget(n, "message", "") or ""),
                "org": "",
                "color": color,
                "pinned": False,
                "dt": dt,
                "when": _when_label(dt, raw),
                "notification_type": ntype,
                "notification_id": rget(n, "notificationID"),
                "read": bool(rget(n, "read_at")),
                "invitation_id": rget(
                    n, "linked_invitationID"
                ),
                "invitation_status": rget(n, "invitation_status"),
                "opportunity_id": rget(
                    n, "related_opportunityID"
                ),
            })

        items.sort(key=lambda i: i["dt"] or datetime.min, reverse=True)
        return items

    # ── Rendering ─────────────────────────────────────────────────────
    def _render_notifications(self):
        self._clear(self.notif_layout)

        kind = self._notif_filter
        items = [
            i for i in self._notif_items
            if kind == "all" or i["kind"] == kind
        ]
        if not items:
            self._empty(self.notif_layout, EMPTY_TEXT[kind])
            return

        pinned = [i for i in items if i["pinned"]]
        rest = [i for i in items if not i["pinned"]]

        if pinned:
            self._add(self.notif_layout, self._notif_group_header("Pinned"))
            for i in pinned:
                self._add(self.notif_layout, self._make_notif_card(i))

        last_label = None
        for i in rest:
            label = _day_label(i["dt"])
            if label != last_label:
                self._add(self.notif_layout, self._notif_group_header(label))
                last_label = label
            self._add(self.notif_layout, self._make_notif_card(i))

    def _notif_group_header(self, text):
        lbl = QLabel(text.upper())
        lbl.setStyleSheet(
            "font-size: 11px; font-weight: bold; color: #6B5B77;"
            " padding-top: 8px;"
        )
        return lbl

    def _make_notif_card(self, item):
        card = QFrame()
        card.setObjectName(theme.EVENT_CARD)
        card.setStyleSheet(
            f"QFrame#{theme.EVENT_CARD} "
            f"{{ border-left: 6px solid {item['color']}; }}"
        )
        lay = QVBoxLayout(card)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(4)

        # Title row: title ........ [PINNED] timestamp
        head = QHBoxLayout()
        head.setSpacing(8)

        title = QLabel(item["title"])
        title.setObjectName(theme.EVENT_TITLE_LIST)
        title.setTextFormat(Qt.TextFormat.PlainText)
        title.setWordWrap(True)
        head.addWidget(title, 1)

        if item.get("read") is not None:
            state = QLabel("READ" if item["read"] else "UNREAD")
            state.setObjectName(
                theme.NOTIFICATION_READ
                if item["read"] else theme.NOTIFICATION_UNREAD
            )
            head.addWidget(state)

        if item["pinned"]:
            pin = QLabel("PINNED")
            pin.setObjectName(theme.EVENT_STATUS_BADGE)
            head.addWidget(pin)

        when = QLabel(item["when"])
        when.setObjectName("EventOrg")          # muted italic, from the QSS
        head.addWidget(when)
        lay.addLayout(head)

        if item.get("notification_id") and item.get("read") is False:
            mark_read = QPushButton("Mark as read")
            mark_read.setObjectName(theme.MARK_ALL_READ_BTN)
            mark_read.setCursor(Qt.CursorShape.PointingHandCursor)
            mark_read.clicked.connect(
                lambda _, i=item: self._mark_notification_read(i)
            )
            lay.addWidget(mark_read, 0, Qt.AlignmentFlag.AlignLeft)

        if item["org"]:
            org = QLabel(f"From {item['org']}")
            org.setObjectName("EventMetaKey")   # muted bold, from the QSS
            org.setTextFormat(Qt.TextFormat.PlainText)
            lay.addWidget(org)

        if item["body"]:
            body = QLabel(item["body"])
            body.setObjectName("EventDescription")  # regular weight
            # Plain text so an announcement containing "<b>" or "&" shows
            # exactly what the organizer typed.
            body.setTextFormat(Qt.TextFormat.PlainText)
            body.setWordWrap(True)
            body.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse
            )
            lay.addWidget(body)

        if item.get("notification_type") == "opportunity_invite":
            if item.get("invitation_id"):
                self._add_invitation_actions(lay, item)
            else:
                unavailable = QLabel(
                    "This invitation was sent before responses were "
                    "supported and is no longer available."
                )
                unavailable.setObjectName(theme.EVENT_META_VALUE)
                lay.addWidget(unavailable)

        return card

    def _mark_notification_read(self, item):
        if self._db_action(
            "markNotificationRead", self.userID, item["notification_id"]
        ):
            self.notificationsUpdated.emit()
            self._refresh_notifications()

    def _add_invitation_actions(self, layout, item):
        status = item.get("invitation_status")
        if status == "pending":
            row = QHBoxLayout()
            accept = QPushButton("Accept invitation")
            accept.setObjectName(theme.PRIMARY_BTN)
            accept.setCursor(Qt.CursorShape.PointingHandCursor)
            accept.clicked.connect(
                lambda: self._respond_to_invitation(item, True)
            )
            decline = QPushButton("Decline")
            decline.setObjectName(theme.SECONDARY_BTN)
            decline.setCursor(Qt.CursorShape.PointingHandCursor)
            decline.clicked.connect(
                lambda: self._respond_to_invitation(item, False)
            )
            row.addWidget(accept)
            row.addWidget(decline)
            row.addStretch(1)
            layout.addLayout(row)
            return

        status_text = {
            "accepted": "Invitation accepted — you're signed up.",
            "declined": "Invitation declined.",
        }.get(status, "This invitation is no longer available.")
        status_label = QLabel(status_text)
        status_label.setObjectName(theme.EVENT_META_VALUE)
        layout.addWidget(status_label)

    def _respond_to_invitation(self, item, accept):
        result = self.db.respondToOpportunityInvitation(
            self.userID, item["invitation_id"], accept
        )
        if result in ("accepted", "already_registered"):
            QMessageBox.information(
                self, "Invitation accepted",
                "You're signed up for the opportunity."
                if result == "accepted"
                else "You were already signed up. The invitation is now "
                     "marked as accepted.",
            )
            self._after_signup_change()
        elif result == "declined":
            QMessageBox.information(
                self, "Invitation declined",
                "You declined the invitation.",
            )
        elif result == "full":
            QMessageBox.warning(
                self, "Opportunity full",
                "There are no spots left. The invitation is still pending.",
            )
        elif result == "unavailable":
            QMessageBox.warning(
                self, "Opportunity unavailable",
                "This opportunity is no longer open.",
            )
        elif result in ("pending", "not_found"):
            QMessageBox.warning(
                self, "Invitation unavailable",
                "This invitation could not be updated. Refresh and try "
                "again.",
            )
        else:
            QMessageBox.warning(
                self, "Invitation error",
                "Could not update the invitation. Please try again.",
            )

        self.notificationsUpdated.emit()
        self._refresh_notifications()