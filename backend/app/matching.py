"""Two-layer matching engine.

Layer 1 — deterministic eligibility gate: hard filter on the structured
eligibility fields in the seed data. A program the farmer flatly doesn't
qualify for never appears in results, regardless of semantic similarity.

Layer 2 — relevance ranking within the eligible set: TF-IDF cosine similarity
between the questionnaire free-text and each program's `eligible_use` field.
"""

import math
import re
from collections import Counter
from typing import Dict, List, Optional, Tuple

from .models import QuestionnaireAnswers

# ---------------------------------------------------------------------------
# Layer 1 — deterministic eligibility gate
# ---------------------------------------------------------------------------

_REVENUE_KEYS = {
    "min_annual_farm_commodities": "annual farm commodity sales",
    "min_gross_farm_income": "gross farm income",
    "min_annual_commercial_production": "annual commercial production",
}


def check_eligibility(program: Dict, a: QuestionnaireAnswers) -> Tuple[bool, List[str]]:
    """Apply the structured eligibility fields. Returns (passes, reasons_passed)."""
    elig = program.get("eligibility", {})
    reasons: List[str] = []

    location = str(elig.get("location", ""))
    if "Alberta" in location:
        if not a.in_alberta:
            return False, []
        reasons.append("located in Alberta")

    for key, label in _REVENUE_KEYS.items():
        if key in elig:
            minimum = float(elig[key])
            if a.annual_farm_revenue < minimum:
                return False, []
            reasons.append(
                "your ${:,.0f} in {} meets the ${:,.0f} minimum".format(
                    a.annual_farm_revenue, label, minimum
                )
            )

    if elig.get("requires_efp") is True:
        if not a.has_efp:
            return False, []
        reasons.append("you hold an Environmental Farm Plan")

    if "min_project_investment" in elig:
        minimum = float(elig["min_project_investment"])
        if a.planned_investment is None or a.planned_investment < minimum:
            return False, []
        reasons.append(
            "your planned ${:,.0f} investment clears the ${:,.0f} minimum".format(
                a.planned_investment, minimum
            )
        )

    applicant = str(elig.get("applicant_type", "")).lower()
    if "indigenous" in applicant:
        if not a.is_indigenous:
            return False, []
        reasons.append("open to Indigenous producers")
    if applicant.startswith("women") or "women," in applicant:
        if not a.is_woman:
            return False, []
        reasons.append("open to women working in Alberta agriculture")
    if "under 40" in applicant or "new entrants" in applicant:
        if not a.is_new_or_young_farmer:
            return False, []
        reasons.append("open to young/new farmers")
    if "cea" in applicant:
        if not a.is_greenhouse_operation:
            return False, []
        reasons.append("you run a greenhouse / controlled-environment operation")

    return True, reasons


# ---------------------------------------------------------------------------
# Layer 2 — TF-IDF relevance ranking within the eligible set
# ---------------------------------------------------------------------------

_STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "in", "for", "on", "with",
    "we", "our", "i", "my", "is", "are", "be", "as", "at", "by", "from",
    "new", "incl", "related", "etc", "per",
}


def _stem(token: str) -> str:
    for suffix in ("ing", "ed"):
        if token.endswith(suffix) and len(token) > len(suffix) + 2:
            token = token[: -len(suffix)]
            if len(token) > 2 and token[-1] == token[-2]:
                token = token[:-1]
            return token
    for suffix in ("es", "s", "e"):
        if token.endswith(suffix) and len(token) > len(suffix) + 2:
            return token[: -len(suffix)]
    return token


def _tokenize(text: str) -> List[str]:
    raw = re.findall(r"[a-z]+", text.lower())
    return [_stem(t) for t in raw if t not in _STOPWORDS and len(t) > 2]


