"""Download Chrom(e|ium) extensions from various sources and serve a update manifest."""

__version__ = "0.3.1"


from signal import SIGINT
from signal import SIGTERM
from typing import Annotated
from asyncio import Event
from asyncio import get_event_loop
from logging import Formatter
from logging import StreamHandler
from logging import getLogger
from pathlib import Path

from rich import print as rich_print
from typer import Exit
from typer import Typer
from typer import Option
from aiohttp.web import TCPSite
from aiohttp.web import UnixSite
from aiohttp.web import AppRunner

from crx_repo.toml import TomlConfigParser
from crx_repo.utils import has_package
from crx_repo.config import Config
from crx_repo.config import ConfigParser
from crx_repo.config import LogLevelType
from crx_repo.server import setup


if has_package("uvloop"):
    from uvloop import run
else:
    from asyncio import run
logger = getLogger(__name__)
main = Typer()


class ParseError(RuntimeError):
    """Exception raised when failed to parse configuration."""

    def __init__(self, config_path: Path):
        """Initialize `ParseError` with arguments given.

        Args:
            config_path(Path): The path of configuration.
        """
        super().__init__(f"Unable to parse config {config_path}")


async def __parse_async(config: Path) -> Config:
    parsers: list[ConfigParser] = [TomlConfigParser()]
    for parser in parsers:
        config_object = await parser.parse_async(config)
        if config_object is not None:
            return config_object
    raise ParseError(config) from None


async def __launch_async(config: Path):
    loop = get_event_loop()
    deserialized_config = await __parse_async(config)
    logger.setLevel(deserialized_config.log_level)
    for handler in logger.handlers:
        handler.setLevel(deserialized_config.log_level)
    event = Event()
    app = setup(deserialized_config, event)
    runner = AppRunner(app)
    await runner.setup()
    if deserialized_config.listen.tcp is not None:
        site = TCPSite(
            runner,
            deserialized_config.listen.tcp.address,
            deserialized_config.listen.tcp.port,
            ssl_context=deserialized_config.listen.tcp.tls.ssl_context
            if deserialized_config.listen.tcp.tls is not None
            else None,
        )
        await site.start()
    if deserialized_config.listen.unix is not None:
        site = UnixSite(
            runner,
            deserialized_config.listen.unix.path,
            ssl_context=deserialized_config.listen.unix.tls.ssl_context
            if deserialized_config.listen.unix.tls is not None
            else None,
        )
        await site.start()

    for signal in [SIGTERM, SIGINT]:
        loop.add_signal_handler(signal, event.set)
    logger.debug("Running with event loop %s...", loop)
    logger.info("Starting web server...")
    _ = await event.wait()
    logger.info("Exiting...")
    await runner.cleanup()


def __version(value: bool):  # noqa: FBT001
    if value:
        rich_print(__version__)
        raise Exit


@main.command(help=__doc__)
def _(
    config: Annotated[Path, Option(help="Config file path.")],
    log_level: Annotated[
        LogLevelType,
        Option(
            help="Log level before config is load.",
            parser=str,
        ),
    ] = "INFO",
    _: Annotated[  # noqa: FBT002
        bool,
        Option(
            "--version",
            help="Print program version.",
            callback=__version,
        ),
    ] = False,
):
    logger.setLevel(log_level)
    formatter = Formatter(
        "%(asctime)s-%(levelname)s-%(message)s",
        "%Y-%m-%d %H:%M:%S",
    )
    if len(logger.handlers) == 0:
        logger.addHandler(StreamHandler())
    for handler in logger.handlers:
        handler.setFormatter(formatter)
        handler.setLevel(log_level)
    run(__launch_async(config))
