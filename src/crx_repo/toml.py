from typing import override
from .config import Config
from .config import ConfigParser
from pathlib import Path
from tomllib import loads
from pydantic import ValidationError
from aiofiles import open as aioopen


class TomlConfigParser(ConfigParser):
    @override
    async def parse_async(self, config: Path) -> Config | None:
        async with aioopen(config, "r") as reader:
            config_dict = loads(await reader.read())
            try:
                config_object = Config.model_validate(config_dict, by_alias=True)
            except ValidationError:
                config_object = None

            return config_object
