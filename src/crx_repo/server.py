"""Classes and functions for serving manifest."""

from asyncio import Task
from asyncio import Event
from asyncio import create_task
from logging import getLogger
from pathlib import Path
from urllib.parse import parse_qs

from aiohttp.web import AppKey
from aiohttp.web import Request
from aiohttp.web import Response
from aiohttp.web import Application

from crx_repo.cache import Cache
from crx_repo.cache import MemoryCache
from crx_repo.utils import has_package
from crx_repo.config import Config
from crx_repo.manifest import App
from crx_repo.manifest import GUpdate
from crx_repo.manifest import UpdateCheck
from crx_repo.manifest import ResponseStatus


logger = getLogger(__name__)

CACHE_WATCHER_KEY = "cache-watcher"
CACHE_KEY = "cache"


async def _wait_tasks(app: Application, *task_keys: AppKey[Task[None]]):
    for task_key in task_keys:
        if task_key in app and not app[task_key].done():
            await app[task_key]


def _get_cache(path: Path, app: Application, prefix: str, router_name: str) -> Cache:
    return MemoryCache(path, app, prefix, router_name)


def _update_gupdate(
    gupdate: GUpdate,
    update_check: UpdateCheck,
    extension_id: str,
    status: ResponseStatus,
):
    for app in gupdate.apps:
        if app.appid == extension_id:
            app.updatechecks.append(update_check)
            return
    app = App(appid=extension_id, status=status, updatechecks=[update_check])
    gupdate.apps.append(app)


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
        AppKey(extension.extension_id, Task[None]): extension
        for extension in config.extensions
    }
    cache_watcher_key = AppKey(CACHE_WATCHER_KEY, Task[None])
    cache_key = AppKey(CACHE_KEY, Cache)

    base = config.base.removesuffix("/") if config.base.endswith("/") else config.base
    prefix = config.prefix if config.prefix.startswith("/") else "/" + config.prefix
    manifest_path = (
        config.manifest_path
        if config.manifest_path.startswith("/")
        else "/" + config.manifest_path
    )

    async def on_cleanup_ctx_async(app: Application):
        watcher_stop_event = Event()
        downloader_stop_event = Event()
        app[cache_key] = _get_cache(config.cache_dir, app, prefix, "crx-handler")
        logger.debug("Creted cache at %s.", config.cache_dir)
        app[cache_watcher_key] = create_task(app[cache_key].watch(watcher_stop_event))
        logger.debug("Started watching cache changes.")
        for extension_key, extension in extensions.items():
            app[extension_key] = create_task(
                extension.get_downloader(
                    config.version,
                    config.proxy,
                    app[cache_key],
                ).download_forever(config.interval, downloader_stop_event),
            )
            logger.debug("Created downloder for extension %s.", extension.extension_id)
        logger.debug("Background tasks initialized successfully.")

        yield

        logger.debug("Stopping downloaders...")
        downloader_stop_event.set()
        logger.debug("Stopping watching cache changes...")
        watcher_stop_event.set()
        logger.debug("Waiting for existing tasks...")
        await _wait_tasks(app, *extensions.keys(), cache_watcher_key)
        event.set()

    app.cleanup_ctx.append(on_cleanup_ctx_async)

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
                        ),
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
                extension_id,
                extension_version,
            )
            hash_sha256 = await request.app[cache_key].extension_sha256_async(
                extension_id,
                extension_version,
            )
            update_check = UpdateCheck(
                codebase=codebase,
                hash_sha256=hash_sha256,
                size=size,
                version=version,
            )
            _update_gupdate(gupdate, update_check, extension_id, status)

        body = gupdate.to_xml(
            exclude_none=True,
            encoding="utf-8",
            **({"pretty_print": True} if has_package("lxml") else {}),
        )
        return Response(body=body, content_type="application/xml", charset="utf-8")

    _ = app.router.add_get(manifest_path, handle_manifest, name="manifest-handler")
    return app
