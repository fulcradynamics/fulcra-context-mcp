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


def server(version="1.0.3", package_version="0.4.1", **overrides):
    return {
        "name": release.SERVER_NAME,
        "description": "Connect your Fulcra Context personal datastore",
        "version": version,
        "packages": [{"registryType": "pypi", "identifier": release.PACKAGE,
                      "version": package_version, "transport": {"type": "stdio"}}],
        **overrides,
    }


def test_the_repos_own_metadata_is_consistent():
    current, package_version, readme = release.read_local()
    assert release.metadata_problems(current, package_version, readme) == []


def test_a_release_pr_bumping_both_versions_passes():
    assert release.metadata_problems(
        server("1.0.4", "0.5.0"), "0.5.0", README,
        base_server=server(), base_package_version="0.4.1",
    ) == []


def test_unchanged_metadata_passes():
    assert release.metadata_problems(
        server(), "0.4.1", README, base_server=server(), base_package_version="0.4.1"
    ) == []


@pytest.mark.parametrize("current,package_version,readme,expected", [
    (server(), "0.5.0", README, "packages[].version is '0.4.1'"),
    (server(name="com.fulcradynamics/other"), "0.4.1", README, "name must stay"),
    (server(description="x" * 101), "0.4.1", README, "over 100 characters"),
    (server(packages=[]), "0.4.1", README, "no PyPI package entry"),
    (server(), "0.4.1", "# no marker\n", "must contain 'mcp-name:"),
    (server("1.0"), "0.4.1", README, "is not an X.Y.Z version"),
])
def test_inconsistent_metadata_is_refused(current, package_version, readme, expected):
    problems = release.metadata_problems(current, package_version, readme)
    assert any(expected in p for p in problems), problems


def test_changing_server_json_requires_a_higher_version():
    # A package bump without a listing bump, which the registry couldn't publish.
    problems = release.metadata_problems(
        server("1.0.3", "0.5.0"), "0.5.0", README,
        base_server=server(), base_package_version="0.4.1",
    )
    assert any("version must go above 1.0.3" in p for p in problems), problems


def test_versions_cannot_go_down():
    problems = release.metadata_problems(
        server("1.0.2", "0.4.0"), "0.4.0", README,
        base_server=server(), base_package_version="0.4.1",
    )
    assert any("must be higher than 0.4.1" in p for p in problems), problems
    assert any("must go above 1.0.3" in p for p in problems), problems


def test_versions_compare_numerically():
    assert release.parse_version("0.10.0") > release.parse_version("0.9.9")


def test_bump_updates_both_files_and_the_next_patch_by_default():
    pyproject = '[project]\nname = "fulcra-context-mcp"\nversion = "0.4.1"\n\n[tool.x]\nversion = "9"\n'
    new_pyproject, new_server = release.bump_files(pyproject, server(), "0.5.0")
    assert release.pyproject_version(new_pyproject) == "0.5.0"
    assert 'version = "9"' in new_pyproject
    assert new_server["version"] == "1.0.4"
    assert new_server["packages"][0]["version"] == "0.5.0"
    assert release.metadata_problems(new_server, "0.5.0", README,
                                     base_server=server(), base_package_version="0.4.1") == []


def test_bump_takes_an_explicit_server_version():
    _, new_server = release.bump_files('[project]\nversion = "0.4.1"\n', server(), "0.5.0", "1.1.0")
    assert new_server["version"] == "1.1.0"


def test_bump_refuses_a_malformed_version():
    with pytest.raises(ValueError):
        release.bump_files('[project]\nversion = "0.4.1"\n', server(), "0.5")


def test_server_json_round_trips_unchanged():
    path = ROOT / "server.json"
    assert release.dump_server(json.loads(path.read_text())) == path.read_text()
