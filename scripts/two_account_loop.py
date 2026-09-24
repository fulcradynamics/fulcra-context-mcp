"""Live two-account verification of the sharing + group coordination loop.

Runs the real MCP tools (in-process FastMCP client) as two Fulcra accounts,
A and B, switching between them by pointing XDG_CONFIG_HOME at two credential
stores. Creates a private group, shares a folder to it, joins from B, reads
both ways, checks the updates feed, exercises soft-delete retraction, has B
leave the group, and cleans everything up. Exit code 1 if any check fails.

Log B in first (prints a device-flow URL to complete as B):

    XDG_CONFIG_HOME=/path/acctB FULCRA_ENVIRONMENT=stdio uv run python -c \\
      "from fulcra_mcp.credentials import get_fulcra_object; print(get_fulcra_object().get_fulcra_userid())"

Then:

    FULCRA_ENVIRONMENT=stdio uv run python scripts/two_account_loop.py \\
      --a-config ~/.config --b-config /path/acctB
"""

import argparse
import asyncio
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

os.environ.setdefault("FULCRA_ENVIRONMENT", "stdio")

from fastmcp import Client  # noqa: E402

import fulcra_mcp.credentials as credentials_module  # noqa: E402
from fulcra_mcp.tools import tools_mcp  # noqa: E402

FAILURES: list[str] = []


def check(label: str, ok: bool, detail: str = ""):
    mark = "ok  " if ok else "FAIL"
    print(f"  [{mark}] {label}" + (f" -- {detail[:200]}" if detail and not ok else ""))
    if not ok:
        FAILURES.append(label)


def payload(text: str):
    """The JSON object/array a tool response ends with."""
    idx = min(i for i in (text.find("{"), text.find("[")) if i >= 0)
    return json.loads(text[idx:])


class Account:
    def __init__(self, label: str, config_dir: Path):
        self.label = label
        self.config_dir = str(config_dir.expanduser())
        self.userid: str | None = None

    async def call(self, name: str, args: dict | None = None) -> str:
        # Point the stdio credential loader at this account and drop the
        # cached client so get_fulcra_object() reloads.
        os.environ["XDG_CONFIG_HOME"] = self.config_dir
        credentials_module.stdio_fulcra = None
        async with Client(tools_mcp) as c:
            text = (await c.call_tool(name, args or {})).content[0].text
        print(f"    {self.label}> {name}({json.dumps(args or {})[:90]}) -> {text[:160]}")
        return text


