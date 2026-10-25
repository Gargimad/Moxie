"""
db.py — Unified database layer for Moxie.
"""
import os
import sqlite3
import hashlib
import math
import secrets
from datetime import datetime, timedelta

try:
    import bcrypt
    _HAS_BCRYPT = True
except ImportError:
    _HAS_BCRYPT = False


DB_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "Volunteer.db"
)


# ── Password hashing ──────────────────────────────────────────────────
def hash_password(plain: str) -> str:
    if _HAS_BCRYPT:
        return bcrypt.hashpw(
            plain.encode("utf-8"), bcrypt.gensalt()
        ).decode("utf-8")
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac(
        "sha256", plain.encode("utf-8"), salt, 200_000
    )
    return f"pbkdf2${salt.hex()}${dk.hex()}"


def verify_password(plain: str, stored: str) -> bool:
    if not stored:
        return False
    if stored.startswith("$2") and _HAS_BCRYPT:
        try:
            return bcrypt.checkpw(
                plain.encode("utf-8"), stored.encode("utf-8")
            )
        except ValueError:
            return False
    if stored.startswith("pbkdf2$"):
        try:
            _, salt_hex, dk_hex = stored.split("$")
            salt = bytes.fromhex(salt_hex)
            expected = bytes.fromhex(dk_hex)
            dk = hashlib.pbkdf2_hmac(
                "sha256", plain.encode("utf-8"), salt, 200_000
            )
            return dk == expected
        except (ValueError, AttributeError):
            return False
    return plain == stored


# ── Column registries ─────────────────────────────────────────────────
# These drive the migrations and the "allowed fields" whitelists so a
# new column only has to be declared once. Every column is TEXT unless
# noted; SQLite is dynamically typed but this keeps intent clear.
VOLUNTEER_PROFILE_COLUMNS = {
    # existing
    "first_name": "TEXT", "last_name": "TEXT", "country": "TEXT",
    "zipcode": "TEXT", "dob": "TEXT", "gender": "TEXT",
    "skills": "TEXT", "phone": "TEXT",
    # new — location
    "city": "TEXT", "state": "TEXT DEFAULT 'GA'",
    "high_school": "TEXT",
    # new — school context
    "grade_level": "TEXT", "graduation_year": "INTEGER",
    # new — identity / preferences
    "pronouns": "TEXT", "bio": "TEXT",
    "preferred_contact": "TEXT DEFAULT 'email'",
    "hours_goal": "INTEGER DEFAULT 0",
    # new — matching
    "availability": "TEXT", "interests": "TEXT",
    "has_transportation": "INTEGER DEFAULT 0",
    "can_work_remote": "INTEGER DEFAULT 0",
    # new — emergency contact
    "emergency_contact_name": "TEXT",
    "emergency_contact_phone": "TEXT",
    "emergency_contact_relationship": "TEXT",
}

ORGANIZATION_COLUMNS = {
    "org_name": "TEXT", "description": "TEXT", "website_link": "TEXT",
    "city": "TEXT", "country": "TEXT", "source_id": "TEXT",
    # new
    "ein": "TEXT",
    "org_type": "TEXT",
    "founded_year": "INTEGER",
    "contact_person": "TEXT",
    "contact_phone": "TEXT",
    "accepting_volunteers": "INTEGER DEFAULT 1",
    "service_area": "TEXT",
    "remote_friendly": "INTEGER DEFAULT 0",
    "needs_volunteers_for": "TEXT",
    "logo_path": "TEXT",
}

OPPORTUNITY_COLUMNS = {
    "orgID": "INTEGER", "title": "TEXT", "description": "TEXT",
    "category": "TEXT", "location": "TEXT", "address": "TEXT",
    "is_remote": "INTEGER DEFAULT 0",
    "event_date": "TEXT", "event_end_date": "TEXT",
    "start_time": "TEXT", "end_time": "TEXT",
    "capacity": "INTEGER", "status": "TEXT DEFAULT 'open'",
    "required_skills": "TEXT",
    "contact_name": "TEXT", "contact_email": "TEXT",
    "thumbnail": "TEXT", "website_link": "TEXT", "source_id": "TEXT",
    # new — location precision
    "city": "TEXT", "state": "TEXT DEFAULT 'GA'",
    "high_school": "TEXT",
    "latitude": "REAL", "longitude": "REAL",
    "timezone": "TEXT DEFAULT 'America/New_York'",
    # new — eligibility
    "min_age": "INTEGER", "max_age": "INTEGER",
    "min_grade": "TEXT", "max_grade": "TEXT",
    # new — logistics
    "meeting_point": "TEXT", "parking_info": "TEXT",
    "accessibility_notes": "TEXT",
    "what_to_bring": "TEXT", "dress_code": "TEXT",
    "meal_provided": "INTEGER DEFAULT 0",
    "background_check_required": "INTEGER DEFAULT 0",
    "training_required": "INTEGER DEFAULT 0",
    "training_description": "TEXT",
}


