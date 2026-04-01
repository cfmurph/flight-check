"""Tests for security validation utilities."""

import pytest
from pathlib import Path

from canada_flight_scanner.security import (
    validate_iata,
    validate_iata_list,
    validate_output_dir,
    cap,
    mask_key,
    MAX_DAYS,
    MAX_WORKERS,
    MAX_TOP,
)


class TestValidateIata:
    def test_valid_code(self):
        assert validate_iata("YYZ") == "YYZ"

    def test_lowercase_normalised(self):
        assert validate_iata("yvr") == "YVR"

    def test_strips_whitespace(self):
        assert validate_iata("  YUL  ") == "YUL"

    def test_too_short_raises(self):
        with pytest.raises(ValueError):
            validate_iata("YY")

    def test_too_long_raises(self):
        with pytest.raises(ValueError):
            validate_iata("YYYY")

    def test_digits_raises(self):
        with pytest.raises(ValueError):
            validate_iata("Y1Z")

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            validate_iata("")

    def test_special_chars_raises(self):
        with pytest.raises(ValueError):
            validate_iata("Y;Z")

    def test_injection_attempt_raises(self):
        with pytest.raises(ValueError):
            validate_iata("'; DROP TABLE flights; --")


class TestValidateIataList:
    def test_valid_list(self):
        result = validate_iata_list(["YYZ", "YVR", "YUL"])
        assert result == ["YYZ", "YVR", "YUL"]

    def test_invalid_in_list_raises(self):
        with pytest.raises(ValueError):
            validate_iata_list(["YYZ", "INVALID"])


class TestValidateOutputDir:
    def test_normal_path(self, tmp_path):
        result = validate_output_dir(str(tmp_path))
        assert result == tmp_path.resolve()

    def test_null_byte_raises(self):
        with pytest.raises(ValueError, match="null bytes"):
            validate_output_dir("/tmp/re\x00ports")

    def test_returns_resolved_path(self):
        result = validate_output_dir("./reports")
        assert result.is_absolute()


class TestCap:
    def test_within_range(self):
        assert cap(50, 1, 100, "x") == 50

    def test_below_minimum(self):
        assert cap(0, 1, 100, "x") == 1

    def test_above_maximum(self):
        assert cap(999, 1, 365, "days") == 365

    def test_at_minimum(self):
        assert cap(1, 1, 100, "x") == 1

    def test_at_maximum(self):
        assert cap(100, 1, 100, "x") == 100

    def test_days_cap(self):
        assert cap(9999, 1, MAX_DAYS, "days") == MAX_DAYS

    def test_workers_cap(self):
        assert cap(999, 1, MAX_WORKERS, "workers") == MAX_WORKERS

    def test_top_cap(self):
        assert cap(9999, 1, MAX_TOP, "top") == MAX_TOP


class TestMaskKey:
    def test_masks_most_of_key(self):
        result = mask_key("abcdefghij1234")
        assert result.startswith("abcd")
        assert "****" in result
        assert "efghij1234" not in result

    def test_short_key(self):
        assert mask_key("abc") == "****"

    def test_empty_key(self):
        assert mask_key("") == "****"

    def test_full_key_not_exposed(self):
        key = "supersecretkey123"
        masked = mask_key(key)
        assert key not in masked
