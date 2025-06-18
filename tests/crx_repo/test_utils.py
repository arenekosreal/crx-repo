"""Test src/crx_repo/utils.py."""

import pytest
from crx_repo.utils import has_package


has_package_map = [
    ("pytest", True),
    ("not-installed", False),
]


@pytest.mark.parametrize(("package", "result"), has_package_map)
def test_has_package(package: str, result: bool):
    """Test `crx_repo.utils.has_package` function."""
    actual = has_package(package)
    assert actual == result
