"""Deterministic, keyword-based sector classification.

Used by the discovery diversifier to cap how many of a day's picks come from any
one sector. Classification runs on the free-text `industry` (and `why_fit`) the
model returns, so it must be robust to varied phrasing. First matching bucket
wins; order matters (most specific / highest-priority first).
"""
from __future__ import annotations

# Ordered: the first bucket with a keyword hit wins.
_BUCKETS: list[tuple[str, list[str]]] = [
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

def classify(*texts: str) -> str:
    """Return a coarse sector bucket for the given text(s), or 'other'."""
    blob = " ".join(t.lower() for t in texts if t)
    for bucket, keywords in _BUCKETS:
        if any(kw in blob for kw in keywords):
            return bucket
    return "other"


def label(bucket: str) -> str:
    """Human-readable label for a bucket key (falls back to the key itself)."""
    return LABELS.get(bucket, bucket)
