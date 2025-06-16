from abc import ABC
from abc import abstractmethod
from typing import Literal
from typing import ClassVar
from pathlib import Path
from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import PositiveInt
from pydantic import field_validator
from pydantic.alias_generators import to_snake
from ssl import SSLContext
from ssl import create_default_context
from ssl import Purpose


type LogLevelType = Literal["NOTSET", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


class ConfigModel(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(alias_generator=to_snake)


class TlsHttpListenConfig(ConfigModel):
    """HTTPS config."""

    cert: Path = Path("crx-repo.crt")
    key: str | None = None
    password: str | None = None

    @property
    def ssl_context(self) -> SSLContext:
        context = create_default_context(Purpose.CLIENT_AUTH)
        context.load_cert_chain(self.cert, self.key, self.password)
        return context


class UnixListenConfig(ConfigModel):
    """Unix domain socket config."""

    path: Path = Path("/run/crx-repo/crx-repo.socket")
    permission: int = 666
    tls: TlsHttpListenConfig | None = None


class TcpListenConfig(ConfigModel):
    """TCP config."""

    address: str = "127.0.0.1"
    port: PositiveInt = 8888
    tls: TlsHttpListenConfig | None = None


class ListenConfig(ConfigModel):
    """Listen config."""

    tcp: TcpListenConfig | None = TcpListenConfig()
    unix: UnixListenConfig | None = None

    @field_validator("tcp")
    @classmethod
    def tcp_is_not_none(
        cls,
        value: TcpListenConfig | None,
    ) -> TcpListenConfig | None:
        if value is None and cls.unix is None:
            raise ValueError("You need to specify at least one of tcp and unix")
        return value

    @field_validator("unix")
    @classmethod
    def unix_is_not_none(
        cls,
        value: UnixListenConfig | None,
    ) -> UnixListenConfig | None:
        if value is None and cls.tcp is None:
            raise ValueError("You need to specify at least one of tcp and unix")
        return value


class Config(ConfigModel):
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
    @abstractmethod
    async def parse_async(self, config: Path) -> Config | None: ...
