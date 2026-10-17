"""
test.py — Standalone importer for the Moxie demo data.

    python test.py                              # auto-detects the CSV
    python test.py path/to/events.csv           # explicit path

What it does:
    1. Creates every organization in the CSV (as an external org —
       no userID/password, just a name and website). Idempotent.
    2. Imports every event as an opportunity, tagging it with the
       career cluster that matches its `category` column.
    3. Writes each event's thumbnail URL through so EventCard fetches
       it on first view (cached under Events/.thumb_cache/).

Safe to re-run: events with the same (title, event_date, org) are
skipped. To start completely fresh, delete Volunteer.db and
Events/.thumb_cache/ first.
"""
import csv
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from db import Database
from Events.careerClusters import CAREER_CLUSTERS


# ── Locate the CSV ────────────────────────────────────────────────────
def _resolve_csv_path():
    if len(sys.argv) > 1:
        return sys.argv[1]
    for candidate in (
        "georgia_volunteer_events.csv",
        "data/opportunities.csv",
        "opportunities.csv",
        "events.csv",
    ):
        if os.path.exists(candidate):
            return candidate
    return "georgia_volunteer_events.csv"


# ── The CSV's category column uses shortened cluster names. Map each
#    one to the canonical CAREER_CLUSTERS name the app uses internally.
CATEGORY_TO_CLUSTER = {
    "human services": "Human Services",
    "agriculture food & natural resources":
        "Agriculture, Food & Natural Resources",
    "education & training": "Education & Training",
    "architecture & construction": "Architecture & Construction",
    "arts audio/visual technology & communications":
        "Arts, Audio/Video Technology & Communications",
    "business management & administration":
        "Business Management & Administration",
    "health science": "Health Science",
    "information technology": "Information Technology",
    "manufacturing": "Manufacturing",
    "finance": "Finance",
    "marketing": "Marketing",
    "stem": "Science, Technology, Engineering & Mathematics",
    "law public safety corrections & security":
        "Law, Public Safety, Corrections & Security",
    "government & public administration":
        "Government & Public Administration",
    "hospitality & tourism": "Hospitality & Tourism",
    "transportation distribution & logistics":
        "Transportation, Distribution & Logistics",
}


# ── Helpers ───────────────────────────────────────────────────────────
def _clean(value):
    return "" if value is None else str(value).strip()


def _bool01(value):
    return _clean(value).lower() in ("1", "true", "yes", "y")


def _int_or_none(value):
    v = _clean(value)
    if not v:
        return None
    try:
        return int(v)
    except ValueError:
        return None


def _norm_date(value):
    v = _clean(value)
    if not v:
        return None
    try:
        return datetime.fromisoformat(v[:10]).date().isoformat()
    except ValueError:
        return None


def _norm_time(value):
    v = _clean(value)
    if not v:
        return None
    try:
        h, m = v.split(":")[:2]
        return f"{int(h):02d}:{int(m):02d}"
    except (ValueError, AttributeError):
        return None


def _cluster_for(category):
    key = _clean(category).lower()
    if key in CATEGORY_TO_CLUSTER:
        return CATEGORY_TO_CLUSTER[key]
    for needle, cluster in CATEGORY_TO_CLUSTER.items():
        if needle in key:
            return cluster
    for name in CAREER_CLUSTERS:
        if name.lower() == key:
            return name
    return None


