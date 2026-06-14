"""Deterministic, keyword-based sector classification.

Used by the discovery diversifier to cap how many of a day's picks come from any
one sector. Classification runs on the free-text `industry` (and `why_fit`) the
model returns, so it must be robust to varied phrasing. First matching bucket
wins; order matters (most specific / highest-priority first).
"""
from __future__ import annotations

import agent_profile

# Default taxonomy (engineering/science oriented). A profile may override it via
# a `sectors:` block in profile.yaml. Ordered: first bucket with a hit wins.
_DEFAULT_BUCKETS: list[tuple[str, list[str]]] = [
    ("aerospace_defense", [
        "aerospace", "aviation", "aircraft", "airline", "defense", "defence",
        "space", "satellite", "rocket", "launch", "propulsion", "turbine",
        "turbomachinery", "jet ", "uav", "drone",
    ]),
    ("automotive", [
        "automotive", "vehicle", "mobility", "autonomous driving", "self-driving",
        "powertrain", "ev maker", "electric vehicle",
    ]),
    ("energy", [
        "energy", "oil", "gas", "petroleum", "nuclear", "reactor", "power plant",
        "renewable", "wind", "solar", "battery", "grid", "geothermal", "fusion",
        "hydrogen",
    ]),
    ("life_sciences", [
        "pharma", "biotech", "biopharma", "drug", "medical", "medtech", "device",
        "healthcare", "clinical", "genomic", "life science", "diagnostic",
        "therapeutic", "biolog",
    ]),
    ("materials_chemicals", [
        "material", "chemical", "polymer", "metallurg", "composite", "coating",
        "catalyst", "specialty chem",
    ]),
    ("semiconductors_electronics", [
        "semiconductor", "chip", "electronics", "photonic", "microelectronic",
        "fab ", "foundry", "wafer", "pcb",
    ]),
    ("climate_geoscience", [
        "climate", "weather", "geoscience", "geophysic", "environmental", "ocean",
        "seismic", "atmospher", "hydrolog", "earth observation",
    ]),
    ("finance", [
        "finance", "financial", "fintech", "quant", "trading", "insurance",
        "bank", "asset management", "hedge fund", "actuar",
    ]),
    ("manufacturing_industrial", [
        "manufactur", "industrial", "robotics", "machinery", "additive",
        "3d printing", "cnc", "factory", "process optimi",
    ]),
]


# Human-readable labels for prompts and help text.
LABELS = {
    "aerospace_defense": "aerospace, defense, and aviation",
    "automotive": "automotive",
    "energy": "energy and power",
    "life_sciences": "pharma, biotech, and medical",
    "materials_chemicals": "materials and chemicals",
    "semiconductors_electronics": "semiconductors and electronics",
    "climate_geoscience": "climate and geoscience",
    "finance": "finance and quantitative trading",
    "manufacturing_industrial": "manufacturing and industrial",
    "other": "other",
}

def _buckets() -> list[tuple[str, list[str]]]:
    """Active taxonomy: the profile's `sectors:` override, else the default."""
    if agent_profile.SECTORS:
        return [(b, [k.lower() for k in kws]) for b, kws in agent_profile.SECTORS.items()]
    return _DEFAULT_BUCKETS


def classify(*texts: str) -> str:
    """Return a coarse sector bucket for the given text(s), or 'other'."""
    blob = " ".join(t.lower() for t in texts if t)
    for bucket, keywords in _buckets():
        if any(kw in blob for kw in keywords):
            return bucket
    return "other"


def label(bucket: str) -> str:
    """Human-readable label for a bucket key (humanizes unknown keys)."""
    return LABELS.get(bucket, bucket.replace("_", " "))
