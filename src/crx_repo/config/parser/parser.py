"""Basic parser implementation."""

# pyright: reportAny=false

import logging
from abc import ABC
from abc import abstractmethod
from typing import Callable
from typing import overload
from pathlib import Path
from crx_repo.config.config import Config


type PathOrStr = Path | str
type ConfigJsonType = dict[str, str | int | None | ConfigJsonType]
type KeyConverterType = Callable[[str], str] | None

_logger = logging.getLogger(__name__)


class ConfigParser(ABC):
    """Class to parse config."""
    def __init__(self):
        """Initialize class with no parameter."""
        super().__init__()
        self._cache: dict[Path, Config] = {}

    @overload
    async def parse_async(self, path: str) -> Config:
        ...

    @overload
    async def parse_async(self, path: Path) -> Config:
        ...

    @abstractmethod
    async def parse_async(self, path: PathOrStr) -> Config:
        """Deserialize config from file at path."""

    @overload
    async def support_async(self, path: str) -> bool:
        ...

    @overload
    async def support_async(self, path: Path) -> bool:
        ...

    @abstractmethod
    async def support_async(self, path: PathOrStr) -> bool:
        """Check if path is supported by the parser."""
