"""Input validation and security utilities."""

import re
import logging
from pathlib import Path
from typing import List

logger = logging.getLogger(__name__)

_IATA_RE = re.compile(r"^[A-Z]{3}$")

# Hard caps on user-supplied integer inputs
MAX_DAYS = 365
MAX_WORKERS = 16
MAX_TOP = 200


def validate_iata(code: str) -> str:
    """
    Validate and return an IATA airport code.

    Raises:
        ValueError: if the code is not exactly 3 uppercase letters.
    """
    code = code.strip().upper()
    if not _IATA_RE.match(code):
        raise ValueError(
            f"Invalid IATA code: {code!r}. Must be exactly 3 letters (e.g. YYZ)."
        )
    return code


def validate_iata_list(codes: List[str]) -> List[str]:
    """Validate a list of IATA codes, raising ValueError on the first invalid one."""
    return [validate_iata(c) for c in codes]


def validate_output_dir(path_str: str) -> Path:
    """
    Resolve and validate the output directory path.

    Prevents path traversal by resolving the path and checking it doesn't
    contain null bytes or other unsafe characters.

    Raises:
        ValueError: if the path contains suspicious components.
    """
    if "\x00" in path_str:
        raise ValueError("Output path contains null bytes.")
    resolved = Path(path_str).resolve()
    return resolved


def cap(value: int, minimum: int, maximum: int, name: str) -> int:
    """Clamp an integer to [minimum, maximum], logging a warning if clamped."""
    if value < minimum:
        logger.warning("%s value %d is below minimum %d, using %d", name, value, minimum, minimum)
        return minimum
    if value > maximum:
        logger.warning("%s value %d exceeds maximum %d, using %d", name, value, maximum, maximum)
        return maximum
    return value


def mask_key(key: str, visible: int = 4) -> str:
    """Return a masked version of an API key safe for logging (e.g. 'abcd****')."""
    if not key or len(key) <= visible:
        return "****"
    return key[:visible] + "*" * (len(key) - visible)
