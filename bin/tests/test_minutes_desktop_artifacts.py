#!/usr/bin/env python3

#
# Copyright 2026 Minutes contributors
# SPDX-License-Identifier: AGPL-3.0-only
#

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[2]
VALIDATOR = PROJECT_DIR / "bin" / "minutes_desktop_artifacts.py"
CHECKSUMS = PROJECT_DIR / "config" / "webrtc_artifact_checksums.json"
MANIFEST = PROJECT_DIR / "config" / "minutes_desktop_artifacts.json"


class MinutesDesktopArtifactsTest(unittest.TestCase):
    @staticmethod
    def valid_manifest() -> dict:
        return {
            "schemaVersion": 1,
            "package": "@minutes/ringrtc",
            "ringrtcVersion": "2.69.7",
            "targets": {
                "mac-arm64": {
                    "runner": "macos-14",
                    "webrtcPlatform": "mac-arm64",
                    "targetArch": "arm64",
                    "cargoTarget": "aarch64-apple-darwin",
                    "nodePlatform": "darwin",
                    "nodeArch": "arm64",
                    "output": "src/node/build/darwin/libringrtc-arm64.node",
                    "artifactName": "minutes-ringrtc-v2.69.7-darwin-arm64",
                },
                "windows-x64": {
                    "runner": "windows-2022",
                    "webrtcPlatform": "windows-x64",
                    "targetArch": "x64",
                    "cargoTarget": "x86_64-pc-windows-msvc",
                    "nodePlatform": "win32",
                    "nodeArch": "x64",
                    "output": "src/node/build/win32/libringrtc-x64.node",
                    "artifactName": "minutes-ringrtc-v2.69.7-win32-x64",
                },
            },
        }

    def run_command(
        self, command: str, manifest: dict
    ) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as temp_dir:
            manifest_path = Path(temp_dir) / "manifest.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            return subprocess.run(
                [
                    sys.executable,
                    str(VALIDATOR),
                    command,
                    "--manifest",
                    str(manifest_path),
                    "--checksums",
                    str(CHECKSUMS),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

    def run_validator(self, manifest: dict) -> subprocess.CompletedProcess[str]:
        return self.run_command("validate", manifest)

    def test_rejects_manifest_missing_required_windows_target(self) -> None:
        manifest = self.valid_manifest()
        del manifest["targets"]["windows-x64"]
        result = self.run_validator(manifest)

        self.assertEqual(result.returncode, 1)
        self.assertEqual(
            result.stderr,
            "manifest error: missing required target(s): windows-x64\n",
        )

    def test_rejects_target_without_upstream_webrtc_checksum(self) -> None:
        manifest = self.valid_manifest()
        manifest["targets"]["windows-x64"]["webrtcPlatform"] = "windows-riscv64"

        result = self.run_validator(manifest)

        self.assertEqual(result.returncode, 1)
        self.assertEqual(
            result.stderr,
            "manifest error: target windows-x64 references WebRTC platform "
            "without a checksum: windows-riscv64\n",
        )

    def test_matrix_emits_only_the_two_supported_targets(self) -> None:
        manifest = self.valid_manifest()

        result = self.run_command("matrix", manifest)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            json.loads(result.stdout),
            {
                "include": [
                    {"id": "mac-arm64", **manifest["targets"]["mac-arm64"]},
                    {
                        "id": "windows-x64",
                        **manifest["targets"]["windows-x64"],
                    },
                ]
            },
        )

    def test_rejects_unexpected_native_addon_output_path(self) -> None:
        manifest = self.valid_manifest()
        manifest["targets"]["mac-arm64"]["output"] = (
            "src/node/build/darwin/libringrtc-x64.node"
        )

        result = self.run_validator(manifest)

        self.assertEqual(result.returncode, 1)
        self.assertEqual(
            result.stderr,
            "manifest error: target mac-arm64 has invalid output; expected "
            "src/node/build/darwin/libringrtc-arm64.node\n",
        )

    def test_rejects_targets_outside_minutes_supported_set(self) -> None:
        manifest = self.valid_manifest()
        manifest["targets"]["linux-x64"] = {
            **manifest["targets"]["windows-x64"],
            "webrtcPlatform": "linux-x64",
        }

        result = self.run_validator(manifest)

        self.assertEqual(result.returncode, 1)
        self.assertEqual(
            result.stderr,
            "manifest error: unsupported target(s): linux-x64\n",
        )

    def test_repository_manifest_is_valid(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(VALIDATOR),
                "validate",
                "--manifest",
                str(MANIFEST),
                "--checksums",
                str(CHECKSUMS),
            ],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)

    def test_rejects_manifest_version_that_differs_from_node_package(self) -> None:
        manifest = self.valid_manifest()
        manifest["ringrtcVersion"] = "9.9.9"

        result = self.run_validator(manifest)

        self.assertEqual(result.returncode, 1)
        self.assertEqual(
            result.stderr,
            "manifest error: ringrtcVersion 9.9.9 does not match Node package "
            "version 2.69.7\n",
        )

    def test_verify_output_rejects_missing_native_addon(self) -> None:
        manifest = self.valid_manifest()
        with tempfile.TemporaryDirectory() as temp_dir:
            project_dir = Path(temp_dir)
            manifest_path = project_dir / "manifest.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable,
                    str(VALIDATOR),
                    "verify-output",
                    "--manifest",
                    str(manifest_path),
                    "--checksums",
                    str(CHECKSUMS),
                    "--target",
                    "mac-arm64",
                    "--project-dir",
                    str(project_dir),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(result.returncode, 1)
        self.assertEqual(
            result.stderr,
            "artifact error: missing or empty native addon: "
            "src/node/build/darwin/libringrtc-arm64.node\n",
        )

    def test_rejects_build_coordinates_for_a_different_target(self) -> None:
        manifest = self.valid_manifest()
        manifest["targets"]["mac-arm64"]["targetArch"] = "x64"

        result = self.run_validator(manifest)

        self.assertEqual(result.returncode, 1)
        self.assertEqual(
            result.stderr,
            "manifest error: target mac-arm64 has invalid targetArch; expected "
            "arm64\n",
        )


if __name__ == "__main__":
    unittest.main()
