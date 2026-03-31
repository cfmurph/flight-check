"""
Factory that selects the right API client based on available credentials.

Priority:
  1. SERPAPI_KEY present  → SerpApiFlightClient  (Google Flights, recommended)
  2. AMADEUS_CLIENT_ID + AMADEUS_CLIENT_SECRET present → AmadeusFlightClient
     (note: Amadeus Self-Service is decommissioned July 17 2026)
  3. Neither present → raises ValueError with setup instructions
"""

import os
from typing import Union

from .api_client import AmadeusFlightClient
from .serpapi_client import SerpApiFlightClient

AnyFlightClient = Union[SerpApiFlightClient, AmadeusFlightClient]


def create_client() -> AnyFlightClient:
    """
    Return the best available flight data client given current environment variables.

    Raises:
        ValueError: if no credentials are configured.
    """
    serpapi_key = os.getenv("SERPAPI_KEY", "").strip()
    amadeus_id = os.getenv("AMADEUS_CLIENT_ID", "").strip()
    amadeus_secret = os.getenv("AMADEUS_CLIENT_SECRET", "").strip()

    if serpapi_key:
        return SerpApiFlightClient(api_key=serpapi_key)

    if amadeus_id and amadeus_secret:
        import warnings
        warnings.warn(
            "Amadeus Self-Service APIs are decommissioned on July 17 2026. "
            "Switch to SERPAPI_KEY for continued access.",
            DeprecationWarning,
            stacklevel=2,
        )
        return AmadeusFlightClient(client_id=amadeus_id, client_secret=amadeus_secret)

    raise ValueError(
        "No flight API credentials found.\n\n"
        "Recommended: SerpApi (Google Flights) — 100 free searches/month\n"
        "  1. Sign up at https://serpapi.com/users/sign_up\n"
        "  2. Add to your .env:  SERPAPI_KEY=your_key_here\n\n"
        "Alternative: Amadeus (decommissioned July 17 2026)\n"
        "  Add AMADEUS_CLIENT_ID and AMADEUS_CLIENT_SECRET to your .env\n\n"
        "Copy .env.example to .env and fill in your key."
    )
