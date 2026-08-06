#!/usr/bin/env python3
# Copyright 2026 Minutes contributors
# SPDX-License-Identifier: AGPL-3.0-only

"""Check and merge stable Signal RingRTC upstream tags."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any, Iterable

from minutes_version import (
    ARTIFACT_MANIFEST,
    ROOT,
    load_json,
    parse_upstream_tag,
)


UPSTREAM_REPOSITORY = "signalapp/ringrtc"
UPSTREAM_URL = "https://github.com/signalapp/ringrtc.git"
DEFAULT_FORK_REPOSITORY = "jiridudekusy/minutes-ringrtc"
SAFE_REF_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")
AUTOMATIC_JSON_CONFLICTS = {
    "src/node/package.json",
}
VERSION_LINE_RE = re.compile(r'^\s*"(?:name|version)"\s*:')


def latest_stable_tag(tags: Iterable[str]) -> str:
    parsed: list[tuple[tuple[int, int, int], str]] = []
    for raw in tags:
        tag = raw.strip()
        try:
            version = parse_upstream_tag(tag)
        except ValueError:
            continue
        parsed.append((version, f"v{'.'.join(str(part) for part in version)}"))
    if not parsed:
        raise ValueError("No stable RingRTC X.Y.Z tag found")
    return max(parsed)[1]


def has_open_sync_pull_request(
    pull_requests: Iterable[dict[str, Any]], tag: str
) -> bool:
    needle = tag.lower()
    version = needle.removeprefix("v")
    for pull_request in pull_requests:
        title = str(pull_request.get("title", "")).lower()
        head = str(pull_request.get("headRefName", "")).lower()
        if "sync ringrtc" in title and (needle in title or version in head):
            return True
    return False


def run(command: list[str], *, capture: bool = False) -> str:
    result = subprocess.run(
        command,
        check=True,
        text=True,
        stdout=subprocess.PIPE if capture else None,
    )
    return result.stdout.strip() if capture else ""


def fetch_latest_stable_tag() -> str:
    tag_output = run(
        [
            "gh",
            "api",
            f"repos/{UPSTREAM_REPOSITORY}/tags?per_page=100",
            "--jq",
            ".[].name",
        ],
        capture=True,
    )
    return latest_stable_tag(tag_output.splitlines())


def set_output(key: str, value: str) -> None:
    line = f"{key}={value}"
    print(line)
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf-8") as output_file:
            output_file.write(line + "\n")


def check(root: Path) -> bool:
    manifest = load_json(root, ARTIFACT_MANIFEST)
    current = str(manifest["upstreamVersion"])
    latest = fetch_latest_stable_tag()
    is_newer = parse_upstream_tag(latest) > parse_upstream_tag(current)
    should_sync = is_newer
    reason = (
        f"RingRTC {latest} is newer than Minutes baseline {current}"
        if is_newer
        else f"Minutes baseline {current} is current (latest {latest})"
    )

    if should_sync:
        repository = os.environ.get("MINUTES_RINGRTC_GITHUB_REPO")
        if not repository:
            repository = os.environ.get("GITHUB_REPOSITORY")
        if not repository:
            repository = DEFAULT_FORK_REPOSITORY
        raw = run(
            [
                "gh",
                "pr",
                "list",
                "--repo",
                repository,
                "--state",
                "open",
                "--limit",
                "50",
                "--json",
                "title,headRefName",
            ],
            capture=True,
        )
        if has_open_sync_pull_request(json.loads(raw or "[]"), latest):
            should_sync = False
            reason = f"An open sync PR already exists for {latest}"

    print(f"current_base={current}")
    print(f"latest_stable={latest}")
    print(f"reason={reason}")
    set_output("should_sync", "true" if should_sync else "false")
    set_output("ringrtc_ref", latest)
    set_output("current_base", current)
    set_output("latest_stable", latest)
    return should_sync


def validate_ref(ref: str) -> None:
    if not SAFE_REF_RE.fullmatch(ref) or ".." in ref:
        raise ValueError(f"Unsafe RingRTC ref: {ref}")


def resolve_version_only_conflicts(source: str) -> str:
    """Choose Minutes metadata in conflict hunks containing name/version only."""
    output: list[str] = []
    ours: list[str] = []
    theirs: list[str] = []
    state = "normal"
    conflict_count = 0

    for line in source.splitlines(keepends=True):
        if line.startswith("<<<<<<< "):
            if state != "normal":
                raise ValueError("Nested Git conflict marker")
            state = "ours"
            ours = []
            theirs = []
            continue
        if line.startswith("=======") and state == "ours":
            state = "theirs"
            continue
        if line.startswith(">>>>>>> ") and state == "theirs":
            hunk_lines = [item for item in ours + theirs if item.strip()]
            if not hunk_lines or not all(
                VERSION_LINE_RE.match(item) for item in hunk_lines
            ):
                raise ValueError(
                    "Automatic merge is limited to package name/version hunks"
                )
            output.extend(ours)
            state = "normal"
            conflict_count += 1
            continue
        if state == "normal":
            output.append(line)
        elif state == "ours":
            ours.append(line)
        else:
            theirs.append(line)

    if state != "normal":
        raise ValueError("Incomplete Git conflict marker")
    if conflict_count == 0:
        raise ValueError("Expected at least one Git conflict marker")
    return "".join(output)


def resolve_automatic_merge_conflicts(root: Path) -> list[str]:
    unresolved_output = run(
        ["git", "diff", "--name-only", "--diff-filter=U"], capture=True
    )
    unresolved = set(unresolved_output.splitlines())
    if not unresolved:
        raise ValueError("Merge failed without unresolved files")
    unexpected = unresolved - AUTOMATIC_JSON_CONFLICTS
    if unexpected:
        joined = ", ".join(sorted(unexpected))
        raise ValueError(f"Manual RingRTC conflict review required: {joined}")

    resolved: list[str] = []
    for relative_path in sorted(unresolved):
        path = root / relative_path
        source = path.read_text(encoding="utf-8")
        result = resolve_version_only_conflicts(source)
        parsed = json.loads(result)
        if parsed.get("name") != "@minutes/ringrtc":
            raise ValueError(f"Minutes package name was not preserved in {relative_path}")
        path.write_text(result, encoding="utf-8")
        resolved.append(relative_path)
    return resolved


def merge(ref: str) -> None:
    validate_ref(ref)
    print(f"Fetching Signal RingRTC {ref} from {UPSTREAM_URL}")
    run(["git", "fetch", UPSTREAM_URL, ref])
    print(f"Merging {ref} into the current Minutes RingRTC branch")
    try:
        run(["git", "merge", "FETCH_HEAD", "--no-edit"])
    except subprocess.CalledProcessError:
        resolved = resolve_automatic_merge_conflicts(ROOT)
        print("Resolving generated package metadata: " + ", ".join(resolved))
        run(["git", "add", "--", *resolved])
        run(["git", "commit", "--no-edit"])
    print("Review docs/MINUTES-PATCHES.md and run the patch-manifest check.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("check")
    subparsers.add_parser("latest")
    merge_parser = subparsers.add_parser("merge")
    merge_parser.add_argument("ref")
    args = parser.parse_args()

    if args.command == "check":
        check(args.root)
    elif args.command == "latest":
        print(fetch_latest_stable_tag())
    else:
        merge(args.ref)


if __name__ == "__main__":
    main()
