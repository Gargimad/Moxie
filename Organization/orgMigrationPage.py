"""Organization roster import, profile editing, and volunteer invitations."""

import csv
import posixpath
import re
import xml.etree.ElementTree as ET
import zipfile
from datetime import date, timedelta

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

import Events.theme as theme
from Authentication.otp import (
    generate_activation_code,
    send_volunteer_activation_email,
)

PROFILE_FIELDS = (
    "first_name", "last_name", "country", "zipcode", "dob", "gender",
    "skills", "phone",
)
IMPORT_FIELDS = ("email",) + PROFILE_FIELDS
ORG_IMPORT_FIELDS = (
    "org_name", "org_description", "org_website", "org_city", "org_country",
)
ORG_FIELD_TO_PROFILE = {
    "org_name": "org_name",
    "org_description": "description",
    "org_website": "website_link",
    "org_city": "city",
    "org_country": "country",
}
TEMPLATE_FIELDS = IMPORT_FIELDS + (
    "organization_name", "organization_description",
    "organization_website", "organization_city", "organization_country",
)
FIELD_LABELS = {
    "email": "Email",
    "first_name": "First name",
    "last_name": "Last name",
    "country": "Country",
    "zipcode": "Postal code",
    "dob": "Date of birth",
    "gender": "Gender",
    "skills": "Skills",
    "phone": "Phone",
    "org_name": "Organization name",
    "org_description": "Organization description",
    "org_website": "Organization website",
    "org_city": "Organization city",
    "org_country": "Organization country",
}
ALIASES = {
    "email": {"email", "emailaddress", "e-mail"},
    "first_name": {"firstname", "givenname", "first"},
    "last_name": {"lastname", "surname", "familyname", "last"},
    "country": {"country"},
    "zipcode": {"zipcode", "postalcode", "postcode", "zip"},
    "dob": {"dob", "dateofbirth", "birthdate"},
    "gender": {"gender"},
    "skills": {"skills", "skill"},
    "phone": {"phone", "phonenumber", "mobile", "telephone"},
    "org_name": {"organizationname", "orgname"},
    "org_description": {"organizationdescription", "orgdescription"},
    "org_website": {"organizationwebsite", "orgwebsite"},
    "org_city": {"organizationcity", "orgcity"},
    "org_country": {"organizationcountry", "orgcountry"},
}
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
XLSX_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
DOC_REL_NS = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
)
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"


def _column_index(cell_ref):
    letters = re.match(r"[A-Z]+", cell_ref or "")
    if not letters:
        return None
    index = 0
    for char in letters.group():
        index = index * 26 + ord(char) - ord("A") + 1
    return index - 1


def _xlsx_rows(path):
    with zipfile.ZipFile(path) as book:
        if sum(info.file_size for info in book.infolist()) > 40_000_000:
            raise ValueError("The spreadsheet is too large to import.")

        workbook = ET.fromstring(book.read("xl/workbook.xml"))
        sheet = workbook.find(f".//{{{XLSX_NS}}}sheet")
        if sheet is None:
            raise ValueError("The workbook has no worksheets.")
        relation_id = sheet.attrib.get(f"{{{DOC_REL_NS}}}id")
        relationships = ET.fromstring(book.read("xl/_rels/workbook.xml.rels"))
        target = next(
            (rel.attrib["Target"] for rel in relationships.findall(
                f"{{{PKG_REL_NS}}}Relationship"
            ) if rel.attrib.get("Id") == relation_id),
            None,
        )
        if not target:
            raise ValueError("The first worksheet could not be opened.")
        sheet_path = (target.lstrip("/") if target.startswith("/")
                      else posixpath.normpath(posixpath.join("xl", target)))

        shared = []
        if "xl/sharedStrings.xml" in book.namelist():
            root = ET.fromstring(book.read("xl/sharedStrings.xml"))
            shared = [
                "".join(part.text or "" for part in item.iter(
                    f"{{{XLSX_NS}}}t"
                ))
                for item in root.findall(f"{{{XLSX_NS}}}si")
            ]

        root = ET.fromstring(book.read(sheet_path))
        all_rows = []
        for row in root.findall(f".//{{{XLSX_NS}}}sheetData/{{{XLSX_NS}}}row"):
            values = []
            for cell in row.findall(f"{{{XLSX_NS}}}c"):
                index = _column_index(cell.attrib.get("r"))
                if index is None:
                    continue
                while len(values) <= index:
                    values.append("")
                value = cell.find(f"{{{XLSX_NS}}}v")
                if cell.attrib.get("t") == "inlineStr":
                    text = "".join(part.text or "" for part in cell.iter(
                        f"{{{XLSX_NS}}}t"
                    ))
                elif value is None or value.text is None:
                    text = ""
                elif cell.attrib.get("t") == "s":
                    try:
                        text = shared[int(value.text)]
                    except (ValueError, IndexError):
                        text = ""
                else:
                    text = value.text
                values[index] = text
            all_rows.append(values)
        return all_rows


