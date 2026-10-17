"""
ml_recommender.py - Unsupervised content-based recommendation.

Past signups are repeated 3x in the user document so TF-IDF weights
behavior above static profile fields. This makes the recommender
"learn" from what the volunteer has actually chosen to do, without
needing a persisted model.
"""

import re

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


def _get(row, key, default=""):
    try:
        v = row[key]
    except (KeyError, IndexError, TypeError):
        return default
    return default if v is None else v


def _clean(text):
    text = re.sub(r"[^\w\s]", " ", str(text).lower())
    return re.sub(r"\s+", " ", text).strip()


def _opp_doc(row):
    return _clean(" ".join([
        _get(row, "title"),
        _get(row, "description"),
        _get(row, "activity"),
        _get(row, "required_skills"),
        _get(row, "location"),
        _get(row, "org_name"),
    ]))


def _user_doc(user_row, signup_rows, joined_org_rows):
    parts = [
        _get(user_row, "skills"),
        _get(user_row, "country"),
        _get(user_row, "zipcode"),
    ]
    for r in joined_org_rows:
        parts.append(_get(r, "activity"))

    # Signups weighted 3x so TF-IDF amplifies behavior.
    for r in signup_rows:
        signup_text = " ".join(filter(None, [
            _get(r, "title"),
            _get(r, "description"),
            _get(r, "category"),
            _get(r, "required_skills"),
        ]))
        if signup_text:
            parts.append(signup_text)
            parts.append(signup_text)
            parts.append(signup_text)

    return _clean(" ".join(p for p in parts if p))


def explain_match(user_row, opportunity_row):
    user_skills = {
        _clean(term) for term in re.split(
            r"[,;|]", str(_get(user_row, "skills"))
        ) if _clean(term)
    }
    required_skills = {
        _clean(term) for term in re.split(
            r"[,;|]", str(_get(opportunity_row, "required_skills"))
        ) if _clean(term)
    }
    shared = sorted(user_skills & required_skills)
    reasons = [f"Matches skill: {skill}" for skill in shared[:2]]

    country = _clean(_get(user_row, "country"))
    location = _clean(_get(opportunity_row, "location"))
    if country and country in location:
        reasons.append("In your country")
    if _get(opportunity_row, "is_remote"):
        reasons.append("Remote-friendly")
    return reasons


def rank_opportunities(user_row, signup_rows, joined_org_rows,
                       candidate_rows, top_n=6):
    if not candidate_rows:
        return [], []

    already = {
        _get(r, "opportunityID") for r in signup_rows
        if _get(r, "opportunityID")
    }
    candidates = [
        r for r in candidate_rows
        if _get(r, "opportunityID") not in already
    ]
    if not candidates:
        return [], []

    user_text = _user_doc(user_row, signup_rows, joined_org_rows)
    if not user_text:
        ordered = sorted(candidates,
                         key=lambda r: str(_get(r, "event_date", "")))
        top = ordered[:top_n]
        return top, [0.0] * len(top)

    docs = [_opp_doc(r) for r in candidates]
    try:
        vec = TfidfVectorizer(
            stop_words="english", min_df=1, ngram_range=(1, 2)
        )
        matrix = vec.fit_transform([user_text] + docs)
        scores = cosine_similarity(matrix[0:1], matrix[1:]).flatten()
    except ValueError:
        top = candidates[:top_n]
        return top, [0.0] * len(top)

    paired = sorted(zip(candidates, scores), key=lambda t: -t[1])
    top = paired[:top_n]
    return [r for r, _ in top], [float(s) for _, s in top]