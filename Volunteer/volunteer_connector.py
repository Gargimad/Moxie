"""
volunteer_connector.py — Pull opportunities from the Volunteer Connector
public API into Moxie's local database.

Multi-day events: the API's `dates` field is free-text. We parse the
first date as event_date and the last date as event_end_date, both in
ISO YYYY-MM-DD form. If parsing fails, the raw string is stored in
event_date and event_end_date is left NULL.

Organizations: each opportunity is attached to a real organizations row
keyed on the API's organization.url (stored as organizations.source_id).
"""

import json
import os
import re
from datetime import datetime
from urllib import error, request

from db import Database

VC_ENDPOINT = "https://www.volunteerconnector.org/api/search/"
EXTERNAL_ORG_NAME = "Volunteer Connector"
USER_AGENT = "Moxie/1.0 (+https://example.org/moxie)"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_FILE = os.path.join(BASE_DIR, "volunteer_cache.json")

DEFAULT_COUNTRY_CODE = 64


# ─────────────────────────────────────────────────────────────────────────────
# Cache
# ─────────────────────────────────────────────────────────────────────────────
def _load_cache() -> dict:
    if not os.path.exists(CACHE_FILE):
        return {}
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError) as e:
        print(f"[VC] Cache read failed, ignoring: {e}")
        return {}


def _save_cache(cache: dict):
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except OSError as e:
        print(f"[VC] Cache write failed: {e}")


def clear_cache():
    if os.path.exists(CACHE_FILE):
        try:
            os.remove(CACHE_FILE)
            print("[VC] Cache cleared.")
            return True
        except OSError as e:
            print(f"[VC] Could not delete cache: {e}")
    return False


# ─────────────────────────────────────────────────────────────────────────────
# HTTP (cache-aware)
# ─────────────────────────────────────────────────────────────────────────────
def fetch_page(
    page: int = 1, timeout: int = 10, use_cache: bool = True
) -> list:
    cache = _load_cache() if use_cache else {}
    key = f"page_{page}"

    if use_cache and key in cache and isinstance(cache[key], list):
        print(f"[VC] Cache hit for {key} ({len(cache[key])} items).")
        return cache[key]

    url = f"{VC_ENDPOINT}?cc={DEFAULT_COUNTRY_CODE}&page={page}"
    req = request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except error.URLError as e:
        print(f"[VC] Network error: {e}")
        return []
    except Exception as e:
        print(f"[VC] Unexpected fetch error: {e}")
        return []

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"[VC] Bad JSON: {e}")
        return []

    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        items = data.get("results", []) or []
    else:
        items = []

    if use_cache and items:
        cache[key] = items
        _save_cache(cache)
        print(f"[VC] Cached {key} ({len(items)} items).")

    return items


# ─────────────────────────────────────────────────────────────────────────────
# Field extractors
# ─────────────────────────────────────────────────────────────────────────────
_MONTHS = {
    "january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "mar": 3,
    "april": 4, "apr": 4, "may": 5, "june": 6, "jun": 6, "july": 7, "jul": 7,
    "august": 8, "aug": 8, "september": 9, "sep": 9, "sept": 9,
    "october": 10, "oct": 10, "november": 11, "nov": 11,
    "december": 12, "dec": 12,
}

_DATE_PATTERN = re.compile(r"([A-Za-z]+)\s+(\d{1,2}),\s*(\d{4})")
_ISO_PATTERN = re.compile(r"(\d{4})-(\d{2})-(\d{2})")


def _as_str(v, default=""):
    if v is None:
        return default
    if isinstance(v, (list, tuple)):
        return ", ".join(str(x) for x in v if x)
    if isinstance(v, dict):
        for k in ("name", "title", "value"):
            if k in v and v[k]:
                return str(v[k]).strip()
        return default
    return str(v).strip()


def _activities_to_str(activities):
    if not activities or not isinstance(activities, list):
        return ""
    seen = []
    for a in activities:
        if not isinstance(a, dict):
            continue
        val = a.get("category") or a.get("name")
        if val and val not in seen:
            seen.append(str(val).strip())
    return ", ".join(seen)


def _audience_to_str(audience):
    if not isinstance(audience, dict):
        return ""
    regions = audience.get("regions")
    if isinstance(regions, list) and regions:
        return ", ".join(str(r) for r in regions if r)
    scope = audience.get("scope")
    if scope in ("remote", "online"):
        return "Remote"
    if scope:
        return str(scope).capitalize()
    return ""


