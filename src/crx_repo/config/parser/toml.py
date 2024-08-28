"""ConfigParser implementation to parse toml config."""

import tomllib
from typing import override
from pathlib import Path
from crx_repo.config.config import Config
from crx_repo.config.parser.parser import PathOrStr
from crx_repo.config.parser.parser import ConfigParser


class TomlConfigParser(ConfigParser):
    """Class to parse toml config."""
    @override
    async def parse_async(self, path: PathOrStr) -> Config:
        if isinstance(path, str):
            path = Path(path)
        if path not in self._cache:
            content = path.read_text()
            config_raw = tomllib.loads(content)
            self._cache[path] = TomlConfigParser.deserialize(
                Config, config_raw,
                lambda x: x.replace("-", "_").lower(),  # Kebab case to snake case
            )
        return self._cache[path]

    @override
    async def support_async(self, path: PathOrStr) -> bool:
        if isinstance(path, str):
            path = Path(path)
        return path.name.endswith(".toml")
