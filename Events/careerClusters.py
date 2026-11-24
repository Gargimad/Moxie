"""
careerClusters.py — Canonical career clusters used everywhere a
category used to be. Keep this list in sync with the seed loop in
db.migrate() and with the org form's multi-select.
"""

CAREER_CLUSTERS = [
    "Agriculture, Food & Natural Resources",
    "Architecture & Construction",
    "Arts, Audio/Video Technology & Communications",
    "Business Management & Administration",
    "Education & Training",
    "Finance",
    "Government & Public Administration",
    "Health Science",
    "Hospitality & Tourism",
    "Human Services",
    "Information Technology",
    "Law, Public Safety, Corrections & Security",
    "Manufacturing",
    "Marketing",
    "Science, Technology, Engineering & Mathematics",
    "Transportation, Distribution & Logistics",
]


_LEGACY = {
    "environment": "Agriculture, Food & Natural Resources",
    "conservation": "Agriculture, Food & Natural Resources",
    "animals": "Agriculture, Food & Natural Resources",
    "construction": "Architecture & Construction",
    "housing": "Architecture & Construction",
    "arts": "Arts, Audio/Video Technology & Communications",
    "music": "Arts, Audio/Video Technology & Communications",
    "media": "Arts, Audio/Video Technology & Communications",
    "admin": "Business Management & Administration",
    "office": "Business Management & Administration",
    "education": "Education & Training",
    "tutoring": "Education & Training",
    "teaching": "Education & Training",
    "finance": "Finance",
    "fundraising": "Finance",
    "government": "Government & Public Administration",
    "civic": "Government & Public Administration",
    "health": "Health Science",
    "medical": "Health Science",
    "hospital": "Health Science",
    "seniors": "Human Services",
    "food bank": "Human Services",
    "homeless": "Human Services",
    "community": "Human Services",
    "hospitality": "Hospitality & Tourism",
    "tourism": "Hospitality & Tourism",
    "it": "Information Technology",
    "technology": "Information Technology",
    "computers": "Information Technology",
    "legal": "Law, Public Safety, Corrections & Security",
    "safety": "Law, Public Safety, Corrections & Security",
    "fire": "Law, Public Safety, Corrections & Security",
    "police": "Law, Public Safety, Corrections & Security",
    "manufacturing": "Manufacturing",
    "marketing": "Marketing",
    "communications": "Marketing",
    "science": "Science, Technology, Engineering & Mathematics",
    "engineering": "Science, Technology, Engineering & Mathematics",
    "stem": "Science, Technology, Engineering & Mathematics",
    "transportation": "Transportation, Distribution & Logistics",
    "logistics": "Transportation, Distribution & Logistics",
}


def legacy_category_to_cluster(category):
    if not category:
        return None
    key = str(category).strip().lower()
    if key in _LEGACY:
        return _LEGACY[key]
    for needle, cluster in _LEGACY.items():
        if needle in key:
            return cluster
    return None