def _human_match_to_iso(match):
    month_name, day, year = match
    month = _MONTHS.get(month_name.lower())
    if not month:
        return ""
    try:
        return datetime(int(year), month, int(day)).strftime("%Y-%m-%d")
    except ValueError:
        return ""


def _date_range_to_iso(dates):
    """
    Parse the free-text `dates` field into (start_iso, end_iso).
    Both may be "" if nothing parseable was found.

    Examples:
        "Ongoing"                                 -> ("", "")
        "April 15, 2024" ->
            ("2024-04-15", "2024-04-15")
        "April 15, 2024 - April 17, 2024" ->
            ("2024-04-15", "2024-04-17")
        "September 1, 2026 - December 15, 2026" ->
            ("2026-09-01", "2026-12-15")
        "2026-09-01 - 2026-12-15" ->
            ("2026-09-01", "2026-12-15")
    """
    if not isinstance(dates, str) or not dates.strip():
        return "", ""

    s = dates.strip()

    # ISO range
    iso_matches = _ISO_PATTERN.findall(s)
    if iso_matches:
        start = "-".join(iso_matches[0])
        end = "-".join(iso_matches[-1])
        return start, end

    # "Month Day, Year" occurrences
    human_matches = _DATE_PATTERN.findall(s)
    if human_matches:
        start = _human_match_to_iso(human_matches[0])
        end = _human_match_to_iso(human_matches[-1])
        return start, end

    return "", ""


def map_item(item: dict) -> dict:
    org = item.get("organization") or {}
    if not isinstance(org, dict):
        org = {"name": str(org)}

    org_url = _as_str(org.get("url")) or None
    start_iso, end_iso = _date_range_to_iso(item.get("dates"))
    raw_dates = _as_str(item.get("dates"))

    return {
        # opportunities columns
        "source_id": f"vc:{_as_str(item.get('id'))}",
        "title": _as_str(item.get("title"), "Untitled opportunity"),
        "description": _as_str(item.get("description")),
        "category": _activities_to_str(item.get("activities")) or "General",
        "location": _audience_to_str(item.get("audience")) or "See link",
        "address": "",
        "is_remote": 1 if item.get("remote_or_online") else 0,
        "event_date": start_iso or raw_dates,
        "event_end_date": end_iso or start_iso or None,
        "start_time": None,
        "end_time": None,
        "capacity": None,
        "status": "open",
        "required_skills": _as_str(item.get("duration")) or None,
        "contact_name": _as_str(org.get("name")),
        "contact_email": None,
        "thumbnail": _as_str(org.get("logo")) or None,
        "website_link": _as_str(item.get("url")),

        # extra keys for org resolution
        "org_name": _as_str(org.get("name")),
        "org_website": org_url,
        "org_source_id": org_url,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Sync
# ─────────────────────────────────────────────────────────────────────────────
def sync(db: Database, max_pages: int = 3, use_cache: bool = True) -> int:
    inserted = 0

    for page in range(1, max_pages + 1):
        items = fetch_page(page=page, use_cache=use_cache)
        if not items:
            break

        for item in items:
            mapped = map_item(item)
            if not mapped["source_id"] or mapped["source_id"] == "vc:":
                continue

            org_id = db.get_or_create_organization(
                mapped["org_name"] or EXTERNAL_ORG_NAME,
                source_id=mapped.get("org_source_id"),
                description="Imported via Volunteer Connector API",
                website_link=mapped.get("org_website"),
            )
            if org_id is None:
                print(f"[VC] Could not resolve org for {mapped['title'][:40]}")
                continue

            try:
                db.cursor.execute(
                    """
                    INSERT INTO opportunities
                    (orgID, title, description, category, location, address,
                     is_remote, event_date, event_end_date,
                     start_time, end_time, capacity,
                     status, required_skills, contact_name, contact_email,
                     thumbnail, website_link, source_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                            ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        org_id,
                        mapped["title"],
                        mapped["description"],
                        mapped["category"],
                        mapped["location"],
                        mapped["address"],
                        mapped["is_remote"],
                        mapped["event_date"],
                        mapped["event_end_date"],
                        mapped["start_time"],
                        mapped["end_time"],
                        mapped["capacity"],
                        mapped["status"],
                        mapped["required_skills"],
                        mapped["contact_name"],
                        mapped["contact_email"],
                        mapped["thumbnail"],
                        mapped["website_link"],
                        mapped["source_id"],
                    ),
                )
                inserted += 1
            except Exception as e:
                print(f"[VC] Insert skipped ({mapped['title'][:40]}): {e}")

    db.connection.commit()
    print(f"[VC] Sync complete — {inserted} new opportunities inserted.")
    return inserted
