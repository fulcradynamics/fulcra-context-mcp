"""The navigation icon retains the official mark, not its background tile."""

import hashlib
from importlib.resources import files
import xml.etree.ElementTree as ET


def test_menu_icon_asset():
    svg = ET.fromstring(files("fulcra_mcp").joinpath("static/menu-icon.svg").read_bytes())
    assert svg.attrib == {"viewBox": "0 0 400 400"}
    paths = list(svg)
    assert [p.tag for p in paths] == ["{http://www.w3.org/2000/svg}path"] * 2
    assert paths[0].attrib["stroke"] == "currentColor"
    assert paths[0].attrib["stroke-width"] == "16"
    assert paths[1].attrib["fill"] == "currentColor"
    # Exact hexagon and spiral from Fulcra's official white vector logo.
    geometry = "\n".join(p.attrib["d"] for p in paths)
    assert hashlib.sha256(geometry.encode()).hexdigest() == "f3b72306018947a380a67a43430e669a870f5c87b1d45b91f5656f74677c27fc"
