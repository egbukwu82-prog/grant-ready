"""GrantReady Phase 1 MVP — FastAPI backend (run on port 8001)."""

from pathlib import Path
from typing import Dict, List

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .blurbs import generate_blurb
from .matching import (
    TIER_ENROLLMENT,
    TIER_INVITE,
    TIER_ROLLING,
    TfidfRanker,
    build_query_text,
    check_eligibility,
    funding_plain_language,
    urgency_tier,
    why_matched,
)
from .models import MatchResponse, ProgramMatch, QuestionnaireAnswers
from .repository import JsonFileProgramRepository, ProgramRepository

SEED_PATH = Path(__file__).resolve().parents[2] / "grantready_seed_programs.json"

repo: ProgramRepository = JsonFileProgramRepository(SEED_PATH)
ranker = TfidfRanker(repo.list_programs())

app = FastAPI(title="GrantReady Phase 1 MVP")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> Dict:
    return {"status": "ok", "programs_loaded": len(repo.list_programs())}


@app.get("/api/programs")
def list_programs() -> List[Dict]:
    return repo.list_programs()


@app.post("/api/match", response_model=MatchResponse)
def match(answers: QuestionnaireAnswers) -> MatchResponse:
    query_text = build_query_text(answers)
    tiers: Dict[str, List[ProgramMatch]] = {
        TIER_ENROLLMENT: [],
        TIER_ROLLING: [],
        TIER_INVITE: [],
    }

    for program in repo.list_programs():
        passes, reasons = check_eligibility(program, answers)
        if not passes:
            continue
        score, overlap = ranker.score(program["id"], query_text)
        blurb, blurb_source = generate_blurb(program, answers)
        # Flags live in a "flag" field, except OFCAF's open/closed conflict,
        # which the seed embeds in the deadline text prefixed "FLAG:". Surface
        # both as the verify-before-applying badge without altering the data.
        flag = program.get("flag")
        deadline = program.get("deadline", "Verify live")
        if flag is None and deadline.upper().startswith("FLAG:"):
            flag = deadline[len("FLAG:"):].strip()
        result = ProgramMatch(
            program_id=program["id"],
            name=program["name"],
            acronym=program.get("acronym"),
            agency=program["agency"],
            gov_tier=program["tier"],
            program_type=program["type"],
            funding_plain=funding_plain_language(program),
            deadline=deadline,
            intake=program.get("intake", ""),
            urgency_tier=urgency_tier(program),
            required_documents=program.get("required_documents", []),
            why_matched=why_matched(reasons, overlap, answers),
            source_url=program["source_url"],
            last_verified=program["last_verified"],
            flag=flag,
            confidence_tier=program.get("confidence_tier"),
            last_crawled=program.get("last_crawled"),
            last_human_verified=program.get("last_human_verified"),
            relevance_score=round(score, 4),
            blurb=blurb,
            blurb_source=blurb_source,
        )
        tiers[result.urgency_tier].append(result)

    for bucket in tiers.values():
        bucket.sort(key=lambda m: (-m.relevance_score, m.name))

    meta = repo.dataset_meta()
    total = sum(len(b) for b in tiers.values())
    return MatchResponse(
        enrollment_deadline=tiers[TIER_ENROLLMENT],
        rolling=tiers[TIER_ROLLING],
        invite_only=tiers[TIER_INVITE],
        total_matched=total,
        total_programs=len(repo.list_programs()),
        dataset_compiled=meta.get("compiled_date", ""),
    )
