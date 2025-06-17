"""Models for a manifest for api requesting.

Example:
    manifest is omitted for clarity.
    ```xml
    <gupdate xmlns="http://www.google.com/update2/response" protocol="2.0">
    <app appid="" status="ok">
    <updatecheck codebase="" hash_sha256="" size="" version=""/>
    </app>
    </gupdate>
    ```
"""

from typing import Literal
from pydantic_xml import BaseXmlModel
from pydantic_xml import attr
from pydantic_xml import element


CHROME_MANIFEST_XML_NAMESPACE = "http://www.google.com/update2/response"


class UpdateCheck(
    BaseXmlModel,
    nsmap={"": CHROME_MANIFEST_XML_NAMESPACE},
    tag="updatecheck",
    search_mode="ordered",
):
    """The model of <updatecheck> element."""

    codebase: str = attr()
    hash_sha256: str | None = attr(default=None)
    size: int | None = attr(default=None)
    version: str = attr()


class App(
    BaseXmlModel,
    nsmap={"": CHROME_MANIFEST_XML_NAMESPACE},
    tag="app",
    search_mode="ordered",
):
    """The model of <app> element."""

    appid: str = attr()
    status: Literal["ok"] = attr()
    updatechecks: list[UpdateCheck] = element(tag="updatecheck")


class GUpdate(
    BaseXmlModel,
    nsmap={"": CHROME_MANIFEST_XML_NAMESPACE},
    tag="gupdate",
    search_mode="ordered",
):
    """The model of <gupdate> element."""

    apps: list[App] = element(tag="app")
    protocol: Literal["2.0"] = attr()
