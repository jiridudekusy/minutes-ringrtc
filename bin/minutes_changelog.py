#!/usr/bin/env python3
# Copyright 2026 Minutes contributors
# SPDX-License-Identifier: AGPL-3.0-only

"""Extract one Minutes RingRTC release section as GitHub release notes."""

from __future__ import annotations

import argparse
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def extract_release(source: str, version: str) -> str:
    pattern = re.compile(
        rf"^## \[{re.escape(version)}\](?: - [^\n]+)?\n+(.*?)(?=^## \[|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(source)
    if match is None:
        raise ValueError(f"MINUTES-CHANGELOG.md has no section for {version}")
    notes = match.group(1).strip()
    if not notes:
        raise ValueError(f"MINUTES-CHANGELOG.md section {version} is empty")
    return notes + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("version")
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    source = (args.root / "MINUTES-CHANGELOG.md").read_text(encoding="utf-8")
    print(extract_release(source, args.version), end="")


if __name__ == "__main__":
    main()
