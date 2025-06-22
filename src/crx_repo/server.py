"""Classes and functions for serving manifest."""

from asyncio import Task
from asyncio import create_task
from logging import getLogger
from pathlib import Path
from itertools import chain
from urllib.parse import parse_qs

from aiohttp.web import AppKey
from aiohttp.web import Request
from aiohttp.web import Response
from aiohttp.web import Application

from crx_repo.cache import Cache
from crx_repo.cache import MemoryCache
from crx_repo.utils import has_package
from crx_repo.config import Config
from crx_repo.manifest import GUpdate


logger = getLogger(__name__)

CACHE_KEY = "cache"


def _get_cache(path: Path, app: Application, prefix: str, router_name: str) -> Cache:
    return MemoryCache(path, app, prefix, router_name)


def setup(config: Config) -> Application:
    """Setup an `aiohttp.web.Application` instance.

    Args:
        config(Config): The deserialized config.
        debug(bool): If set application in debug mode.

    Returns:
        Application: The `aiohttp.web.Application` object which can be run later.
    """
    app = Application(logger=logger)
    extensions = {
        AppKey(extension.extension_id, Task[None]): extension
        for extension in config.extensions
    }
    cache_key = AppKey(CACHE_KEY, Cache)

    base = config.base.removesuffix("/") if config.base.endswith("/") else config.base
    prefix = config.prefix if config.prefix.startswith("/") else "/" + config.prefix
    manifest_path = (
        config.manifest_path
        if config.manifest_path.startswith("/")
        else "/" + config.manifest_path
    )

    async def on_cleanup_ctx_async(app: Application):
        app[cache_key] = _get_cache(config.cache_dir, app, prefix, "crx-handler")
        logger.debug("Creted cache at %s.", config.cache_dir)
        for extension_key, extension in extensions.items():
            app[extension_key] = create_task(
                extension.get_downloader(
                    config.version,
                    config.proxy,
                    app[cache_key],
                ).download_forever(config.interval, base, prefix),
            )
            logger.debug("Created downloder for extension %s.", extension.extension_id)
        logger.debug("Background tasks initialized successfully.")

        yield

        logger.debug("Stopping downloaders...")
        for extension_key in extensions:
            _ = app[extension_key].cancel()
            await app[extension_key]

    app.cleanup_ctx.append(on_cleanup_ctx_async)

    async def handle_manifest(request: Request) -> Response:
        logger.debug("Handling query params keys %s...", list(request.query.keys()))

        gupdate = None
        if "x" in request.query:
            gupdate = GUpdate(apps=[], protocol="2.0")
            logger.debug("Query found, sending filtered extensions...")
            for x in request.query.getall("x"):
                logger.debug("Parsing extension query %s...", x)
                extension_query = {
                    k: v[0] for k, v in parse_qs(x).items() if len(v) == 1
                }
                extension_id = extension_query.get("id")
                extension_version = extension_query.get("v")
                if extension_id is not None:
                    logger.debug(
                        "Extension in query params: %s=%s",
                        extension_id,
                        extension_version,
                    )
                    gupdate.apps = list(
                        chain(
                            gupdate.apps,
                            (
                                await request.app[cache_key].get_gupdate_async(
                                    base,
                                    prefix,
                                    extension_id,
                                    extension_version,
                                )
                            ).apps,
                        ),
                    )
            if len(gupdate.apps) == 0:
                gupdate = None
        if gupdate is None:
            logger.debug("No query found, sending all extensions...")
            gupdate = await request.app[cache_key].get_gupdate_async(base, prefix)

        body = gupdate.to_xml(
            exclude_none=True,
            encoding="utf-8",
            **({"pretty_print": True} if has_package("lxml") else {}),
        )
        return Response(body=body, content_type="application/xml", charset="utf-8")

    _ = app.router.add_get(manifest_path, handle_manifest, name="manifest-handler")
    return app
