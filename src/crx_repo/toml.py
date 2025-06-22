"""Parse config in toml format."""

from typing import override
from logging import getLogger
from pathlib import Path
from tomllib import TOMLDecodeError
from tomllib import loads

from pydantic import ValidationError

from crx_repo.config import Config
from crx_repo.config import ConfigParser


logger = getLogger(__name__)


class TomlConfigParser(ConfigParser):
    """A ConfigParser implementation to parse toml config."""

    @override
    async def parse_async(self, config: Path) -> Config | None:
        if not config.exists():
            return None
        try:
            config_dict = loads(config.read_text())
            config_object = Config.model_validate(config_dict)
        except TOMLDecodeError:
            logger.exception("Failed to parse toml file.")
            config_object = None
        except ValidationError:
            logger.exception("Failed to validate model.")
            config_object = None

        return config_object
