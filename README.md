# Moxie

Moxie is a local-first desktop app for volunteers and nonprofit
organizations. It is built with Python, PyQt6, and SQLite.

## Features

### Volunteers

Volunteers can do the following actions
- Browse, search, and filter volunteer opportunities; RSVP and manage
  signups.
- Check in and out of events and view recorded hours and notifications.
- Get content-based opportunity recommendations. Matching considers
  profile information and past activity; explanations can include shared
  skills, a country match, or a remote-friendly event.
- Export volunteer hour records as CSV or PDF.

### Organizations

- Create and manage opportunities, review signups, and track attendance.
- Check volunteers in or out, record hours, verify hours, and mark
  no-shows.
- Browse volunteer history and maintain organization-specific notes and
  tags.
- Review reports by volunteer or opportunity, filter by date, and export
  detailed CSV data.
- View volunteer recommendations based on career-cluster overlap, event
  city, and prior signups with the organization. These are separate from
  volunteer-side opportunity recommendations.
- Import a volunteer roster using a CSV
  template. The first worksheet is used for Excel files. An email column
  is required; volunteer and organization profile fields are optional.
  Existing accounts and duplicate emails in an import are skipped.

### Account activation and email

When email is configured, imported volunteers receive an eight-digit
activation code and set their own password in Moxie. Activation codes
expire after 24 hours and are limited to five attempts. Email sending
uses Gmail SMTP and requires a Gmail app password configured through
environment variables:

```text
SENDER_EMAIL=your-sender@gmail.com
SENDER_PASSWORD=your-gmail-app-password
DISPLAY_NAME=Moxie
```

`DISPLAY_NAME` is optional. Put these settings in a local `.env` file or
provide them through the environment. Do not commit credentials.

## Run from source

Use Python 3.11 for the development setup. Create and activate a virtual
environment from the repository root, then install the app's direct
dependencies and start it:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install PyQt6 scikit-learn python-dotenv SpeechRecognition
python main.py
```

This repository does not currently include a pinned dependency file, so
these package versions are not locked. Microphone input additionally
requires a working audio input and PyAudio. To render event QR images,
install `qrcode[pil]`.

## Data and limitations

- The app uses a local SQLite database at `Volunteer.db` in the
  repository. If the database is absent, the app creates it on startup.
  The database is not a shared hosted service: separate installations
  do not sync users, signups, or organization data.
- Organizations can display a time-gated QR code for an event. This
  source build does not include a mobile QR scanner or a server-side
  check-in service, so end-to-end phone-to-desktop QR check-in is not
  available. Check-ins can be recorded through the app's attendance
  controls.
- Upcoming-event reminders are in-app notifications created while a
  volunteer's dashboard is open; they are not push or email reminders.
- Email features need valid sender credentials and an internet
  connection. Without them, Moxie cannot send login or activation codes.

Before sharing or publishing this repository, inspect the included
SQLite database, CSV files, and cache/history files and remove or replace
any private or personal data.

## License

No license is currently included. Until one is added, reuse and
redistribution permissions are not specified.
