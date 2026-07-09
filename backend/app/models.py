"""Pydantic models for the GrantReady Phase 1 API."""

from typing import List, Optional

from pydantic import BaseModel, Field


class QuestionnaireAnswers(BaseModel):
    """Everything the eligibility gate and ranking layer need — nothing more."""

    in_alberta: bool = True
    crop_type: str = ""
    livestock_type: str = ""
    acreage: float = 0
    annual_farm_revenue: float = Field(0, description="Annual farm commodity revenue in CAD")
    has_efp: bool = False
    plans: str = Field("", description="Equipment/technology/project plans, free text")
    planned_investment: Optional[float] = Field(
        None, description="Estimated total project investment in CAD, if known"
    )
    certifications: str = ""
    is_new_or_young_farmer: bool = False
    is_indigenous: bool = False
    is_woman: bool = False
    is_greenhouse_operation: bool = False


class ProgramMatch(BaseModel):
    program_id: str
    name: str
    acronym: Optional[str] = None
    agency: str
    gov_tier: str
    program_type: str
    funding_plain: List[str]
    deadline: str
    intake: str
    urgency_tier: str  # "enrollment_deadline" | "rolling" | "invite_only"
    required_documents: List[str]
    why_matched: str
    source_url: str
    last_verified: str
    flag: Optional[str] = None
    # Crawler confidence-tier fields — None until the first crawl run.
    # Distinct from `flag`: a program can be un-flagged but still only
    # crawler_confirmed rather than verified.
    confidence_tier: Optional[str] = None  # "verified" | "crawler_confirmed" | "flagged"
    last_crawled: Optional[str] = None
    last_human_verified: Optional[str] = None
    relevance_score: float
    blurb: str
    blurb_source: str  # "template" | "llm"


class MatchResponse(BaseModel):
    enrollment_deadline: List[ProgramMatch]
    rolling: List[ProgramMatch]
    invite_only: List[ProgramMatch]
    total_matched: int
    total_programs: int
    dataset_compiled: str
