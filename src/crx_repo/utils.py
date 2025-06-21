"""Misc utils for various situations."""

from enum import Enum
from logging import getLogger
from importlib.metadata import PackageNotFoundError
from importlib.metadata import metadata


logger = getLogger(__name__)


def has_package(package: str) -> bool:
    """Check if the package is installed.

    Args:
        package(str): The name of package.

    Returns:
        bool: If this package is found.
    """
    try:
        _ = metadata(package)
    except PackageNotFoundError:
        logger.debug("%s is not found.", package)
        return False
    else:
        logger.debug("Found package %s.", package)
        return True


class VersionComparationResult(Enum):
    """An Enum to represent result of version comparation."""

    LessThan = -1
    Equal = 0
    GreaterThan = 1


def _try_get_int(strings: list[str], index: int, default: int) -> int:
    if len(strings) >= index + 1:
        try:
            return int(strings[index])
        except ValueError:
            return default
    return default


def compare_version_string(a: str, b: str) -> VersionComparationResult:
    """Compare version string.

    Args:
        a(str): Version string a
        b(str): Version string b

    Returns:
        VersionComparationResult: If a is greater than b.
    """
    logger.debug("Comparing %s and %s...", a, b)
    splited_a = a.split(".")
    splited_b = b.split(".")
    max_component_count = max(len(splited_a), len(splited_b))
    for i in range(max_component_count):
        a_value = _try_get_int(splited_a, i, 0)
        b_value = _try_get_int(splited_b, i, 0)
        logger.debug("Comparing part %d and %d...", a_value, b_value)
        if a_value > b_value:
            return VersionComparationResult.GreaterThan
        if a_value < b_value:
            return VersionComparationResult.LessThan
    return VersionComparationResult.Equal
