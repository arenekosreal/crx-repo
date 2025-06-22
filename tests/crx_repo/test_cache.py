"""Test src/crx_repo/cache.py."""

from random import randbytes
from hashlib import sha256
from pathlib import Path

import pytest
from aiohttp.web import Application

from crx_repo.cache import MemoryCache


@pytest.fixture
def cache(tmp_path: Path) -> MemoryCache:
    """A pytest fixture to generate a MemoryCache object for testing."""
    return MemoryCache(tmp_path, Application(), "/test-prefix", "test-name")


class TestMemoryCache:
    """Test MemoryCache object."""

    @pytest.mark.asyncio
    async def test_new_extension_async(self, cache: MemoryCache, tmp_path: Path):
        """Test `crx_repo.cache.MemoryCache.new_extension_async` method."""
        async with cache.new_extension_async(
            "example-id",
            "example-ver",
            metakey="metaver",
        ) as path:
            path.parent.mkdir(parents=True)
            _ = path.write_bytes(randbytes(42))  # noqa: S311
        target_file = tmp_path / "example-id" / "example-ver.crx"
        meta_file = tmp_path / "example-id" / "example-ver.meta.json"
        assert target_file.is_file()
        assert meta_file.is_file()

    @pytest.mark.asyncio
    async def test_get_gupdate_async(self, cache: MemoryCache):
        """Test `crx_repo.cache.MemoryCache.get_gupdate_async` method."""
        mock_data = randbytes(42)  # noqa: S311
        mock_data_hash = sha256(mock_data).hexdigest()
        async with cache.new_extension_async(
            "example-id",
            "example-ver",
            metakey="metaver",
        ) as path:
            path.parent.mkdir(parents=True)
            _ = path.write_bytes(mock_data)
        gupdate = await cache.get_gupdate_async("https://example.com", "/prefix")
        assert len(gupdate.apps) == 1
        app = gupdate.apps[0]
        assert len(app.updatechecks) == 1
        assert app.appid == "example-id"
        updatecheck = app.updatechecks[0]
        assert updatecheck.hash_sha256 == mock_data_hash
