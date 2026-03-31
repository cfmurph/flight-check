"""Tests for the client factory / credential selection logic."""

import pytest
from unittest.mock import patch

from canada_flight_scanner.client_factory import create_client
from canada_flight_scanner.serpapi_client import SerpApiFlightClient
from canada_flight_scanner.api_client import AmadeusFlightClient


class TestCreateClient:
    def test_serpapi_key_wins(self):
        env = {
            "SERPAPI_KEY": "serp-test-key",
            "AMADEUS_CLIENT_ID": "amadeus-id",
            "AMADEUS_CLIENT_SECRET": "amadeus-secret",
        }
        with patch.dict("os.environ", env, clear=True):
            with patch("canada_flight_scanner.serpapi_client.GoogleSearch"):
                client = create_client()
        assert isinstance(client, SerpApiFlightClient)

    def test_falls_back_to_amadeus(self):
        env = {
            "AMADEUS_CLIENT_ID": "amadeus-id",
            "AMADEUS_CLIENT_SECRET": "amadeus-secret",
        }
        with patch.dict("os.environ", env, clear=True):
            with patch("canada_flight_scanner.api_client.Client"):
                with pytest.warns(DeprecationWarning, match="decommissioned"):
                    client = create_client()
        assert isinstance(client, AmadeusFlightClient)

    def test_no_credentials_raises(self):
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(ValueError, match="SERPAPI_KEY"):
                create_client()
