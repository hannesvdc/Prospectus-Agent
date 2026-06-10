"""Tests for the keyword sector classifier used by the diversifier."""
from __future__ import annotations

import pytest

import sectors


@pytest.mark.parametrize("text,expected", [
    ("Commercial aviation", "aerospace_defense"),
    ("Aerospace & Defense", "aerospace_defense"),
    ("Aircraft engine manufacturer", "aerospace_defense"),
    ("Automotive OEM", "automotive"),
    ("Oil and gas exploration", "energy"),
    ("Battery storage startup", "energy"),
    ("Pharmaceutical company", "life_sciences"),
    ("Medical devices", "life_sciences"),
    ("Semiconductor foundry", "semiconductors_electronics"),
    ("Specialty chemicals", "materials_chemicals"),
    ("Quantitative trading firm", "finance"),
    ("Industrial robotics", "manufacturing_industrial"),
    ("Climate modelling services", "climate_geoscience"),
    ("Artisan cheese shop", "other"),
])
def test_classify(text, expected):
    assert sectors.classify(text) == expected


def test_classify_is_case_insensitive():
    assert sectors.classify("AEROSPACE") == "aerospace_defense"


def test_classify_uses_all_texts():
    # Industry blank, but why_fit carries the signal.
    assert sectors.classify("", "they run CFD on jet engines") == "aerospace_defense"


def test_classify_empty_is_other():
    assert sectors.classify("", "") == "other"
