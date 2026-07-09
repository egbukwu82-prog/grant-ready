"""Manual crawl of every seed program's source URL.

Run from backend/:  python -m crawler.run

For each of the seed programs: fetch the official source page, diff it
against stored facts (LLM field extraction when ANTHROPIC_API_KEY is set,
raw content-hash otherwise), append any discrepancies to the change log as
pending_review, store the raw snapshot for audit, and assign a confidence
tier. Stored grant facts are never overwritten — detect and flag only.
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from app.repository import JsonFileProgramRepository

from .differ import DiffOutcome, diff_program, llm_available
from .history import SqliteCrawlHistoryRepository
from .sources import Source

REPO_ROOT = Path(__file__).resolve().parents[2]
SEED_PATH = REPO_ROOT / "grantready_seed_programs.json"
DB_PATH = REPO_ROOT / "crawler_history.db"

TIER_VERIFIED = "verified"
TIER_CRAWLER_CONFIRMED = "crawler_confirmed"
TIER_FLAGGED = "flagged"

# "Stale" per spec: no successful crawl in 30+ days. The same window bounds
# how long a manual confirmation counts as "recent" for the verified tier.
STALE_DAYS = 30


def seed_flag(program: Dict) -> Optional[str]:
    """The Phase 1 verify-before-applying flag: a `flag` field, or OFCAF's
    conflict embedded in the deadline text prefixed FLAG:."""
    flag = program.get("flag")
    if flag:
        return flag
    deadline = str(program.get("deadline", ""))
    if deadline.upper().startswith("FLAG:"):
        return deadline[len("FLAG:"):].strip()
    return None


def _days_since(date_str: Optional[str], now: datetime) -> Optional[float]:
    if not date_str:
        return None
    try:
        parsed = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return (now - parsed).total_seconds() / 86400


def assign_tier(
    program: Dict,
    fetch_ok: bool,
    fetch_error: Optional[str],
    pending_count: int,
    outcome: Optional[DiffOutcome],
    now: datetime,
) -> Tuple[str, str]:
    """Returns (tier, reason). Order matters: problems flag before anything
    can count as verified or crawler-confirmed."""
    if not fetch_ok:
        return TIER_FLAGGED, "fetch failed ({})".format(fetch_error or "unknown error")
    if pending_count:
        return TIER_FLAGGED, "{} change(s) pending human review".format(pending_count)
    if seed_flag(program):
        return TIER_FLAGGED, "unresolved conflict recorded in seed data — needs human confirmation"

    human_days = _days_since(
        program.get("last_human_verified") or program.get("last_verified"), now
    )
    confirmed = bool(outcome and outcome.confirmed)
    if human_days is not None and human_days <= STALE_DAYS:
        reason = "human-verified {} day(s) ago".format(int(human_days))
        if not confirmed:
            reason += " (crawler could not independently confirm this run)"
        return TIER_VERIFIED, reason
    if confirmed:
        return TIER_CRAWLER_CONFIRMED, "source fetched, no discrepancy found; no recent human verification"
    return TIER_FLAGGED, "no recent human verification and crawler could not confirm"


def _already_pending(history_entries: List[Dict], entry: Dict) -> bool:
    """Avoid re-appending the identical pending discrepancy on every run —
    the log stays append-only, but duplicates add no information."""
    return any(
        e["field"] == entry["field"]
        and e.get("new_value") == entry["new_value"]
        and e["status"] == "pending_review"
        for e in history_entries
    )


def crawl_all() -> None:
    repo = JsonFileProgramRepository(SEED_PATH)
    history = SqliteCrawlHistoryRepository(DB_PATH)
    programs = repo.list_programs()
    now = datetime.now(timezone.utc)
    mode = "LLM field extraction ({})".format("ANTHROPIC_API_KEY set") if llm_available() \
        else "raw content-hash diff (no ANTHROPIC_API_KEY — flagging changes for manual review)"

    print("GrantReady crawler — {} programs".format(len(programs)))
    print("Diff mode: {}".format(mode))
    print("Change log + snapshots: {}".format(DB_PATH))
    print("-" * 78)

    tier_counts: Dict[str, int] = {}
    for program in programs:
        pid = program["id"]
        result = Source(program["source_url"]).fetch()
        previous = history.get_snapshot(pid)

        outcome: Optional[DiffOutcome] = None
        new_entries: List[Dict] = []
        if result.ok:
            outcome = diff_program(program, result, previous)
            existing = history.list_changes(pid)
            for d in outcome.discrepancies:
                entry = {
                    "timestamp": result.fetched_at,
                    "field": d["field"],
                    "old_value": d["old_value"],
                    "new_value": d["new_value"],
                    "status": "pending_review",
                }
                if _already_pending(existing, entry):
                    continue
                history.append_change(pid, entry)
                new_entries.append(entry)

        # Snapshot every attempt (success or failure) for the audit trail.
        history.save_snapshot(pid, result)

        pending = history.list_changes(pid, status="pending_review")
        tier, reason = assign_tier(
            program, result.ok, result.error, len(pending), outcome, now
        )
        tier_counts[tier] = tier_counts.get(tier, 0) + 1

        # Update current facts in the seed file — tier and timestamps only;
        # deadline/funding/eligibility are never touched by the crawler.
        repo.update_program(pid, {
            "confidence_tier": tier,
            "last_crawled": result.fetched_at,
            "last_human_verified": program.get("last_human_verified")
            or program.get("last_verified"),
            "change_log": program.get("change_log", []) + new_entries,
        })

        status = "HTTP {}".format(result.http_status) if result.http_status else "ERROR"
        print("{:<32} {:<9} tier={:<18} {}".format(pid, status, tier, reason))
        if outcome:
            for note in outcome.notes:
                print("{:<32} {:<9} note: {}".format("", "", note))
        for entry in new_entries:
            print(
                "{:<32} {:<9} NEW pending_review [{}]: {!r} -> {!r}".format(
                    "", "", entry["field"], entry["old_value"], entry["new_value"]
                )
            )

    repo.save()

    print("-" * 78)
    print("Tiers: " + ", ".join(
        "{}={}".format(t, tier_counts.get(t, 0))
        for t in (TIER_VERIFIED, TIER_CRAWLER_CONFIRMED, TIER_FLAGGED)
    ))
    pending_all = history.list_changes(status="pending_review")
    print("Change-log entries pending human review: {}".format(len(pending_all)))
    for e in pending_all:
        print(
            "  [{}] {} {}: {!r} -> {!r}".format(
                e["id"], e["program_id"], e["field"], e["old_value"], e["new_value"]
            )
        )
    print("Seed file updated: {}".format(SEED_PATH))


if __name__ == "__main__":
    crawl_all()
