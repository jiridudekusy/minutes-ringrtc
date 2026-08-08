#!/usr/bin/env python3

#
# Copyright 2026 Minutes contributors
# SPDX-License-Identifier: AGPL-3.0-only
#

import argparse
import subprocess
import sys
from pathlib import Path


def git_apply(source: Path, *args: str, patch: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(source), "apply", *args, str(patch)],
        check=False,
        capture_output=True,
        text=True,
    )


def apply_patches(source: Path, patch_dir: Path) -> None:
    if not source.is_dir():
        raise ValueError(f"WebRTC source directory does not exist: {source}")
    if not patch_dir.is_dir():
        return

    for patch in sorted(patch_dir.glob("*.patch")):
        reverse_check = git_apply(source, "--reverse", "--check", patch=patch)
        if reverse_check.returncode == 0:
            print(f"already applied {patch.name}")
            continue

        check = git_apply(source, "--check", patch=patch)
        if check.returncode != 0:
            detail = check.stderr.strip() or check.stdout.strip()
            raise ValueError(f"cannot apply {patch.name}: {detail}")

        applied = git_apply(source, patch=patch)
        if applied.returncode != 0:
            detail = applied.stderr.strip() or applied.stdout.strip()
            raise ValueError(f"failed to apply {patch.name}: {detail}")
        print(f"applied {patch.name}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply versioned WebRTC patches.")
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--patch-dir", required=True, type=Path)
    args = parser.parse_args()

    try:
        apply_patches(args.source.resolve(), args.patch_dir.resolve())
    except ValueError as error:
        print(f"WebRTC patch error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
