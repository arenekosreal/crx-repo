"""Test src/crx_repo/server.py."""

import pytest
from asyncio import Event
from aiohttp.web import HTTPOk
from pytest_aiohttp import AiohttpClient
from crx_repo.config import Config
from crx_repo.server import setup


@pytest.fixture
def config(unused_tcp_port: int) -> Config:
    """A pytest fixture to generate Config object for testing."""
    return Config.model_validate(
        {
            "listen": {
                "tcp": {
                    "address": "127.0.0.1",
                    "port": unused_tcp_port,
                }
            }
        }
    )


@pytest.mark.asyncio
async def test_setup(
    config: Config,
    aiohttp_client: AiohttpClient,
):
    """Test `crx_repo.server.setup` function."""
    event = Event()
    app = setup(config, event)
    client = await aiohttp_client(app)
    async with client.get("/updates.xml") as response:
        assert response.status == HTTPOk.status_code
        content = await response.text()
        assert content
