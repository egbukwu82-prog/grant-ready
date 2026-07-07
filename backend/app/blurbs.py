"""Draft application blurbs.

Template-based per program, filled with the farmer's questionnaire answers.
If ANTHROPIC_API_KEY is set in the environment, a live-generated draft is
attempted (Claude Opus 4.8), with the template as the fallback on any failure.
Blurbs describe the farmer's own answers plus facts already in the seed data —
no grant figures are invented here.
"""

import os
from typing import Dict, Tuple

from .models import QuestionnaireAnswers


def _farm_desc(a: QuestionnaireAnswers) -> str:
    parts = []
    if a.crop_type.strip():
        parts.append(a.crop_type.strip())
    if a.livestock_type.strip():
        parts.append(a.livestock_type.strip())
    kind = " and ".join(parts) if parts else "mixed farming"
    if a.acreage > 0:
        return "{:,.0f}-acre {} operation".format(a.acreage, kind)
    return "{} operation".format(kind)


def _intro(a: QuestionnaireAnswers) -> str:
    intro = "We operate a {} in Alberta".format(_farm_desc(a))
    if a.annual_farm_revenue > 0:
        intro += " with approximately ${:,.0f} in annual farm commodity sales".format(
            a.annual_farm_revenue
        )
    return intro + "."


def _plans(a: QuestionnaireAnswers) -> str:
    return a.plans.strip() or "planned improvements to our operation"


# One template per seed program, keyed by program id. Each states only what the
# farmer told us plus program facts present in the seed data.
_TEMPLATES = {
    "ofep": (
        "{intro} We hold a current Environmental Farm Plan certificate. We are "
        "applying to the On-Farm Efficiency Program for cost-shared support of "
        "{plans}. This project will improve the efficiency of our day-to-day "
        "operation, and we understand funding is reimbursement-based at up to 50% "
        "of eligible expenses."
    ),
    "ofcaf": (
        "{intro} We are applying to the On-Farm Climate Action Fund to adopt "
        "beneficial management practices on our land, specifically: {plans}. We "
        "will work with a Professional Agrologist or Certified Crop Advisor to "
        "develop the required BMP Action Plan, and we understand costs are shared "
        "at up to 85% of eligible cash expenditures on a reimbursement basis."
    ),
    "on-farm-value-added": (
        "{intro} We are applying to the On-Farm Value-Added Program to add value "
        "to our products past harvest or slaughter through {plans}. This project "
        "will expand our processing capacity and market access, and we understand "
        "the program cost-shares capital and non-capital expenses."
    ),
    "agristability": (
        "{intro} We report our farming income to the CRA and wish to enrol in "
        "AgriStability for whole-farm income protection against margin declines "
        "from market, weather, disease, or trade disruption. We understand "
        "enrolment must be completed by the program deadline with no late "
        "applications accepted."
    ),
    "agriinvest": (
        "{intro} We file farm income for tax purposes and wish to participate in "
        "AgriInvest, depositing eligible amounts to receive the government match "
        "of 1% of allowable net sales as a flexible risk-management reserve for "
        "our operation."
    ),
    "emerging-opportunities": (
        "{intro} We are contacting the Emerging Opportunities Program regarding a "
        "planned investment of ${investment:,.0f} in {plans}. We understand intake "
        "is invite-only and request the opportunity to submit a letter of request "
        "describing the project's contribution to Alberta's processing capacity "
        "and market access."
    ),
    "ralp": (
        "{intro} We hold a current Environmental Farm Plan. We are applying to the "
        "Resilient Agricultural Landscape Program to implement beneficial "
        "management practices — {plans} — that deliver ecological goods and "
        "services including carbon sequestration and climate resilience, under "
        "the program's per-acre payment structure over a 3-year term."
    ),
    "water-program": (
        "{intro} We are applying to the Water Program for cost-shared support of "
        "on-farm water infrastructure: {plans}. Where the project involves a "
        "dugout, dam, or spring development, we will complete the required prior "
        "consultation with an Agriculture and Irrigation Water Specialist and "
        "obtain an approved Construction Sheet."
    ),
    "growing-greenhouses": (
        "{intro} As a controlled-environment agriculture operation, we are "
        "applying to the Growing Greenhouses Program to support {plans}, "
        "increasing year-round local access to fresh produce."
    ),
    "alberta-indigenous-ag-funding": (
        "{intro} As an Indigenous producer holding a current Environmental Farm "
        "Plan, we are applying to Alberta Indigenous Agricultural Funding for "
        "non-repayable cost-shared support of {plans}, strengthening our "
        "agricultural operation and its long-term viability."
    ),
    "alberta-young-farmer-grants": (
        "{intro} As a new/young farmer, we are applying to the Alberta Young "
        "Farmer Grants program with a farm business plan covering {plans}, to "
        "support the development and implementation of our farm business."
    ),
    "women-in-ag-grant": (
        "{intro} As a woman working in Alberta agriculture and a legal resident "
        "of Alberta, I am applying to the Credit Unions of Alberta Women in Ag "
        "Grant to support {plans} and my continued work in the sector."
    ),
    "alberta-farm-fuel-benefit": (
        "{intro} As a registered Alberta farm operation, we are applying for the "
        "Alberta Farm Fuel Benefit to access reduced-cost marked fuel for "
        "eligible farm use across our operation."
    ),
}

_FALLBACK_TEMPLATE = (
    "{intro} We are applying to this program for support of {plans}, which will "
    "strengthen the productivity and sustainability of our operation."
)


def render_template(program: Dict, a: QuestionnaireAnswers) -> str:
    template = _TEMPLATES.get(program["id"], _FALLBACK_TEMPLATE)
    return template.format(
        intro=_intro(a),
        plans=_plans(a),
        investment=a.planned_investment or 0,
    )


def _llm_blurb(program: Dict, a: QuestionnaireAnswers, template_text: str) -> str:
    import anthropic

    client = anthropic.Anthropic()
    prompt = (
        "Rewrite this draft grant-application paragraph so it reads naturally and "
        "persuasively, in 3-5 sentences. Use ONLY the facts below — do not invent "
        "any dollar figure, deadline, or eligibility rule. Return only the "
        "paragraph.\n\n"
        "Program: {name} ({agency})\n"
        "Eligible uses per program: {uses}\n"
        "Farmer's answers: crops={crops}; livestock={livestock}; acreage={acres}; "
        "annual revenue=${rev:,.0f}; EFP={efp}; plans={plans}\n\n"
        "Current draft:\n{draft}"
    ).format(
        name=program["name"],
        agency=program["agency"],
        uses=program.get("eligible_use", ""),
        crops=a.crop_type or "n/a",
        livestock=a.livestock_type or "n/a",
        acres=a.acreage,
        rev=a.annual_farm_revenue,
        efp="yes" if a.has_efp else "no",
        plans=a.plans or "n/a",
        draft=template_text,
    )
    response = client.messages.create(
        model="claude-opus-4-8",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    text = "".join(b.text for b in response.content if b.type == "text").strip()
    return text


def generate_blurb(program: Dict, a: QuestionnaireAnswers) -> Tuple[str, str]:
    """Returns (blurb, source) where source is 'template' or 'llm'."""
    template_text = render_template(program, a)
    if os.environ.get("ANTHROPIC_API_KEY"):
        try:
            live = _llm_blurb(program, a, template_text)
            if live:
                return live, "llm"
        except Exception:
            pass
    return template_text, "template"
