"""Navigation assets retain the official mark, not its background tile."""

import hashlib
from importlib.resources import files
import xml.etree.ElementTree as ET

import httpx
import pytest

from fulcra_mcp.main import app


@pytest.fixture
async def http_client():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
        yield client


@pytest.mark.parametrize("theme,color", [("light", "black"), ("dark", "white")])
async def test_menu_icon_asset_and_http(http_client, theme, color):
    response = await http_client.get(f"/menu-{theme}.svg")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/svg+xml")
    asset = files("fulcra_mcp").joinpath(f"static/menu-{theme}.svg").read_bytes()
    assert response.content == asset
    svg = ET.fromstring(asset)
    assert svg.attrib == {"width": "256", "height": "256", "viewBox": "-32 -32 464 464", "fill": "none"}
    paths = list(svg)
    assert [p.tag for p in paths] == ["{http://www.w3.org/2000/svg}path"] * 2
    assert paths[0].attrib["stroke"] == color
    assert paths[0].attrib["stroke-width"] == "16"
    assert paths[1].attrib["fill"] == color
    # Exact hexagon and spiral from Fulcra's official white vector logo.
    geometry = "\n".join(p.attrib["d"] for p in paths)
    assert hashlib.sha256(geometry.encode()).hexdigest() == "f3b72306018947a380a67a43430e669a870f5c87b1d45b91f5656f74677c27fc"