# ── Main ──────────────────────────────────────────────────────────────
def main():
    csv_path = _resolve_csv_path()
    if not os.path.exists(csv_path):
        print(f"CSV not found: {csv_path}")
        print("Pass the path explicitly:")
        print("    python test.py path/to/your_events.csv")
        return

    print(f"Reading {csv_path}")
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    print(f"  {len(rows)} rows\n")

    db = Database()

    # ── Step 1 — organizations ────────────────────────────────────
    print("Step 1 · Organizations")
    unique_orgs = {}
    for row in rows:
        name = _clean(row.get("org_name"))
        if not name or name in unique_orgs:
            continue
        unique_orgs[name] = {
            "city": _clean(row.get("city")) or None,
            "website": _clean(row.get("website_link")) or None,
        }

    org_ids = {}
    for name, info in unique_orgs.items():
        try:
            orgID = db.get_or_create_organization(
                org_name=name,
                website_link=info["website"],
                city=info["city"],
                country="United States",
            )
        except Exception as e:
            print(f"  ! {name}: {e}")
            continue
        if orgID:
            org_ids[name] = orgID
            print(f"  ✓ #{orgID:>3}  {name}")
        else:
            print(f"  ✗ failed: {name}")

    print(f"  {len(org_ids)} organizations ready\n")

    # ── Step 2 — opportunities ────────────────────────────────────
    print("Step 2 · Opportunities")
    added = 0
    skipped = 0
    unmapped_cluster = 0
    cluster_counts = {name: 0 for name in CAREER_CLUSTERS}

    for i, row in enumerate(rows, start=2):
        org_name = _clean(row.get("org_name"))
        orgID = org_ids.get(org_name)
        if not orgID:
            skipped += 1
            continue

        title = _clean(row.get("title"))
        if not title:
            skipped += 1
            continue

        # Dates — keep raw text if it can't be parsed (some imported
        # rows legitimately have free-text dates like "Ongoing").
        start_iso = _norm_date(row.get("event_date"))
        if not start_iso:
            start_iso = _clean(row.get("event_date")) or None
        end_iso = _norm_date(row.get("event_end_date"))

        # Dedup within this org's existing events.
        existing = db.getOpportunitiesByOrg(orgID)
        if any(
            o["title"] == title
            and str(o["event_date"] or "")[:10] == (start_iso or "")[:10]
            for o in existing
        ):
            skipped += 1
            continue

        cluster = _cluster_for(row.get("category"))
        if cluster is None:
            unmapped_cluster += 1

        try:
            oppID = db.addOpportunity(
                orgID=orgID,
                title=title,
                description=_clean(row.get("description")),
                category="",                    # superseded by clusters
                location=_clean(row.get("location")) or "See link",
                address=_clean(row.get("address")),
                is_remote=_bool01(row.get("is_remote")),
                event_date=start_iso,
                event_end_date=end_iso,
                thumbnail=_clean(row.get("thumbnail")) or None,
                start_time=_norm_time(row.get("start_time")),
                end_time=_norm_time(row.get("end_time")),
                capacity=_int_or_none(row.get("capacity")),
                status=_clean(row.get("status")) or "open",
                required_skills=_clean(row.get("required_skills")) or None,
                contact_name=_clean(row.get("contact_name")) or None,
                contact_email=_clean(row.get("contact_email")) or None,
                website_link=_clean(row.get("website_link")) or None,
                city=_clean(row.get("city")) or None,
                state=_clean(row.get("state")) or "GA",
                high_school=_clean(row.get("high_school")) or None,
                min_age=_int_or_none(row.get("min_age")),
                max_age=_int_or_none(row.get("max_age")),
                meal_provided=_bool01(row.get("meal_provided")),
                background_check_required=_bool01(
                    row.get("background_check_required")
                ),
                training_required=_bool01(row.get("training_required")),
                training_description=(
                    _clean(row.get("training_description")) or None
                ),
            )
        except Exception as e:
            print(f"  row {i}: ! {e}")
            skipped += 1
            continue

        if not oppID:
            skipped += 1
            continue

        if cluster:
            db.setOpportunityClusters(oppID, [cluster])
            cluster_counts[cluster] += 1

        added += 1
        if added % 20 == 0:
            print(f"  ... {added} imported")

    # ── Summary ───────────────────────────────────────────────────
    print(f"\nDone.")
    print(f"  {added} events imported")
    print(f"  {skipped} skipped (duplicates or missing data)")
    if unmapped_cluster:
        print(f"  {unmapped_cluster} events had an unmapped category "
              f"— add it to CATEGORY_TO_CLUSTER in test.py")

    # ── Verify ────────────────────────────────────────────────────
    print("\nVerifying...")
    total_opps = len(db.getAllOpportunities(limit=1000))
    total_orgs = len(db.getOrganizations(1))
    print(f"  Events in DB:         {total_opps}")
    print(f"  Organizations in DB:  {total_orgs}")
    print(f"  Clusters available:   {len(db.getCareerClusters())}")

    print("\nCluster coverage:")
    for name in CAREER_CLUSTERS:
        n = cluster_counts[name]
        marker = "✓" if n else "·"
        print(f"  {marker} {n:>3}  {name}")

    missing = [n for n in CAREER_CLUSTERS if not cluster_counts[n]]
    if missing:
        print(f"\n  {len(missing)} cluster(s) still empty:")
        for n in missing:
            print(f"    · {n}")
    else:
        print("\n  All 16 clusters covered.")

    db.close()


if __name__ == "__main__":
    main()