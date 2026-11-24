"""
volunteerProfileDialog.py - One volunteer as seen by one org.

Opens from the roster (OrgVolunteersPage). Shows:
    - contact info (name, email, phone, location, skills)
    - aggregate stats (hours, signups, no-shows)
    - full history of this org's events with the volunteer
    - org-private notes and tags
    - ban / unban button

Org-private means: notes and ban flags are scoped to (orgID, userID).
A different org sees a different set of notes for the same volunteer.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QCursor
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
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
from Events.dateFormat import format_range, format_time_range


class VolunteerProfileDialog(QDialog):
    def __init__(self, db, org, user_id, parent=None):
        super().__init__(parent)
        self.db = db
        self.org = org
        self.user_id = user_id

        self.setObjectName(theme.EVENT_DETAILS_DIALOG)
        self.setWindowTitle("Volunteer profile")
        self.setModal(True)
        self.setMinimumWidth(640)
        self.setMinimumHeight(600)

        # Pull everything up front so the render methods stay simple.
        self.profile = self._db(
            "getVolunteerProfileForOrg",
            org["orgID"], user_id, default={},
        ) or {}
        self.history = self._db(
            "getVolunteerHistoryForOrg",
            org["orgID"], user_id, default=[],
        ) or []
        self.notes = self._db(
            "getVolunteerNotes",
            org["orgID"], user_id, default=[],
        ) or []

        self._build_ui()

    # ── Layout ─────────────────────────────────────────────────────
    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 24, 28, 24)
        outer.setSpacing(12)

        # ── Header ─────────────────────────────────────────────────
        name = " ".join(
            x for x in [self.profile.get("first_name"),
                        self.profile.get("last_name")] if x
        ) or "(no name)"
        title = QLabel(name)
        title.setObjectName(theme.EVENT_TITLE_LIST)
        outer.addWidget(title)

        contact_bits = [
            self.profile.get("email"),
            self.profile.get("phone"),
            self.profile.get("country"),
        ]
        contact_text = "  •  ".join(str(b) for b in contact_bits if b)
        if contact_text:
            contact = QLabel(contact_text)
            contact.setObjectName(theme.EVENT_META_VALUE)
            contact.setWordWrap(True)
            outer.addWidget(contact)

        if self.profile.get("skills"):
            skills = QLabel(f"Skills: {self.profile['skills']}")
            skills.setObjectName(theme.EVENT_META_VALUE)
            skills.setWordWrap(True)
            outer.addWidget(skills)

        if self.profile.get("banned"):
            banned_lbl = QLabel("This volunteer is banned from your org.")
            banned_lbl.setObjectName(theme.EVENT_STATUS_BADGE)
            banned_lbl.setWordWrap(True)
            outer.addWidget(banned_lbl)

        # ── Stats row ──────────────────────────────────────────────
        total_hours = sum(
            float(r["hours_logged"] or 0)
            for r in self.history if not r["no_show"]
        )
        signups = len(self.history)
        no_shows = sum(1 for r in self.history if r["no_show"])

        stats = QHBoxLayout()
        stats.setSpacing(10)
        for label, value in (
            ("Hours", f"{total_hours:.1f}"),
            ("Signups", str(signups)),
            ("No-shows", str(no_shows)),
        ):
            tile = QFrame()
            tile.setObjectName(theme.EVENT_CARD)
            tl = QVBoxLayout(tile)
            tl.setContentsMargins(14, 10, 14, 10)
            tl.setSpacing(2)
            val = QLabel(value)
            val.setStyleSheet("font-size: 22px; font-weight: bold;")
            cap = QLabel(label)
            cap.setObjectName(theme.EVENT_META_VALUE)
            tl.addWidget(val)
            tl.addWidget(cap)
            stats.addWidget(tile, 1)
        outer.addLayout(stats)

        # ── Two-column split: history on the left, notes on the right
        split = QHBoxLayout()
        split.setSpacing(12)

        # History column
        hist_col = QVBoxLayout()
        hist_col.setSpacing(6)
        hist_title = QLabel("Event history")
        hist_title.setObjectName(theme.EVENT_TITLE_LIST)
        hist_col.addWidget(hist_title)

        hist_scroll = QScrollArea()
        hist_scroll.setWidgetResizable(True)
        hist_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        hist_scroll.setObjectName(theme.DETAILS_SCROLL)

        hist_content = QWidget()
        self.hist_layout = QVBoxLayout(hist_content)
        self.hist_layout.setContentsMargins(0, 0, 0, 0)
        self.hist_layout.setSpacing(6)
        self.hist_layout.addStretch(1)
        hist_scroll.setWidget(hist_content)
        hist_col.addWidget(hist_scroll, 1)
        split.addLayout(hist_col, 3)

        # Notes column
        notes_col = QVBoxLayout()
        notes_col.setSpacing(6)
        notes_title = QLabel("Notes")
        notes_title.setObjectName(theme.EVENT_TITLE_LIST)
        notes_col.addWidget(notes_title)

        # Composer
        composer = QFrame()
        composer.setObjectName(theme.EVENT_CARD)
        cl = QVBoxLayout(composer)
        cl.setContentsMargins(12, 10, 12, 10)
        cl.setSpacing(6)

        self.note_input = QLineEdit()
        self.note_input.setPlaceholderText("Add a note…")
        self.note_input.returnPressed.connect(self._add_note)
        cl.addWidget(self.note_input)

        tag_row = QHBoxLayout()
        tag_row.setSpacing(6)
        self.tag_combo = QComboBox()
        self.tag_combo.setEditable(True)
        self.tag_combo.addItems([
            "",
            "Reliable",
            "First-timer",
            "Great with kids",
            "Spanish speaker",
            "Needs reminder",
            "Do not re-invite",
        ])
        tag_row.addWidget(self.tag_combo, 1)

        add_btn = QPushButton("Add")
        add_btn.setObjectName(theme.PRIMARY_BTN)
        add_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        add_btn.clicked.connect(self._add_note)
        tag_row.addWidget(add_btn)
        cl.addLayout(tag_row)
        notes_col.addWidget(composer)

        # Notes list
        notes_scroll = QScrollArea()
        notes_scroll.setWidgetResizable(True)
        notes_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        notes_scroll.setObjectName(theme.DETAILS_SCROLL)

        notes_content = QWidget()
        self.notes_layout = QVBoxLayout(notes_content)
        self.notes_layout.setContentsMargins(0, 0, 0, 0)
        self.notes_layout.setSpacing(6)
        self.notes_layout.addStretch(1)
        notes_scroll.setWidget(notes_content)
        notes_col.addWidget(notes_scroll, 1)
        split.addLayout(notes_col, 2)

        outer.addLayout(split, 1)

        # ── Footer actions ─────────────────────────────────────────
        footer = QHBoxLayout()
        footer.setSpacing(8)

        self.ban_btn = QPushButton(
            "Unban volunteer" if self.profile.get("banned")
            else "Ban volunteer"
        )
        self.ban_btn.setObjectName(theme.SECONDARY_BTN)
        self.ban_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.ban_btn.clicked.connect(self._toggle_ban)
        footer.addWidget(self.ban_btn)
        footer.addStretch(1)

        close_btn = QPushButton("Close")
        close_btn.setObjectName(theme.DETAILS_CLOSE_BTN)
        close_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        close_btn.clicked.connect(self.reject)
        footer.addWidget(close_btn)
        outer.addLayout(footer)

        self._render_history()
        self._render_notes()

    # ── History rendering ──────────────────────────────────────────
    def _render_history(self):
        self._clear(self.hist_layout)

        if not self.history:
            lbl = QLabel("No events with this org yet.")
            lbl.setObjectName(theme.VOLUNTEER_EMPTY)
            lbl.setWordWrap(True)
            self.hist_layout.insertWidget(0, lbl)
            return

        for r in self.history:
            self.hist_layout.insertWidget(
                self.hist_layout.count() - 1,
                self._make_history_row(r),
            )

    def _make_history_row(self, r):
        card = QFrame()
        card.setObjectName(theme.EVENT_CARD)

        # Left border colour encodes status, same convention as the
        # attendance dialog.
        if r["no_show"]:
            card.setStyleSheet(
                f"QFrame#{theme.EVENT_CARD} "
                "{ border-left: 6px solid #C0392B; }"
            )
        elif r["verified"]:
            card.setStyleSheet(
                f"QFrame#{theme.EVENT_CARD} "
                "{ border-left: 6px solid #27AE60; }"
            )
        elif r["check_out_time"]:
            card.setStyleSheet(
                f"QFrame#{theme.EVENT_CARD} "
                "{ border-left: 6px solid #E67E22; }"
            )

        lay = QVBoxLayout(card)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(2)

        title = QLabel(str(r["title"] or "Untitled event"))
        title.setObjectName(theme.EVENT_TITLE_LIST)
        title.setWordWrap(True)
        lay.addWidget(title)

        # Date line
        # Date line
        date = format_range(r["event_date"], r["event_end_date"])
        if not date:
            date = "TBD"

        bits = [date]
        time_txt = format_time_range(r["start_time"], r["end_time"])
        if time_txt:
            bits.append(time_txt)

        if r["no_show"]:
            bits.append("NO-SHOW")
        elif r["verified"]:
            bits.append(
                f"{float(r['hours_logged'] or 0):.1f} h · verified"
            )
        elif r["check_out_time"]:
            bits.append(
                f"{float(r['hours_logged'] or 0):.1f} h · pending"
            )
        elif r["check_in_time"]:
            bits.append("checked in")
        else:
            bits.append(str(r["status"] or "registered"))

        meta = QLabel("  •  ".join(bits))
        meta.setObjectName(theme.EVENT_META_VALUE)
        meta.setWordWrap(True)
        lay.addWidget(meta)

        if r["org_notes"]:
            n = QLabel(f"Note: {r['org_notes']}")
            n.setObjectName(theme.EVENT_META_VALUE)
            n.setWordWrap(True)
            lay.addWidget(n)

        return card

    # ── Notes rendering ────────────────────────────────────────────
    def _render_notes(self):
        self._clear(self.notes_layout)

        if not self.notes:
            lbl = QLabel("No notes yet.")
            lbl.setObjectName(theme.VOLUNTEER_EMPTY)
            lbl.setWordWrap(True)
            self.notes_layout.insertWidget(0, lbl)
            return

        for r in self.notes:
            self.notes_layout.insertWidget(
                self.notes_layout.count() - 1,
                self._make_note_row(r),
            )

    def _make_note_row(self, r):
        card = QFrame()
        card.setObjectName(theme.EVENT_CARD)
        lay = QHBoxLayout(card)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(6)

        col = QVBoxLayout()
        col.setSpacing(2)

        text = QLabel(str(r["note"] or ""))
        text.setWordWrap(True)
        col.addWidget(text)

        meta_bits = []
        if r["tag"]:
            meta_bits.append(str(r["tag"]))
        meta_bits.append(str(r["created_at"] or "")[:19])
        meta = QLabel("  •  ".join(b for b in meta_bits if b))
        meta.setObjectName(theme.EVENT_META_VALUE)
        meta.setWordWrap(True)
        col.addWidget(meta)
        lay.addLayout(col, 1)

        del_btn = QPushButton("✕")
        del_btn.setFixedSize(24, 24)
        del_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        del_btn.setToolTip("Delete note")
        del_btn.setStyleSheet(
            "QPushButton { border: none; background: transparent; }"
            "QPushButton:hover { background: rgba(127,127,127,40); "
            "border-radius: 12px; }"
        )
        del_btn.clicked.connect(
            lambda _, nid=r["noteID"]: self._delete_note(nid)
        )
        lay.addWidget(del_btn)
        return card

    # ── Actions ────────────────────────────────────────────────────
    def _add_note(self):
        text = self.note_input.text().strip()
        if not text:
            return
        tag = self.tag_combo.currentText().strip() or None

        ok = self._db(
            "addVolunteerNote",
            self.org["orgID"], self.user_id, text, tag,
            default=None,
        )
        if not ok:
            QMessageBox.warning(self, "Could not save",
                                "The note was not saved.")
            return

        self.note_input.clear()
        self.tag_combo.setCurrentIndex(0)
        self.notes = self._db(
            "getVolunteerNotes",
            self.org["orgID"], self.user_id, default=[],
        ) or []
        self._render_notes()

    def _delete_note(self, note_id):
        self._db("deleteVolunteerNote", note_id, default=False)
        self.notes = self._db(
            "getVolunteerNotes",
            self.org["orgID"], self.user_id, default=[],
        ) or []
        self._render_notes()

    def _toggle_ban(self):
        currently_banned = bool(self.profile.get("banned"))

        if currently_banned:
            prompt = "Allow this volunteer to sign up for your events again?"
            title = "Unban volunteer"
        else:
            prompt = ("Block this volunteer from signing up for your "
                      "events? Their past signups stay in your records.")
            title = "Ban volunteer"

        if QMessageBox.question(
            self, title, prompt
        ) != QMessageBox.StandardButton.Yes:
            return

        new_state = not currently_banned
        self._db(
            "setVolunteerBanned",
            self.org["orgID"], self.user_id, new_state,
            default=False,
        )
        self.profile["banned"] = 1 if new_state else 0
        self.ban_btn.setText(
            "Unban volunteer" if new_state else "Ban volunteer"
        )

    # ── Helpers ────────────────────────────────────────────────────
    def _db(self, method, *args, default=None):
        fn = getattr(self.db, method, None) if self.db else None
        if fn is None:
            print(f"Database.{method}() is not implemented yet")
            return default
        try:
            return fn(*args)
        except Exception as e:
            print(f"Database.{method}() failed:", e)
            return default

    def _clear(self, layout):
        """Remove every widget above the trailing stretch."""
        while layout.count() > 1:
            item = layout.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)
                w.deleteLater()
