#!/usr/bin/env python3
# Copyright 2026 Minutes contributors
# SPDX-License-Identifier: AGPL-3.0-only

"""Keep all Minutes RingRTC version metadata in sync."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_MANIFEST = Path("config/minutes_desktop_artifacts.json")
PATCH_MANIFEST = Path("config/minutes_fork_patch_manifest.json")
PACKAGE_JSON = Path("src/node/package.json")
PACKAGE_LOCK = Path("src/node/package-lock.json")
PREBUILDS = Path("src/node/prebuilds.json")
CHANGELOG = Path("MINUTES-CHANGELOG.md")

UPSTREAM_TAG_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")
PACKAGE_VERSION_RE = re.compile(
    r"^(\d+)\.(\d+)\.(\d+)-minutes\.(\d+)$"
)


def parse_upstream_tag(value: str) -> tuple[int, int, int]:
    match = UPSTREAM_TAG_RE.fullmatch(value.strip())
    if match is None:
        raise ValueError(f"Expected a stable RingRTC tag, got: {value}")
    return tuple(int(part) for part in match.groups())  # type: ignore[return-value]


def normalize_upstream_version(value: str) -> str:
    return ".".join(str(part) for part in parse_upstream_tag(value))


def parse_package_version(value: str) -> tuple[str, int]:
    match = PACKAGE_VERSION_RE.fullmatch(value.strip())
    if match is None:
        raise ValueError(f"Invalid Minutes RingRTC package version: {value}")
    upstream = ".".join(match.groups()[:3])
    return upstream, int(match.group(4))


def load_json(root: Path, path: Path) -> dict[str, Any]:
    return json.loads((root / path).read_text(encoding="utf-8"))


def write_json(root: Path, path: Path, value: dict[str, Any]) -> None:
    (root / path).write_text(
        json.dumps(value, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def current_versions(root: Path) -> tuple[str, str, int]:
    manifest = load_json(root, ARTIFACT_MANIFEST)
    upstream = str(manifest["upstreamVersion"])
    package = str(manifest["packageVersion"])
    package_upstream, revision = parse_package_version(package)
    if upstream != package_upstream:
        raise ValueError(
            f"Artifact manifest mismatch: {upstream=} but {package_upstream=}"
        )
    return upstream, package, revision


def set_versions(root: Path, upstream: str, revision: int) -> str:
    upstream = normalize_upstream_version(upstream)
    if revision < 0:
        raise ValueError("Minutes revision must not be negative")
    package_version = f"{upstream}-minutes.{revision}"

    artifacts = load_json(root, ARTIFACT_MANIFEST)
    artifacts["upstreamVersion"] = upstream
    artifacts["packageVersion"] = package_version
    for target in artifacts["targets"].values():
        target["artifactName"] = (
            f"minutes-ringrtc-v{package_version}-"
            f"{target['nodePlatform']}-{target['nodeArch']}"
        )
    write_json(root, ARTIFACT_MANIFEST, artifacts)

    package = load_json(root, PACKAGE_JSON)
    package["version"] = package_version
    package.setdefault("config", {})["upstreamVersion"] = upstream
    write_json(root, PACKAGE_JSON, package)

    package_lock = load_json(root, PACKAGE_LOCK)
    package_lock["version"] = package_version
    root_package = package_lock.setdefault("packages", {}).setdefault("", {})
    root_package["version"] = package_version
    write_json(root, PACKAGE_LOCK, package_lock)

    prebuilds = load_json(root, PREBUILDS)
    prebuilds["packageVersion"] = package_version
    prebuilds["upstreamVersion"] = upstream
    for target_id, target in prebuilds["targets"].items():
        target["asset"] = f"minutes-ringrtc-v{package_version}-{target_id}.node"
        target["sha256"] = ""
    write_json(root, PREBUILDS, prebuilds)
    return package_version


def add_unreleased_entry(root: Path, entry: str) -> None:
    path = root / CHANGELOG
    source = path.read_text(encoding="utf-8")
    if entry in source:
        return
    marker = "## [Unreleased]\n"
    if marker not in source:
        raise ValueError("MINUTES-CHANGELOG.md has no [Unreleased] section")
    source = source.replace(marker, f"{marker}\n- {entry}\n", 1)
    path.write_text(source, encoding="utf-8")


def prepare_upstream(root: Path, tag: str) -> str:
    next_upstream = normalize_upstream_version(tag)
    current_upstream, _, _ = current_versions(root)
    if parse_upstream_tag(next_upstream) <= parse_upstream_tag(current_upstream):
        raise ValueError(
            f"Upstream {next_upstream} is not newer than {current_upstream}"
        )
    package_version = set_versions(root, next_upstream, 0)
    patch_manifest = load_json(root, PATCH_MANIFEST)
    patch_manifest["upstreamTag"] = f"v{next_upstream}"
    write_json(root, PATCH_MANIFEST, patch_manifest)
    add_unreleased_entry(
        root,
        f"Synchronize the Signal RingRTC baseline from {current_upstream} "
        f"to {next_upstream}.",
    )
    return package_version


def promote_changelog(root: Path, package_version: str, today: str) -> None:
    path = root / CHANGELOG
    source = path.read_text(encoding="utf-8")
    marker = "## [Unreleased]\n"
    start = source.find(marker)
    if start < 0:
        raise ValueError("MINUTES-CHANGELOG.md has no [Unreleased] section")
    body_start = start + len(marker)
    next_section = source.find("\n## [", body_start)
    if next_section < 0:
        next_section = len(source)
    body = source[body_start:next_section].strip()
    if not body or body == "- (add release notes)":
        raise ValueError("MINUTES-CHANGELOG.md [Unreleased] is empty")
    replacement = (
        "## [Unreleased]\n\n- (add release notes)\n\n"
        f"## [{package_version}] - {today}\n\n{body}\n"
    )
    source = source[:start] + replacement + source[next_section:]
    path.write_text(source, encoding="utf-8")


def prepare_release(root: Path, today: str | None = None) -> str:
    upstream, _, revision = current_versions(root)
    package_version = set_versions(root, upstream, revision + 1)
    promote_changelog(root, package_version, today or dt.date.today().isoformat())
    return package_version


def validate(root: Path) -> str:
    upstream, package_version, _ = current_versions(root)
    package = load_json(root, PACKAGE_JSON)
    package_lock = load_json(root, PACKAGE_LOCK)
    prebuilds = load_json(root, PREBUILDS)
    patch_manifest = load_json(root, PATCH_MANIFEST)

    expected = {
        "package.json version": package["version"],
        "package.json upstreamVersion": package["config"]["upstreamVersion"],
        "package-lock version": package_lock["version"],
        "package-lock root version": package_lock["packages"][""]["version"],
        "prebuild packageVersion": prebuilds["packageVersion"],
        "prebuild upstreamVersion": prebuilds["upstreamVersion"],
        "patch manifest upstreamTag": patch_manifest["upstreamTag"].removeprefix("v"),
    }
    for label, value in expected.items():
        wanted = upstream if "upstream" in label.lower() else package_version
        if value != wanted:
            raise ValueError(f"{label} is {value}, expected {wanted}")

    for target in load_json(root, ARTIFACT_MANIFEST)["targets"].values():
        expected_name = (
            f"minutes-ringrtc-v{package_version}-"
            f"{target['nodePlatform']}-{target['nodeArch']}"
        )
        if target["artifactName"] != expected_name:
            raise ValueError(
                f"Artifact name {target['artifactName']} != {expected_name}"
            )
    for target_id, target in prebuilds["targets"].items():
        expected_asset = f"minutes-ringrtc-v{package_version}-{target_id}.node"
        if target["asset"] != expected_asset:
            raise ValueError(f"Prebuild asset {target['asset']} != {expected_asset}")
    return package_version


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare = subparsers.add_parser("prepare-upstream")
    prepare.add_argument("tag")
    release = subparsers.add_parser("prepare-release")
    release.add_argument("--date")
    subparsers.add_parser("validate")
    args = parser.parse_args()

    if args.command == "prepare-upstream":
        result = prepare_upstream(args.root, args.tag)
    elif args.command == "prepare-release":
        result = prepare_release(args.root, args.date)
    else:
        result = validate(args.root)
    print(result)


if __name__ == "__main__":
    main()
