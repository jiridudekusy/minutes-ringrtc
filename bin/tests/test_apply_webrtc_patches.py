#!/usr/bin/env python3

#
# Copyright 2026 Minutes contributors
# SPDX-License-Identifier: AGPL-3.0-only
#

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[2]
PATCHER = PROJECT_DIR / "bin" / "apply-webrtc-patches.py"


class ApplyWebrtcPatchesTest(unittest.TestCase):
    def test_applies_patches_once_and_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "source"
            patches = root / "patches"
            source.mkdir()
            patches.mkdir()
            subprocess.run(["git", "init", "-q", str(source)], check=True)
            target = source / "value.txt"
            target.write_text("before\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(source), "add", "value.txt"], check=True)
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(source),
                    "-c",
                    "user.name=Minutes Test",
                    "-c",
                    "user.email=minutes@example.invalid",
                    "commit",
                    "-qm",
                    "base",
                ],
                check=True,
            )
            patch = patches / "0001-change-value.patch"
            patch.write_text(
                "diff --git a/value.txt b/value.txt\n"
                "--- a/value.txt\n"
                "+++ b/value.txt\n"
                "@@ -1 +1 @@\n"
                "-before\n"
                "+after\n",
                encoding="utf-8",
            )

            command = [
                sys.executable,
                str(PATCHER),
                "--source",
                str(source),
                "--patch-dir",
                str(patches),
            ]
            first = subprocess.run(command, check=False, capture_output=True, text=True)
            second = subprocess.run(command, check=False, capture_output=True, text=True)

            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(target.read_text(encoding="utf-8"), "after\n")
            self.assertIn("applied 0001-change-value.patch", first.stdout)
            self.assertIn("already applied 0001-change-value.patch", second.stdout)


if __name__ == "__main__":
    unittest.main()