def read_roster_file(path):
    suffix = path.lower().rsplit(".", 1)[-1]
    if suffix == "csv":
        with open(path, "r", encoding="utf-8-sig", newline="") as source:
            rows = list(csv.reader(source))
    elif suffix == "xlsx":
        rows = _xlsx_rows(path)
    else:
        raise ValueError("Choose a .csv or .xlsx file.")

    if not rows:
        raise ValueError("The selected file is empty.")
    headers = {}
    for index, raw in enumerate(rows[0]):
        normalized = re.sub(r"[^a-z0-9]", "", str(raw).lower())
        for field, names in ALIASES.items():
            if normalized in names and field not in headers:
                headers[field] = index
    if "email" not in headers:
        raise ValueError("The first row must include an Email column.")

    parsed, seen = [], set()
    org_values = {field: set() for field in ORG_IMPORT_FIELDS}
    for row_number, values in enumerate(rows[1:], start=2):
        record = {
            field: (str(values[index]).strip()
                    if index < len(values) and values[index] is not None
                    else "")
            for field, index in headers.items()
        }
        for field in ORG_IMPORT_FIELDS:
            value = record.get(field, "").strip()
            if value:
                org_values[field].add(value)
        if re.fullmatch(r"\d+(?:\.\d+)?", record.get("dob", "")):
            serial = float(record["dob"])
            if 1 <= serial <= 100_000:
                record["dob"] = (
                    date(1899, 12, 30) + timedelta(days=int(serial))
                ).isoformat()
        if not any(
            record.get(field)
            for field in IMPORT_FIELDS + ORG_IMPORT_FIELDS
        ):
            continue
        record.setdefault("email", "")
        email = record["email"].strip().lower()
        record["email"] = email
        if not email and not any(
            record.get(field)
            for field in PROFILE_FIELDS
        ):
            continue
        issue = ""
        if not EMAIL_RE.match(email):
            issue = "Enter a valid email"
        elif email in seen:
            issue = "Duplicate email in file"
        seen.add(email)
        record["_row"] = row_number
        record["_issue"] = issue
        parsed.append(record)
    if not parsed:
        raise ValueError("No volunteer rows were found below the header.")

    org_fields = {}
    for field in ORG_IMPORT_FIELDS:
        values = org_values[field]
        if len(values) > 1:
            raise ValueError(
                f"Conflicting values found in the {FIELD_LABELS[field]} "
                "column. Use one organization value per file."
            )
        if values:
            org_fields[field] = values.pop()
    return parsed, org_fields


class InviteWorker(QThread):
    result = pyqtSignal(str, bool)

    def __init__(self, invites, organization_name, parent=None):
        super().__init__(parent)
        self.invites = invites
        self.organization_name = organization_name

    def run(self):
        for email, code in self.invites:
            sent = send_volunteer_activation_email(
                email, code, self.organization_name
            )
            self.result.emit(email, sent)


