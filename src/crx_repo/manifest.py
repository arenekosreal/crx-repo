"""
Example:
    ```xml
    <gupdate xmlns="http://www.google.com/update2/response" protocol="2.0" server="prod">
        <daystart elapsed_days="6741" elapsed_seconds="8266"/>
        <app appid="<id>" cohort="" cohortname="" status="ok">
            <updatecheck _esbAllowlist="true" codebase="<url>" fp="" hash_sha256="" protected="0" size="" status="ok" version=""/>
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
    appid: str = attr()
    status: Literal["ok"] = attr()
    updatechecks: list[UpdateCheck] = element(tag="updatecheck")


class GUpdate(
    BaseXmlModel,
    nsmap={"": CHROME_MANIFEST_XML_NAMESPACE},
    tag="gupdate",
    search_mode="ordered",
):
    apps: list[App] = element(tag="app")
    protocol: Literal["2.0"] = attr()
