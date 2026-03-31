"""Canadian airports configuration and route generation."""

from dataclasses import dataclass
from typing import List, Tuple


@dataclass(frozen=True)
class Airport:
    iata: str
    name: str
    city: str
    province: str
    timezone: str


CANADIAN_AIRPORTS: List[Airport] = [
    Airport("YYZ", "Toronto Pearson International", "Toronto", "Ontario", "America/Toronto"),
    Airport("YYZ", "Toronto Pearson International", "Toronto", "Ontario", "America/Toronto"),
    Airport("YVR", "Vancouver International", "Vancouver", "British Columbia", "America/Vancouver"),
    Airport("YUL", "Montréal–Trudeau International", "Montreal", "Quebec", "America/Toronto"),
    Airport("YYC", "Calgary International", "Calgary", "Alberta", "America/Edmonton"),
    Airport("YEG", "Edmonton International", "Edmonton", "Alberta", "America/Edmonton"),
    Airport("YOW", "Ottawa Macdonald–Cartier International", "Ottawa", "Ontario", "America/Toronto"),
    Airport("YHZ", "Halifax Stanfield International", "Halifax", "Nova Scotia", "America/Halifax"),
    Airport("YWG", "Winnipeg Richardson International", "Winnipeg", "Manitoba", "America/Winnipeg"),
    Airport("YXE", "Saskatoon John G. Diefenbaker International", "Saskatoon", "Saskatchewan", "America/Regina"),
    Airport("YQR", "Regina International", "Regina", "Saskatchewan", "America/Regina"),
    Airport("YQB", "Quebec City Jean Lesage International", "Quebec City", "Quebec", "America/Toronto"),
    Airport("YYJ", "Victoria International", "Victoria", "British Columbia", "America/Vancouver"),
    Airport("YLW", "Kelowna International", "Kelowna", "British Columbia", "America/Vancouver"),
    Airport("YXX", "Abbotsford International", "Abbotsford", "British Columbia", "America/Vancouver"),
    Airport("YYT", "St. John's International", "St. John's", "Newfoundland", "America/St_Johns"),
    Airport("YFC", "Fredericton International", "Fredericton", "New Brunswick", "America/Halifax"),
    Airport("YQM", "Greater Moncton Roméo LeBlanc International", "Moncton", "New Brunswick", "America/Halifax"),
    Airport("YSJ", "Saint John Airport", "Saint John", "New Brunswick", "America/Halifax"),
    Airport("YZF", "Yellowknife Airport", "Yellowknife", "Northwest Territories", "America/Yellowknife"),
    Airport("YXY", "Erik Nielsen Whitehorse International", "Whitehorse", "Yukon", "America/Whitehorse"),
    Airport("YFB", "Iqaluit Airport", "Iqaluit", "Nunavut", "America/Iqaluit"),
]

# Remove duplicate YYZ entry
_seen: set = set()
_unique: List[Airport] = []
for _ap in CANADIAN_AIRPORTS:
    if _ap.iata not in _seen:
        _seen.add(_ap.iata)
        _unique.append(_ap)
CANADIAN_AIRPORTS = _unique

AIRPORTS_BY_IATA: dict = {ap.iata: ap for ap in CANADIAN_AIRPORTS}

# High-traffic airports get more scanning priority
TIER_1_AIRPORTS = ["YYZ", "YVR", "YUL", "YYC", "YEG"]
TIER_2_AIRPORTS = ["YOW", "YHZ", "YWG", "YXE", "YQR", "YQB", "YYJ"]
TIER_3_AIRPORTS = ["YLW", "YXX", "YYT", "YFC", "YQM", "YSJ", "YZF", "YXY", "YFB"]


def get_airports_by_tier(tier: int) -> List[Airport]:
    """Return airports for the given tier (1=busiest, 3=smallest)."""
    tier_map = {
        1: TIER_1_AIRPORTS,
        2: TIER_2_AIRPORTS,
        3: TIER_3_AIRPORTS,
    }
    codes = tier_map.get(tier, [])
    return [AIRPORTS_BY_IATA[c] for c in codes if c in AIRPORTS_BY_IATA]


def get_all_routes(origins: List[str] = None, max_tier: int = 2) -> List[Tuple[str, str]]:
    """
    Generate all origin→destination route pairs for scanning.

    Args:
        origins: List of IATA codes to use as origins. Defaults to Tier 1 airports.
        max_tier: Include destinations up to this tier (1, 2, or 3).

    Returns:
        List of (origin_iata, destination_iata) tuples.
    """
    if origins is None:
        origins = TIER_1_AIRPORTS

    destinations: List[str] = []
    for t in range(1, max_tier + 1):
        tier_airports = get_airports_by_tier(t)
        destinations.extend([ap.iata for ap in tier_airports])
    destinations = list(dict.fromkeys(destinations))  # deduplicate, preserve order

    routes = []
    for origin in origins:
        for dest in destinations:
            if origin != dest:
                routes.append((origin, dest))
    return routes


def get_airport_info(iata: str) -> Airport:
    """Look up airport by IATA code, raises KeyError if not found."""
    return AIRPORTS_BY_IATA[iata.upper()]
