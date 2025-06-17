"""Classes and functions to parse config files."""

from abc import ABC
from abc import abstractmethod
from ssl import Purpose
from ssl import SSLContext
from ssl import create_default_context
from typing import Literal
from typing import ClassVar
from pathlib import Path
from pydantic import BaseModel as PyDanticBaseModel
from pydantic import ConfigDict
from pydantic import PositiveInt
from pydantic import field_validator
from pydantic.alias_generators import to_snake


type LogLevelType = Literal["NOTSET", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


def _to_kebab(string: str) -> str:
    return to_snake(string).replace("_", "-")


class BaseModel(PyDanticBaseModel):
    """A base class which defines models of config files."""

    model_config: ClassVar[ConfigDict] = ConfigDict(alias_generator=_to_kebab)


class TlsHttpListenConfig(BaseModel):
    """HTTPS config."""

    cert: Path = Path("crx-repo.crt")
    key: str | None = None
    password: str | None = None

    @property
    def ssl_context(self) -> SSLContext:
        """The ssl context of current HTTPS config."""
        context = create_default_context(Purpose.CLIENT_AUTH)
        context.load_cert_chain(self.cert, self.key, self.password)
        return context


class UnixListenConfig(BaseModel):
    """Unix domain socket config."""

    path: Path = Path("/run/crx-repo/crx-repo.socket")
    permission: int = 666
    tls: TlsHttpListenConfig | None = None


class TcpListenConfig(BaseModel):
    """TCP config."""

    address: str = "127.0.0.1"
    port: PositiveInt = 8888
    tls: TlsHttpListenConfig | None = None


class ListenConfig(BaseModel):
    """Listen config."""

    tcp: TcpListenConfig | None = None
    unix: UnixListenConfig | None = None

    @field_validator("tcp")
    @classmethod
    def tcp_is_not_none(
        cls,
        value: TcpListenConfig | None,
    ) -> TcpListenConfig | None:
        """Ensure tcp and unix are not None either."""
        if value is None and cls.unix is None:
            raise ValueError("You need to specify at least one of tcp and unix")
        return value

    @field_validator("unix")
    @classmethod
    def unix_is_not_none(
        cls,
        value: UnixListenConfig | None,
    ) -> UnixListenConfig | None:
        """Ensure unix and tcp are not None either."""
        if value is None and cls.tcp is None:
            raise ValueError("You need to specify at least one of tcp and unix")
        return value


class Config(BaseModel):
    """Main runtime config."""

    log_level: LogLevelType = "INFO"
    manifest_path: str = "/updates.xml"
    prefix: str = "/crx-repo"
    base: str = "http://localhost:8888"
    proxy: str | None = None
    version: str = "128.0"
    interval: PositiveInt = 10800
    extensions: list[str] = []
    cache_dir: Path = Path("cache")
    listen: ListenConfig = ListenConfig()


class ConfigParser(ABC):
    """Abstract class for what a config parser should do."""

    @abstractmethod
    async def parse_async(self, config: Path) -> Config | None:
        """Parse the config asynchronously.

        Args:
            config(Path): The path of config file.

        Returns:
            Config | None: Deserialized config. None means failed to parse.
        """
