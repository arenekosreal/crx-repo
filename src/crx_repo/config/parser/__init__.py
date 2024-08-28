"""Classes and functions to parse config."""

from typing import overload
from pathlib import Path
from crx_repo.config.config import Config
from crx_repo.config.parser.toml import TomlConfigParser
from crx_repo.config.parser.parser import PathOrStr
from crx_repo.config.parser.parser import ConfigParser


_parsers: list[ConfigParser] = [
    TomlConfigParser(),
]


@overload
async def parse_config_async(config_path: str) -> Config:
    ...


@overload
async def parse_config_async(config_path: Path) -> Config:
    ...


async def parse_config_async(config_path: PathOrStr) -> Config:
    """Parse the config.

    Raises:
        ValueError: If no supported parser found.
    """
    for parser in _parsers:
        if await parser.support_async(config_path):
            return await parser.parse_async(config_path)
    raise ValueError("Unsupported config file %s", config_path)


__all__ = ["parse_config_async"]
