#!/usr/bin/env python3
# Copyright 2026 Minutes contributors
# SPDX-License-Identifier: AGPL-3.0-only

import json
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_DIR / "bin"))

from minutes_changelog import extract_release  # noqa: E402
from minutes_patch_manifest import classify_paths, render  # noqa: E402
from minutes_upstream import (  # noqa: E402
    AUTOMATIC_JSON_CONFLICTS,
    has_open_sync_pull_request,
    latest_stable_tag,
    resolve_version_only_conflicts,
    validate_ref,
)
from minutes_version import (  # noqa: E402
    ARTIFACT_MANIFEST,
    CHANGELOG,
    PACKAGE_JSON,
    PACKAGE_LOCK,
    PATCH_MANIFEST,
    PREBUILDS,
    prepare_release,
    prepare_upstream,
    validate,
)


class MinutesUpstreamTest(unittest.TestCase):
    def test_selects_highest_stable_tag_and_ignores_prereleases(self) -> None:
        self.assertEqual(
            latest_stable_tag(
                ["v2.70.1", "v2.71.0-alpha.1", "v2.69.9", "2.70.2"]
            ),
            "v2.70.2",
        )

    def test_detects_existing_sync_pull_request(self) -> None:
        pull_requests = [
            {
                "title": "Sync RingRTC (v2.70.2)",
                "headRefName": "sync/ringrtc-2.70.2-123",
            }
        ]
        self.assertTrue(has_open_sync_pull_request(pull_requests, "v2.70.2"))
        self.assertFalse(has_open_sync_pull_request(pull_requests, "v2.70.3"))

    def test_rejects_unsafe_manual_refs(self) -> None:
        for ref in ("--upload-pack=bad", "main..evil", "main;echo"):
            with self.assertRaises(ValueError):
                validate_ref(ref)
        validate_ref("v2.70.2")
        validate_ref("feature/audio-fix")

    def test_resolves_only_package_name_and_version_conflicts(self) -> None:
        start = "<" * 7
        separator = "=" * 7
        end = ">" * 7
        source = (
            "{\n"
            f"{start} HEAD\n"
            '  "name": "@minutes/ringrtc",\n'
            '  "version": "2.69.7-minutes.3",\n'
            f"{separator}\n"
            '  "name": "@signalapp/ringrtc",\n'
            '  "version": "2.70.2",\n'
            f"{end} upstream\n"
            '  "license": "AGPL-3.0-only"\n'
            "}\n"
        )
        resolved = resolve_version_only_conflicts(source)
        self.assertEqual(json.loads(resolved)["name"], "@minutes/ringrtc")
        self.assertNotIn("<<<<<<<", resolved)

    def test_refuses_to_auto_resolve_dependency_conflict(self) -> None:
        start = "<" * 7
        separator = "=" * 7
        end = ">" * 7
        source = (
            "{\n"
            f"{start} HEAD\n"
            '  "dependency": "1"\n'
            f"{separator}\n"
            '  "dependency": "2"\n'
            f"{end} upstream\n"
            "}\n"
        )
        with self.assertRaises(ValueError):
            resolve_version_only_conflicts(source)

    def test_lockfile_conflicts_always_require_manual_review(self) -> None:
        self.assertNotIn(
            "src/node/package-lock.json", AUTOMATIC_JSON_CONFLICTS
        )

    def test_patch_manifest_reports_unknown_and_stale_paths(self) -> None:
        manifest = {
            "upstreamPatches": [
                {"path": "src/upstream.rs", "purpose": "hook"}
            ],
            "forkOwnedPaths": [
                {"pattern": "minutes/**", "purpose": "owned"}
            ],
        }
        unknown, stale = classify_paths(
            manifest, {"src/upstream.rs", "minutes/new.rs", "src/unknown.rs"}
        )
        self.assertEqual(unknown, {"src/unknown.rs"})
        self.assertEqual(stale, set())
        _, stale = classify_paths(manifest, {"minutes/new.rs"})
        self.assertEqual(stale, {"src/upstream.rs"})

    def test_generated_patch_document_contains_baseline(self) -> None:
        manifest = {
            "upstreamRepository": "signalapp/ringrtc",
            "upstreamTag": "v2.69.7",
            "upstreamPatches": [
                {"path": "src/upstream.rs", "purpose": "thin hook"}
            ],
            "forkOwnedPaths": [
                {"pattern": "minutes/**", "purpose": "owned"}
            ],
        }
        document = render(manifest)
        self.assertIn("`v2.69.7`", document)
        self.assertIn("`src/upstream.rs`", document)

    def test_extracts_only_requested_release_notes(self) -> None:
        source = (
            "# Changelog\n\n## [Unreleased]\n\n- later\n\n"
            "## [2.0.0-minutes.1] - 2026-08-05\n\n- wanted\n\n"
            "## [1.0.0-minutes.1] - 2026-01-01\n\n- old\n"
        )
        self.assertEqual(
            extract_release(source, "2.0.0-minutes.1"), "- wanted\n"
        )


class MinutesVersionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        paths = [
            ARTIFACT_MANIFEST,
            PATCH_MANIFEST,
            PACKAGE_JSON,
            PACKAGE_LOCK,
            PREBUILDS,
            CHANGELOG,
        ]
        for path in paths:
            destination = self.root / path
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes((PROJECT_DIR / path).read_bytes())
        artifacts = json.loads(
            (self.root / ARTIFACT_MANIFEST).read_text(encoding="utf-8")
        )
        self.initial_upstream = artifacts["upstreamVersion"]
        self.initial_package = artifacts["packageVersion"]

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_prepares_new_upstream_as_unreleased_revision_zero(self) -> None:
        major, minor, patch = (
            int(part) for part in self.initial_upstream.split(".")
        )
        next_upstream = f"{major}.{minor}.{patch + 1}"
        expected = f"{next_upstream}-minutes.0"
        result = prepare_upstream(self.root, f"v{next_upstream}")
        self.assertEqual(result, expected)
        artifacts = json.loads(
            (self.root / ARTIFACT_MANIFEST).read_text(encoding="utf-8")
        )
        self.assertEqual(artifacts["upstreamVersion"], next_upstream)
        self.assertEqual(
            artifacts["targets"]["mac-arm64"]["artifactName"],
            f"minutes-ringrtc-v{expected}-darwin-arm64",
        )
        self.assertEqual(validate(self.root), expected)

    def test_release_increments_only_minutes_revision_and_promotes_notes(self) -> None:
        changelog_path = self.root / CHANGELOG
        changelog = changelog_path.read_text(encoding="utf-8")
        changelog_path.write_text(
            changelog.replace(
                "## [Unreleased]\n",
                "## [Unreleased]\n\n- Test release note.\n",
                1,
            ),
            encoding="utf-8",
        )
        revision = int(self.initial_package.rsplit(".", 1)[1]) + 1
        expected = f"{self.initial_upstream}-minutes.{revision}"
        result = prepare_release(self.root, "2026-08-05")
        self.assertEqual(result, expected)
        changelog = (self.root / CHANGELOG).read_text(encoding="utf-8")
        self.assertIn(f"## [{expected}] - 2026-08-05", changelog)
        self.assertEqual(validate(self.root), expected)

    def test_validation_rejects_metadata_drift(self) -> None:
        package = json.loads(
            (self.root / PACKAGE_JSON).read_text(encoding="utf-8")
        )
        package["version"] = "9.9.9-minutes.9"
        (self.root / PACKAGE_JSON).write_text(
            json.dumps(package), encoding="utf-8"
        )
        with self.assertRaises(ValueError):
            validate(self.root)


if __name__ == "__main__":
    unittest.main()
