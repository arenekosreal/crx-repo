"""Test src/crx_repo/client.py."""

import pytest

from crx_repo.client import VersionComparationResult
from crx_repo.client import compare_version_string


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
