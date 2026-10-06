"""Release helpers: version bumps, release-PR checks, and publish steps for CI.

A release is a PR that bumps the package version (and server.json with it);
merging it to main publishes to PyPI and then to the official MCP Registry
(.github/workflows/release.yml). See docs/registry-publishing.md.

Usage:
    # In a release PR: bump pyproject.toml, server.json and uv.lock together.
    uv run python scripts/release.py bump 0.5.0 [--server-version 1.1.0]

    # What the PR check runs (compares against the PR's base branch).
    uv run --no-project --with jsonschema python scripts/release.py check --base origin/main

    # Used by the release workflow; each prints what it found.
    python3 scripts/release.py plan              # key=value lines for $GITHUB_OUTPUT
    python3 scripts/release.py wait-pypi         # until PyPI serves the version
    python3 scripts/release.py check-urls        # server.json's URLs respond
    python3 scripts/release.py verify-registry   # registry lists it as latest

Stdlib only (jsonschema is optional, for `check`), so CI can run it without
installing the project.
"""

import argparse
import json
import re
import subprocess
import sys
import time
import tomllib
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = "fulcra-context-mcp"
SERVER_NAME = "com.fulcradynamics/context"
REGISTRY = "https://registry.modelcontextprotocol.io/v0.1"
# The registry proves PyPI ownership by finding this in the release's description.
MCP_NAME_MARKER = f"mcp-name: {SERVER_NAME}"
# The registry's limit on server.json's description.
MAX_DESCRIPTION = 100

VERSION_LINE = re.compile(r'^version\s*=\s*"([^"]+)"', re.MULTILINE)


def parse_version(version: str) -> tuple[int, int, int]:
    """A strict X.Y.Z version as a comparable tuple."""
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", version)
    if not match:
        raise ValueError(f"{version!r} is not an X.Y.Z version")
    major, minor, patch = (int(p) for p in match.groups())
    return major, minor, patch


def pyproject_version(text: str) -> str:
    return tomllib.loads(text)["project"]["version"]


def pypi_package(server: dict) -> dict | None:
    for package in server.get("packages", []):
        if package.get("registryType") == "pypi" and package.get("identifier") == PACKAGE:
            return package
    return None


def metadata_problems(
    server: dict,
    package_version: str,
    readme: str,
    base_server: dict | None = None,
    base_package_version: str | None = None,
) -> list[str]:
    """What's wrong with this release metadata, compared with the base branch's."""
    problems = []
    if server.get("name") != SERVER_NAME:
        problems.append(
            f"server.json name must stay {SERVER_NAME!r}; anything else publishes a "
            "separate listing"
        )
    if len(server.get("description", "")) > MAX_DESCRIPTION:
        problems.append(f"server.json description is over {MAX_DESCRIPTION} characters")
    package = pypi_package(server)
    if package is None:
        problems.append(f"server.json has no PyPI package entry for {PACKAGE}")
    elif package.get("version") != package_version:
        problems.append(
            f"server.json packages[].version is {package.get('version')!r}, but "
            f"pyproject.toml says {package_version!r}"
        )
    if MCP_NAME_MARKER not in readme:
        problems.append(f"README.md must contain {MCP_NAME_MARKER!r} for the registry")
    for label, version in (("server.json version", server.get("version", "")),
                           ("pyproject.toml version", package_version)):
        try:
            parse_version(version)
        except ValueError as e:
            problems.append(f"{label}: {e}")
    if problems:
        return problems

    if base_package_version is not None and package_version != base_package_version:
        if parse_version(package_version) <= parse_version(base_package_version):
            problems.append(
                f"pyproject.toml version {package_version} must be higher than "
                f"{base_package_version}"
            )
    # Published registry versions are immutable, so any change to the listing
    # needs a new, higher version, or it would never be published.
    if base_server is not None and server != base_server:
        if parse_version(server["version"]) <= parse_version(base_server["version"]):
            problems.append(
                f"server.json changed, so its version must go above "
                f"{base_server['version']} (registry versions can't be republished)"
            )
    return problems