async def run(a: Account, b: Account, keep: bool):
    topic = f"/shared/loop-{int(time.time())}/"
    hello, reply = topic + "hello.json", topic + "reply.json"
    now = datetime.now(timezone.utc)
    window = {
        "start_time": (now - timedelta(hours=1)).isoformat(),
        "end_time": (now + timedelta(hours=1)).isoformat(),
    }
    created = {"gid": None, "a_group_share": None, "a_user_share": None, "b_share": None}

    try:
        print("\nPhase 1 (A): identity, private group, file, share to group")
        a.userid = payload(await a.call("list_shares", {"direction": "outgoing"}))["own_fulcra_userid"]
        t = await a.call("create_group", {"title": "loop test", "description": "temporary two-account loop test",
                                          "responsible_entity": "fulcra-context-mcp verification"})
        g = payload(t); created["gid"] = g["id"]
        check("group is private by default", g.get("is_public") is False, t)
        # Creating a group does not enroll the creator; without joining, A
        # would never receive shares made to the group.
        t = await a.call("join_group", {"group_id": g["id"]})
        check("owner joins own group", t.startswith("Joined group"), t)
        await a.call("write_file", {"path": hello, "content": json.dumps({"from": "A", "n": 1}), "content_type": "application/json"})
        t = await a.call("create_share", {"name": "loop group share", "file_paths": [topic], "with_group_ids": [g["id"]]})
        s = payload(t); created["a_group_share"] = s["datashare_id"]
        check("share targets the group", s.get("with_group_ids") == [g["id"]], t)

        print("\nPhase 2 (B): identity, join private group by ID")
        b.userid = payload(await b.call("list_shares", {"direction": "outgoing"}))["own_fulcra_userid"]
        check("A and B are different accounts", a.userid != b.userid)
        t = await b.call("join_group", {"group_id": g["id"]})
        check("join private group by ID", t.startswith("Joined group"), t)

        print("\nPhase 3 (B): incoming shares show the group grant")
        inc = payload(await b.call("list_shares", {"direction": "incoming"}))["incoming"]
        mine = [e for e in inc if e.get("sharing_fulcra_userid") == a.userid and e.get("group_id") == g["id"]]
        check("group grant from A visible", len(mine) == 1, json.dumps(inc)[:300])
        check("grant carries the folder", bool(mine) and mine[0].get("file_paths") == [topic], json.dumps(mine)[:300])
        check("grant_type is group", bool(mine) and mine[0].get("grant_type") == "group")

        print("\nPhase 4 (B): list and read A's folder; unshared root refused")
        t = await b.call("list_files", {"path": topic, "fulcra_userid": a.userid})
        check("folder lists hello.json", "hello.json" in t, t)
        t = await b.call("read_file", {"path": hello, "fulcra_userid": a.userid})
        check("read hello.json content", '"from": "A"' in t, t)
        t = await b.call("list_files", {"path": "/", "fulcra_userid": a.userid})
        root = payload(t)
        check("root shows only the path to the shared folder", root.get("folders") == ["shared"] and root.get("files") == [], t)
        t = await b.call("list_files", {"path": "/agents/", "fulcra_userid": a.userid})
        check("unshared folder is refused with friendly message", "has not shared" in t, t)

        print("\nPhase 5 (B): updates feed, per-peer and fan-out")
        t = await b.call("get_data_updates", {**window, "fulcra_userid": a.userid})
        check("peer updates list hello.json", "hello.json" in t, t)
        u = payload(await b.call("get_data_updates", {**window, "include_shared": True}))
        check("fan-out includes A", a.userid in u.get("shared", {}) and u.get("peers_checked", 0) >= 1, json.dumps(u)[:300])

        print("\nPhase 6 (B): reply and share back to the group")
        await b.call("write_file", {"path": reply, "content": json.dumps({"from": "B", "ack": 1}), "content_type": "application/json"})
        t = await b.call("create_share", {"name": "loop reply share", "file_paths": [topic], "with_group_ids": [g["id"]]})
        created["b_share"] = payload(t)["datashare_id"]

        print("\nPhase 7 (A): sees B via the group and reads the reply")
        inc = payload(await a.call("list_shares", {"direction": "incoming"}))["incoming"]
        check("B's group grant visible to A", any(e.get("sharing_fulcra_userid") == b.userid for e in inc), json.dumps(inc)[:300])
        t = await a.call("read_file", {"path": reply, "fulcra_userid": b.userid})
        check("A reads reply.json", '"from": "B"' in t, t)
        u = payload(await a.call("get_data_updates", {**window, "include_shared": True}))
        check("A's fan-out includes B", b.userid in u.get("shared", {}), json.dumps(u)[:300])

        print("\nPhase 8 (A->B): direct user share (mailbox pattern)")
        t = await a.call("create_share", {"name": "loop user share", "file_paths": [topic], "with_user_ids": [b.userid]})
        created["a_user_share"] = payload(t)["datashare_id"]
        inc = payload(await b.call("list_shares", {"direction": "incoming"}))["incoming"]
        check("user grant from A visible", any(e.get("sharing_fulcra_userid") == a.userid and e.get("grant_type") == "user" for e in inc), json.dumps(inc)[:300])

        print("\nPhase 9 (A): soft delete hides the file from B")
        await a.call("delete_file", {"path": hello})
        t = await b.call("list_files", {"path": topic, "fulcra_userid": a.userid})
        check("hello.json no longer listed", "hello.json" not in t, t)

        print("\nPhase 10 (B): leave the group")
        t = await b.call("leave_group", {"group_id": g["id"]})
        check("leave group", "no longer a member" in t, t)
        joined = payload(await b.call("get_groups", {"subscribed_only": True}))
        check("group gone from B's joined list", not any(x.get("id") == g["id"] for x in joined), json.dumps(joined)[:300])
        inc = payload(await b.call("list_shares", {"direction": "incoming"}))["incoming"]
        check("A's group grant gone after leaving", not any(e.get("group_id") == g["id"] for e in inc), json.dumps(inc)[:300])
    finally:
        if keep:
            print("\n--keep: skipping cleanup; created =", created)
        else:
            print("\nPhase 11: cleanup")
            for key, acct in (("a_group_share", a), ("a_user_share", a), ("b_share", b)):
                if created[key]:
                    await acct.call("delete_share", {"share_id": created[key]})
            if created["gid"]:
                await a.call("delete_group", {"group_id": created["gid"]})
            await b.call("delete_file", {"path": reply})
            inc = payload(await b.call("list_shares", {"direction": "incoming"}))["incoming"]
            check("B has no grants from A left", not any(e.get("sharing_fulcra_userid") == a.userid for e in inc), json.dumps(inc)[:300])
            joined = payload(await b.call("get_groups", {"subscribed_only": True}))
            check("B no longer in the group", not any(x.get("id") == created["gid"] for x in joined), json.dumps(joined)[:300])

    print("\nRESULT:", "all checks passed" if not FAILURES else f"{len(FAILURES)} failed: {FAILURES}")
    return 0 if not FAILURES else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--a-config", required=True, help="XDG_CONFIG_HOME holding account A's fulcra/credentials.json")
    ap.add_argument("--b-config", required=True, help="XDG_CONFIG_HOME holding account B's fulcra/credentials.json")
    ap.add_argument("--keep", action="store_true", help="skip cleanup (leave group, shares, files in place)")
    args = ap.parse_args()
    for d in (args.a_config, args.b_config):
        if not (Path(d).expanduser() / "fulcra" / "credentials.json").exists():
            sys.exit(f"no fulcra/credentials.json under {d}; log that account in first (see module docstring)")
    sys.exit(asyncio.run(run(Account("A", Path(args.a_config)), Account("B", Path(args.b_config)), args.keep)))


if __name__ == "__main__":
    main()
