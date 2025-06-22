"""Test src/crx_repo/utils.py."""

import pytest

from crx_repo.utils import VersionComparationResult
from crx_repo.utils import has_package
from crx_repo.utils import compare_version_string


has_package_map = [
    ("pytest", True),
    ("not-installed", False),
]


@pytest.mark.parametrize(("package", "result"), has_package_map)
def test_has_package(package: str, *, result: bool):
    """Test `crx_repo.utils.has_package` function."""
    actual = has_package(package)
    assert actual == result


test_map = [
    ("1", "2", VersionComparationResult.LessThan),
    ("2", "1", VersionComparationResult.GreaterThan),
    ("1", "1", VersionComparationResult.Equal),
    ("1.0", "1.1", VersionComparationResult.LessThan),
    ("1.0.0", "1.1", VersionComparationResult.LessThan),
]


@pytest.mark.parametrize(("a", "b", "target_result"), test_map)
def test_compare_version_string(a: str, b: str, target_result: bool):  # noqa: FBT001
    """Test `crx_repo.client.compare_version_string` function."""
    result = compare_version_string(a, b)
    assert result == target_result
