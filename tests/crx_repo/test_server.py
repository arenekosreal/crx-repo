"""Test src/crx_repo/server.py."""

from pathlib import Path

import pytest
from aiohttp.web import HTTPOk
from pytest_aiohttp import AiohttpClient

from crx_repo.config import Config
from crx_repo.server import setup


@pytest.fixture
def config(unused_tcp_port: int, tmp_path: Path) -> Config:
    """A pytest fixture to generate Config object for testing."""
    return Config.model_validate(
        {
            "listen": {
                "tcp": {
                    "address": "127.0.0.1",
                    "port": unused_tcp_port,
                },
            },
            "cache-dir": str(tmp_path / "cache"),
        },
    )


@pytest.mark.asyncio
async def test_setup(
    config: Config,
    aiohttp_client: AiohttpClient,
):
    """Test `crx_repo.server.setup` function."""
    app = setup(config)
    client = await aiohttp_client(app)
    async with client.get("/crx-repo/updates.xml") as response:
        assert response.status == HTTPOk.status_code
        content = await response.text()
        assert content
