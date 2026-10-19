"""Client for the Antislop menu-bar app's private Unix socket."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any


def data_dir() -> Path:
    return Path(os.getenv("ANTISLOP_DATA_DIR", "~/Library/Application Support/Antislop")).expanduser()


def app_path() -> Path:
    return Path(os.getenv("ANTISLOP_APP_PATH", "~/Applications/Antislop.app")).expanduser()


async def request(body: dict[str, Any], timeout: float = 60) -> dict[str, Any]:
    async with asyncio.timeout(timeout):
        reader, writer = await asyncio.open_unix_connection(str(data_dir() / "control.sock"))
        try:
            writer.write(json.dumps(body).encode() + b"\n")
            await writer.drain()
            return json.loads(await reader.readline())
        finally:
            writer.close()
            await writer.wait_closed()


async def ensure_app() -> dict[str, Any]:
    try:
        return await request({"action": "status"}, timeout=2)
    except (OSError, ValueError, TimeoutError):
        pass
    if not app_path().exists():
        return {"status": "unavailable", "message": "Install Antislop.app before using this plugin."}
    try:
        process = await asyncio.create_subprocess_exec(
            "/usr/bin/open", "-g", str(app_path()), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        await process.wait()
    except OSError as exc:
        return {"status": "unavailable", "message": f"Could not open Antislop.app: {exc}"}
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        try:
            return await request({"action": "status"}, timeout=1)
        except (OSError, ValueError, TimeoutError):
            await asyncio.sleep(0.25)
    return {"status": "unavailable", "message": "Antislop.app did not start. Check its logs."}
