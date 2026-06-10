"""Prompts for the discovery loop (finding prospective client companies)."""
from __future__ import annotations

import config

# Rotated so successive rounds don't re-mine the same corner of the market.
INDUSTRY_ANGLES = [
    "aerospace, defense, automotive, and energy (turbomachinery, CFD, structures)",
    "pharma, biotech, medical devices, and materials science (molecular/process modelling)",
    "semiconductors, electronics, climate/geoscience, and quantitative finance",
]

SYSTEM = (
    "You are a B2B lead-generation researcher for Open Numerics (ON), a "
    "scientific-computing consultancy. You search the web for potential CLIENTS "
    "for ON — companies that have hard physical/engineering/scientific problems "
    "ON could be hired to solve — and assess fit honestly.\n\n"
    "CRITICAL DISTINCTION: ON's clients are end-users with in-house R&D, "
    "engineering, or product-development needs (e.g. a turbine manufacturer, a "
    "battery startup, a drug developer). They are NOT companies that themselves "
    "sell simulation, uncertainty quantification, scientific ML, CFD/FEA, or "
    "HPC/GPU services or software — those are ON's peers and competitors, not "
    "clients. If a company's PRODUCT or SERVICE is the modelling itself, it is "
    "not a lead: set is_service_provider=true. ON wants the company with the "
    "engineering problem, not the company that sells the solution.\n\n"
    "You never invent companies, domains, or facts — every candidate must be a "
    "real company you can cite, and fit claims must follow from what you find."
)


def build_user(on_profile: str, deny: list[dict], angle: str, avoid_labels=None) -> str:
    deny_lines = "\n".join(f"- {d['name']} ({d['domain']})" for d in deny) or "(none yet)"
    services = "\n".join(f"- {a}" for a in config.ON_SERVICE_AREAS)
    avoid_block = ""
    if avoid_labels:
        avoid_block = (
            "\nHARD EXCLUSION — do NOT return any companies in these sectors: "
            + "; ".join(avoid_labels)
            + ". Skip them entirely, even if they look like a strong fit.\n"
        )
    return f"""About Open Numerics (current profile):
{on_profile}

ON's core service areas:
{services}

TASK: Use web search to find up to 10 {config.TARGET_REGION}-based companies that
would BENEFIT FROM ON's services — i.e. companies with their own engineering,
R&D, or scientific problems that simulation / UQ / scientific ML / GPU-HPC could
help solve. Focus this round on: {angle}.
{avoid_block}
EXCLUDE companies whose own business is providing these capabilities — simulation
/ CFD / FEA / UQ / scientific-ML / HPC consultancies, software vendors, and
research-software houses. They are ON's competitors, not its clients. If you list
such a company at all, set is_service_provider=true (it will be filtered out).
ON wants, e.g., the aerospace OEM that needs better CFD — NOT the firm that sells
CFD software.

For each company:
- Give the real name and primary website domain (e.g. acme.com).
- Set is_service_provider: true if the company itself sells modelling/UQ/ML/HPC
  services or software; false if it is a potential client with its own problems.
- Score fit from 0-10. Reserve {config.FIT_SCORE_THRESHOLD}+ for end-user companies
  whose actual work clearly involves heavy simulation, modelling, UQ, scientific
  ML, or GPU/HPC compute that they'd plausibly outsource. Be discerning — a high
  score must be defensible.
- In `why_fit`, explain the specific reason, grounded in what you found.
- In `suggested_applications`, list 2-4 concrete things ON could do for THIS
  company, tied to ON's services and the company's real activities.
- Include source_urls that back up your assessment.

Do NOT include any of these already-seen companies:
{deny_lines}

Spread your picks across DISTINCT industries within this focus area — avoid
returning many companies from a single niche (e.g. don't return all commercial
aviation; mix in defense, automotive, energy, etc.).

Prioritise strong, defensible fits over filling a quota. When done, call the
`submit_candidates` tool with your results.
"""