def bump_files(pyproject: str, server: dict, package_version: str,
               server_version: str | None = None) -> tuple[str, dict]:
    """pyproject.toml text and server.json with the new versions."""
    parse_version(package_version)
    if server_version is None:
        major, minor, patch = parse_version(server["version"])
        server_version = f"{major}.{minor}.{patch + 1}"
    parse_version(server_version)
    new_pyproject, count = VERSION_LINE.subn(f'version = "{package_version}"', pyproject, count=1)
    if count != 1:
        raise ValueError("no version line in pyproject.toml")
    server = json.loads(json.dumps(server))
    server["version"] = server_version
    package = pypi_package(server)
    if package is None:
        raise ValueError(f"server.json has no PyPI package entry for {PACKAGE}")
    package["version"] = package_version
    return new_pyproject, server


def dump_server(server: dict) -> str:
    return json.dumps(server, indent=2, ensure_ascii=False) + "\n"


def fetch(url: str, accept: str = "application/json") -> tuple[int, bytes]:
    request = urllib.request.Request(
        url, headers={"Accept": accept, "User-Agent": f"{PACKAGE}-release"}
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def pypi_release(version: str) -> dict | None:
    status, body = fetch(f"https://pypi.org/pypi/{PACKAGE}/{version}/json")
    if status == 404:
        return None
    if status != 200:
        raise RuntimeError(f"PyPI returned HTTP {status} for {PACKAGE} {version}")
    return json.loads(body)


def registry_versions() -> list[dict]:
    """Every published version of our listing, with the registry's metadata."""
    name = urllib.parse.quote(SERVER_NAME, safe="")
    status, body = fetch(f"{REGISTRY}/servers/{name}/versions")
    if status == 404:
        return []
    if status != 200:
        raise RuntimeError(f"the registry returned HTTP {status}")
    return json.loads(body).get("servers", [])


def read_local() -> tuple[dict, str, str]:
    server = json.loads((ROOT / "server.json").read_text())
    package_version = pyproject_version((ROOT / "pyproject.toml").read_text())
    readme = (ROOT / "README.md").read_text()
    return server, package_version, readme


def git_show(ref: str, path: str) -> str | None:
    result = subprocess.run(["git", "show", f"{ref}:{path}"], cwd=ROOT,
                            capture_output=True, text=True)
    return result.stdout if result.returncode == 0 else None


def cmd_bump(args) -> int:
    pyproject_path, server_path = ROOT / "pyproject.toml", ROOT / "server.json"
    pyproject, server = bump_files(
        pyproject_path.read_text(), json.loads(server_path.read_text()),
        args.version, args.server_version,
    )
    pyproject_path.write_text(pyproject)
    server_path.write_text(dump_server(server))
    subprocess.run(["uv", "lock"], cwd=ROOT, check=True)
    print(f"{PACKAGE} {args.version}; server.json {server['version']}. "
          "Commit pyproject.toml, server.json and uv.lock in a release PR.")
    return 0


def cmd_check(args) -> int:
    server, package_version, readme = read_local()
    base_server = base_package_version = None
    if args.base:
        if (text := git_show(args.base, "server.json")) is not None:
            base_server = json.loads(text)
        if (text := git_show(args.base, "pyproject.toml")) is not None:
            base_package_version = pyproject_version(text)
    problems = metadata_problems(server, package_version, readme,
                                 base_server, base_package_version)
    try:
        import jsonschema
    except ImportError:
        print("jsonschema not installed; skipping the schema check", file=sys.stderr)
    else:
        status, body = fetch(server["$schema"])
        if status != 200:
            problems.append(f"couldn't fetch the schema {server['$schema']} (HTTP {status})")
        else:
            problems += [f"server.json: {e.message} (at {'/'.join(map(str, e.path)) or 'top level'})"
                         for e in jsonschema.Draft7Validator(json.loads(body)).iter_errors(server)]
    for problem in problems:
        print(f"::error::{problem}" if args.github else problem)
    if not problems:
        print(f"OK: {PACKAGE} {package_version}, server.json {server['version']}")
    return 1 if problems else 0


def cmd_plan(args) -> int:
    server, package_version, _ = read_local()
    publish_pypi = pypi_release(package_version) is None
    published = {s["server"]["version"] for s in registry_versions()}
    publish_registry = server["version"] not in published
    print(f"version={package_version}")
    print(f"server_version={server['version']}")
    print(f"publish_pypi={str(publish_pypi).lower()}")
    print(f"publish_registry={str(publish_registry).lower()}")
    print(f"{PACKAGE} {package_version}: {'publish' if publish_pypi else 'already'} on PyPI; "
          f"server.json {server['version']}: "
          f"{'publish' if publish_registry else 'already'} in the registry", file=sys.stderr)
    return 0


def cmd_wait_pypi(args) -> int:
    _, version, _ = read_local()
    deadline = time.monotonic() + args.timeout
    while True:
        release = pypi_release(version)
        if release is not None:
            if MCP_NAME_MARKER in (release["info"].get("description") or ""):
                print(f"PyPI serves {PACKAGE} {version} with its mcp-name marker")
                return 0
            print(f"::error::PyPI's {PACKAGE} {version} description lacks {MCP_NAME_MARKER!r}")
            return 1
        if time.monotonic() >= deadline:
            print(f"::error::PyPI still doesn't serve {PACKAGE} {version}")
            return 1
        time.sleep(15)


def cmd_check_urls(args) -> int:
    server, _, _ = read_local()
    failed = False
    # An MCP endpoint answers an unauthenticated GET with 401/405, so anything
    # short of a server error means it's up. Icons must actually be served.
    for remote in server.get("remotes", []):
        status, _ = fetch(remote["url"])
        ok = status < 500
        failed |= not ok
        print(f"{'ok' if ok else 'FAIL'} {remote['url']} (HTTP {status})")
    for icon in server.get("icons", []):
        status, _ = fetch(icon["src"], accept="*/*")
        ok = status == 200
        failed |= not ok
        print(f"{'ok' if ok else 'FAIL'} {icon['src']} (HTTP {status})")
    return 1 if failed else 0


def cmd_verify_registry(args) -> int:
    server, _, _ = read_local()
    deadline = time.monotonic() + args.timeout
    while True:
        for entry in registry_versions():
            meta = entry.get("_meta", {}).get("io.modelcontextprotocol.registry/official", {})
            if entry["server"]["version"] == server["version"] and meta.get("isLatest"):
                print(f"The registry lists {SERVER_NAME} {server['version']} as latest")
                return 0
        if time.monotonic() >= deadline:
            print(f"::error::The registry doesn't list {server['version']} as latest")
            return 1
        time.sleep(10)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    bump = sub.add_parser("bump", help="bump the package version and server.json")
    bump.add_argument("version", help="new package version, X.Y.Z")
    bump.add_argument("--server-version", help="server.json version (default: next patch)")
    bump.set_defaults(func=cmd_bump)
    check = sub.add_parser("check", help="check release metadata against a base ref")
    check.add_argument("--base", help="git ref to compare with, e.g. origin/main")
    check.add_argument("--github", action="store_true", help="emit GitHub annotations")
    check.set_defaults(func=cmd_check)
    sub.add_parser("plan").set_defaults(func=cmd_plan)
    for name, func, timeout in (("wait-pypi", cmd_wait_pypi, 600),
                                ("verify-registry", cmd_verify_registry, 300)):
        p = sub.add_parser(name)
        p.add_argument("--timeout", type=int, default=timeout, help="seconds")
        p.set_defaults(func=func)
    sub.add_parser("check-urls").set_defaults(func=cmd_check_urls)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
