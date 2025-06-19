"""Test src/crx_repo/cache.py."""

from random import randbytes
from hashlib import sha256
from pathlib import Path

import pytest
from aiofiles import open as aioopen
from aiohttp.web import Application

from crx_repo.cache import MemoryCache


@pytest.fixture
def cache(tmp_path: Path) -> MemoryCache:
    """A pytest fixture to generate a MemoryCache object for testing."""
    return MemoryCache(tmp_path, Application(), "/test-prefix", "test-name")


class TestMemoryCache:
    """Test MemoryCache object."""

    def test_extension_path(self, tmp_path: Path, cache: MemoryCache):
        """Test `crx_repo.cache.MemoryCache.extension_path` method."""
        path = cache.extension_path("example-id", "example-version")
        assert path == tmp_path / "example-id" / "example-version.crx"

    def test_extension_size(self, cache: MemoryCache):
        """Test `crx_repo.cache.MemoryCache.extension_size` method."""
        size = cache.extension_size("example-id", "example-version")
        assert size == 0

    @pytest.mark.asyncio
    async def test_extension_sha256_async(self, tmp_path: Path, cache: MemoryCache):
        """Test `crx_repo.cache.MemoryCache.extension_sha256_async` method."""
        example_file = tmp_path / "example-id" / "example-version.crx"
        data = randbytes(42)  # noqa: S311
        target_hash = sha256(data).hexdigest()
        example_file.parent.mkdir(exist_ok=True, parents=True)
        async with aioopen(example_file, "wb") as writer:
            _ = await writer.write(data)
        actual_hash = await cache.extension_sha256_async(
            "example-id",
            "example-version",
        )
        assert actual_hash == target_hash

    def test_extension_codebase(self, cache: MemoryCache):
        """Test `crx_repo.cache.MemoryCache.extension_codebase` method."""
        result = cache.extension_codebase(
            "http://example.com",
            "/example-prefix",
            "example-id",
            "example-version",
        )
        target = "http://example.com/example-prefix/example-id/example-version.crx"
        assert result == target
