"""Misc utils for various situations."""

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
