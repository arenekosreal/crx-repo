"""Parse config in toml format."""

from typing import override
from .config import Config
from .config import ConfigParser
from pathlib import Path
from tomllib import loads
from aiofiles import open as aioopen
from pydantic import ValidationError


class TomlConfigParser(ConfigParser):
    """A ConfigParser implementation to parse toml config."""

    @override
    async def parse_async(self, config: Path) -> Config | None:
        if not config.exists():
            return None
        async with aioopen(config, "r") as reader:
            config_dict = loads(await reader.read())
            try:
                config_object = Config.model_validate(config_dict, by_alias=True)
            except ValidationError:
                config_object = None

            return config_object
