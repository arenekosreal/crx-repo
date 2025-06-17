"""Download Chrom(e|ium) extensions from Chrome Web Store and serve a update manifest."""

__version__ = "0.3.0"


from rich import print as rich_print
from typer import Exit
from typer import Typer
from typer import Option
from typing import Annotated
from asyncio import Event
from logging import DEBUG
from logging import Formatter
from logging import StreamHandler
from logging import getLogger
from pathlib import Path
from aiohttp.web import TCPSite
from aiohttp.web import UnixSite
from aiohttp.web import AppRunner


try:
    from uvloop import run
except ImportError:
    from asyncio import run

from .toml import TomlConfigParser
from .config import Config
from .config import ConfigParser
from .config import LogLevelType
from .server import setup


logger = getLogger(__name__)
main = Typer(help=__doc__)


async def __parse_async(config: Path) -> Config:
    parsers: list[ConfigParser] = [TomlConfigParser()]
    for parser in parsers:
        try:
            config_object = await parser.parse_async(config)
            if config_object is not None:
                return config_object
        except Exception as e:
            logger.debug(
                "Failed to parse %s with %s because %s",
                config,
                parser.__class__.__name__,
                e,
            )
    raise RuntimeError("Unable to parse config %s" % config) from None


async def __launch_async(config: Path):
    deserialized_config = await __parse_async(config)
    event = Event()
    app = setup(deserialized_config, logger.level == DEBUG, event)
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

    _ = await event.wait()
    logger.info("Exiting...")
    await runner.cleanup()


def __version(value: bool):
    if value:
        rich_print(__version)
        raise Exit


@main.command()
def _(
    config: Annotated[Path, Option(help="Config file path.")],
    log_level: Annotated[
        LogLevelType,
        Option(
            help="Log level before config is load.",
            parser=str,
        ),
    ] = "INFO",
    _: Annotated[
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
