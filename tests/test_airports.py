"""Tests for airports module."""

import pytest
from canada_flight_scanner.airports import (
    CANADIAN_AIRPORTS,
    AIRPORTS_BY_IATA,
    TIER_1_AIRPORTS,
    TIER_2_AIRPORTS,
    get_airports_by_tier,
    get_all_routes,
    get_airport_info,
)


def test_no_duplicate_iata_codes():
    iata_codes = [ap.iata for ap in CANADIAN_AIRPORTS]
    assert len(iata_codes) == len(set(iata_codes)), "Duplicate IATA codes found"


def test_airports_by_iata_lookup():
    assert "YYZ" in AIRPORTS_BY_IATA
    assert "YVR" in AIRPORTS_BY_IATA
    assert AIRPORTS_BY_IATA["YYZ"].city == "Toronto"


def test_get_airport_info():
    ap = get_airport_info("YVR")
    assert ap.iata == "YVR"
    assert "Vancouver" in ap.city


def test_get_airport_info_case_insensitive():
    ap = get_airport_info("yvr")
    assert ap.iata == "YVR"


def test_get_airport_info_unknown():
    with pytest.raises(KeyError):
        get_airport_info("ZZZ")


def test_tier1_airports_present():
    for code in TIER_1_AIRPORTS:
        assert code in AIRPORTS_BY_IATA, f"{code} missing from AIRPORTS_BY_IATA"


def test_get_airports_by_tier():
    tier1 = get_airports_by_tier(1)
    assert len(tier1) == len(TIER_1_AIRPORTS)
    tier2 = get_airports_by_tier(2)
    assert len(tier2) == len(TIER_2_AIRPORTS)


def test_get_all_routes_no_self_routes():
    routes = get_all_routes(origins=["YYZ", "YVR"], max_tier=1)
    for origin, dest in routes:
        assert origin != dest


def test_get_all_routes_count():
    origins = ["YYZ", "YVR"]
    routes = get_all_routes(origins=origins, max_tier=1)
    # 2 origins × (5 tier-1 destinations - 1 self) = max 8 routes
    assert len(routes) > 0
    assert len(routes) <= 2 * (len(TIER_1_AIRPORTS) - 1) * 2
