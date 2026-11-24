"""
dateFormat.py - Human-readable date and time formatting.

The database stores dates as ISO strings (YYYY-MM-DD) and times as
free-text (HH:MM). Nothing in the UI should ever show the raw ISO
string to a user. Every page imports from here so dates read
consistently across cards, dialogs, and dashboards.

Public API:
    format_date(iso)                  -> "Oct 15, 2026"
    format_date_short(iso)            -> "Oct 15"
    format_date_long(iso)             -> "Thursday, October 15, 2026"
    format_weekday(iso)               -> "Thu"
    format_range(start, end)          -> "Oct 15 – Oct 17, 2026"
    format_time(hhmm)                 -> "9:00 AM"
    format_time_range(start, end)     -> "9:00 AM – 12:00 PM"
    format_event_when(row)            -> "Thu, Oct 15 · 9:00 AM – 12:00 PM"
    relative_day(iso)                 -> "Today" / "Tomorrow" / "in 3 days"

Cross-platform: avoids %-d (not supported on Windows) and uses
strftime for the month name only, formatting the day number with
`d.day` so we get "Oct 5" instead of "Oct 05".

Anything that can't be parsed is returned as-is so raw text still
shows up (imported events sometimes have free-text dates).
"""

from datetime import date, datetime, timedelta


# ── Core parsers ────────────────────────────────────────────────────
def _parse_iso(value):
    """Return a datetime.date from an ISO string, or None."""
    if not value:
        return None
    s = str(value).strip()
    if not s:
        return None
    # Accept "YYYY-MM-DD" and "YYYY-MM-DDTHH:MM:SS" (from timestamps).
    try:
        return datetime.fromisoformat(s[:10]).date()
    except ValueError:
        pass
    # Some imported rows carry free-text dates ("Ongoing", "See link").
    return None


def _parse_time(value):
    """Return (hour, minute) from 'HH:MM', 'H:MM', or 'HH:MM:SS'."""
    if not value:
        return None
    s = str(value).strip()
    if not s:
        return None
    parts = s.split(":")
    if len(parts) < 2:
        return None
    try:
        return int(parts[0]), int(parts[1])
    except ValueError:
        return None


# ── Date formatting ─────────────────────────────────────────────────
def format_date(iso):
    """'2026-10-15' -> 'Oct 15, 2026'. Falls back to the raw string."""
    d = _parse_iso(iso)
    if not d:
        return str(iso or "").strip()
    return f"{d.strftime('%b')} {d.day}, {d.year}"


def format_date_short(iso):
    """'2026-10-15' -> 'Oct 15'."""
    d = _parse_iso(iso)
    if not d:
        return str(iso or "").strip()
    return f"{d.strftime('%b')} {d.day}"


def format_date_long(iso):
    """'2026-10-15' -> 'Thursday, October 15, 2026'."""
    d = _parse_iso(iso)
    if not d:
        return str(iso or "").strip()
    return f"{d.strftime('%A, %B')} {d.day}, {d.year}"


def format_weekday(iso):
    """'2026-10-15' -> 'Thu'. Unparseable -> ''."""
    d = _parse_iso(iso)
    return d.strftime("%a") if d else ""


def format_range(start, end):
    """
    Two ISO dates -> a compact range.

    '2026-10-15', ''                  -> 'Oct 15, 2026'
    '2026-10-15', '2026-10-15'        -> 'Oct 15, 2026'
    '2026-10-15', '2026-10-17'        -> 'Oct 15 – 17, 2026'
    '2026-10-15', '2026-11-02'        -> 'Oct 15 – Nov 2, 2026'
    '2026-12-30', '2027-01-02'        -> 'Dec 30, 2026 – Jan 2, 2027'
    Unparseable values are returned joined with ' – '.
    """
    s = _parse_iso(start)
    e = _parse_iso(end)

    if not s and not e:
        return ""
    if not s:
        return format_date(end)
    if not e or e == s:
        return format_date(start)

    # Same month and year: "Oct 15 – 17, 2026"
    if s.year == e.year and s.month == e.month:
        return f"{s.strftime('%b')} {s.day} – {e.day}, {s.year}"

    # Same year, different months: "Oct 15 – Nov 2, 2026"
    if s.year == e.year:
        return (f"{s.strftime('%b')} {s.day} – "
                f"{e.strftime('%b')} {e.day}, {s.year}")

    # Different years: "Dec 30, 2026 – Jan 2, 2027"
    return f"{format_date(start)} – {format_date(end)}"


# ── Time formatting ─────────────────────────────────────────────────
def format_time(hhmm):
    """'09:00' -> '9:00 AM'. '13:30' -> '1:30 PM'. Unknown -> as-is."""
    t = _parse_time(hhmm)
    if not t:
        return str(hhmm or "").strip()
    h, m = t
    suffix = "AM" if h < 12 else "PM"
    h12 = h % 12 or 12
    return f"{h12}:{m:02d} {suffix}"


def format_time_range(start, end):
    """'09:00', '12:00' -> '9:00 AM – 12:00 PM'."""
    s = format_time(start)
    e = format_time(end)
    if s and e:
        return f"{s} – {e}"
    return s or e


# ── Composite helpers ───────────────────────────────────────────────
def format_event_when(row):
    """
    Read a row (sqlite3.Row or dict) and produce a single readable line
    for the date + time of an event:

        'Thu, Oct 15 · 9:00 AM – 12:00 PM'
        'Thu, Oct 15 – Fri, Oct 17 · 9:00 AM – 12:00 PM'
        'Oct 15, 2026'                    (no times)
        'TBD'                             (no date at all)
    """
    def g(key, default=""):
        try:
            v = row[key]
        except (KeyError, IndexError, TypeError):
            return default
        return default if v is None else v

    start = g("event_date")
    end = g("event_end_date")
    t_start = g("start_time")
    t_end = g("end_time")

    if not start:
        return "TBD"

    s_date = _parse_iso(start)
    e_date = _parse_iso(end)

    # Date part
    if s_date and (not e_date or e_date == s_date):
        date_part = f"{format_weekday(start)}, {format_date_short(start)}"
    else:
        date_part = format_range(start, end)

    # Time part
    time_part = format_time_range(t_start, t_end)

    if time_part:
        return f"{date_part} · {time_part}"
    return date_part


def relative_day(iso):
    """
    'Today' / 'Tomorrow' / 'Yesterday' / 'in 3 days' / '3 days ago'.
    Falls back to format_date_short for far dates.
    """
    d = _parse_iso(iso)
    if not d:
        return str(iso or "").strip()
    delta = (d - date.today()).days
    if delta == 0:
        return "Today"
    if delta == 1:
        return "Tomorrow"
    if delta == -1:
        return "Yesterday"
    if 1 < delta < 7:
        return f"in {delta} days"
    if -7 < delta < -1:
        return f"{abs(delta)} days ago"
    return format_date_short(iso)
