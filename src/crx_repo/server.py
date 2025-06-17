"""Classes and functions for serving manifest."""

from .cache import Cache
from .cache import MemoryCache
from .utils import has_package
from .chrome import ChromeExtensionDownloader
from .config import Config
from asyncio import Task
from asyncio import Event
from asyncio import create_task
from logging import getLogger
from .manifest import App
from .manifest import GUpdate
from .manifest import UpdateCheck
from aiohttp.web import AppKey
from aiohttp.web import Request
from aiohttp.web import Response
from aiohttp.web import Application
from urllib.parse import parse_qs


logger = getLogger(__name__)

CACHE_WATCHER_KEY = "cache-watcher"
CACHE_KEY = "cache"


def setup(config: Config, event: Event) -> Application:
    """Setup an `aiohttp.web.Application` instance.

    Args:
        config(Config): The deserialized config.
        debug(bool): If set application in debug mode.
        event(Event): The `asyncio.Event` object for blocking without sleeping forever.

    Returns:
        Application: The `aiohttp.web.Application` object which can be run later.
    """
    app = Application(logger=logger)
    extensions = {
        extension: AppKey(extension, Task[None]) for extension in config.extensions
    }
    cache_watcher_key = AppKey(CACHE_WATCHER_KEY, Task[None])
    cache_key = AppKey(CACHE_KEY, Cache)

    async def on_cleanup_ctx_async(app: Application):
        app[cache_key] = MemoryCache(config.cache_dir)
        app[cache_watcher_key] = create_task(app[cache_key].watch())
        for extension_id, extension_key in extensions.items():
            app[extension_key] = create_task(
                ChromeExtensionDownloader(
                    extension_id,
                    config.interval,
                    config.version,
                    config.proxy,
                    app[cache_key],
                ).download_forever()
            )

        yield

        for extension_key in extensions.values():
            _ = app[extension_key].cancel()
            await app[extension_key]
        _ = app[cache_watcher_key].cancel()
        await app[cache_watcher_key]
        event.set()

    app.cleanup_ctx.append(on_cleanup_ctx_async)
    base = config.base.removesuffix("/") if config.base.endswith("/") else config.base
    prefix = config.prefix if config.prefix.startswith("/") else "/" + config.prefix
    manifest_path = (
        config.manifest_path
        if config.manifest_path.startswith("/")
        else "/" + config.manifest_path
    )

    async def handle_manifest(request: Request) -> Response:
        logger.debug("Handling query params keys %s...", list(request.query.keys()))

        extension_infos: list[tuple[str, str]] = []
        if "x" in request.query:
            logger.debug("Query found, sending filtered extensions...")
            for x in request.query.getall("x"):
                logger.debug("Parsing extension query %s...", x)
                extension_query = {
                    k: v[0] for k, v in parse_qs(x).items() if len(v) == 1
                }
                extension_id = extension_query.get("id")
                extension_version = extension_query.get("v")
                if extension_id is not None and extension_version is not None:
                    logger.debug(
                        "Extension in query params: %s=%s",
                        extension_id,
                        extension_version,
                    )
                    extension_infos.extend(
                        request.app[cache_key].iter_extensions(
                            extension_id,
                            extension_version,
                        )
                    )
        else:
            logger.debug("No query found, sending all extensions...")
            extension_infos.extend(request.app[cache_key].iter_extensions())

        gupdate = GUpdate(apps=[], protocol="2.0")

        for extension_id, extension_version in extension_infos:
            codebase = f"{base}{prefix}/{extension_id}/{extension_version}.crx"
            version = extension_version
            status = "ok"
            size = request.app[cache_key].extension_size(
                extension_id, extension_version
            )
            hash_sha256 = await request.app[cache_key].extension_sha256_async(
                extension_id, extension_version
            )
            update_check = UpdateCheck(
                codebase=codebase, hash_sha256=hash_sha256, size=size, version=version
            )
            app = App(appid=extension_id, status=status, updatechecks=[update_check])
            gupdate.apps.append(app)

        body = gupdate.to_xml(
            exclude_none=True,
            encoding="utf-8",
            **({"pretty_print": True} if has_package("lxml") else {}),
        )
        return Response(body=body, content_type="application/xml", charset="utf-8")

    if config.cache_dir.exists() and not config.cache_dir.is_dir():
        logger.warning("Removing %s to create cache directory...", config.cache_dir)
        config.cache_dir.unlink()
    config.cache_dir.mkdir(parents=True, exist_ok=True)

    _ = app.router.add_static(prefix, config.cache_dir, name="crx-handler")
    _ = app.router.add_get(manifest_path, handle_manifest, name="manifest-handler")
    return app
