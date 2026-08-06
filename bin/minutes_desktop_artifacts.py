#!/usr/bin/env python3

#
# Copyright 2026 Minutes contributors
# SPDX-License-Identifier: AGPL-3.0-only
#

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


REQUIRED_TARGETS = frozenset(("linux-x64", "mac-arm64", "windows-x64"))
EXPECTED_OUTPUTS = {
    "linux-x64": "src/node/build/linux/libringrtc-x64.node",
    "mac-arm64": "src/node/build/darwin/libringrtc-arm64.node",
    "windows-x64": "src/node/build/win32/libringrtc-x64.node",
}
EXPECTED_BUILD_COORDINATES = {
    "linux-x64": {
        "webrtcPlatform": "linux-x64",
        "targetArch": "x64",
        "cargoTarget": "x86_64-unknown-linux-gnu",
        "nodePlatform": "linux",
        "nodeArch": "x64",
    },
    "mac-arm64": {
        "webrtcPlatform": "mac-arm64",
        "targetArch": "arm64",
        "cargoTarget": "aarch64-apple-darwin",
        "nodePlatform": "darwin",
        "nodeArch": "arm64",
    },
    "windows-x64": {
        "webrtcPlatform": "windows-x64",
        "targetArch": "x64",
        "cargoTarget": "x86_64-pc-windows-msvc",
        "nodePlatform": "win32",
        "nodeArch": "x64",
    },
}
REQUIRED_TARGET_FIELDS = frozenset(
    (
        "runner",
        "webrtcPlatform",
        "targetArch",
        "cargoTarget",
        "nodePlatform",
        "nodeArch",
        "output",
        "artifactName",
    )
)
PROJECT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_NODE_PACKAGE = PROJECT_DIR / "src" / "node" / "package.json"
ADDON_VERIFIER = PROJECT_DIR / "bin" / "verify_minutes_node_addon.js"


class ManifestError(ValueError):
    pass


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ManifestError(f"file not found: {path}") from error
    except json.JSONDecodeError as error:
        raise ManifestError(f"invalid JSON in {path}: {error.msg}") from error


def validate_manifest(manifest: Any, checksums: Any, node_package: Any) -> None:
    if not isinstance(manifest, dict):
        raise ManifestError("manifest root must be an object")

    if manifest.get("schemaVersion") != 1:
        raise ManifestError("schemaVersion must be 1")
    if manifest.get("package") != "@minutes/ringrtc":
        raise ManifestError("package must be @minutes/ringrtc")
    if not isinstance(node_package, dict) or not isinstance(
        node_package.get("version"), str
    ):
        raise ManifestError("Node package must contain a string version")
    if node_package.get("name") != "@minutes/ringrtc":
        raise ManifestError("Node package name must be @minutes/ringrtc")
    node_config = node_package.get("config")
    if not isinstance(node_config, dict):
        raise ManifestError("Node package must contain config")

    package_version = manifest.get("packageVersion")
    if package_version != node_package["version"]:
        raise ManifestError(
            f"packageVersion {package_version} does not match Node package "
            f"version {node_package['version']}"
        )
    upstream_version = manifest.get("upstreamVersion")
    if upstream_version != node_config.get("upstreamVersion"):
        raise ManifestError(
            f"upstreamVersion {upstream_version} does not match Node package "
            f"upstreamVersion {node_config.get('upstreamVersion')}"
        )
    tap_api_version = manifest.get("tapApiVersion")
    if tap_api_version != node_config.get("tapApiVersion"):
        raise ManifestError(
            f"tapApiVersion {tap_api_version} does not match Node package "
            f"tapApiVersion {node_config.get('tapApiVersion')}"
        )
    if not re.fullmatch(
        rf"{re.escape(upstream_version)}-minutes\.[1-9][0-9]*", package_version
    ):
        raise ManifestError(
            "packageVersion must be the supported Minutes semver derived from "
            "upstreamVersion"
        )

    targets = manifest.get("targets")
    if not isinstance(targets, dict):
        raise ManifestError("targets must be an object")

    missing_targets = sorted(REQUIRED_TARGETS.difference(targets))
    if missing_targets:
        raise ManifestError(
            f"missing required target(s): {', '.join(missing_targets)}"
        )

    unsupported_targets = sorted(set(targets).difference(REQUIRED_TARGETS))
    if unsupported_targets:
        raise ManifestError(
            f"unsupported target(s): {', '.join(unsupported_targets)}"
        )

    if not isinstance(checksums, dict):
        raise ManifestError("WebRTC checksum manifest root must be an object")

    for target_name, target in targets.items():
        if not isinstance(target, dict):
            raise ManifestError(f"target {target_name} must be an object")
        missing_fields = sorted(REQUIRED_TARGET_FIELDS.difference(target))
        if missing_fields:
            raise ManifestError(
                f"target {target_name} is missing field(s): "
                f"{', '.join(missing_fields)}"
            )
        webrtc_platform = target.get("webrtcPlatform")
        if webrtc_platform not in checksums:
            raise ManifestError(
                f"target {target_name} references WebRTC platform without a "
                f"checksum: {webrtc_platform}"
            )
        for field, expected_value in EXPECTED_BUILD_COORDINATES[target_name].items():
            if target[field] != expected_value:
                raise ManifestError(
                    f"target {target_name} has invalid {field}; expected "
                    f"{expected_value}"
                )
        expected_output = EXPECTED_OUTPUTS[target_name]
        if target["output"] != expected_output:
            raise ManifestError(
                f"target {target_name} has invalid output; expected {expected_output}"
            )
        expected_artifact_name = (
            f"minutes-ringrtc-v{package_version}-{target['nodePlatform']}-"
            f"{target['nodeArch']}"
        )
        if target["artifactName"] != expected_artifact_name:
            raise ManifestError(
                f"target {target_name} has invalid artifactName; expected "
                f"{expected_artifact_name}"
            )


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate Minutes RingRTC desktop artifact metadata."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("validate", "matrix", "verify-output", "release-manifest"):
        subparser = subparsers.add_parser(command)
        subparser.add_argument("--manifest", required=True, type=Path)
        subparser.add_argument("--checksums", required=True, type=Path)
        subparser.add_argument(
            "--node-package", type=Path, default=DEFAULT_NODE_PACKAGE
        )
        if command == "verify-output":
            subparser.add_argument(
                "--target", required=True, choices=sorted(REQUIRED_TARGETS)
            )
            subparser.add_argument("--project-dir", type=Path, default=PROJECT_DIR)
        if command == "release-manifest":
            subparser.add_argument("--assets-dir", required=True, type=Path)
            subparser.add_argument("--release-dir", required=True, type=Path)
            subparser.add_argument("--output", required=True, type=Path)
    return parser


