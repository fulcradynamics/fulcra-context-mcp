"""scripts/release.py: the checks a release PR must pass, and the version bump."""

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("release", ROOT / "scripts" / "release.py")
assert _spec and _spec.loader
release = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(release)

README = f"<!-- {release.MCP_NAME_MARKER} -->\n# fulcra-context-mcp\n"


def server(version="1.1.0", package_version=None, **overrides):
    """A server.json; the listing and the package share `version` unless told otherwise."""
    return {
        "name": release.SERVER_NAME,
        "title": "Fulcra",
        "description": "Connect your Fulcra Context personal datastore",
        "version": version,
        "remotes": [{"type": "streamable-http", "url": "https://mcp.fulcradynamics.com/mcp"}],
        "packages": [{"registryType": "pypi", "identifier": release.PACKAGE,
                      "version": package_version or version, "transport": {"type": "stdio"}}],
        **overrides,
    }


def test_the_repos_own_metadata_is_consistent():
    current, package_version, readme = release.read_local()
    assert release.metadata_problems(current, package_version, readme) == []


def test_a_release_pr_bumping_the_version_passes():
    assert release.metadata_problems(
        server("1.1.1"), "1.1.1", README, base_server=server(), base_package_version="1.1.0",
    ) == []


def test_unchanged_metadata_passes():
    assert release.metadata_problems(
        server(), "1.1.0", README, base_server=server(), base_package_version="1.1.0"
    ) == []


@pytest.mark.parametrize("current,package_version,readme,expected", [
    (server(), "1.2.0", README, "the listing and the package share one version"),
    (server(package_version="1.0.0"), "1.1.0", README, "packages[].version is '1.0.0'"),
    (server(name="com.fulcradynamics/other"), "1.1.0", README, "name must stay"),
    (server(description="x" * 101), "1.1.0", README, "over 100 characters"),
    (server(title=""), "1.1.0", README, "title must be 1-100 characters"),
    (server(title="x" * 101), "1.1.0", README, "title must be 1-100 characters"),
    (server(packages=[]), "1.1.0", README, "no PyPI package entry"),
    (server(), "1.1.0", "# no marker\n", "must contain 'mcp-name:"),
    (server("1.1"), "1.1", README, "is not an X.Y.Z version"),
])
def test_inconsistent_metadata_is_refused(current, package_version, readme, expected):
    problems = release.metadata_problems(current, package_version, readme)
    assert any(expected in p for p in problems), problems


def test_changing_server_json_requires_a_higher_version():
    # A new description without a version bump, which the registry couldn't publish.
    problems = release.metadata_problems(
        server(description="A new description"), "1.1.0", README,
        base_server=server(), base_package_version="1.1.0",
    )
    assert any("version must go above 1.1.0" in p for p in problems), problems


def test_versions_cannot_go_down():
    problems = release.metadata_problems(
        server("1.0.9"), "1.0.9", README, base_server=server(), base_package_version="1.1.0",
    )
    assert any("must be higher than 1.1.0" in p for p in problems), problems
    assert any("must go above 1.1.0" in p for p in problems), problems


def test_versions_compare_numerically():
    assert release.parse_version("0.10.0") > release.parse_version("0.9.9")


def test_bump_sets_one_version_everywhere():
    pyproject = '[project]\nname = "fulcra-context-mcp"\nversion = "1.1.0"\n\n[tool.x]\nversion = "9"\n'
    new_pyproject, new_server = release.bump_files(pyproject, server(), "1.2.0")
    assert release.pyproject_version(new_pyproject) == "1.2.0"
    assert 'version = "9"' in new_pyproject
    assert new_server["version"] == "1.2.0"
    assert new_server["packages"][0]["version"] == "1.2.0"
    assert release.metadata_problems(new_server, "1.2.0", README,
                                     base_server=server(), base_package_version="1.1.0") == []


def test_bump_refuses_a_malformed_version():
    with pytest.raises(ValueError):
        release.bump_files('[project]\nversion = "1.1.0"\n', server(), "1.2")


def test_server_card_url_is_the_endpoint_plus_server_card():
    assert release.server_card_url(server()) == "https://mcp.fulcradynamics.com/mcp/server-card"


def test_server_json_round_trips_unchanged():
    path = ROOT / "server.json"
    assert release.dump_server(json.loads(path.read_text())) == path.read_text()
