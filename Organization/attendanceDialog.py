"""Organizer attendance and verified-hours controls for one opportunity."""

import sqlite3

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDoubleSpinBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

import Events.theme as theme


class AttendanceDialog(QDialog):
    def __init__(self, db, org, opportunity, parent=None):
        super().__init__(parent)
        self.db = db
        self.org = org
        self.opportunity = opportunity
        self.setWindowTitle(f"Attendance - {opportunity['title']}")
        self.setMinimumSize(760, 420)

        layout = QVBoxLayout(self)
        heading = QLabel(f"Attendance: {opportunity['title']}")
        heading.setObjectName(theme.EVENT_TITLE_LIST)
        layout.addWidget(heading)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            ["Volunteer", "Attendance", "Hours", "No-show", "Actions"]
        )
        self.table.setAccessibleName("Event attendance and hours")
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        layout.addWidget(self.table)
        self.empty_label = QLabel(
            "No volunteers are registered for this event.")
        self.empty_label.setObjectName(theme.VOLUNTEER_EMPTY)
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.empty_label)

        close_btn = QPushButton("Close")
        close_btn.setObjectName(theme.SECONDARY_BTN)
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn, 0, Qt.AlignmentFlag.AlignRight)
        self._refresh()

    def _refresh(self):
        try:
            rows = self.db.get_signups_for_opportunity_detailed(
                self.opportunity["opportunityID"]
            )
        except sqlite3.Error as exc:
            QMessageBox.warning(
                self, "Attendance unavailable",
                f"Could not load the event roster:\n{exc}",
            )
            return

        self.table.setRowCount(len(rows))
        self.table.setVisible(bool(rows))
        self.empty_label.setVisible(not rows)
        for index, signup in enumerate(rows):
            name = " ".join(
                value for value in
                (signup["first_name"], signup["last_name"]) if value
            ) or signup["email"] or "Volunteer"
            self.table.setItem(index, 0, QTableWidgetItem(name))

            if signup["no_show"]:
                attendance = "Marked no-show"
            elif signup["check_out_time"]:
                attendance = f"Checked out {signup['check_out_time'][:16]}"
            elif signup["check_in_time"]:
                attendance = f"Checked in {signup['check_in_time'][:16]}"
            else:
                attendance = "Not checked in"
            self.table.setItem(index, 1, QTableWidgetItem(attendance))

            hours = QDoubleSpinBox()
            hours.setRange(0, 10000)
            hours.setDecimals(2)
            hours.setSuffix(" h")
            hours.setValue(float(signup["hours_logged"] or 0))
            hours.setAccessibleName(f"Verified hours for {name}")
            self.table.setCellWidget(index, 2, hours)

            no_show = QCheckBox()
            no_show.setChecked(bool(signup["no_show"]))
            no_show.setEnabled(not bool(
                signup["verified"] or signup["check_in_time"]
            ))
            no_show.setAccessibleName(f"Mark {name} as a no-show")
            no_show.toggled.connect(
                lambda checked, sid=signup["signupID"],
                verified=bool(signup["verified"]):
                    self._set_no_show(sid, checked, verified)
            )
            self.table.setCellWidget(index, 3, no_show)

            actions_widget = QWidget()
            actions = QHBoxLayout(actions_widget)
            actions.setContentsMargins(4, 0, 4, 0)
            if not signup["check_in_time"] and not signup["no_show"]:
                check_in = QPushButton("Check in")
                check_in.clicked.connect(
                    lambda _, uid=signup["userID"]:
                        self._check_in(uid)
                )
                actions.addWidget(check_in)
            elif signup["check_in_time"] and not signup["check_out_time"]:
                check_out = QPushButton("Check out")
                check_out.clicked.connect(
                    lambda _, uid=signup["userID"]:
                        self._check_out(uid)
                )
                actions.addWidget(check_out)

            if signup["verified"]:
                verify = QPushButton("Undo verification")
                verify.clicked.connect(
                    lambda _, sid=signup["signupID"]:
                        self._unverify(sid)
                )
            else:
                verify = QPushButton("Verify hours")
                verify.setEnabled(not bool(signup["no_show"]))
                verify.clicked.connect(
                    lambda _, sid=signup["signupID"], spin=hours:
                        self._verify(sid, spin.value())
                )
            verify.setObjectName(theme.SECONDARY_BTN)
            actions.addWidget(verify)
            actions.addStretch(1)
            self.table.setCellWidget(index, 4, actions_widget)

    def _run(self, action, *args):
        try:
            if not action(*args):
                QMessageBox.warning(
                    self, "Update failed",
                    "The attendance record could not be updated.",
                )
                return False
        except sqlite3.Error as exc:
            QMessageBox.warning(
                self, "Update failed", f"Could not update attendance:\n{exc}"
            )
            return False
        self._refresh()
        return True

    def _check_in(self, user_id):
        self._run(self.db.check_in, user_id, self.opportunity["opportunityID"])

    def _check_out(self, user_id):
        self._run(
            self.db.check_out,
            user_id,
            self.opportunity["opportunityID"],
        )

    def _verify(self, signup_id, hours):
        try:
            verified_by = self.org["userID"]
        except (KeyError, IndexError, TypeError):
            verified_by = None
        self._run(self.db.verify_signup_hours, signup_id, verified_by, hours)

    def _unverify(self, signup_id):
        self._run(self.db.unverify_signup, signup_id)

    def _set_no_show(self, signup_id, no_show, verified):
        if no_show and verified:
            self._refresh()
            QMessageBox.information(
                self, "Hours already verified",
                "Undo hour verification before marking this volunteer "
                "as a no-show.",
            )
            return
        self._run(self.db.set_signup_no_show, signup_id, no_show)