class VolunteerEditDialog(QDialog):
    def __init__(self, db, org_id, volunteer, parent=None):
        super().__init__(parent)
        self.db = db
        self.org_id = org_id
        self.volunteer = volunteer
        self.setWindowTitle("Edit volunteer profile")
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.fields = {}
        email = QLineEdit(str(volunteer.get("email") or ""))
        email.setReadOnly(True)
        form.addRow("Email", email)
        for key in PROFILE_FIELDS:
            field = QLineEdit(str(volunteer.get(key) or ""))
            self.fields[key] = field
            form.addRow(FIELD_LABELS[key], field)
        layout.addLayout(form)

        buttons = QHBoxLayout()
        cancel = QPushButton("Cancel")
        save = QPushButton("Save changes")
        save.setObjectName(theme.PRIMARY_BTN)
        buttons.addStretch(1)
        buttons.addWidget(cancel)
        buttons.addWidget(save)
        layout.addLayout(buttons)
        cancel.clicked.connect(self.reject)
        save.clicked.connect(self._save)

    def _save(self):
        fields = {key: widget.text().strip()
                  for key, widget in self.fields.items()}
        if not self.db.update_imported_volunteer_profile(
                self.org_id, self.volunteer["userID"], fields):
            QMessageBox.warning(
                self, "Save failed",
                "The volunteer profile could not be updated."
            )
            return
        self.accept()