def main() -> int:
    args = build_argument_parser().parse_args()
    try:
        manifest = read_json(args.manifest)
        checksums = read_json(args.checksums)
        node_package = read_json(args.node_package)
        validate_manifest(manifest, checksums, node_package)
    except ManifestError as error:
        print(f"manifest error: {error}", file=sys.stderr)
        return 1
    if args.command == "verify-output":
        relative_output = manifest["targets"][args.target]["output"]
        output = args.project_dir / relative_output
        try:
            output_is_valid = output.is_file() and output.stat().st_size > 0
        except OSError as error:
            print(
                f"artifact error: cannot inspect native addon {relative_output}: "
                f"{error}",
                file=sys.stderr,
            )
            return 1
        if not output_is_valid:
            print(
                f"artifact error: missing or empty native addon: {relative_output}",
                file=sys.stderr,
            )
            return 1
        verification = subprocess.run(
            [
                "node",
                str(ADDON_VERIFIER),
                str(output),
                str(manifest["tapApiVersion"]),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if verification.returncode != 0:
            sys.stderr.write(verification.stderr)
            return 1
        return 0
    if args.command == "release-manifest":
        release_targets = {}
        args.release_dir.mkdir(parents=True, exist_ok=True)
        for target_name in sorted(REQUIRED_TARGETS):
            target = manifest["targets"][target_name]
            source = args.assets_dir / target["output"]
            if not source.is_file() or source.stat().st_size == 0:
                print(
                    f"artifact error: missing or empty native addon: {source}",
                    file=sys.stderr,
                )
                return 1
            asset = f"{target['artifactName']}.node"
            destination = args.release_dir / asset
            shutil.copyfile(source, destination)
            release_targets[
                f"{target['nodePlatform']}-{target['nodeArch']}"
            ] = {
                "asset": asset,
                "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            }
        release_manifest = {
            "schemaVersion": 1,
            "packageVersion": manifest["packageVersion"],
            "upstreamVersion": manifest["upstreamVersion"],
            "tapApiVersion": manifest["tapApiVersion"],
            "targets": release_targets,
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(release_manifest, indent=2) + "\n", encoding="utf-8"
        )
        return 0
    if args.command == "matrix":
        matrix = {
            "include": [
                {"id": target_name, **manifest["targets"][target_name]}
                for target_name in sorted(REQUIRED_TARGETS)
            ]
        }
        print(json.dumps(matrix, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