class Database:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self.connection = sqlite3.connect(
            db_path, check_same_thread=False
        )
        self.connection.row_factory = sqlite3.Row
        self.cursor = self.connection.cursor()
        self.cursor.execute("PRAGMA foreign_keys = ON")
        self.cursor.execute("PRAGMA journal_mode = WAL")
        self.createTable()
        self.migrate()

    # ── Schema ────────────────────────────────────────────────────────
    def createTable(self):
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                userID INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('volunteer', 'org')),
                email_verified INTEGER DEFAULT 0,
                mfa_enabled INTEGER DEFAULT 1,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # Volunteer profiles now include GA city / state / high school
        # plus matching and emergency-contact fields.
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS volunteer_profiles (
                userID INTEGER PRIMARY KEY,
                first_name TEXT,
                last_name TEXT,
                country TEXT,
                zipcode TEXT,
                dob TEXT,
                gender TEXT,
                skills TEXT,
                phone TEXT,
                city TEXT,
                state TEXT DEFAULT 'GA',
                high_school TEXT,
                grade_level TEXT,
                graduation_year INTEGER,
                pronouns TEXT,
                bio TEXT,
                preferred_contact TEXT DEFAULT 'email',
                hours_goal INTEGER DEFAULT 0,
                availability TEXT,
                interests TEXT,
                has_transportation INTEGER DEFAULT 0,
                can_work_remote INTEGER DEFAULT 0,
                emergency_contact_name TEXT,
                emergency_contact_phone TEXT,
                emergency_contact_relationship TEXT,
                FOREIGN KEY(userID) REFERENCES users(userID)
                    ON DELETE CASCADE
            );
        """)

        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS organizations (
                orgID INTEGER PRIMARY KEY AUTOINCREMENT,
                userID INTEGER,
                org_name TEXT NOT NULL,
                description TEXT,
                website_link TEXT,
                city TEXT,
                country TEXT,
                source_id TEXT,
                ein TEXT,
                org_type TEXT,
                founded_year INTEGER,
                contact_person TEXT,
                contact_phone TEXT,
                accepting_volunteers INTEGER DEFAULT 1,
                service_area TEXT,
                remote_friendly INTEGER DEFAULT 0,
                needs_volunteers_for TEXT,
                logo_path TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(userID) REFERENCES users(userID)
                    ON DELETE CASCADE
            );
        """)

        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS org_members (
                memberID INTEGER PRIMARY KEY AUTOINCREMENT,
                userID INTEGER NOT NULL,
                orgID INTEGER NOT NULL,
                member_role TEXT DEFAULT 'member',
                UNIQUE(userID, orgID),
                FOREIGN KEY(userID) REFERENCES users(userID)
                    ON DELETE CASCADE,
                FOREIGN KEY(orgID) REFERENCES organizations(orgID)
                    ON DELETE CASCADE
            );
        """)

        # Opportunities now carry city / state / high school, eligibility,
        # logistics, coordinates, and timezone.
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS opportunities (
                opportunityID INTEGER PRIMARY KEY AUTOINCREMENT,
                orgID INTEGER,
                title TEXT NOT NULL,
                description TEXT,
                category TEXT,
                location TEXT,
                address TEXT,
                is_remote INTEGER DEFAULT 0,
                event_date TEXT,
                event_end_date TEXT,
                start_time TEXT,
                end_time TEXT,
                capacity INTEGER,
                status TEXT DEFAULT 'open',
                required_skills TEXT,
                contact_name TEXT,
                contact_email TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                thumbnail TEXT,
                website_link TEXT,
                source_id TEXT,
                city TEXT,
                state TEXT DEFAULT 'GA',
                high_school TEXT,
                latitude REAL,
                longitude REAL,
                timezone TEXT DEFAULT 'America/New_York',
                min_age INTEGER,
                max_age INTEGER,
                min_grade TEXT,
                max_grade TEXT,
                meeting_point TEXT,
                parking_info TEXT,
                accessibility_notes TEXT,
                what_to_bring TEXT,
                dress_code TEXT,
                meal_provided INTEGER DEFAULT 0,
                background_check_required INTEGER DEFAULT 0,
                training_required INTEGER DEFAULT 0,
                training_description TEXT,
                FOREIGN KEY(orgID) REFERENCES organizations(orgID)
            );
        """)

        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS event_signups (
                signupID INTEGER PRIMARY KEY AUTOINCREMENT,
                userID INTEGER NOT NULL,
                opportunityID INTEGER NOT NULL,
                status TEXT DEFAULT 'registered',
                signup_time TEXT DEFAULT CURRENT_TIMESTAMP,
                check_in_time TEXT,
                check_out_time TEXT,
                hours_logged REAL DEFAULT 0,
                UNIQUE(userID, opportunityID),
                FOREIGN KEY(userID) REFERENCES users(userID)
                    ON DELETE CASCADE,
                FOREIGN KEY(opportunityID)
                    REFERENCES opportunities(opportunityID)
                    ON DELETE CASCADE
            );
        """)

        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS notifications (
                notificationID INTEGER PRIMARY KEY AUTOINCREMENT,
                userID INTEGER NOT NULL,
                message TEXT NOT NULL,
                type TEXT,
                related_opportunityID INTEGER,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                read_at TEXT,
                FOREIGN KEY(userID) REFERENCES users(userID)
                    ON DELETE CASCADE
            );
        """)

        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS opportunity_invitations (
                invitationID INTEGER PRIMARY KEY AUTOINCREMENT,
                orgID INTEGER NOT NULL,
                userID INTEGER NOT NULL,
                opportunityID INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending'
                    CHECK(status IN ('pending', 'accepted', 'declined')),
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                responded_at TEXT,
                FOREIGN KEY(orgID) REFERENCES organizations(orgID)
                    ON DELETE CASCADE,
                FOREIGN KEY(userID) REFERENCES users(userID)
                    ON DELETE CASCADE,
                FOREIGN KEY(opportunityID)
                    REFERENCES opportunities(opportunityID)
                    ON DELETE CASCADE
            );
        """)

        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_org_colors (
                userID INTEGER NOT NULL,
                orgID INTEGER NOT NULL,
                color TEXT NOT NULL,
                PRIMARY KEY (userID, orgID),
                FOREIGN KEY(userID) REFERENCES users(userID)
                    ON DELETE CASCADE,
                FOREIGN KEY(orgID) REFERENCES organizations(orgID)
                    ON DELETE CASCADE
            );
        """)

        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS announcements (
                announcementID INTEGER PRIMARY KEY AUTOINCREMENT,
                orgID INTEGER NOT NULL,
                title TEXT NOT NULL,
                body TEXT NOT NULL,
                pinned INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(orgID) REFERENCES organizations(orgID)
                    ON DELETE CASCADE
            );
        """)

        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS org_volunteer_notes (
                noteID INTEGER PRIMARY KEY AUTOINCREMENT,
                orgID INTEGER NOT NULL,
                userID INTEGER NOT NULL,
                note TEXT,
                tag TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(orgID) REFERENCES organizations(orgID)
                    ON DELETE CASCADE,
                FOREIGN KEY(userID) REFERENCES users(userID)
                    ON DELETE CASCADE
            );
        """)

        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS org_volunteer_flags (
                orgID INTEGER NOT NULL,
                userID INTEGER NOT NULL,
                banned INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (orgID, userID),
                FOREIGN KEY(orgID) REFERENCES organizations(orgID)
                    ON DELETE CASCADE,
                FOREIGN KEY(userID) REFERENCES users(userID)
                    ON DELETE CASCADE
            );
        """)

        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS bookmarks (
                bookmarkID INTEGER PRIMARY KEY AUTOINCREMENT,
                userID INTEGER NOT NULL,
                opportunityID INTEGER NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(userID, opportunityID),
                FOREIGN KEY(userID) REFERENCES users(userID)
                    ON DELETE CASCADE,
                FOREIGN KEY(opportunityID)
                    REFERENCES opportunities(opportunityID)
                    ON DELETE CASCADE
            );
        """)

        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS career_clusters (
                clusterID INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL
            );
        """)

        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS opportunity_clusters (
                opportunityID INTEGER NOT NULL,
                clusterID INTEGER NOT NULL,
                PRIMARY KEY (opportunityID, clusterID),
                FOREIGN KEY(opportunityID)
                    REFERENCES opportunities(opportunityID)
                    ON DELETE CASCADE,
                FOREIGN KEY(clusterID)
                    REFERENCES career_clusters(clusterID)
                    ON DELETE CASCADE
            );
        """)

        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS organization_clusters (
                orgID INTEGER NOT NULL,
                clusterID INTEGER NOT NULL,
                PRIMARY KEY (orgID, clusterID),
                FOREIGN KEY(orgID) REFERENCES organizations(orgID)
                    ON DELETE CASCADE,
                FOREIGN KEY(clusterID)
                    REFERENCES career_clusters(clusterID)
                    ON DELETE CASCADE
            );
        """)

        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS volunteer_match (
                userID INTEGER PRIMARY KEY,
                location TEXT,
                city TEXT,
                high_school TEXT,
                cluster1 TEXT,
                cluster2 TEXT,
                cluster3 TEXT,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(userID) REFERENCES users(userID)
                    ON DELETE CASCADE
            );
        """)

        for stmt in (
            "CREATE INDEX IF NOT EXISTS idx_opp_org "
            "ON opportunities(orgID)",
            "CREATE INDEX IF NOT EXISTS idx_opp_city "
            "ON opportunities(city)",
            "CREATE INDEX IF NOT EXISTS idx_opp_state "
            "ON opportunities(state)",
            "CREATE INDEX IF NOT EXISTS idx_opp_event_date "
            "ON opportunities(event_date)",
            "CREATE INDEX IF NOT EXISTS idx_ann_org "
            "ON announcements(orgID)",
            "CREATE INDEX IF NOT EXISTS idx_signup_user "
            "ON event_signups(userID)",
            "CREATE INDEX IF NOT EXISTS idx_signup_opp "
            "ON event_signups(opportunityID)",
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_org_source "
            "ON organizations(source_id) WHERE source_id IS NOT NULL",
            "CREATE INDEX IF NOT EXISTS idx_notes_org_user "
            "ON org_volunteer_notes(orgID, userID)",
            "CREATE INDEX IF NOT EXISTS idx_bookmark_user "
            "ON bookmarks(userID)",
            "CREATE INDEX IF NOT EXISTS idx_opp_cluster "
            "ON opportunity_clusters(clusterID)",
            "CREATE INDEX IF NOT EXISTS idx_vol_city "
            "ON volunteer_profiles(city)",
            "CREATE INDEX IF NOT EXISTS idx_vol_state "
            "ON volunteer_profiles(state)",
            "CREATE INDEX IF NOT EXISTS idx_vol_school "
            "ON volunteer_profiles(high_school)",
        ):
            self.cursor.execute(stmt)
        self.connection.commit()

    # ── Column-adding helper ──────────────────────────────────────────
    def _add_columns(self, table, spec):
        """
        Idempotently add any missing columns described by `spec`
        ({column_name: ddl}). Returns the list of added names.
        """
        existing = {
            row["name"]
            for row in self.cursor.execute(
                f"PRAGMA table_info({table})"
            ).fetchall()
        }
        added = []
        for col, ddl in spec.items():
            if col in existing:
                continue
            self.cursor.execute(
                f"ALTER TABLE {table} ADD COLUMN {col} {ddl}"
            )
            added.append(f"{table}.{col}")
        return added

    # ── Migrations ────────────────────────────────────────────────────
    def migrate(self):
        added = []

        added += self._add_columns(
            "notifications",
            {"invitationID": "INTEGER"},
        )
        added += self._add_columns(
            "event_signups",
            {
                "verified": "INTEGER DEFAULT 0",
                "verified_by": "INTEGER",
                "verified_at": "TEXT",
                "no_show": "INTEGER DEFAULT 0",
                "org_notes": "TEXT",
                "reminder_sent": "INTEGER DEFAULT 0",
            },
        )
        added += self._add_columns(
            "volunteer_profiles", VOLUNTEER_PROFILE_COLUMNS
        )
        added += self._add_columns(
            "organizations", ORGANIZATION_COLUMNS
        )
        added += self._add_columns(
            "opportunities", OPPORTUNITY_COLUMNS
        )

        if added:
            self.connection.commit()

        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS org_volunteer_notes (
                noteID INTEGER PRIMARY KEY AUTOINCREMENT,
                orgID INTEGER NOT NULL,
                userID INTEGER NOT NULL,
                note TEXT,
                tag TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(orgID) REFERENCES organizations(orgID)
                    ON DELETE CASCADE,
                FOREIGN KEY(userID) REFERENCES users(userID)
                    ON DELETE CASCADE
            );
        """)
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS org_volunteer_flags (
                orgID INTEGER NOT NULL,
                userID INTEGER NOT NULL,
                banned INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (orgID, userID),
                FOREIGN KEY(orgID) REFERENCES organizations(orgID)
                    ON DELETE CASCADE,
                FOREIGN KEY(userID) REFERENCES users(userID)
                    ON DELETE CASCADE
            );
        """)
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS volunteer_activation_codes (
                userID INTEGER PRIMARY KEY,
                code_hash TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY(userID) REFERENCES users(userID)
                    ON DELETE CASCADE
            );
        """)
        self.connection.commit()

        # Seed career clusters (idempotent).
        from Events.careerClusters import (
            CAREER_CLUSTERS, legacy_category_to_cluster,
        )
        for name in CAREER_CLUSTERS:
            self.cursor.execute(
                "INSERT OR IGNORE INTO career_clusters (name) VALUES (?)",
                (name,),
            )

        # Backfill legacy category -> cluster.
        self.cursor.execute(
            "SELECT opportunityID, category FROM opportunities "
            "WHERE category IS NOT NULL AND category != ''"
        )
        for row in self.cursor.fetchall():
            cluster = legacy_category_to_cluster(row["category"])
            if not cluster:
                continue
            self.cursor.execute(
                "SELECT clusterID FROM career_clusters WHERE name = ?",
                (cluster,),
            )
            cid = self.cursor.fetchone()
            if cid:
                self.cursor.execute(
                    "INSERT OR IGNORE INTO opportunity_clusters "
                    "(opportunityID, clusterID) VALUES (?, ?)",
                    (row["opportunityID"], cid["clusterID"]),
                )

        # Backfill opportunity.city from legacy free-text `location` when
        # a Georgia city name is present and `city` is empty.
        try:
            from Events.gaLocations import GA_CITIES
        except Exception:
            GA_CITIES = []
        if GA_CITIES:
            self.cursor.execute(
                "SELECT opportunityID, location FROM opportunities "
                "WHERE (city IS NULL OR city = '') "
                "AND location IS NOT NULL AND location != ''"
            )
            for row in self.cursor.fetchall():
                loc = str(row["location"])
                for city in GA_CITIES:
                    if city.lower() in loc.lower():
                        self.cursor.execute(
                            "UPDATE opportunities SET city = ?, "
                            "state = COALESCE(state, 'GA') "
                            "WHERE opportunityID = ?",
                            (city, row["opportunityID"]),
                        )
                        break

        # Backfill volunteer state to 'GA' when the city matches a known
        # Georgia city (imported rosters sometimes leave state blank).
        if GA_CITIES:
            self.cursor.execute(
                "SELECT userID, city, state FROM volunteer_profiles "
                "WHERE (state IS NULL OR state = '') "
                "AND city IS NOT NULL AND city != ''"
            )
            for row in self.cursor.fetchall():
                if str(row["city"]) in GA_CITIES:
                    self.cursor.execute(
                        "UPDATE volunteer_profiles SET state = 'GA' "
                        "WHERE userID = ?",
                        (row["userID"],),
                    )

        self.connection.commit()

        if added:
            print(f"[db] migrate: added columns -> {', '.join(added)}")
        return added

    # ── Users / auth ──────────────────────────────────────────────────
    def register_user(self, email, password, role, **profile):
        if role not in ("volunteer", "org"):
            return None
        try:
            self.cursor.execute(
                "INSERT INTO users (email, password, role, email_verified) "
                "VALUES (?, ?, ?, 1)",
                (email.strip().lower(), hash_password(password), role),
            )
            userID = self.cursor.lastrowid

            if role == "volunteer":
                fields = {
                    k: profile.get(k, "")
                    for k in VOLUNTEER_PROFILE_COLUMNS
                }
                # Make sure state defaults to GA when not supplied.
                if not fields.get("state"):
                    fields["state"] = "GA"
                cols = ", ".join(fields.keys())
                placeholders = ", ".join("?" for _ in fields)
                self.cursor.execute(
                    f"INSERT INTO volunteer_profiles "
                    f"(userID, {cols}) VALUES (?, {placeholders})",
                    (userID, *fields.values()),
                )
            else:
                fields = {
                    k: profile.get(k, "")
                    for k in ORGANIZATION_COLUMNS
                    if k not in ("source_id",)
                }
                fields["org_name"] = (
                    profile.get("org_name", "") or "Unnamed organization"
                )
                cols = ", ".join(fields.keys())
                placeholders = ", ".join("?" for _ in fields)
                self.cursor.execute(
                    f"INSERT INTO organizations "
                    f"(userID, {cols}) VALUES (?, {placeholders})",
                    (userID, *fields.values()),
                )
            self.connection.commit()
            return userID
        except sqlite3.IntegrityError:
            self.connection.rollback()
            return None

    def importVolunteerRoster(self, orgID, volunteers):
        imported, skipped = [], []
        seen = set()
        try:
            with self.connection:
                self.cursor.execute(
                    "SELECT 1 FROM organizations WHERE orgID = ?",
                    (orgID,),
                )
                if not self.cursor.fetchone():
                    raise ValueError("Organization does not exist.")

                for volunteer in volunteers:
                    email = str(volunteer.get("email", "")).strip().lower()
                    code = str(
                        volunteer.get("activation_code", "")
                    ).strip()
                    if not email or not code:
                        skipped.append(
                            (email, "Email and activation code required")
                        )
                        continue
                    if email in seen:
                        skipped.append(
                            (email, "Duplicate email in file")
                        )
                        continue
                    seen.add(email)

                    self.cursor.execute(
                        "SELECT userID FROM users WHERE email = ?",
                        (email,),
                    )
                    if self.cursor.fetchone():
                        skipped.append(
                            (email, "Account already exists")
                        )
                        continue

                    self.cursor.execute(
                        "INSERT INTO users "
                        "(email, password, role, email_verified, mfa_enabled) "
                        "VALUES (?, ?, 'volunteer', 0, 1)",
                        (
                            email,
                            hash_password(secrets.token_urlsafe(32)),
                        ),
                    )
                    userID = self.cursor.lastrowid

                    fields = {
                        k: volunteer.get(k, "")
                        for k in VOLUNTEER_PROFILE_COLUMNS
                    }
                    if not fields.get("state"):
                        fields["state"] = "GA"
                    cols = ", ".join(fields.keys())
                    placeholders = ", ".join("?" for _ in fields)
                    self.cursor.execute(
                        f"INSERT INTO volunteer_profiles "
                        f"(userID, {cols}) VALUES (?, {placeholders})",
                        (userID, *fields.values()),
                    )

                    self.cursor.execute(
                        "INSERT INTO org_members (userID, orgID) "
                        "VALUES (?, ?)",
                        (userID, orgID),
                    )
                    expires = (
                        datetime.now() + timedelta(hours=24)
                    ).isoformat(timespec="seconds")
                    self.cursor.execute(
                        "INSERT INTO volunteer_activation_codes "
                        "(userID, code_hash, expires_at) VALUES (?, ?, ?)",
                        (
                            userID,
                            hashlib.sha256(code.encode()).hexdigest(),
                            expires,
                        ),
                    )
                    imported.append({"userID": userID, "email": email})
        except (sqlite3.Error, ValueError) as e:
            print("importVolunteerRoster error:", e)
            return None
        return {"imported": imported, "skipped": skipped}

    def getMigratedVolunteers(self, orgID):
        self.cursor.execute("""
            SELECT u.userID, u.email, u.email_verified,
                   vp.first_name, vp.last_name, vp.country, vp.zipcode,
                   vp.city, vp.state, vp.high_school,
                   vp.dob, vp.gender, vp.skills, vp.phone
            FROM org_members m
            JOIN users u ON u.userID = m.userID
            LEFT JOIN volunteer_profiles vp ON vp.userID = u.userID
            WHERE m.orgID = ? AND u.role = 'volunteer'
            ORDER BY vp.last_name COLLATE NOCASE,
                     vp.first_name COLLATE NOCASE,
                     u.email COLLATE NOCASE
        """, (orgID,))
        return [dict(row) for row in self.cursor.fetchall()]

    def setVolunteerActivationCode(self, orgID, userID, code):
        expires = (datetime.now() + timedelta(hours=24)).isoformat(
            timespec="seconds"
        )
        try:
            self.cursor.execute("""
                INSERT INTO volunteer_activation_codes
                (userID, code_hash, expires_at)
                SELECT u.userID, ?, ?
                FROM users u
                JOIN org_members m ON m.userID = u.userID
                WHERE u.userID = ? AND u.role = 'volunteer'
                  AND u.email_verified = 0 AND m.orgID = ?
                ON CONFLICT(userID) DO UPDATE SET
                    code_hash = excluded.code_hash,
                    expires_at = excluded.expires_at,
                    attempts = 0
            """, (
                hashlib.sha256(code.encode()).hexdigest(),
                expires, userID, orgID,
            ))
            self.connection.commit()
            return self.cursor.rowcount > 0
        except sqlite3.Error as e:
            self.connection.rollback()
            print("setVolunteerActivationCode error:", e)
            return False

    def activateImportedVolunteer(self, email, code, password):
        email = email.strip().lower()
        if not email or len(code.strip()) != 8 or len(password) < 8:
            return False
        code_hash = hashlib.sha256(code.strip().encode()).hexdigest()
        try:
            with self.connection:
                self.cursor.execute("""
                    SELECT u.userID, a.code_hash, a.expires_at, a.attempts
                    FROM users u
                    JOIN volunteer_activation_codes a
                        ON a.userID = u.userID
                    WHERE u.email = ? AND u.role = 'volunteer'
                      AND u.email_verified = 0
                """, (email,))
                row = self.cursor.fetchone()
                if not row or row["attempts"] >= 5:
                    return False
                if datetime.fromisoformat(row["expires_at"]) < \
                        datetime.now():
                    self.cursor.execute(
                        "DELETE FROM volunteer_activation_codes "
                        "WHERE userID = ?",
                        (row["userID"],),
                    )
                    return False
                if not secrets.compare_digest(
                        row["code_hash"], code_hash):
                    attempts = row["attempts"] + 1
                    if attempts >= 5:
                        self.cursor.execute(
                            "DELETE FROM volunteer_activation_codes "
                            "WHERE userID = ?",
                            (row["userID"],),
                        )
                    else:
                        self.cursor.execute(
                            "UPDATE volunteer_activation_codes "
                            "SET attempts = ? WHERE userID = ?",
                            (attempts, row["userID"]),
                        )
                    return False
                self.cursor.execute(
                    "UPDATE users SET password = ?, email_verified = 1 "
                    "WHERE userID = ?",
                    (hash_password(password), row["userID"]),
                )
                self.cursor.execute(
                    "DELETE FROM volunteer_activation_codes "
                    "WHERE userID = ?",
                    (row["userID"],),
                )
                return True
        except (sqlite3.Error, ValueError) as e:
            print("activateImportedVolunteer error:", e)
            return False

    def updateOrganizationProfile(self, userID, orgID, fields):
        allowed = set(ORGANIZATION_COLUMNS) - {"source_id"}
        updates = [
            (key, value) for key, value in fields.items()
            if key in allowed
        ]
        if not updates:
            return False
        try:
            assignments = ", ".join(
                f"{key} = ?" for key, _ in updates
            )
            values = [value for _, value in updates] + [orgID, userID]
            self.cursor.execute(
                f"UPDATE organizations SET {assignments} "
                "WHERE orgID = ? AND userID = ?",
                values,
            )
            self.connection.commit()
            return self.cursor.rowcount > 0
        except sqlite3.Error as e:
            self.connection.rollback()
            print("updateOrganizationProfile error:", e)
            return False

    def updateImportedVolunteerProfile(self, orgID, userID, fields):
        allowed = set(VOLUNTEER_PROFILE_COLUMNS)
        updates = [
            (key, value) for key, value in fields.items()
            if key in allowed
        ]
        if not updates:
            return False
        try:
            self.cursor.execute(
                "SELECT 1 FROM org_members WHERE orgID = ? AND userID = ?",
                (orgID, userID),
            )
            if not self.cursor.fetchone():
                return False
            assignments = ", ".join(
                f"{key} = ?" for key, _ in updates
            )
            values = [value for _, value in updates] + [userID]
            self.cursor.execute(
                f"UPDATE volunteer_profiles SET {assignments} "
                "WHERE userID = ?",
                values,
            )
            self.connection.commit()
            return self.cursor.rowcount > 0
        except sqlite3.Error as e:
            self.connection.rollback()
            print("updateImportedVolunteerProfile error:", e)
            return False

    def email_exists(self, email):
        self.cursor.execute(
            "SELECT 1 FROM users WHERE email = ?",
            (email.strip().lower(),),
        )
        return self.cursor.fetchone() is not None

    def getUserByEmail(self, email):
        self.cursor.execute(
            "SELECT userID, email, role FROM users WHERE email = ?",
            (email.strip().lower(),),
        )
        row = self.cursor.fetchone()
        return dict(row) if row else None

    def authenticate(self, email, password):
        self.cursor.execute(
            "SELECT userID, email, password, role, email_verified, "
            "mfa_enabled "
            "FROM users WHERE email = ?",
            (email.strip().lower(),),
        )
        row = self.cursor.fetchone()
        if not row or not verify_password(password, row["password"]):
            return None
        return self.get_user_profile(row["userID"])

    def get_user_profile(self, userID):
        self.cursor.execute(
            "SELECT userID, email, role, email_verified, mfa_enabled, "
            "created_at "
            "FROM users WHERE userID = ?",
            (userID,),
        )
        user = self.cursor.fetchone()
        if not user:
            return None
        result = dict(user)
        if user["role"] == "volunteer":
            self.cursor.execute(
                "SELECT * FROM volunteer_profiles WHERE userID = ?",
                (userID,),
            )
            prof = self.cursor.fetchone()
            if prof:
                result.update(dict(prof))
        elif user["role"] == "org":
            self.cursor.execute(
                "SELECT * FROM organizations WHERE userID = ?",
                (userID,),
            )
            org = self.cursor.fetchone()
            if org:
                result.update(dict(org))
        return result

    def getUserProfile(self, userID):
        return self.get_user_profile(userID)

    def updateUserProfile(self, userID, fields):
        return self.update_volunteer_profile(userID, **fields)

    def changePassword(self, userID, old, new):
        self.cursor.execute(
            "SELECT password FROM users WHERE userID = ?", (userID,)
        )
        row = self.cursor.fetchone()
        if not row or not verify_password(old, row["password"]):
            return False
        self.cursor.execute(
            "UPDATE users SET password = ? WHERE userID = ?",
            (hash_password(new), userID),
        )
        self.connection.commit()
        return True

    def set_mfa_enabled(self, userID, enabled: bool):
        self.cursor.execute(
            "UPDATE users SET mfa_enabled = ? WHERE userID = ?",
            (1 if enabled else 0, userID),
        )
        self.connection.commit()

    def update_volunteer_profile(self, userID, **fields):
        allowed = set(VOLUNTEER_PROFILE_COLUMNS)
        sets, params = [], []
        for k, v in fields.items():
            if k in allowed:
                sets.append(f"{k} = ?")
                params.append(v)
        if not sets:
            return False
        params.append(userID)
        self.cursor.execute(
            f"UPDATE volunteer_profiles SET {', '.join(sets)} "
            "WHERE userID = ?",
            params,
        )
        self.connection.commit()
        return True

    # ── Volunteer location helpers ────────────────────────────────────
    def searchVolunteersByCity(self, city, state="GA"):
        """Return volunteers matching a Georgia city (and state)."""
        self.cursor.execute("""
            SELECT u.userID, u.email, vp.first_name, vp.last_name,
                   vp.city, vp.state, vp.high_school
            FROM volunteer_profiles vp
            JOIN users u ON u.userID = vp.userID
            WHERE vp.city = ? AND (vp.state = ? OR ? = '')
            ORDER BY vp.last_name COLLATE NOCASE,
                     vp.first_name COLLATE NOCASE
        """, (city, state, state))
        return self.cursor.fetchall()

    def searchVolunteersByHighSchool(self, high_school):
        self.cursor.execute("""
            SELECT u.userID, u.email, vp.first_name, vp.last_name,
                   vp.city, vp.state, vp.high_school
            FROM volunteer_profiles vp
            JOIN users u ON u.userID = vp.userID
            WHERE vp.high_school = ?
            ORDER BY vp.last_name COLLATE NOCASE,
                     vp.first_name COLLATE NOCASE
        """, (high_school,))
        return self.cursor.fetchall()

    # ── Organizations ─────────────────────────────────────────────────
    def get_or_create_organization(self, org_name, source_id=None,
                                    description=None, website_link=None,
                                    city=None, country=None):
        if source_id:
            self.cursor.execute(
                "SELECT orgID FROM organizations WHERE source_id = ?",
                (source_id,),
            )
            row = self.cursor.fetchone()
            if row:
                return row["orgID"]

        if org_name:
            self.cursor.execute(
                "SELECT orgID FROM organizations "
                "WHERE org_name = ? AND source_id IS NULL",
                (org_name,),
            )
            row = self.cursor.fetchone()
            if row:
                return row["orgID"]

        if not org_name and not source_id:
            return None

        try:
            self.cursor.execute(
                "INSERT INTO organizations "
                "(userID, org_name, source_id, description, "
                "website_link, city, country) "
                "VALUES (NULL, ?, ?, ?, ?, ?, ?)",
                (org_name or "Unknown organization", source_id,
                 description, website_link, city, country),
            )
            self.connection.commit()
            return self.cursor.lastrowid
        except sqlite3.Error as e:
            print("get_or_create_organization error:", e)
            return None

    def get_or_create_external_org(self, org_name: str) -> int:
        return self.get_or_create_organization(
            org_name,
            description="Imported via Volunteer Connector",
        )

    def getOrganizations(self, userID):
        self.cursor.execute("""
            SELECT o.orgID AS organizationID, o.org_name AS name,
                   o.description, o.website_link, o.city, o.country,
                   o.source_id, o.org_type, o.accepting_volunteers,
                   o.remote_friendly, o.service_area,
                   CASE WHEN m.memberID IS NULL THEN 0 ELSE 1 END
                       AS is_member
            FROM organizations o
            LEFT JOIN org_members m
                ON m.orgID = o.orgID AND m.userID = ?
            ORDER BY is_member DESC, o.org_name ASC
        """, (userID,))
        return self.cursor.fetchall()
    def searchOrganizations(self, keyword="", city=None, state="GA",
                        cluster_list=None, accepting_only=False,
                        limit=500):
        """
        Public org directory query. Works for guests (no login needed)
        and for logged-in volunteers.

        - keyword: matched against org_name, description,
          needs_volunteers_for, service_area
        - city: Georgia city name; matches org.city or falls back to
          service_area text
        - cluster_list: list of career cluster names; org must have
          at least one of them
        - accepting_only: only orgs flagged accepting_volunteers = 1
        """
        conditions = ["1=1"]
        params = []

        if keyword:
            like = f"%{keyword}%"
            conditions.append(
                "(o.org_name LIKE ? OR o.description LIKE ? "
                " OR o.needs_volunteers_for LIKE ? "
                " OR o.service_area LIKE ?)"
            )
            params.extend([like] * 4)

        if city and city not in ("All cities", ""):
            conditions.append(
                "(o.city = ? OR o.service_area LIKE ?)"
            )
            params.extend([city, f"%{city}%"])

        if accepting_only:
            conditions.append(
                "COALESCE(o.accepting_volunteers, 1) = 1"
            )

        if cluster_list:
            cluster_list = [
                c for c in cluster_list
                if c and c not in ("All clusters", "All Causes")
            ]
            if cluster_list:
                placeholders = ", ".join("?" for _ in cluster_list)
                conditions.append(f"""
                    o.orgID IN (
                        SELECT oc.orgID
                        FROM organization_clusters oc
                        JOIN career_clusters c
                            ON c.clusterID = oc.clusterID
                        WHERE c.name IN ({placeholders})
                    )
                """)
                params.extend(cluster_list)

        q = """
            SELECT o.orgID, o.org_name, o.description, o.website_link,
                   o.city, o.country, o.org_type,
                   o.accepting_volunteers, o.remote_friendly,
                   o.service_area, o.needs_volunteers_for,
                   o.contact_person, o.contact_phone, o.source_id,
                   o.userID,
                   CASE WHEN o.userID IS NULL THEN 0 ELSE 1 END
                       AS is_moxie_org,
                   (SELECT COUNT(*) FROM opportunities op
                    WHERE op.orgID = o.orgID
                      AND COALESCE(op.status, 'open') != 'cancelled'
                      AND (op.event_date IS NULL OR
                           COALESCE(op.event_end_date, op.event_date)
                           >= date('now'))
                   ) AS active_opportunities
            FROM organizations o
            WHERE """ + " AND ".join(conditions) + """
            ORDER BY active_opportunities DESC,
                     o.org_name COLLATE NOCASE ASC
            LIMIT ?
        """
        params.append(limit)
        self.cursor.execute(q, params)
        return self.cursor.fetchall()

    def joinOrganization(self, userID, orgID):
        try:
            self.cursor.execute(
                "INSERT INTO org_members (userID, orgID) VALUES (?, ?)",
                (userID, orgID),
            )
            self.connection.commit()
            return True
        except sqlite3.IntegrityError:
            return True
        except sqlite3.Error as e:
            print("joinOrganization error:", e)
            return False

    def leaveOrganization(self, userID, orgID):
        self.cursor.execute(
            "DELETE FROM org_members WHERE userID = ? AND orgID = ?",
            (userID, orgID),
        )
        self.connection.commit()
        return self.cursor.rowcount > 0

    def getUserOrgColors(self, userID):
        self.cursor.execute(
            "SELECT orgID, color FROM user_org_colors WHERE userID = ?",
            (userID,),
        )
        return {r["orgID"]: r["color"] for r in self.cursor.fetchall()}

    def setUserOrgColor(self, userID, orgID, color):
        try:
            self.cursor.execute("""
                INSERT INTO user_org_colors (userID, orgID, color)
                VALUES (?, ?, ?)
                ON CONFLICT(userID, orgID)
                DO UPDATE SET color = excluded.color
            """, (userID, orgID, color))
            self.connection.commit()
            return True
        except sqlite3.Error as e:
            print("setUserOrgColor error:", e)
            return False

    def clearUserOrgColor(self, userID, orgID):
        self.cursor.execute(
            "DELETE FROM user_org_colors WHERE userID = ? AND orgID = ?",
            (userID, orgID),
        )
        self.connection.commit()
        return self.cursor.rowcount > 0

    # ── Opportunities ─────────────────────────────────────────────────
    def _opportunity_base_query(self):
        return """
            SELECT o.*,
                   COALESCE(o.website_link, org.website_link)
                       AS website_link_resolved,
                   org.org_name, org.orgID,
                   CASE WHEN org.userID IS NULL THEN 0 ELSE 1 END
                       AS is_moxie_org,
                   CASE WHEN org.userID IS NULL THEN 1 ELSE 0 END
                       AS is_external,
                   (SELECT COUNT(*) FROM event_signups s
                    WHERE s.opportunityID = o.opportunityID
                      AND s.status = 'registered') AS registered_count
            FROM opportunities o
            LEFT JOIN organizations org ON o.orgID = org.orgID
        """

    def getAllOpportunitiesWithLinks(self, limit=500):
        self.cursor.execute(
            self._opportunity_base_query() +
            " ORDER BY o.event_date ASC LIMIT ?", (limit,),
        )
        return self.cursor.fetchall()

    def getAllOpportunities(self, limit=500):
        today = datetime.now().strftime("%Y-%m-%d")
        self.cursor.execute(
            self._opportunity_base_query() +
            " WHERE COALESCE(o.status, 'open') != 'cancelled' "
            " AND (o.event_date IS NULL OR "
            "      COALESCE(o.event_end_date, o.event_date) >= ?) "
            " ORDER BY o.event_date ASC LIMIT ?",
            (today, limit),
        )
        return self.cursor.fetchall()

    def getSoonestOpportunities(self, limit=10):
        today = datetime.now().strftime("%Y-%m-%d")
        self.cursor.execute(
            self._opportunity_base_query() + " "
            "WHERE o.event_date IS NOT NULL AND o.event_date >= ? "
            "AND COALESCE(o.status, 'open') != 'cancelled' "
            "ORDER BY o.event_date ASC LIMIT ?",
            (today, limit),
        )
        return self.cursor.fetchall()

    def getNewestOpportunities(self, limit=10):
        today = datetime.now().strftime("%Y-%m-%d")
        self.cursor.execute(
            self._opportunity_base_query() + " "
            "WHERE COALESCE(o.status, 'open') != 'cancelled' "
            "AND (o.event_date IS NULL OR "
            "     COALESCE(o.event_end_date, o.event_date) >= ?) "
            "ORDER BY o.created_at DESC LIMIT ?",
            (today, limit),
        )
        return self.cursor.fetchall()

    def getRemoteOpportunities(self, limit=10):
        today = datetime.now().strftime("%Y-%m-%d")
        self.cursor.execute(
            self._opportunity_base_query() + " "
            "WHERE o.is_remote = 1 "
            "AND COALESCE(o.status, 'open') != 'cancelled' "
            "AND (o.event_date IS NULL OR "
            "     COALESCE(o.event_end_date, o.event_date) >= ?) "
            "ORDER BY o.event_date ASC LIMIT ?",
            (today, limit),
        )
        return self.cursor.fetchall()

    def getOpportunitiesByOrg(self, orgID):
        self.cursor.execute(
            self._opportunity_base_query() +
            " WHERE o.orgID = ? ORDER BY o.event_date ASC",
            (orgID,),
        )
        return self.cursor.fetchall()

    def getOpportunityByID(self, opportunityID):
        self.cursor.execute(
            self._opportunity_base_query() +
            " WHERE o.opportunityID = ?",
            (opportunityID,),
        )
        return self.cursor.fetchone()

    def getDistinctCategories(self):
        self.cursor.execute("""
            SELECT DISTINCT category FROM opportunities
            WHERE category IS NOT NULL AND category != ''
            ORDER BY category ASC
        """)
        return [r["category"] for r in self.cursor.fetchall()]

    def searchOpportunitiesFiltered(
        self, keyword="", type_filter="All", location="",
        category="All Causes", date_from=None, date_to=None,
        upcoming_only=True, limit=1000,
        cluster=None, clusters=None, city=None, high_school=None,
        state="GA", zipcode=None,
        min_age=None, max_age=None, meal_provided=None,
        remote_only=False, org_id=None,
    ):
        """
        Filter opportunities.

        `clusters` accepts a list of career cluster names (what the
        filter bar sends). `cluster` accepts a single name for backward
        compatibility. Both are handled — pass either or neither.
        """
        conditions, params = [], []

        # ── Keyword ───────────────────────────────────────────────────
        if keyword:
            like = f"%{keyword}%"
            conditions.append(
                "(o.title LIKE ? OR o.description LIKE ? "
                " OR o.location LIKE ? OR o.address LIKE ? "
                " OR o.meeting_point LIKE ? "
                " OR org.org_name LIKE ? OR o.category LIKE ?)"
            )
            params.extend([like] * 7)

        # ── In-person / remote ────────────────────────────────────────
        if type_filter == "Remote" or remote_only:
            conditions.append("o.is_remote = 1")
        elif type_filter == "In-person":
            conditions.append("o.is_remote = 0")

        # ── Free-text location (legacy; kept for caller compat) ──────
        if location:
            like = f"%{location}%"
            conditions.append(
                "(o.location LIKE ? OR o.address LIKE ? "
                " OR o.city LIKE ? OR o.meeting_point LIKE ?)"
            )
            params.extend([like, like, like, like])

        # ── Legacy single-category filter ────────────────────────────
        if category and category != "All Causes":
            conditions.append("o.category = ?")
            params.append(category)

        # ── Date range ────────────────────────────────────────────────
        if date_from:
            end_col = "COALESCE(o.event_end_date, o.event_date)"
            conditions.append(f"{end_col} >= ?")
            params.append(date_from)

        if date_to:
            conditions.append("o.event_date <= ?")
            params.append(date_to)

        if upcoming_only:
            today = datetime.now().strftime("%Y-%m-%d")
            conditions.append(
                "(o.event_date IS NULL OR "
                "COALESCE(o.event_end_date, o.event_date) >= ?)"
            )
            params.append(today)

        # ── Career clusters (multi-select) ────────────────────────────
        cluster_names = []
        if clusters:
            cluster_names = [
                c for c in clusters
                if c and c not in ("All clusters", "All Causes")
            ]
        elif cluster and cluster not in ("All clusters", "All Causes"):
            cluster_names = [cluster]

        if cluster_names:
            placeholders = ", ".join("?" for _ in cluster_names)
            conditions.append(f"""
                o.opportunityID IN (
                    SELECT oc.opportunityID
                    FROM opportunity_clusters oc
                    JOIN career_clusters c ON c.clusterID = oc.clusterID
                    WHERE c.name IN ({placeholders})
                )
            """)
            params.extend(cluster_names)

        # ── Georgia city ──────────────────────────────────────────────
        if city and city not in ("All cities", ""):
            conditions.append("(o.city = ? OR o.location LIKE ?)")
            params.extend([city, f"%{city}%"])

        # ── State ─────────────────────────────────────────────────────
        if state and state not in ("All states", ""):
            conditions.append("(o.state = ? OR o.state IS NULL)")
            params.append(state)

        # ── High school ───────────────────────────────────────────────
        if high_school and high_school not in ("All schools", ""):
            conditions.append(
                "(o.high_school = ? OR o.high_school LIKE ? "
                " OR o.description LIKE ?)"
            )
            params.extend([high_school, f"%{high_school}%",
                           f"%{high_school}%"])

        # ── ZIP code (string match against address / location) ────────
        if zipcode:
            z = f"%{zipcode.strip()}%"
            conditions.append(
                "(o.address LIKE ? OR o.location LIKE ? "
                " OR o.meeting_point LIKE ?)"
            )
            params.extend([z, z, z])

        # ── Optional extras ───────────────────────────────────────────
        if org_id is not None:
            conditions.append("o.orgID = ?")
            params.append(org_id)

        if meal_provided is not None:
            conditions.append("COALESCE(o.meal_provided, 0) = ?")
            params.append(1 if meal_provided else 0)

        # ── Never show cancelled ──────────────────────────────────────
        conditions.append("COALESCE(o.status, 'open') != 'cancelled'")

        q = self._opportunity_base_query()
        if conditions:
            q += " WHERE " + " AND ".join(conditions)
        q += " ORDER BY o.event_date ASC LIMIT ?"
        params.append(limit)

        self.cursor.execute(q, params)
        return self.cursor.fetchall()
    def searchOpportunities(self, keyword, category="All", limit=25):
        return self.searchOpportunitiesFiltered(
            keyword=keyword, type_filter=category, limit=limit
        )

    def addOpportunity(self, orgID, title, description, category, location,
                       address, is_remote, event_date, thumbnail=None,
                       start_time=None, end_time=None, capacity=None,
                       status="open", required_skills=None,
                       contact_name=None, contact_email=None,
                       website_link=None, event_end_date=None,
                       city=None, state="GA", high_school=None,
                       latitude=None, longitude=None,
                       timezone="America/New_York",
                       min_age=None, max_age=None,
                       min_grade=None, max_grade=None,
                       meeting_point=None, parking_info=None,
                       accessibility_notes=None,
                       what_to_bring=None, dress_code=None,
                       meal_provided=0, background_check_required=0,
                       training_required=0, training_description=None):
        try:
            self.cursor.execute("""
                INSERT INTO opportunities (
                    orgID, title, description, category, location, address,
                    is_remote, event_date, event_end_date, start_time,
                    end_time, capacity, status, required_skills,
                    contact_name, contact_email, thumbnail, website_link,
                    city, state, high_school, latitude, longitude,
                    timezone, min_age, max_age, min_grade, max_grade,
                    meeting_point, parking_info, accessibility_notes,
                    what_to_bring, dress_code, meal_provided,
                    background_check_required, training_required,
                    training_description
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                        ?, ?, ?, ?, ?)
            """, (
                orgID, title, description, category, location, address,
                1 if is_remote else 0, event_date, event_end_date,
                start_time, end_time, capacity, status, required_skills,
                contact_name, contact_email, thumbnail, website_link,
                city, state, high_school, latitude, longitude,
                timezone, min_age, max_age, min_grade, max_grade,
                meeting_point, parking_info, accessibility_notes,
                what_to_bring, dress_code,
                1 if meal_provided else 0,
                1 if background_check_required else 0,
                1 if training_required else 0,
                training_description,
            ))
            self.connection.commit()
            return self.cursor.lastrowid
        except sqlite3.Error as e:
            print("addOpportunity error:", e)
            return None

    def updateOpportunity(self, opportunityID, **fields):
        allowed = set(OPPORTUNITY_COLUMNS) - {"orgID", "source_id"}
        sets, params = [], []
        for k, v in fields.items():
            if k not in allowed:
                continue
            if k in ("is_remote", "meal_provided",
                     "background_check_required", "training_required"):
                v = 1 if v else 0
            sets.append(f"{k} = ?")
            params.append(v)
        if not sets:
            return False
        sets.append("updated_at = CURRENT_TIMESTAMP")
        params.append(opportunityID)
        try:
            self.cursor.execute(
                f"UPDATE opportunities SET {', '.join(sets)} "
                "WHERE opportunityID = ?",
                params,
            )
            self.connection.commit()
            return True
        except sqlite3.Error as e:
            print("updateOpportunity error:", e)
            return False

    # ── Org dashboard helpers ─────────────────────────────────────────
    def getRecentSignupsForOrg(self, orgID, limit=10):
        self.cursor.execute("""
            SELECT s.signupID, s.userID, s.opportunityID, s.status,
                   s.signup_time, vp.first_name, vp.last_name, u.email,
                   o.title, o.event_date
            FROM event_signups s
            JOIN opportunities o ON s.opportunityID = o.opportunityID
            JOIN users u ON s.userID = u.userID
            LEFT JOIN volunteer_profiles vp ON u.userID = vp.userID
            WHERE o.orgID = ? AND s.status = 'registered'
            ORDER BY s.signup_time DESC
            LIMIT ?
        """, (orgID, limit))
        return self.cursor.fetchall()

    def getOrgStats(self, orgID):
        stats = {}
        self.cursor.execute("""
            SELECT COUNT(*) AS total,
                   SUM(CASE WHEN COALESCE(status, 'open') = 'open'
                       THEN 1 ELSE 0 END) AS open_count
            FROM opportunities WHERE orgID = ?
        """, (orgID,))
        row = self.cursor.fetchone()
        stats["total_opportunities"] = row["total"] or 0
        stats["open_opportunities"] = row["open_count"] or 0

        self.cursor.execute("""
            SELECT COUNT(*) AS signups,
                   COALESCE(SUM(s.hours_logged), 0) AS hours,
                   COUNT(DISTINCT s.userID) AS volunteers
            FROM event_signups s
            JOIN opportunities o ON s.opportunityID = o.opportunityID
            WHERE o.orgID = ? AND s.status = 'registered'
        """, (orgID,))
        row = self.cursor.fetchone()
        stats["total_signups"] = row["signups"] or 0
        stats["total_hours"] = float(row["hours"] or 0)
        stats["unique_volunteers"] = row["volunteers"] or 0
        return stats

    def getUpcomingForOrg(self, orgID, limit=3):
        today = datetime.now().strftime("%Y-%m-%d")
        self.cursor.execute("""
            SELECT opportunityID, title, event_date, event_end_date,
                   start_time, end_time, capacity, city, state,
                   meeting_point,
                   (SELECT COUNT(*) FROM event_signups s
                    WHERE s.opportunityID = opportunities.opportunityID
                      AND s.status = 'registered') AS registered_count
            FROM opportunities
            WHERE orgID = ?
              AND COALESCE(status, 'open') = 'open'
              AND (event_date IS NULL OR
                   COALESCE(event_end_date, event_date) >= ?)
            ORDER BY event_date ASC
            LIMIT ?
        """, (orgID, today, limit))
        return self.cursor.fetchall()

    # ── Signups ───────────────────────────────────────────────────────
    def registerForOpportunity(self, userID, opportunityID):
        try:
            self.cursor.execute(
                "SELECT capacity, COALESCE(status, 'open') AS status "
                "FROM opportunities WHERE opportunityID = ?",
                (opportunityID,),
            )
            row = self.cursor.fetchone()
            if not row:
                return "error"
            if row["status"] != "open":
                return "full"
            if row["capacity"] is not None:
                self.cursor.execute(
                    "SELECT COUNT(*) AS c FROM event_signups "
                    "WHERE opportunityID = ? AND status = 'registered'",
                    (opportunityID,),
                )
                if self.cursor.fetchone()["c"] >= row["capacity"]:
                    return "full"

            self.cursor.execute("""
                INSERT INTO event_signups
                (userID, opportunityID, status)
                VALUES (?, ?, 'registered')
            """, (userID, opportunityID))
            self.connection.commit()
            return "ok"
        except sqlite3.IntegrityError:
            return "duplicate"
        except sqlite3.Error as e:
            print("registerForOpportunity error:", e)
            return "error"

    def cancelSignup(self, userID, opportunityID):
        self.cursor.execute("""
            UPDATE event_signups SET status = 'cancelled'
            WHERE userID = ? AND opportunityID = ?
        """, (userID, opportunityID))
        self.connection.commit()
        return self.cursor.rowcount > 0

    def checkIn(self, userID, opportunityID):
        now = datetime.now().isoformat(timespec="seconds")
        self.cursor.execute("""
            UPDATE event_signups SET check_in_time = ?
            WHERE userID = ? AND opportunityID = ?
              AND status = 'registered' AND check_in_time IS NULL
        """, (now, userID, opportunityID))
        self.connection.commit()
        return self.cursor.rowcount > 0

    def checkOut(self, userID, opportunityID):
        now = datetime.now().isoformat(timespec="seconds")
        self.cursor.execute("""
            UPDATE event_signups
            SET check_out_time = ?,
                hours_logged = ROUND(
                    (julianday(?) - julianday(check_in_time)) * 24.0, 2
                )
            WHERE userID = ? AND opportunityID = ?
              AND status = 'registered'
              AND check_in_time IS NOT NULL AND check_out_time IS NULL
        """, (now, now, userID, opportunityID))
        self.connection.commit()
        return self.cursor.rowcount > 0

    def getSignupsForVolunteer(self, userID):
        self.cursor.execute("""
            SELECT s.*, o.title, o.event_date, o.event_end_date,
                   o.start_time, o.end_time,
                   o.location, o.city, o.state, o.meeting_point,
                   o.is_remote, o.category,
                   o.required_skills, org.org_name
            FROM event_signups s
            JOIN opportunities o ON s.opportunityID = o.opportunityID
            LEFT JOIN organizations org ON o.orgID = org.orgID
            WHERE s.userID = ?
            ORDER BY o.event_date DESC
        """, (userID,))
        return self.cursor.fetchall()

    def getSignup(self, userID, opportunityID):
        self.cursor.execute("""
            SELECT * FROM event_signups
            WHERE userID = ? AND opportunityID = ?
        """, (userID, opportunityID))
        return self.cursor.fetchone()

    def getSignupsForOpportunity(self, opportunityID):
        self.cursor.execute("""
            SELECT s.*, u.email, vp.first_name, vp.last_name,
                   vp.city, vp.state, vp.high_school, vp.phone
            FROM event_signups s
            JOIN users u ON s.userID = u.userID
            LEFT JOIN volunteer_profiles vp ON u.userID = vp.userID
            WHERE s.opportunityID = ? AND s.status = 'registered'
            ORDER BY s.signup_time ASC
        """, (opportunityID,))
        return self.cursor.fetchall()

    def getSignupsForOpportunityDetailed(self, opportunityID):
        self.cursor.execute("""
            SELECT s.signupID, s.userID, s.status, s.signup_time,
                   s.check_in_time, s.check_out_time, s.hours_logged,
                   s.verified, s.verified_at, s.verified_by,
                   s.no_show, s.org_notes,
                   u.email, vp.first_name, vp.last_name, vp.phone,
                   vp.city, vp.state, vp.high_school
            FROM event_signups s
            JOIN users u ON s.userID = u.userID
            LEFT JOIN volunteer_profiles vp ON u.userID = vp.userID
            WHERE s.opportunityID = ? AND s.status = 'registered'
            ORDER BY vp.last_name ASC, vp.first_name ASC
        """, (opportunityID,))
        return self.cursor.fetchall()

    # ── Org volunteer management ──────────────────────────────────────
    def getOrgVolunteers(self, orgID):
        self.cursor.execute("""
            SELECT u.userID, u.email, u.email_verified,
                   vp.first_name, vp.last_name, vp.phone, vp.skills,
                   vp.city, vp.state, vp.high_school,
                   COALESCE(stats.total_signups, 0) AS total_signups,
                   COALESCE(stats.total_hours, 0) AS total_hours,
                   COALESCE(stats.no_shows, 0) AS no_shows,
                   stats.last_event_date,
                   COALESCE(f.banned, 0) AS banned
            FROM (
                SELECT userID FROM org_members WHERE orgID = ?
                UNION
                SELECT DISTINCT s.userID
                FROM event_signups s
                JOIN opportunities o ON o.opportunityID = s.opportunityID
                WHERE o.orgID = ? AND s.status = 'registered'
            ) roster
            JOIN users u ON u.userID = roster.userID
            LEFT JOIN volunteer_profiles vp ON u.userID = vp.userID
            LEFT JOIN org_volunteer_flags f
                ON f.orgID = ? AND f.userID = u.userID
            LEFT JOIN (
                SELECT s.userID,
                       COUNT(s.signupID) AS total_signups,
                       SUM(CASE WHEN s.no_show = 0
                           THEN s.hours_logged ELSE 0 END)
                           AS total_hours,
                       SUM(CASE WHEN s.no_show = 1 THEN 1 ELSE 0 END)
                           AS no_shows,
                       MAX(o.event_date) AS last_event_date
                FROM event_signups s
                JOIN opportunities o ON o.opportunityID = s.opportunityID
                WHERE o.orgID = ? AND s.status = 'registered'
                GROUP BY s.userID
            ) stats ON stats.userID = u.userID
            WHERE u.role = 'volunteer'
            ORDER BY total_hours DESC, u.userID ASC
        """, (orgID, orgID, orgID, orgID))
        return self.cursor.fetchall()

    def getVolunteerHistoryForOrg(self, orgID, userID):
        self.cursor.execute("""
            SELECT s.signupID, s.opportunityID, s.status, s.signup_time,
                   s.check_in_time, s.check_out_time, s.hours_logged,
                   s.verified, s.no_show, s.org_notes,
                   o.title, o.event_date, o.event_end_date,
                   o.start_time, o.end_time, o.location, o.is_remote,
                   o.category
            FROM event_signups s
            JOIN opportunities o ON s.opportunityID = o.opportunityID
            WHERE o.orgID = ? AND s.userID = ?
            ORDER BY o.event_date DESC
        """, (orgID, userID))
        return self.cursor.fetchall()

    def getVolunteerProfileForOrg(self, orgID, userID):
        self.cursor.execute("""
            SELECT u.userID, u.email,
                   vp.first_name, vp.last_name, vp.phone, vp.skills,
                   vp.country, vp.zipcode, vp.dob, vp.gender,
                   vp.city, vp.state, vp.high_school,
                   vp.emergency_contact_name, vp.emergency_contact_phone,
                   vp.emergency_contact_relationship,
                   COALESCE(f.banned, 0) AS banned
            FROM users u
            LEFT JOIN volunteer_profiles vp ON u.userID = vp.userID
            LEFT JOIN org_volunteer_flags f
                ON f.orgID = ? AND f.userID = u.userID
            WHERE u.userID = ?
        """, (orgID, userID))
        row = self.cursor.fetchone()
        return dict(row) if row else None

    def getVolunteerNotes(self, orgID, userID):
        self.cursor.execute("""
            SELECT noteID, note, tag, created_at
            FROM org_volunteer_notes
            WHERE orgID = ? AND userID = ?
            ORDER BY created_at DESC
        """, (orgID, userID))
        return self.cursor.fetchall()

    def addVolunteerNote(self, orgID, userID, note, tag=None):
        try:
            self.cursor.execute(
                "INSERT INTO org_volunteer_notes "
                "(orgID, userID, note, tag) VALUES (?, ?, ?, ?)",
                (orgID, userID, (note or "").strip(), tag),
            )
            self.connection.commit()
            return self.cursor.lastrowid
        except sqlite3.Error as e:
            print("addVolunteerNote error:", e)
            return None

    def deleteVolunteerNote(self, noteID):
        self.cursor.execute(
            "DELETE FROM org_volunteer_notes WHERE noteID = ?",
            (noteID,),
        )
        self.connection.commit()
        return self.cursor.rowcount > 0

    def setVolunteerBanned(self, orgID, userID, banned):
        try:
            self.cursor.execute("""
                INSERT INTO org_volunteer_flags (orgID, userID, banned)
                VALUES (?, ?, ?)
                ON CONFLICT(orgID, userID)
                DO UPDATE SET banned = excluded.banned
            """, (orgID, userID, 1 if banned else 0))
            self.connection.commit()
            return True
        except sqlite3.Error as e:
            print("setVolunteerBanned error:", e)
            return False

    def verifySignupHours(self, signupID, verifiedBy, hours=None):
        try:
            if hours is not None:
                hours = float(hours)
                if not math.isfinite(hours) or hours < 0:
                    return False
            if hours is None:
                self.cursor.execute("""
                    UPDATE event_signups
                    SET verified = 1, verified_by = ?,
                        verified_at = CURRENT_TIMESTAMP
                    WHERE signupID = ? AND status = 'registered'
                      AND no_show = 0
                """, (verifiedBy, signupID))
            else:
                self.cursor.execute("""
                    UPDATE event_signups
                    SET verified = 1, verified_by = ?,
                        verified_at = CURRENT_TIMESTAMP,
                        hours_logged = ?
                    WHERE signupID = ? AND status = 'registered'
                      AND no_show = 0
                """, (verifiedBy, float(hours), signupID))
            self.connection.commit()
            return self.cursor.rowcount > 0
        except sqlite3.Error as e:
            print("verifySignupHours error:", e)
            return False
        except (TypeError, ValueError):
            return False

    def unverifySignup(self, signupID):
        self.cursor.execute("""
            UPDATE event_signups
            SET verified = 0, verified_by = NULL, verified_at = NULL
            WHERE signupID = ?
        """, (signupID,))
        self.connection.commit()
        return self.cursor.rowcount > 0

    def setSignupNoShow(self, signupID, no_show):
        self.cursor.execute(
            "UPDATE event_signups SET no_show = ? WHERE signupID = ? "
            "AND status = 'registered' "
            "AND (? = 1 OR check_in_time IS NULL)",
            (1 if no_show else 0, signupID, 1 if no_show else 0),
        )
        self.connection.commit()
        return self.cursor.rowcount > 0

    def setSignupOrgNotes(self, signupID, notes):
        self.cursor.execute(
            "UPDATE event_signups SET org_notes = ? WHERE signupID = ?",
            (notes, signupID),
        )
        self.connection.commit()
        return self.cursor.rowcount > 0

    def addManualSignup(self, orgID, opportunityID, userID):
        try:
            self.cursor.execute("""
                INSERT INTO event_signups
                (userID, opportunityID, status, signup_time)
                VALUES (?, ?, 'registered', CURRENT_TIMESTAMP)
            """, (userID, opportunityID))
            self.connection.commit()
            return self.cursor.lastrowid
        except sqlite3.IntegrityError:
            return "duplicate"
        except sqlite3.Error as e:
            print("addManualSignup error:", e)
            return None

    # ── Reports ───────────────────────────────────────────────────────
    def getOrgHoursReport(self, orgID, date_from=None, date_to=None,
                          volunteer_id=None, opportunity_id=None):
        conditions = ["o.orgID = ?"]
        params = [orgID]

        if date_from:
            conditions.append(
                "COALESCE(o.event_end_date, o.event_date) >= ?"
            )
            params.append(date_from)
        if date_to:
            conditions.append("o.event_date <= ?")
            params.append(date_to)
        if volunteer_id:
            conditions.append("s.userID = ?")
            params.append(volunteer_id)
        if opportunity_id:
            conditions.append("s.opportunityID = ?")
            params.append(opportunity_id)

        self.cursor.execute(f"""
            SELECT s.signupID, s.signup_time, s.check_in_time,
                   s.check_out_time, s.hours_logged, s.verified,
                   s.no_show, s.status,
                   u.userID, u.email,
                   vp.first_name, vp.last_name, vp.city, vp.state,
                   o.opportunityID, o.title, o.event_date,
                   o.event_end_date, o.category,
                   o.city AS event_city, o.state AS event_state
            FROM event_signups s
            JOIN opportunities o ON s.opportunityID = o.opportunityID
            JOIN users u ON s.userID = u.userID
            LEFT JOIN volunteer_profiles vp ON u.userID = vp.userID
            WHERE {' AND '.join(conditions)}
              AND s.status = 'registered'
            ORDER BY o.event_date DESC, vp.last_name ASC
        """, params)
        return self.cursor.fetchall()

    def getOrgVolunteerLeaderboard(self, orgID, limit=10):
        self.cursor.execute("""
            SELECT u.userID, u.email,
                   vp.first_name, vp.last_name,
                   COALESCE(SUM(CASE WHEN s.no_show = 0
                       THEN s.hours_logged ELSE 0 END), 0) AS hours,
                   COUNT(s.signupID) AS events
            FROM event_signups s
            JOIN opportunities o ON s.opportunityID = o.opportunityID
            JOIN users u ON s.userID = u.userID
            LEFT JOIN volunteer_profiles vp ON u.userID = vp.userID
            WHERE o.orgID = ? AND s.status = 'registered'
            GROUP BY u.userID
            HAVING hours > 0
            ORDER BY hours DESC
            LIMIT ?
        """, (orgID, limit))
        return self.cursor.fetchall()

    # ── Notifications ─────────────────────────────────────────────────
    def addNotification(self, userID, message, type_=None,
                        related_opportunityID=None):
        self.cursor.execute("""
            INSERT INTO notifications
            (userID, message, type, related_opportunityID)
            VALUES (?, ?, ?, ?)
        """, (userID, message, type_, related_opportunityID))
        self.connection.commit()

    def notifyUpcomingSignup(self, signupID, userID, opportunityID,
                             title):
        with self.connection:
            self.cursor.execute("""
                UPDATE event_signups SET reminder_sent = 1
                WHERE signupID = ? AND userID = ?
                  AND status = 'registered' AND reminder_sent = 0
            """, (signupID, userID))
            if not self.cursor.rowcount:
                return False
            self.cursor.execute("""
                INSERT INTO notifications
                (userID, message, type, related_opportunityID)
                VALUES (?, ?, 'event_reminder', ?)
            """, (
                userID,
                f"Reminder: {title} is coming up within 24 hours.",
                opportunityID,
            ))
            return True

    def getNotifications(self, userID, limit=50):
        self.cursor.execute("""
            SELECT n.*,
                   i.status AS invitation_status,
                   i.invitationID AS linked_invitationID
            FROM notifications n
            LEFT JOIN opportunity_invitations i
                ON i.invitationID = n.invitationID
            WHERE n.userID = ?
            ORDER BY n.created_at DESC, n.notificationID DESC LIMIT ?
        """, (userID, limit))
        return self.cursor.fetchall()

    def createOpportunityInvitation(self, orgID, userID, opportunityID):
        try:
            self.connection.execute("BEGIN IMMEDIATE")
            self.cursor.execute(
                "SELECT o.title, o.capacity, org.org_name "
                "FROM opportunities o "
                "JOIN organizations org ON org.orgID = o.orgID "
                "WHERE o.opportunityID = ? AND o.orgID = ? "
                "AND COALESCE(o.status, 'open') = 'open'",
                (opportunityID, orgID),
            )
            opportunity = self.cursor.fetchone()
            if not opportunity:
                self.connection.rollback()
                return "unavailable"

            self.cursor.execute(
                "SELECT 1 FROM users "
                "WHERE userID = ? AND role = 'volunteer'",
                (userID,),
            )
            if not self.cursor.fetchone():
                self.connection.rollback()
                return "invalid_volunteer"

            self.cursor.execute(
                "SELECT status FROM event_signups "
                "WHERE userID = ? AND opportunityID = ?",
                (userID, opportunityID),
            )
            signup = self.cursor.fetchone()
            if signup and signup["status"] == "registered":
                self.connection.rollback()
                return "already_registered"
            if opportunity["capacity"] is not None:
                self.cursor.execute("""
                    SELECT COUNT(*) AS registered_count
                    FROM event_signups
                    WHERE opportunityID = ? AND status = 'registered'
                """, (opportunityID,))
                if (self.cursor.fetchone()["registered_count"]
                        >= opportunity["capacity"]):
                    self.connection.rollback()
                    return "full"

            self.cursor.execute("""
                SELECT invitationID, status
                FROM opportunity_invitations
                WHERE orgID = ? AND userID = ? AND opportunityID = ?
                ORDER BY invitationID DESC LIMIT 1
            """, (orgID, userID, opportunityID))
            invitation = self.cursor.fetchone()
            if invitation and invitation["status"] == "pending":
                self.connection.rollback()
                return "pending"

            self.cursor.execute("""
                INSERT INTO opportunity_invitations
                    (orgID, userID, opportunityID)
                VALUES (?, ?, ?)
            """, (orgID, userID, opportunityID))
            invitationID = self.cursor.lastrowid

            self.cursor.execute("""
                INSERT INTO notifications
                    (userID, message, type, related_opportunityID,
                     invitationID)
                VALUES (?, ?, 'opportunity_invite', ?, ?)
            """, (
                userID,
                f"{opportunity['org_name']} invited you to "
                f"{opportunity['title'] or 'an opportunity'}.",
                opportunityID,
                invitationID,
            ))
            self.connection.commit()
            return "sent"
        except sqlite3.Error as e:
            self.connection.rollback()
            print("createOpportunityInvitation error:", e)
            return "error"

    def respondToOpportunityInvitation(self, userID, invitationID,
                                       accept):
        try:
            self.connection.execute("BEGIN IMMEDIATE")
            self.cursor.execute("""
                SELECT i.status, i.opportunityID, o.capacity,
                       COALESCE(o.status, 'open') AS opportunity_status
                FROM opportunity_invitations i
                JOIN opportunities o
                    ON o.opportunityID = i.opportunityID
                WHERE i.invitationID = ? AND i.userID = ?
            """, (invitationID, userID))
            invitation = self.cursor.fetchone()
            if not invitation:
                self.connection.rollback()
                return "not_found"
            if invitation["status"] != "pending":
                self.connection.rollback()
                return invitation["status"]

            if not accept:
                self.cursor.execute("""
                    UPDATE opportunity_invitations
                    SET status = 'declined',
                        responded_at = CURRENT_TIMESTAMP
                    WHERE invitationID = ? AND status = 'pending'
                """, (invitationID,))
                self.cursor.execute("""
                    UPDATE notifications SET read_at = CURRENT_TIMESTAMP
                    WHERE invitationID = ?
                """, (invitationID,))
                self.connection.commit()
                return "declined"

            if invitation["opportunity_status"] != "open":
                self.connection.rollback()
                return "unavailable"

            opportunityID = invitation["opportunityID"]
            self.cursor.execute("""
                SELECT status FROM event_signups
                WHERE userID = ? AND opportunityID = ?
            """, (userID, opportunityID))
            signup = self.cursor.fetchone()
            if signup and signup["status"] == "registered":
                self.cursor.execute("""
                    UPDATE opportunity_invitations
                    SET status = 'accepted',
                        responded_at = CURRENT_TIMESTAMP
                    WHERE invitationID = ?
                """, (invitationID,))
                self.cursor.execute("""
                    UPDATE notifications SET read_at = CURRENT_TIMESTAMP
                    WHERE invitationID = ?
                """, (invitationID,))
                self.connection.commit()
                return "already_registered"

            if invitation["capacity"] is not None:
                self.cursor.execute("""
                    SELECT COUNT(*) AS registered_count
                    FROM event_signups
                    WHERE opportunityID = ? AND status = 'registered'
                """, (opportunityID,))
                if (self.cursor.fetchone()["registered_count"]
                        >= invitation["capacity"]):
                    self.connection.rollback()
                    return "full"

            if signup:
                self.cursor.execute("""
                    UPDATE event_signups
                    SET status = 'registered',
                        signup_time = CURRENT_TIMESTAMP,
                        check_in_time = NULL,
                        check_out_time = NULL,
                        hours_logged = 0,
                        verified = 0,
                        verified_by = NULL,
                        verified_at = NULL,
                        no_show = 0,
                        reminder_sent = 0
                    WHERE userID = ? AND opportunityID = ?
                """, (userID, opportunityID))
            else:
                self.cursor.execute("""
                    INSERT INTO event_signups
                        (userID, opportunityID, status)
                    VALUES (?, ?, 'registered')
                """, (userID, opportunityID))

            self.cursor.execute("""
                UPDATE opportunity_invitations
                SET status = 'accepted',
                    responded_at = CURRENT_TIMESTAMP
                WHERE invitationID = ? AND status = 'pending'
            """, (invitationID,))
            self.cursor.execute("""
                UPDATE notifications SET read_at = CURRENT_TIMESTAMP
                WHERE invitationID = ?
            """, (invitationID,))
            self.connection.commit()
            return "accepted"
        except sqlite3.Error as e:
            self.connection.rollback()
            print("respondToOpportunityInvitation error:", e)
            return "error"

    def markNotificationRead(self, userID, notificationID):
        self.cursor.execute("""
            UPDATE notifications SET read_at = CURRENT_TIMESTAMP
            WHERE notificationID = ? AND userID = ? AND read_at IS NULL
        """, (notificationID, userID))
        self.connection.commit()
        return self.cursor.rowcount > 0

    def markNotificationsRead(self, userID):
        self.cursor.execute("""
            UPDATE notifications SET read_at = CURRENT_TIMESTAMP
            WHERE userID = ? AND read_at IS NULL
        """, (userID,))
        self.connection.commit()
        return self.cursor.rowcount > 0

    # ── Announcements ─────────────────────────────────────────────────
    def addAnnouncement(self, orgID, title, body, pinned=0):
        title = (title or "").strip()
        body = (body or "").strip()
        if not title or not body:
            return None
        try:
            self.cursor.execute("""
                INSERT INTO announcements (orgID, title, body, pinned)
                VALUES (?, ?, ?, ?)
            """, (orgID, title, body, 1 if pinned else 0))
            ann_id = self.cursor.lastrowid

            recipients = self._announcement_recipients(orgID)
            preview = body[:120] + ("…" if len(body) > 120 else "")
            for uid in recipients:
                self.cursor.execute("""
                    INSERT INTO notifications
                    (userID, message, type, related_opportunityID)
                    VALUES (?, ?, 'announcement', NULL)
                """, (uid, f"{title} — {preview}"))

            self.connection.commit()
            return ann_id
        except sqlite3.Error as e:
            print("addAnnouncement error:", e)
            return None

    def _announcement_recipients(self, orgID):
        ids = set()
        self.cursor.execute(
            "SELECT userID FROM org_members WHERE orgID = ?", (orgID,)
        )
        for r in self.cursor.fetchall():
            ids.add(r["userID"])

        self.cursor.execute("""
            SELECT DISTINCT s.userID
            FROM event_signups s
            JOIN opportunities o ON s.opportunityID = o.opportunityID
            WHERE o.orgID = ? AND s.status = 'registered'
        """, (orgID,))
        for r in self.cursor.fetchall():
            ids.add(r["userID"])
        return ids

    def getAnnouncementsForOrg(self, orgID, limit=50):
        self.cursor.execute("""
            SELECT announcementID, orgID, title, body, pinned, created_at
            FROM announcements WHERE orgID = ?
            ORDER BY pinned DESC, created_at DESC LIMIT ?
        """, (orgID, limit))
        return self.cursor.fetchall()

    def deleteAnnouncement(self, announcementID):
        self.cursor.execute(
            "DELETE FROM announcements WHERE announcementID = ?",
            (announcementID,),
        )
        self.connection.commit()
        return self.cursor.rowcount > 0

    def setAnnouncementPinned(self, announcementID, pinned):
        self.cursor.execute(
            "UPDATE announcements SET pinned = ? "
            "WHERE announcementID = ?",
            (1 if pinned else 0, announcementID),
        )
        self.connection.commit()
        return self.cursor.rowcount > 0

    def getAnnouncementsForVolunteer(self, userID, limit=50):
        self.cursor.execute("""
            SELECT a.announcementID, a.orgID, a.title, a.body,
                   a.pinned, a.created_at, org.org_name,
                   CASE WHEN a.pinned = 1 THEN 0 ELSE 1 END AS pinned_rank
            FROM announcements a
            JOIN organizations org ON a.orgID = org.orgID
            WHERE a.orgID IN (
                SELECT orgID FROM org_members WHERE userID = ?
                UNION
                SELECT DISTINCT o.orgID
                FROM event_signups s
                JOIN opportunities o ON s.opportunityID = o.opportunityID
                WHERE s.userID = ? AND s.status = 'registered'
            )
            ORDER BY pinned_rank ASC, a.created_at DESC
            LIMIT ?
        """, (userID, userID, limit))
        return self.cursor.fetchall()

    # ── Bookmarks ─────────────────────────────────────────────────────
    def toggleBookmark(self, userID, opportunityID):
        try:
            self.cursor.execute(
                "SELECT 1 FROM bookmarks WHERE userID = ? "
                "AND opportunityID = ?",
                (userID, opportunityID),
            )
            if self.cursor.fetchone():
                self.cursor.execute(
                    "DELETE FROM bookmarks WHERE userID = ? "
                    "AND opportunityID = ?",
                    (userID, opportunityID),
                )
                self.connection.commit()
                return "removed"
            self.cursor.execute(
                "INSERT INTO bookmarks (userID, opportunityID) "
                "VALUES (?, ?)",
                (userID, opportunityID),
            )
            self.connection.commit()
            return "added"
        except sqlite3.Error as e:
            print("toggleBookmark error:", e)
            return "error"

    def isBookmarked(self, userID, opportunityID):
        if not userID:
            return False
        self.cursor.execute(
            "SELECT 1 FROM bookmarks WHERE userID = ? "
            "AND opportunityID = ?",
            (userID, opportunityID),
        )
        return self.cursor.fetchone() is not None

    def getBookmarkedOpportunities(self, userID):
        today = datetime.now().strftime("%Y-%m-%d")
        self.cursor.execute(
            self._opportunity_base_query() + """
                JOIN bookmarks b
                    ON b.opportunityID = o.opportunityID
                WHERE b.userID = ?
                  AND COALESCE(o.status, 'open') != 'cancelled'
                  AND (o.event_date IS NULL
                       OR COALESCE(o.event_end_date, o.event_date) >= ?)
                ORDER BY b.created_at DESC
            """,
            (userID, today),
        )
        return self.cursor.fetchall()

    def getBookmarkedIDs(self, userID):
        if not userID:
            return set()
        self.cursor.execute(
            "SELECT opportunityID FROM bookmarks WHERE userID = ?",
            (userID,),
        )
        return {r["opportunityID"] for r in self.cursor.fetchall()}

    # ── Career clusters ───────────────────────────────────────────────
    def getCareerClusters(self):
        self.cursor.execute(
            "SELECT name FROM career_clusters "
            "ORDER BY name COLLATE NOCASE"
        )
        return [r["name"] for r in self.cursor.fetchall()]

    def setOpportunityClusters(self, opportunityID, cluster_names):
        try:
            self.cursor.execute(
                "DELETE FROM opportunity_clusters "
                "WHERE opportunityID = ?",
                (opportunityID,),
            )
            for name in cluster_names:
                self.cursor.execute(
                    "SELECT clusterID FROM career_clusters "
                    "WHERE name = ?",
                    (name,),
                )
                row = self.cursor.fetchone()
                if not row:
                    continue
                self.cursor.execute(
                    "INSERT OR IGNORE INTO opportunity_clusters "
                    "(opportunityID, clusterID) VALUES (?, ?)",
                    (opportunityID, row["clusterID"]),
                )
            self.connection.commit()
            return True
        except sqlite3.Error as e:
            self.connection.rollback()
            print("setOpportunityClusters error:", e)
            return False

    def getOpportunityClusters(self, opportunityID):
        self.cursor.execute(
            "SELECT c.name FROM opportunity_clusters oc "
            "JOIN career_clusters c ON c.clusterID = oc.clusterID "
            "WHERE oc.opportunityID = ?",
            (opportunityID,),
        )
        return [r["name"] for r in self.cursor.fetchall()]

    def setOrganizationClusters(self, orgID, cluster_names):
        try:
            self.cursor.execute(
                "DELETE FROM organization_clusters WHERE orgID = ?",
                (orgID,),
            )
            for name in cluster_names:
                self.cursor.execute(
                    "SELECT clusterID FROM career_clusters "
                    "WHERE name = ?",
                    (name,),
                )
                row = self.cursor.fetchone()
                if not row:
                    continue
                self.cursor.execute(
                    "INSERT OR IGNORE INTO organization_clusters "
                    "(orgID, clusterID) VALUES (?, ?)",
                    (orgID, row["clusterID"]),
                )
            self.connection.commit()
            return True
        except sqlite3.Error as e:
            self.connection.rollback()
            print("setOrganizationClusters error:", e)
            return False

    def getOrganizationClusters(self, orgID):
        self.cursor.execute(
            "SELECT c.name FROM organization_clusters oc "
            "JOIN career_clusters c ON c.clusterID = oc.clusterID "
            "WHERE oc.orgID = ?",
            (orgID,),
        )
        return [r["name"] for r in self.cursor.fetchall()]

    # ── Volunteer match profile ───────────────────────────────────────
    def saveVolunteerMatch(self, userID, location, city, high_school,
                           clusters):
        c = (list(clusters) + ["", "", ""])[:3]
        try:
            self.cursor.execute("""
                INSERT INTO volunteer_match
                  (userID, location, city, high_school,
                   cluster1, cluster2, cluster3, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(userID) DO UPDATE SET
                  location = excluded.location,
                  city = excluded.city,
                  high_school = excluded.high_school,
                  cluster1 = excluded.cluster1,
                  cluster2 = excluded.cluster2,
                  cluster3 = excluded.cluster3,
                  updated_at = CURRENT_TIMESTAMP
            """, (userID, location, city, high_school,
                  c[0], c[1], c[2]))
            self.connection.commit()
            return True
        except sqlite3.Error as e:
            self.connection.rollback()
            print("saveVolunteerMatch error:", e)
            return False

    def getVolunteerMatch(self, userID):
        self.cursor.execute(
            "SELECT * FROM volunteer_match WHERE userID = ?",
            (userID,),
        )
        row = self.cursor.fetchone()
        return dict(row) if row else None

    # ── Backup / restore ──────────────────────────────────────────────
    def backupTo(self, path):
        if os.path.normcase(os.path.realpath(path)) == \
                os.path.normcase(os.path.realpath(self.db_path)):
            raise ValueError(
                "Choose a backup path different from the live database."
            )
        self.connection.commit()
        destination = sqlite3.connect(path)
        try:
            self.connection.backup(destination)
        finally:
            destination.close()

    def restoreFrom(self, path):
        if not os.path.isfile(path):
            raise FileNotFoundError(path)
        if os.path.normcase(os.path.realpath(path)) == \
                os.path.normcase(os.path.realpath(self.db_path)):
            raise ValueError(
                "Choose a backup file different from the live database."
            )
        source = sqlite3.connect(path)
        try:
            if source.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise sqlite3.DatabaseError(
                    "The selected backup failed its integrity check."
                )
            if source.execute("PRAGMA foreign_key_check").fetchone():
                raise sqlite3.DatabaseError(
                    "The selected backup contains invalid references."
                )
            tables = {
                row[0] for row in source.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
            required = {
                "users", "organizations", "opportunities", "event_signups",
            }
            if not required.issubset(tables):
                raise sqlite3.DatabaseError(
                    "The selected file is not a Moxie database backup."
                )
            self.connection.commit()
            source.backup(self.connection)
            self.connection.commit()
            self.createTable()
            self.migrate()
        finally:
            source.close()
        # ── Org-side volunteer recommendations ────────────────────────────
    def getRecommendedVolunteersForOpportunity(self, opportunityID,
                                               limit=8):
        """
        Rank volunteers for a single opportunity using three signals:
          · cluster overlap with the volunteer's match profile (weight 3)
          · same Georgia city as the event (weight 2)
          · already signed up for this org's other events (weight 1)
        Excludes anyone already signed up for this opportunity and
        anyone this org has banned. Returns a list of dicts.
        """
        # 1. What clusters is this opportunity tagged with?
        opp_clusters = set(self.getOpportunityClusters(opportunityID) or [])
        if not opp_clusters:
            return []

        # 2. Event city + org id for the scoring.
        self.cursor.execute(
            "SELECT orgID, city FROM opportunities "
            "WHERE opportunityID = ?",
            (opportunityID,),
        )
        row = self.cursor.fetchone()
        if not row:
            return []
        orgID = row["orgID"]
        event_city = (row["city"] or "").strip()

        # 3. Pull every volunteer + their match profile + ban status
        #    + whether they've already signed up for this event.
        self.cursor.execute("""
            SELECT u.userID, u.email,
                   vp.first_name, vp.last_name, vp.city, vp.state,
                   vp.high_school, vp.skills,
                   vm.cluster1, vm.cluster2, vm.cluster3,
                   COALESCE(f.banned, 0) AS banned,
                   (SELECT 1 FROM event_signups s
                    WHERE s.userID = u.userID
                      AND s.opportunityID = ?
                      AND s.status = 'registered') AS already_signed,
                   (SELECT COUNT(*) FROM event_signups s
                    JOIN opportunities o2
                        ON o2.opportunityID = s.opportunityID
                    WHERE s.userID = u.userID
                      AND o2.orgID = ?
                      AND s.status = 'registered') AS past_with_org
            FROM users u
            LEFT JOIN volunteer_profiles vp ON vp.userID = u.userID
            LEFT JOIN volunteer_match vm ON vm.userID = u.userID
            LEFT JOIN org_volunteer_flags f
                ON f.orgID = ? AND f.userID = u.userID
            WHERE u.role = 'volunteer'
        """, (opportunityID, orgID, orgID))

        scored = []
        for r in self.cursor.fetchall():
            if r["banned"] or r["already_signed"]:
                continue

            v_clusters = {
                r["cluster1"] or "", r["cluster2"] or "",
                r["cluster3"] or "",
            } - {""}
            overlap = len(v_clusters & opp_clusters)
            if overlap == 0 and not r["past_with_org"]:
                continue

            score = overlap * 3
            if event_city and (r["city"] or "").lower() == \
                    event_city.lower():
                score += 2
            if r["past_with_org"]:
                score += 1

            scored.append((score, dict(r),
                           sorted(v_clusters & opp_clusters)))

        scored.sort(key=lambda t: (-t[0],
                                   (t[1].get("last_name") or "").lower()))
        return [
            {"volunteer": v, "score": s, "shared_clusters": c}
            for s, v, c in scored[:limit]
        ]

    def getAvailableVolunteersForOpportunity(self, orgID, opportunityID):
        """Return volunteers eligible for a new invitation to this event."""
        self.cursor.execute("""
            SELECT u.userID, u.email,
                   vp.first_name, vp.last_name, vp.city, vp.state,
                   vp.high_school
            FROM users u
            LEFT JOIN volunteer_profiles vp ON vp.userID = u.userID
            LEFT JOIN org_volunteer_flags f
                ON f.orgID = ? AND f.userID = u.userID
            WHERE u.role = 'volunteer'
              AND COALESCE(f.banned, 0) = 0
              AND NOT EXISTS (
                  SELECT 1 FROM event_signups s
                  WHERE s.userID = u.userID
                    AND s.opportunityID = ?
                    AND s.status = 'registered'
              )
              AND NOT EXISTS (
                  SELECT 1 FROM opportunity_invitations i
                  WHERE i.orgID = ?
                    AND i.userID = u.userID
                    AND i.opportunityID = ?
                    AND i.status = 'pending'
              )
            ORDER BY LOWER(COALESCE(vp.last_name, '')),
                     LOWER(COALESCE(vp.first_name, '')), u.userID
        """, (orgID, opportunityID, orgID, opportunityID))
        return self.cursor.fetchall()

    def notifyVolunteersAboutOpportunity(self, opportunityID):
        """
        Create an in-app notification for every volunteer whose match
        profile overlaps with the opportunity's clusters, or — if the
        opportunity has no clusters — for every volunteer who has
        joined this org.
        Respects the org's banned list.
        """
        self.cursor.execute(
            "SELECT orgID, title FROM opportunities "
            "WHERE opportunityID = ?",
            (opportunityID,),
        )
        row = self.cursor.fetchone()
        if not row:
            return 0
        orgID = row["orgID"]
        title = row["title"] or "a new event"

        clusters = set(
            self.getOpportunityClusters(opportunityID) or []
        )

        if clusters:
            placeholders = ", ".join("?" for _ in clusters)
            self.cursor.execute(f"""
                SELECT u.userID
                FROM users u
                JOIN volunteer_match vm ON vm.userID = u.userID
                LEFT JOIN org_volunteer_flags f
                    ON f.orgID = ? AND f.userID = u.userID
                WHERE u.role = 'volunteer'
                  AND COALESCE(f.banned, 0) = 0
                  AND (
                      vm.cluster1 IN ({placeholders}) OR
                      vm.cluster2 IN ({placeholders}) OR
                      vm.cluster3 IN ({placeholders})
                  )
            """, (orgID, *clusters, *clusters, *clusters))
        else:
            self.cursor.execute("""
                SELECT DISTINCT m.userID
                FROM org_members m
                LEFT JOIN org_volunteer_flags f
                    ON f.orgID = m.orgID AND f.userID = m.userID
                WHERE m.orgID = ?
                  AND COALESCE(f.banned, 0) = 0
            """, (orgID,))

        recipients = [r["userID"] for r in self.cursor.fetchall()]
        for uid in recipients:
            self.addNotification(
                uid,
                f"New opportunity from a cause you follow: {title}",
                "opportunity_match",
                opportunityID,
            )
        return len(recipients)
    # ── Shutdown ──────────────────────────────────────────────────────
    def close(self):
        try:
            self.cursor.close()
        except Exception:
            pass
        try:
            self.connection.close()
        except Exception:
            pass