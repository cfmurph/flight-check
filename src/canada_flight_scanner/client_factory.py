"""Creates the flight data client from environment credentials."""

import logging
import os

from .security import mask_key
from .serpapi_client import SerpApiFlightClient

logger = logging.getLogger(__name__)


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
    logger.debug("Initialising SerpApi client (key=%s)", mask_key(api_key))
    return SerpApiFlightClient(api_key=api_key)
