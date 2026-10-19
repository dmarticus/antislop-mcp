"""Build the lightweight Antislop menu-bar app bundle on macOS."""

from __future__ import annotations

import argparse
import plistlib
import shutil
import subprocess
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("build/Antislop.app"))
    parser.add_argument("--python", type=Path, default=Path(".venv/bin/python"))
    args = parser.parse_args()
    if shutil.which("swiftc") is None:
        raise SystemExit("swiftc is required; install Xcode Command Line Tools first.")
    root = Path(__file__).resolve().parents[1]
    contents = args.output / "Contents"
    resources = contents / "Resources"
    if args.output.exists():
        shutil.rmtree(args.output)
    resources.mkdir(parents=True)
    subprocess.run(
        ["swiftc", str(root / "macos/Antislop.swift"), "-o", str(contents / "MacOS"), "-framework", "AppKit"],
        check=True,
    )
    plist = {
        "CFBundleName": "Antislop",
        "CFBundleDisplayName": "Antislop",
        "CFBundleIdentifier": "com.local.antislop",
        "CFBundleExecutable": "MacOS",
        "CFBundlePackageType": "APPL",
        "LSUIElement": True,
    }
    with (contents / "Info.plist").open("wb") as file:
        plistlib.dump(plist, file)
    shutil.copytree(root / "src/antislop_mcp", resources / "python/antislop_mcp")
    print(f"Built {args.output}")


if __name__ == "__main__":
    main()
