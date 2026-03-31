"""Creates the flight data client from environment credentials."""

import os

from .serpapi_client import SerpApiFlightClient


def create_client() -> SerpApiFlightClient:
    """
    Return a SerpApiFlightClient using SERPAPI_KEY from the environment.

    Raises:
        ValueError: if SERPAPI_KEY is not set.
    """
    api_key = os.getenv("SERPAPI_KEY", "").strip()
    if not api_key:
        raise ValueError(
            "No API key found.\n\n"
            "Set SERPAPI_KEY in your .env file.\n"
            "Free account (100 searches/month): https://serpapi.com/users/sign_up\n\n"
            "Copy .env.example to .env and fill in your key."
        )
    return SerpApiFlightClient(api_key=api_key)
