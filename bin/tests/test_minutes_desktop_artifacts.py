#!/usr/bin/env python3

#
# Copyright 2026 Minutes contributors
# SPDX-License-Identifier: AGPL-3.0-only
#

import json
import hashlib
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[2]
VALIDATOR = PROJECT_DIR / "bin" / "minutes_desktop_artifacts.py"
ADDON_VERIFIER = PROJECT_DIR / "bin" / "verify_minutes_node_addon.js"
CHECKSUMS = PROJECT_DIR / "config" / "webrtc_artifact_checksums.json"
MANIFEST = PROJECT_DIR / "config" / "minutes_desktop_artifacts.json"
NODE_PACKAGE = PROJECT_DIR / "src" / "node" / "package.json"
WORKFLOW = PROJECT_DIR / ".github" / "workflows" / "minutes_desktop_artifacts.yml"


class MinutesDesktopArtifactsTest(unittest.TestCase):
    @staticmethod
    def valid_manifest() -> dict:
        return {
            "schemaVersion": 1,
            "package": "@minutes/ringrtc",
            "packageVersion": "2.69.7-minutes.2",
            "upstreamVersion": "2.69.7",
            "tapApiVersion": 1,
            "targets": {
                "mac-arm64": {
                    "runner": "macos-14",
                    "webrtcPlatform": "mac-arm64",
                    "targetArch": "arm64",
                    "cargoTarget": "aarch64-apple-darwin",
                    "nodePlatform": "darwin",
                    "nodeArch": "arm64",
                    "output": "src/node/build/darwin/libringrtc-arm64.node",
                    "artifactName": (
                        "minutes-ringrtc-v2.69.7-minutes.2-darwin-arm64"
                    ),
                },
                "windows-x64": {
                    "runner": "windows-2022",
                    "webrtcPlatform": "windows-x64",
                    "targetArch": "x64",
                    "cargoTarget": "x86_64-pc-windows-msvc",
                    "nodePlatform": "win32",
                    "nodeArch": "x64",
                    "output": "src/node/build/win32/libringrtc-x64.node",
                    "artifactName": (
                        "minutes-ringrtc-v2.69.7-minutes.2-win32-x64"
                    ),
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

    def test_rejects_manifest_missing_required_linux_target(self) -> None:
        manifest = self.valid_manifest()
        del manifest["targets"]["linux-x64"]
        result = self.run_validator(manifest)

        self.assertEqual(result.returncode, 1)
        self.assertEqual(
            result.stderr,
            "manifest error: missing required target(s): linux-x64\n",
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

    def test_matrix_emits_all_three_supported_targets(self) -> None:
        manifest = self.valid_manifest()

        result = self.run_command("matrix", manifest)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            json.loads(result.stdout),
            {
                "include": [
                    {"id": "linux-x64", **manifest["targets"]["linux-x64"]},
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
        manifest["targets"]["freebsd-x64"] = {
            **manifest["targets"]["windows-x64"],
        }

        result = self.run_validator(manifest)

        self.assertEqual(result.returncode, 1)
        self.assertEqual(
            result.stderr,
            "manifest error: unsupported target(s): freebsd-x64\n",
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
        manifest["packageVersion"] = "9.9.9"

        result = self.run_validator(manifest)

        self.assertEqual(result.returncode, 1)
        self.assertEqual(
            result.stderr,
            "manifest error: packageVersion 9.9.9 does not match Node package "
            "version 2.69.7-minutes.2\n",
        )

    def test_rejects_manifest_with_wrong_audio_tap_api_version(self) -> None:
        manifest = self.valid_manifest()
        manifest["tapApiVersion"] = 2

        result = self.run_validator(manifest)

        self.assertEqual(result.returncode, 1)
        self.assertEqual(
            result.stderr,
            "manifest error: tapApiVersion 2 does not match Node package "
            "tapApiVersion 1\n",
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

    def test_verify_output_rejects_addon_without_tap_api(self) -> None:
        manifest = self.valid_manifest()
        with tempfile.TemporaryDirectory() as temp_dir:
            project_dir = Path(temp_dir)
            manifest_path = project_dir / "manifest.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            output = project_dir / manifest["targets"]["mac-arm64"]["output"]
            output.parent.mkdir(parents=True)
            output.write_bytes(b"not a native addon")
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
        self.assertIn("addon error:", result.stderr)

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

    def test_node_package_is_minutes_compatibility_package(self) -> None:
        package = json.loads(NODE_PACKAGE.read_text(encoding="utf-8"))

        self.assertEqual(package["name"], "@minutes/ringrtc")
        self.assertEqual(package["version"], "2.69.7-minutes.2")
        self.assertEqual(package["config"]["upstreamVersion"], "2.69.7")
        self.assertEqual(package["config"]["tapApiVersion"], 1)
        self.assertEqual(
            package["scripts"]["install"],
            "node scripts/fetch-minutes-prebuild.js",
        )
        self.assertIn("prebuilds.json", package["files"])
        self.assertFalse((NODE_PACKAGE.parent / "scripts" / "fetch-prebuild.js").exists())
        self.assertNotIn(
            "build-artifacts.signal.org",
            (NODE_PACKAGE.parent / "scripts" / "fetch-minutes-prebuild.js").read_text(
                encoding="utf-8"
            ),
        )

    def test_addon_verifier_rejects_wrong_audio_tap_api_version(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            addon = Path(temp_dir) / "addon.js"
            addon.write_text(
                "module.exports = {"
                "cm_audioTapIsSupported: () => true,"
                "cm_audioTapVersion: () => 2,"
                "cm_startAudioTap() {},"
                "cm_readAudioTap() {},"
                "cm_stopAudioTap() {},"
                "cm_videoTapIsSupported: () => true,"
                "cm_videoTapVersion: () => 1,"
                "cm_startVideoTap() {},"
                "cm_readVideoTap() {},"
                "cm_stopVideoTap() {}"
                "};",
                encoding="utf-8",
            )
            result = subprocess.run(
                ["node", str(ADDON_VERIFIER), str(addon), "1"],
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(result.returncode, 1)
        self.assertEqual(
            result.stderr,
            "addon error: expected audio tap API version 1, got 2\n",
        )

    def test_addon_verifier_rejects_wrong_video_tap_api_version(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            addon = Path(temp_dir) / "addon.js"
            addon.write_text(
                "module.exports = {"
                "cm_audioTapIsSupported: () => true,"
                "cm_audioTapVersion: () => 1,"
                "cm_startAudioTap() {},"
                "cm_readAudioTap() {},"
                "cm_stopAudioTap() {},"
                "cm_videoTapIsSupported: () => true,"
                "cm_videoTapVersion: () => 2,"
                "cm_startVideoTap() {},"
                "cm_readVideoTap() {},"
                "cm_stopVideoTap() {}"
                "};",
                encoding="utf-8",
            )
            result = subprocess.run(
                ["node", str(ADDON_VERIFIER), str(addon), "1"],
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(result.returncode, 1)
        self.assertEqual(
            result.stderr,
            "addon error: expected video tap API version 1, got 2\n",
        )

    def test_addon_verifier_requires_video_tap_api(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            addon = Path(temp_dir) / "addon.js"
            addon.write_text(
                "module.exports = {"
                "cm_audioTapIsSupported: () => true,"
                "cm_audioTapVersion: () => 1,"
                "cm_startAudioTap() {},"
                "cm_readAudioTap() {},"
                "cm_stopAudioTap() {}"
                "};",
                encoding="utf-8",
            )
            result = subprocess.run(
                ["node", str(ADDON_VERIFIER), str(addon), "1"],
                check=False,
                capture_output=True,
                text=True,
            )

        self.assertEqual(result.returncode, 1)
        self.assertEqual(
            result.stderr,
            "addon error: missing native export cm_videoTapIsSupported\n",
        )

    def test_release_manifest_requires_and_checksums_all_addons(self) -> None:
        manifest = self.valid_manifest()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            manifest_path = root / "manifest.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            assets = root / "assets"
            release = root / "release"
            output_manifest = root / "prebuilds.json"
            addon_bytes = {}
            for target_name, target in manifest["targets"].items():
                data = f"addon-{target_name}".encode()
                addon_bytes[target_name] = data
                output = assets / target["output"]
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_bytes(data)

            result = subprocess.run(
                [
                    sys.executable,
                    str(VALIDATOR),
                    "release-manifest",
                    "--manifest",
                    str(manifest_path),
                    "--checksums",
                    str(CHECKSUMS),
                    "--assets-dir",
                    str(assets),
                    "--release-dir",
                    str(release),
                    "--output",
                    str(output_manifest),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            generated = json.loads(output_manifest.read_text(encoding="utf-8"))
            self.assertEqual(generated["tapApiVersion"], 1)
            for target_name, target in manifest["targets"].items():
                runtime = f"{target['nodePlatform']}-{target['nodeArch']}"
                asset = f"{target['artifactName']}.node"
                self.assertEqual(generated["targets"][runtime]["asset"], asset)
                self.assertEqual(
                    generated["targets"][runtime]["sha256"],
                    hashlib.sha256(addon_bytes[target_name]).hexdigest(),
                )
                self.assertEqual((release / asset).read_bytes(), addon_bytes[target_name])

    def test_workflow_verifies_and_packages_all_release_addons(self) -> None:
        workflow = WORKFLOW.read_text(encoding="utf-8")

        self.assertIn("node bin/verify_minutes_node_addon.js", workflow)
        self.assertIn("release-manifest", workflow)
        self.assertIn("npm run build", workflow)
        self.assertIn("npm pack", workflow)
        self.assertNotIn("npm publish", workflow)
        self.assertNotIn("id-token: write", workflow)
        self.assertIn("gh release create", workflow)
        self.assertIn("gh release upload", workflow)
        self.assertIn("--clobber", workflow)
        self.assertIn(
            "actions/download-artifact@3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c",
            workflow,
        )
        external_actions = re.findall(r"uses:\s+([^\s#]+)", workflow)
        for action in external_actions:
            if action.startswith("./"):
                continue
            self.assertRegex(action, r"@[a-f0-9]{40}$")


if __name__ == "__main__":
    unittest.main()
