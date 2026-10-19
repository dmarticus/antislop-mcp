"""Install Antislop.app and its local service configuration for the current user."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--app", type=Path, default=Path("build/Antislop.app"))
    # The runner commonly has flags such as `-hf`; consume everything after
    # --runner instead of letting argparse interpret those flags as ours.
    parser.add_argument(
        "--runner", nargs=argparse.REMAINDER, required=True,
        help="Command that serves /v1/chat/completions; must be the final install.py argument",
    )
    parser.add_argument("--python", type=Path, default=Path(".venv/bin/python"))
    args = parser.parse_args()
    data = Path.home() / "Library/Application Support/Antislop"
    applications = Path.home() / "Applications"
    applications.mkdir(parents=True, exist_ok=True)
    data.mkdir(parents=True, exist_ok=True)
    destination = applications / "Antislop.app"
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(args.app, destination)
    config = {
        # Keep the venv launcher path. Resolving it follows uv's symlink to a
        # bare interpreter, which loses the venv's installed dependencies.
        "python": str(args.python.absolute()),
        "runner_command": args.runner,
        "runner_environment": {
            "ANTISLOP_BASE_URL": "http://127.0.0.1:8000/v1",
            "ANTISLOP_MODEL": "antislop",
        },
    }
    (data / "config.json").write_text(json.dumps(config, indent=2) + "\n")
    (data / "settings.json").write_text(json.dumps({"enabled": True}) + "\n")
    print(f"Installed {destination}")
    print(f"Configured {data / 'config.json'}")


if __name__ == "__main__":
    main()