class TfidfRanker:
    """Tiny TF-IDF over the programs' eligible_use text. 13 docs — no infra needed."""

    def __init__(self, programs: List[Dict]):
        self._docs: Dict[str, Counter] = {
            p["id"]: Counter(_tokenize(p.get("eligible_use", ""))) for p in programs
        }
        n_docs = max(len(self._docs), 1)
        df: Counter = Counter()
        for counts in self._docs.values():
            df.update(counts.keys())
        self._idf = {t: math.log(n_docs / (1 + d)) + 1.0 for t, d in df.items()}

    def _vector(self, counts: Counter) -> Dict[str, float]:
        return {t: c * self._idf.get(t, 1.0) for t, c in counts.items()}

    def score(self, program_id: str, query_text: str) -> Tuple[float, List[str]]:
        """Cosine similarity plus the overlapping terms (for 'why matched')."""
        raw_words = re.findall(r"[a-z]+", query_text.lower())
        # Map each stem back to the farmer's own wording for display
        originals = {}
        for word in raw_words:
            if word not in _STOPWORDS and len(word) > 2:
                originals.setdefault(_stem(word), word)
        query = Counter(_tokenize(query_text))
        doc = self._docs.get(program_id, Counter())
        qv, dv = self._vector(query), self._vector(doc)
        shared = set(qv) & set(dv)
        if not shared:
            return 0.0, []
        dot = sum(qv[t] * dv[t] for t in shared)
        norm = math.sqrt(sum(v * v for v in qv.values())) * math.sqrt(
            sum(v * v for v in dv.values())
        )
        overlap = sorted(shared, key=lambda t: qv[t] * dv[t], reverse=True)
        return (dot / norm if norm else 0.0), [originals.get(t, t) for t in overlap[:4]]


# ---------------------------------------------------------------------------
# Urgency tiering
# ---------------------------------------------------------------------------

TIER_ENROLLMENT = "enrollment_deadline"
TIER_ROLLING = "rolling"
TIER_INVITE = "invite_only"


def urgency_tier(program: Dict) -> str:
    intake = str(program.get("intake", "")).lower()
    deadline = str(program.get("deadline", "")).lower()
    if "invite" in intake:
        return TIER_INVITE
    if "enrol" in intake or "enrol" in deadline or "tax filing" in intake:
        return TIER_ENROLLMENT
    return TIER_ROLLING


# ---------------------------------------------------------------------------
# Plain-language funding summary
# ---------------------------------------------------------------------------

_FUNDING_LABELS = {
    "max_per_applicant": "Up to {} per applicant",
    "cost_share_rate": "Cost share: {}",
    "min_funding": "Minimum grant {}",
    "min_project_cost": "Minimum project cost {}",
    "program_term": "Program term: {}",
    "note_on_amount": "{}",
    "note": "{}",
    "stream_a_max": "Stream A: up to {}",
    "stream_b_range": "Stream B: {}",
    "cost_share_capital": "Capital costs: {}",
    "cost_share_noncapital": "Non-capital costs: {}",
    "compensation_rate": "Compensation: {}",
    "trigger": "Payment triggers when: {}",
    "max_payment": "Maximum payment: {}",
    "admin_fee": "Admin fee: {}",
    "match_rate": "{}",
    "example": "Example: {}",
    "withdrawal": "Withdrawals: {}",
    "max_per_fiscal_year": "Up to {} per fiscal year",
    "max_project": "Project cap {}",
    "structure": "{}",
    "min": "Minimum {}",
    "max_primary_producer": "Up to {} for primary producers",
    "max_community_project": "Up to {} for community projects",
    "max": "Up to {}",
    "amount_each": "{} per award",
    "number_awarded_annually": "{} awarded annually",
}


def _fmt_value(value) -> str:
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, (int, float)):
        return "${:,.0f}".format(value)
    text = str(value)
    m = re.fullmatch(r"(\d+)\s+to\s+(\d+)", text)
    if m:
        return "${:,.0f} to ${:,.0f}".format(int(m.group(1)), int(m.group(2)))
    return text


def funding_plain_language(program: Dict) -> List[str]:
    lines: List[str] = []
    for key, value in program.get("funding_amount", {}).items():
        label = _FUNDING_LABELS.get(key, key.replace("_", " ").capitalize() + ": {}")
        lines.append(label.format(_fmt_value(value)))
    return lines


# ---------------------------------------------------------------------------
# One-line "why this matched"
# ---------------------------------------------------------------------------

def why_matched(reasons: List[str], overlap_terms: List[str], a: QuestionnaireAnswers) -> str:
    parts = list(reasons)
    if overlap_terms:
        parts.append(
            "your plans line up with this program's eligible uses ({})".format(
                ", ".join(overlap_terms)
            )
        )
    if not parts:
        parts.append("open to active producers like your operation")
    sentence = "; ".join(parts)
    return "Matched because " + sentence + "."


def build_query_text(a: QuestionnaireAnswers) -> str:
    return " ".join([a.plans, a.crop_type, a.livestock_type, a.certifications])
