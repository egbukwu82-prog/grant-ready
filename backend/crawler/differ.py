"""Detect-and-flag diffing between a fetched page and the stored facts.

Core principle: never resolve. Every discrepancy this module reports
becomes a pending_review change-log entry for a human to confirm or
reject — the crawler never overwrites a stored fact.

Two modes:
- With ANTHROPIC_API_KEY set: extract the meaningful fields (deadline,
  funding amounts, open/closed status) from the page text and diff them
  against the structured seed values — catches real changes, ignores
  cosmetic ones (redesigns, unrelated copy edits).
- Without a key: raw content-hash diff against the last stored snapshot;
  any change is flagged as "content changed, review manually".
"""

import json
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .sources import FetchResult

ANTHROPIC_MODEL = "claude-opus-4-8"
_MAX_PAGE_CHARS = 24000

_EXTRACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "page_describes_program": {
            "type": "boolean",
            "description": "True only if this page actually describes the named grant program",
        },
        "discrepancies": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "field": {"type": "string"},
                    "stored_value": {"type": "string"},
                    "page_value": {"type": "string"},
                },
                "required": ["field", "stored_value", "page_value"],
                "additionalProperties": False,
            },
        },
        "notes": {"type": "string"},
    },
    "required": ["page_describes_program", "discrepancies", "notes"],
    "additionalProperties": False,
}

_SYSTEM_PROMPT = (
    "You verify grant program facts against their official source pages. "
    "You compare ONLY meaningful fields: application deadline, funding amounts / "
    "caps / cost-share rates, and open/closed intake status. Ignore page "
    "redesigns, wording changes, and anything cosmetic. Report a discrepancy "
    "only when the page clearly states a fact that contradicts the stored value. "
    "Never guess: if the page does not mention a field, that is not a discrepancy."
)


@dataclass
class DiffOutcome:
    # Each: {"field": ..., "old_value": ..., "new_value": ...}
    discrepancies: List[Dict] = field(default_factory=list)
    # True only when the crawler positively confirmed no meaningful change
    confirmed: bool = False
    notes: List[str] = field(default_factory=list)


def llm_available() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def diff_program(
    program: Dict, result: FetchResult, previous: Optional[Dict]
) -> DiffOutcome:
    """Compare a successful fetch against stored data. Caller handles fetch failures."""
    if llm_available():
        try:
            return _llm_diff(program, result)
        except Exception as exc:
            outcome = _hash_diff(result, previous)
            outcome.notes.append(
                "LLM extraction failed ({}: {}); fell back to hash diff".format(
                    type(exc).__name__, exc
                )
            )
            return outcome
    return _hash_diff(result, previous)


# ---------------------------------------------------------------------------
# Hash mode — no API key
# ---------------------------------------------------------------------------

def _hash_diff(result: FetchResult, previous: Optional[Dict]) -> DiffOutcome:
    if previous is None or not previous.get("content_hash"):
        return DiffOutcome(
            confirmed=False,
            notes=["first crawl — baseline snapshot stored, nothing to compare yet"],
        )
    if previous["content_hash"] == result.content_hash:
        return DiffOutcome(confirmed=True, notes=["content unchanged since last crawl"])
    return DiffOutcome(
        discrepancies=[
            {
                "field": "page_content",
                "old_value": "content hash {}".format(previous["content_hash"][:16]),
                "new_value": "content hash {} — content changed, review manually".format(
                    result.content_hash[:16]
                ),
            }
        ],
        confirmed=False,
        notes=["raw content changed since last crawl"],
    )


# ---------------------------------------------------------------------------
# LLM mode — field-level extraction and comparison
# ---------------------------------------------------------------------------

def _stored_facts(program: Dict) -> str:
    return json.dumps(
        {
            "program_name": program["name"],
            "deadline": program.get("deadline"),
            "funding_amount": program.get("funding_amount"),
            "intake": program.get("intake"),
        },
        indent=2,
        ensure_ascii=False,
    )


def _llm_diff(program: Dict, result: FetchResult) -> DiffOutcome:
    import anthropic

    client = anthropic.Anthropic()
    prompt = (
        "Stored facts for the grant program:\n{facts}\n\n"
        "Text fetched from the program's official source URL ({url}):\n"
        "<page_text>\n{page}\n</page_text>\n\n"
        "Compare the page against the stored deadline, funding amounts, and "
        "open/closed status. List only clear contradictions."
    ).format(
        facts=_stored_facts(program),
        url=result.url,
        page=result.text[:_MAX_PAGE_CHARS],
    )

    response = client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=2000,
        system=_SYSTEM_PROMPT,
        output_config={"format": {"type": "json_schema", "schema": _EXTRACTION_SCHEMA}},
        messages=[{"role": "user", "content": prompt}],
    )
    text = next(b.text for b in response.content if b.type == "text")
    data = json.loads(text)

    outcome = DiffOutcome()
    if data.get("notes"):
        outcome.notes.append(data["notes"])
    if not data["page_describes_program"]:
        outcome.notes.append(
            "source page does not appear to describe this program "
            "(URL may be generic) — crawler could not confirm"
        )
        return outcome
    for d in data["discrepancies"]:
        outcome.discrepancies.append(
            {
                "field": d["field"],
                "old_value": d["stored_value"],
                "new_value": d["page_value"],
            }
        )
    outcome.confirmed = not outcome.discrepancies
    return outcome
