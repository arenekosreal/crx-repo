"""Test src/crx_repo/toml.py."""

from pathlib import Path

import pytest

from crx_repo.toml import TomlConfigParser


@pytest.fixture
def parser() -> TomlConfigParser:
    """A pytest fixture to generate a TomlConfigParser object for testing."""
    return TomlConfigParser()


@pytest.fixture
def empty_config(tmp_path: Path) -> Path:
    """A pytest fixture to generate an empty toml config for testing."""
    return tmp_path / "config.toml"


@pytest.fixture
def invalid_config(empty_config: Path) -> Path:
    """A pytest fixture to generate an invalid toml config for testing."""
    _ = empty_config.write_text("key is value")
    return empty_config


@pytest.fixture
def broken_config(empty_config: Path) -> Path:
    """A pytest fixture to generate a broken toml config for testing."""
    _ = empty_config.touch()
    return empty_config


@pytest.fixture
def normal_config(empty_config: Path) -> Path:
    """A pytest fixture to generate a normal toml config for testing."""
    _ = empty_config.write_text('log-level = "DEBUG"\ncache-dir = "example"')
    return empty_config


class TestTomlConfigParser:
    """Test `crx_repo.toml.TomlConfigParser`."""

    @pytest.mark.asyncio
    async def test_parse_async_no_file(
        self,
        empty_config: Path,
        parser: TomlConfigParser,
    ):
        """Test `crx_repo.toml.TomlConfigParser.parse_async` method when no file."""
        result = await parser.parse_async(empty_config)
        assert result is None

    @pytest.mark.asyncio
    async def test_parse_async_invalid_file(
        self,
        invalid_config: Path,
        parser: TomlConfigParser,
    ):
        """Test `crx_repo.toml.TomlConfigParser.parse_async` method when config invalid."""
        result = await parser.parse_async(invalid_config)
        assert result is None

    @pytest.mark.asyncio
    async def test_parse_async_broken_file(
        self,
        broken_config: Path,
        parser: TomlConfigParser,
    ):
        """Test `crx_repo.toml.TomlConfigParser.parse_async` method when config broken."""
        result = await parser.parse_async(broken_config)
        assert result is not None

    @pytest.mark.asyncio
    async def test_parse_async_normal(
        self,
        normal_config: Path,
        parser: TomlConfigParser,
    ):
        """Test `crx_repo.toml.TomlConfigParser.parse_async` method when config correct."""
        result = await parser.parse_async(normal_config)
        assert result is not None
        assert result.log_level == "DEBUG"
        assert result.cache_dir == Path("example")