class OrgMigrationPage(QWidget):
    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.org = None
        self._preview_rows = []
        self._pending_org_import = {}
        self._members = []
        self._worker = None
        self._invite_failures = 0

        outer = QVBoxLayout(self)
        outer.setContentsMargins(32, 18, 32, 18)
        outer.setSpacing(10)

        header = QHBoxLayout()
        title = QLabel("Data migration")
        title.setObjectName(theme.SECTION_TITLE)
        header.addWidget(title)
        header.addStretch(1)
        template_btn = QPushButton("Download CSV template")
        template_btn.setObjectName(theme.SECONDARY_BTN)
        template_btn.clicked.connect(self._save_template)
        header.addWidget(template_btn)
        outer.addLayout(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setObjectName(theme.HOME_SCROLL)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        org_card = QFrame()
        org_card.setObjectName(theme.EVENT_CARD)
        org_layout = QVBoxLayout(org_card)
        org_layout.addWidget(self._section_title("Organization profile"))
        org_layout.addWidget(self._section_text(
            "Review or update the organization details shown to volunteers."
        ))
        org_form = QFormLayout()
        self.org_fields = {
            "org_name": QLineEdit(),
            "description": QTextEdit(),
            "website_link": QLineEdit(),
            "city": QLineEdit(),
            "country": QLineEdit(),
        }
        self.org_fields["description"].setFixedHeight(68)
        for field, widget in self.org_fields.items():
            org_form.addRow({
                "org_name": "Name",
                "description": "Description",
                "website_link": "Website",
                "city": "City",
                "country": "Country",
            }[field], widget)
        org_layout.addLayout(org_form)
        save_org = QPushButton("Save organization details")
        save_org.setObjectName(theme.PRIMARY_BTN)
        save_org.clicked.connect(self._save_organization)
        org_layout.addWidget(save_org, 0, Qt.AlignmentFlag.AlignRight)
        layout.addWidget(org_card)

        upload_card = QFrame()
        upload_card.setObjectName(theme.EVENT_CARD)
        upload_layout = QVBoxLayout(upload_card)
        upload_layout.addWidget(self._section_title("Import volunteer roster"))
        upload_layout.addWidget(self._section_text(
            "Import a CSV or Excel .xlsx roster. Email is required; "
            "recognized profile columns are optional. New volunteers "
            "receive a one-time activation code by email and choose their "
            "own password in Moxie. Excel imports use the first worksheet. "
            "Optional organization_name, organization_description, "
            "organization_website, organization_city, and "
            "organization_country columns update this organization."
        ))
        file_row = QHBoxLayout()
        self.file_label = QLabel("No roster selected")
        self.file_label.setObjectName(theme.EVENT_META_VALUE)
        choose_file = QPushButton("Choose file")
        choose_file.setObjectName(theme.SECONDARY_BTN)
        choose_file.clicked.connect(self._choose_file)
        file_row.addWidget(self.file_label, 1)
        file_row.addWidget(choose_file)
        upload_layout.addLayout(file_row)

        self.preview = QTableWidget(0, 4)
        self.preview.setHorizontalHeaderLabels(
            ["Name", "Email", "Phone", "Import status"]
        )
        self.preview.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.preview.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.preview.setMaximumHeight(210)
        upload_layout.addWidget(self.preview)

        import_row = QHBoxLayout()
        self.import_status = QLabel("")
        self.import_status.setObjectName(theme.EVENT_META_VALUE)
        self.import_btn = QPushButton("Import roster and send invitations")
        self.import_btn.setObjectName(theme.PRIMARY_BTN)
        self.import_btn.setEnabled(False)
        self.import_btn.clicked.connect(self._import_roster)
        import_row.addWidget(self.import_status, 1)
        import_row.addWidget(self.import_btn)
        upload_layout.addLayout(import_row)
        layout.addWidget(upload_card)

        roster_card = QFrame()
        roster_card.setObjectName(theme.EVENT_CARD)
        roster_layout = QVBoxLayout(roster_card)
        roster_header = QHBoxLayout()
        roster_header.addWidget(self._section_title("Organization volunteers"))
        roster_header.addStretch(1)
        self.resend_btn = QPushButton("Resend selected invitation")
        self.resend_btn.setObjectName(theme.SECONDARY_BTN)
        self.resend_btn.clicked.connect(self._resend_selected)
        roster_header.addWidget(self.resend_btn)
        roster_layout.addLayout(roster_header)
        roster_layout.addWidget(self._section_text(
            "Double-click a volunteer to edit their imported profile. "
            "Only pending accounts can receive a new activation code."
        ))
        self.roster = QTableWidget(0, 4)
        self.roster.setHorizontalHeaderLabels(
            ["Name", "Email", "Phone", "Account"]
        )
        self.roster.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.roster.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.roster.setSelectionMode(
            QTableWidget.SelectionMode.SingleSelection
        )
        self.roster.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.roster.doubleClicked.connect(self._edit_selected)
        roster_layout.addWidget(self.roster)
        layout.addWidget(roster_card)

        layout.addStretch(1)
        scroll.setWidget(content)
        outer.addWidget(scroll, 1)

    @staticmethod
    def _section_title(text):
        label = QLabel(text)
        label.setObjectName(theme.EVENT_TITLE_LIST)
        return label

    @staticmethod
    def _section_text(text):
        label = QLabel(text)
        label.setObjectName(theme.EVENT_META_VALUE)
        label.setWordWrap(True)
        return label

    def set_org_data(self, org):
        self.org = org
        for key, field in self.org_fields.items():
            value = str(org.get(key) or "")
            if isinstance(field, QTextEdit):
                field.setPlainText(value)
            else:
                field.setText(value)
        self.refresh()

    def refresh(self):
        if not self.org:
            return
        self._members = self.db.get_migrated_volunteers(self.org["orgID"])
        self.roster.setRowCount(len(self._members))
        for index, volunteer in enumerate(self._members):
            name = " ".join(
                part for part in (volunteer.get("first_name"),
                                  volunteer.get("last_name")) if part
            ) or "(no name)"
            status = ("Active" if volunteer["email_verified"]
                      else "Pending activation")
            for column, value in enumerate((
                    name, volunteer["email"], volunteer.get("phone") or "",
                    status)):
                item = QTableWidgetItem(str(value or ""))
                item.setData(Qt.ItemDataRole.UserRole, index)
                self.roster.setItem(index, column, item)

    def _save_organization(self):
        if not self.org:
            return
        fields = {}
        for key, widget in self.org_fields.items():
            fields[key] = (widget.toPlainText().strip()
                           if isinstance(widget, QTextEdit)
                           else widget.text().strip())
        if not fields["org_name"]:
            QMessageBox.warning(
                self, "Organization name required",
                "Enter an organization name before saving."
            )
            return
        if not self.db.update_organization_profile(
                self.org["userID"], self.org["orgID"], fields):
            QMessageBox.warning(
                self, "Save failed",
                "The organization profile could not be updated."
            )
            return
        self.org.update(fields)
        QMessageBox.information(
            self, "Organization updated",
            "Organization details have been saved."
        )

    def _save_template(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Save roster template", "volunteer_roster_template.csv",
            "CSV files (*.csv)",
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8-sig", newline="") as output:
                writer = csv.writer(output)
                writer.writerow(TEMPLATE_FIELDS)
                writer.writerow([
                    "volunteer@example.com", "Jordan", "Lee", "Canada",
                    "M5V 2T6", "2000-01-15", "", "Food bank", "555-0100",
                    self.org.get("org_name", "") if self.org else "",
                    self.org.get("description", "") if self.org else "",
                    self.org.get("website_link", "") if self.org else "",
                    self.org.get("city", "") if self.org else "",
                    self.org.get("country", "") if self.org else "",
                ])
        except OSError as e:
            QMessageBox.warning(self, "Could not save template", str(e))

    def _choose_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose volunteer roster", "",
            "Roster files (*.csv *.xlsx);;CSV files (*.csv);;"
            "Excel workbooks (*.xlsx)",
        )
        if not path:
            return
        try:
            rows, org_fields = read_roster_file(path)
        except (OSError, ValueError, KeyError,
                zipfile.BadZipFile, ET.ParseError) as e:
            QMessageBox.warning(self, "Could not read roster", str(e))
            return
        self.file_label.setText(path.rsplit("\\", 1)[-1])
        self._pending_org_import = org_fields
        for key, widget in self.org_fields.items():
            value = str(self.org.get(key) or "") if self.org else ""
            if isinstance(widget, QTextEdit):
                widget.setPlainText(value)
            else:
                widget.setText(value)
        for key, value in org_fields.items():
            widget = self.org_fields[ORG_FIELD_TO_PROFILE[key]]
            if isinstance(widget, QTextEdit):
                widget.setPlainText(value)
            else:
                widget.setText(value)
        self._preview_rows = [row for row in rows if not row["_issue"]]
        self.preview.setRowCount(len(rows))
        for index, row in enumerate(rows):
            name = " ".join(x for x in (
                row.get("first_name", ""), row.get("last_name", "")
            ) if x) or "(no name)"
            status = row["_issue"] or "Ready"
            for column, value in enumerate((
                    name, row.get("email", ""), row.get("phone", ""), status)):
                self.preview.setItem(
                    index, column, QTableWidgetItem(str(value))
                )
        status = (
            f"{len(self._preview_rows)} ready; "
            f"{len(rows) - len(self._preview_rows)} need correction."
        )
        if org_fields:
            status += " Organization details will be updated."
        self.import_status.setText(status)
        self.import_btn.setEnabled(bool(self._preview_rows))

    def _import_roster(self):
        if not self.org or not self._preview_rows:
            return
        answer = QMessageBox.question(
            self, "Import volunteers",
            f"Create pending accounts for up to {len(self._preview_rows)} "
            "new volunteers? Existing account emails will be skipped.",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        records = []
        codes = {}
        for row in self._preview_rows:
            code = generate_activation_code()
            record = {field: row.get(field, "") for field in IMPORT_FIELDS}
            record["activation_code"] = code
            records.append(record)
            codes[record["email"]] = code

        result = self.db.import_volunteer_roster(self.org["orgID"], records)
        if result is None:
            QMessageBox.critical(
                self, "Import failed",
                "The roster could not be imported. No accounts were added."
            )
            return
        org_update_failed = False
        if self._pending_org_import:
            org_profile = {
                ORG_FIELD_TO_PROFILE[key]: self.org_fields[
                    ORG_FIELD_TO_PROFILE[key]
                ].toPlainText().strip()
                if isinstance(self.org_fields[ORG_FIELD_TO_PROFILE[key]],
                              QTextEdit)
                else self.org_fields[ORG_FIELD_TO_PROFILE[key]].text().strip()
                for key in self._pending_org_import
            }
            if self.db.update_organization_profile(
                    self.org["userID"], self.org["orgID"], org_profile):
                self.org.update(org_profile)
            else:
                org_update_failed = True
        imported = result["imported"]
        invites = [(row["email"], codes[row["email"]]) for row in imported]
        self.import_btn.setEnabled(False)
        if invites:
            self.import_status.setText(
                f"Created {len(imported)}; skipped {len(result['skipped'])}. "
                "Sending invitations…" +
                (" Organization details could not be saved."
                 if org_update_failed else "")
            )
            self._start_invites(invites)
        else:
            self.import_status.setText(
                f"Created 0; skipped {len(result['skipped'])}. "
                "No new accounts needed invitations." +
                (" Organization details could not be saved."
                 if org_update_failed else "")
            )
            self.import_btn.setEnabled(bool(self._preview_rows))
        self.refresh()

    def _start_invites(self, invites):
        if not invites:
            return
        if self._worker and self._worker.isRunning():
            QMessageBox.information(
                self, "Invitations already sending",
                "Wait for the current invitation batch to finish."
            )
            return
        self._invite_failures = 0
        self.import_btn.setEnabled(False)
        self.resend_btn.setEnabled(False)
        self._worker = InviteWorker(
            invites, self.org.get("org_name") or "Your organization", self
        )
        self._worker.result.connect(self._on_invite_result)
        self._worker.finished.connect(self._on_invites_finished)
        self._worker.start()

    def _on_invite_result(self, email, sent):
        if not sent:
            self._invite_failures += 1

    def _on_invites_finished(self):
        total = len(self._worker.invites) if self._worker else 0
        sent = total - self._invite_failures
        self.import_status.setText(
            f"Invitations sent: {sent}; failed: {self._invite_failures}. "
            "Resend failed invitations from the roster."
        )
        self._worker = None
        self.import_btn.setEnabled(bool(self._preview_rows))
        self.resend_btn.setEnabled(True)
        self.refresh()

    def _selected_volunteer(self):
        row = self.roster.currentRow()
        return self._members[row] if 0 <= row < len(self._members) else None

    def _edit_selected(self, *_):
        volunteer = self._selected_volunteer()
        if not volunteer:
            return
        dialog = VolunteerEditDialog(
            self.db, self.org["orgID"], volunteer, self
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.refresh()

    def _resend_selected(self):
        if self._worker and self._worker.isRunning():
            return
        volunteer = self._selected_volunteer()
        if not volunteer:
            QMessageBox.information(
                self, "Select a volunteer",
                "Select a volunteer from the roster first."
            )
            return
        if volunteer["email_verified"]:
            QMessageBox.information(
                self, "Account already active",
                "This volunteer has already activated their account."
            )
            return
        code = generate_activation_code()
        if not self.db.set_volunteer_activation_code(
                self.org["orgID"], volunteer["userID"], code):
            QMessageBox.warning(
                self, "Invitation unavailable",
                "A new activation code could not be created."
            )
            return
        self._start_invites([(volunteer["email"], code)])
