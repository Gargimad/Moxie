"""
orgRecommendationsPage.py — AI-ranked volunteer recruitment.

For each open opportunity, shows the top matching volunteers with
avatar, match score, shared career clusters, and an inline Invite
button. Rows are styled like a clean admin table.
"""
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QCursor
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea,
    QFrame, QMessageBox,
)

import Events.theme as theme
from Events.dateFormat import format_event_when


def _initials(first, last, email):
    f = (first or "").strip()[:1]
    l = (last or "").strip()[:1]
    if f or l:
        return (f + l).upper()
    e = (email or "?").strip()
    return e[:1].upper()


class OrgRecommendationsPage(QWidget):
    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.setObjectName(theme.ORG_DASHBOARD)
        self.db = db
        self.org = None

        v = QVBoxLayout(self)
        v.setContentsMargins(40, 24, 40, 24)
        v.setSpacing(14)

        heading = QLabel("Recommended volunteers")
        heading.setObjectName(theme.SECTION_TITLE)
        v.addWidget(heading)

        sub = QLabel(
            "For each open event, Moxie ranks volunteers by career "
            "cluster match, city, and past signups with your org. "
            "Send an invite with one click."
        )
        sub.setObjectName(theme.EVENT_META_VALUE)
        sub.setWordWrap(True)
        v.addWidget(sub)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setObjectName(theme.HOME_SCROLL)
        content = QWidget()
        self.list_layout = QVBoxLayout(content)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.list_layout.setSpacing(18)
        self.list_layout.addStretch(1)
        scroll.setWidget(content)
        v.addWidget(scroll, 1)

    def set_org(self, org):
        self.org = org

    def refresh(self):
        if not self.org:
            return
        while self.list_layout.count() > 1:
            item = self.list_layout.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)
                w.deleteLater()

        rows = self.db.getOpportunitiesByOrg(self.org["orgID"]) or []
        rows = [r for r in rows if (r["status"] or "open") == "open"]

        if not rows:
            empty = QLabel(
                "No open opportunities to recruit for yet. Post one "
                "and it will appear here with its top matches."
            )
            empty.setObjectName(theme.VOLUNTEER_EMPTY)
            empty.setWordWrap(True)
            self.list_layout.insertWidget(0, empty)
            return

        for r in rows:
            self.list_layout.insertWidget(
                self.list_layout.count() - 1,
                self._make_opportunity_block(r),
            )

    # ── Opportunity block ──────────────────────────────────────────
    def _make_opportunity_block(self, opp):
        wrapper = QFrame()
        wrapper.setObjectName("OrgRecBlock")
        v = QVBoxLayout(wrapper)
        v.setContentsMargins(22, 18, 22, 18)
        v.setSpacing(12)

        # Header: title + event metadata + cluster chips
        head = QHBoxLayout()
        head.setSpacing(10)

        col = QVBoxLayout()
        col.setSpacing(2)
        title = QLabel(opp["title"] or "Untitled event")
        title.setObjectName(theme.EVENT_TITLE_LIST)
        col.addWidget(title)
        meta = QLabel(format_event_when(opp))
        meta.setObjectName("OrgRowSub")
        col.addWidget(meta)
        head.addLayout(col, 1)

        clusters = self.db.getOpportunityClusters(
            opp["opportunityID"]
        ) or []
        chip_row = QHBoxLayout()
        chip_row.setSpacing(6)
        for name in clusters[:3]:
            chip = QLabel(name)
            chip.setObjectName(theme.EVENT_LOCATION_BADGE)
            chip_row.addWidget(chip)
        chip_row.addStretch(1)
        head.addLayout(chip_row)

        v.addLayout(head)

        # Divider
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setObjectName("OrgRecDivider")
        line.setFixedHeight(1)
        v.addWidget(line)

        # Matches
        matches = self.db.getRecommendedVolunteersForOpportunity(
            opp["opportunityID"], limit=8
        )

        if matches:
            # Table-style header row
            header = QWidget()
            header.setObjectName("OrgRecTableHeader")
            hl = QHBoxLayout(header)
            hl.setContentsMargins(12, 6, 12, 6)
            hl.setSpacing(12)
            hl.addWidget(self._col_label("Volunteer", 0))
            hl.addStretch(2)
            hl.addWidget(self._col_label("Match", 0))
            hl.addStretch(1)
            hl.addWidget(self._col_label("Why", 0))
            hl.addStretch(2)
            hl.addWidget(self._col_label("", 0))
            v.addWidget(header)

            for entry in matches:
                v.addWidget(self._make_volunteer_row(entry, opp))
        else:
            none = QLabel(
                "No close matches yet — tag this event with a few "
                "career clusters and volunteers whose profiles overlap "
                "will show up here."
            )
            none.setObjectName(theme.VOLUNTEER_EMPTY)
            none.setWordWrap(True)
            v.addWidget(none)

        all_volunteers = self.db.getAvailableVolunteersForOpportunity(
            self.org["orgID"], opp["opportunityID"]
        ) or []
        all_volunteers = [dict(volunteer) for volunteer in all_volunteers]
        recommended_ids = {
            entry["volunteer"]["userID"] for entry in matches
        }
        other_volunteers = [
            volunteer for volunteer in all_volunteers
            if volunteer["userID"] not in recommended_ids
        ]

        all_heading = QLabel("All other volunteers")
        all_heading.setObjectName(theme.MATCH_STEP_TITLE)
        v.addWidget(all_heading)
        all_subtitle = QLabel(
            "Browse every other volunteer registered in Moxie who is "
            "available to invite to this opportunity."
        )
        all_subtitle.setObjectName(theme.EVENT_META_VALUE)
        all_subtitle.setWordWrap(True)
        v.addWidget(all_subtitle)

        if not other_volunteers:
            none = QLabel("No other volunteers are currently available.")
            none.setObjectName(theme.VOLUNTEER_EMPTY)
            v.addWidget(none)
        else:
            for volunteer in other_volunteers:
                v.addWidget(self._make_volunteer_row(
                    {"volunteer": volunteer}, opp, show_match=False
                ))

        return wrapper

    @staticmethod
    def _col_label(text, stretch):
        lbl = QLabel(text)
        lbl.setObjectName("OrgRecColLabel")
        return lbl

    # ── Volunteer row ──────────────────────────────────────────────
    def _make_volunteer_row(self, entry, opp, show_match=True):
        vol = entry["volunteer"]
        name = " ".join(
            x for x in (vol.get("first_name"), vol.get("last_name"))
            if x
        ) or vol.get("email", "Volunteer")
        initials = _initials(
            vol.get("first_name"), vol.get("last_name"),
            vol.get("email")
        )

        row = QFrame()
        row.setObjectName("OrgRecRow")
        h = QHBoxLayout(row)
        h.setContentsMargins(12, 10, 12, 10)
        h.setSpacing(14)

        # Avatar (letter in a circle)
        avatar = QLabel(initials)
        avatar.setObjectName("OrgRecAvatar")
        avatar.setFixedSize(38, 38)
        avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        h.addWidget(avatar)

        # Name + location block
        name_col = QVBoxLayout()
        name_col.setSpacing(2)
        n = QLabel(name)
        n.setObjectName("OrgRecName")
        name_col.addWidget(n)
        bits = []
        if vol.get("city"):
            bits.append(vol["city"])
        if vol.get("state"):
            bits.append(vol["state"])
        if vol.get("high_school"):
            bits.append(vol["high_school"])
        if bits:
            sub = QLabel(" · ".join(bits))
            sub.setObjectName("OrgRecSub")
            name_col.addWidget(sub)
        h.addLayout(name_col, 3)

        if show_match:
            # Match % badge
            score = int(round(min(1.0, entry["score"] / 6.0) * 100))
            score_lbl = QLabel(f"{score}%")
            score_lbl.setObjectName("OrgRecScore")
            score_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            score_lbl.setFixedWidth(56)
            h.addWidget(score_lbl, 0)

            # Reason chips
            reason_col = QVBoxLayout()
            reason_col.setSpacing(2)
            if entry["shared_clusters"]:
                r = QLabel("Match: " + ", ".join(entry["shared_clusters"]))
                r.setObjectName("OrgRecReason")
                r.setWordWrap(True)
                reason_col.addWidget(r)
            past = vol.get("past_with_org") or 0
            if past:
                p = QLabel(
                    f"{past} event{'s' if past != 1 else ''} with you"
                )
                p.setObjectName("OrgRecReason")
                reason_col.addWidget(p)
            h.addLayout(reason_col, 3)
        else:
            h.addStretch(1)

        # Invite button
        invite = QPushButton("Invite")
        invite.setObjectName(theme.PRIMARY_BTN)
        invite.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        invite.setFixedWidth(90)
        invite.clicked.connect(
            lambda _, v=vol, o=opp: self._invite(v, o)
        )
        h.addWidget(invite)

        return row

    def _invite(self, volunteer, opportunity):
        if not self.org:
            QMessageBox.warning(
                self, "Invite failed",
                "Select an organization before sending an invitation.",
            )
            return

        uid = volunteer["userID"]
        oid = opportunity["opportunityID"]
        result = self.db.createOpportunityInvitation(
            self.org["orgID"], uid, oid
        )
        if result == "sent":
            QMessageBox.information(
                self, "Invitation sent",
                f"Sent an invitation to "
                f"{volunteer.get('email', 'the volunteer')}.",
            )
        elif result in ("pending", "accepted"):
            QMessageBox.information(
                self, "Invitation already sent",
                "This volunteer already has an invitation for this "
                "opportunity.",
            )
        elif result == "already_registered":
            QMessageBox.information(
                self, "Already signed up",
                "This volunteer is already signed up for the opportunity.",
            )
        elif result == "full":
            QMessageBox.warning(
                self, "Opportunity full",
                "There are no spots left for this opportunity.",
            )
        elif result == "unavailable":
            QMessageBox.warning(
                self, "Opportunity unavailable",
                "This opportunity is no longer open.",
            )
        elif result == "invalid_volunteer":
            QMessageBox.warning(
                self, "Invite failed",
                "The selected account is not an active volunteer account.",
            )
        else:
            QMessageBox.warning(
                self, "Invite failed",
                "Could not send this invitation. Please try again.",
            )