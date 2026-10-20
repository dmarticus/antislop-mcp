"""Private Unix-socket controller owned by Antislop.app."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import signal
from pathlib import Path
from typing import Any

from .client import AntislopClient, AntislopError

MAX_MESSAGE = 2 * 1024 * 1024


class Controller:
    def __init__(self, root: Path, parent_pid: int | None = None) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.socket_path = root / "control.sock"
        self.config = self._read_json(root / "config.json", {})
        self.enabled = self._read_json(root / "settings.json", {"enabled": True}).get("enabled", True)
        self.runner: asyncio.subprocess.Process | None = None
        self.state = "off" if not self.enabled else "starting"
        self.message = "Antislop is off" if not self.enabled else "Starting Antislop"
        self.parent_pid = parent_pid
        runner_environment = self.config.get("runner_environment", {})
        if isinstance(runner_environment, dict):
            os.environ.update({str(key): str(value) for key, value in runner_environment.items()})
        os.environ.setdefault(
            "ANTISLOP_TIMEOUT", str(self.config.get("request_timeout", 240))
        )
        self.client = AntislopClient()

    @staticmethod
    def _read_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
        try:
            return json.loads(path.read_text())
        except (OSError, ValueError):
            return default

    def status(self) -> dict[str, Any]:
        running = self.runner is not None and self.runner.returncode is None
        return {
            "status": self.state,
            "enabled": self.enabled,
            "message": self.message,
            "runner_pid": self.runner.pid if running else None,
            "controller_pid": os.getpid(),
            "model": self.client.model,
            "endpoint": self.client.base_url,
            "request_timeout": self.client.timeout,
        }

    async def _wait_ready(self) -> None:
        deadline = asyncio.get_running_loop().time() + float(self.config.get("startup_timeout", 180))
        while asyncio.get_running_loop().time() < deadline:
            if self.runner and self.runner.returncode is not None:
                raise RuntimeError("The model runner stopped during startup.")
            status = await self.client.status()
            if status.get("status") == "ready":
                self.state, self.message = "ready", "Ready"
                return
            await asyncio.sleep(0.5)
        raise TimeoutError("The model runner did not become ready in time.")

    async def start_runner(self) -> None:
        if not self.enabled or (self.runner and self.runner.returncode is None):
            return
        command = self.config.get("runner_command")
        if not isinstance(command, list) or not command:
            self.state, self.message = "error", "Configure runner_command in config.json."
            return
        log_path = self.root / "runner.log"
        log = open(log_path, "ab", buffering=0)
        environment = dict(os.environ)
        environment.update(self.config.get("runner_environment", {}))
        environment["ANTISLOP_BASE_URL"] = self.client.base_url
        environment["ANTISLOP_MODEL"] = self.client.model
        self.state, self.message = "loading", "Loading model"
        self.runner = await asyncio.create_subprocess_exec(
            *[str(item) for item in command],
            stdin=asyncio.subprocess.DEVNULL,
            stdout=log,
            stderr=log,
            env=environment,
        )
        try:
            await self._wait_ready()
        except Exception as exc:
            self.state, self.message = "error", str(exc)

    async def stop_runner(self) -> None:
        runner, self.runner = self.runner, None
        if runner and runner.returncode is None:
            runner.terminate()
            try:
                await asyncio.wait_for(runner.wait(), 8)
            except TimeoutError:
                runner.kill()
                await runner.wait()
        self.state = "off"
        self.message = "Antislop is off"

    async def handle(self, body: dict[str, Any]) -> dict[str, Any]:
        action = body.get("action")
        if action == "status":
            return self.status()
        if action == "enable":
            self.enabled = bool(body.get("enabled"))
            (self.root / "settings.json").write_text(json.dumps({"enabled": self.enabled}))
            if self.enabled:
                await self.start_runner()
            else:
                await self.stop_runner()
            return self.status()
        if action == "rewrite":
            if not self.enabled:
                return {"status": "off", "message": "Antislop is off."}
            if not self.runner or self.runner.returncode is not None:
                await self.start_runner()
            if self.state != "ready":
                return {"status": "unavailable", "message": self.message}
            request = body.get("request", {})
            try:
                output = await self.client.complete(
                    text=request["text"],
                    instruction=request.get("instruction", "Humanize this text."),
                    max_tokens=int(request.get("max_tokens", 1200)),
                    temperature=float(request.get("temperature", 0.8)),
                )
            except (AntislopError, KeyError, TypeError, ValueError) as exc:
                return {"status": "unavailable", "message": str(exc)}
            return {"status": "ok", "text": output, "model": self.client.model}
        return {"status": "error", "message": "Unknown action."}

    async def serve(self) -> None:
        try:
            self.socket_path.unlink()
        except FileNotFoundError:
            pass
        server = await asyncio.start_unix_server(self._connection, path=str(self.socket_path))
        os.chmod(self.socket_path, 0o600)
        if self.enabled:
            await self.start_runner()
        async with server:
            await server.serve_forever()

    async def _connection(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            line = await asyncio.wait_for(reader.readline(), 2)
            if len(line) > MAX_MESSAGE:
                raise ValueError("Request too large")
            result = await self.handle(json.loads(line))
        except Exception as exc:
            result = {"status": "error", "message": type(exc).__name__}
        writer.write(json.dumps(result).encode() + b"\n")
        await writer.drain()
        writer.close()
        await writer.wait_closed()


async def run(args: argparse.Namespace) -> None:
    controller = Controller(Path(args.data_dir).expanduser(), args.parent_pid)
    stop = asyncio.Event()
    if controller.parent_pid:
        asyncio.create_task(_watch_parent(controller.parent_pid, stop))
    for sig in (signal.SIGTERM, signal.SIGINT):
        asyncio.get_running_loop().add_signal_handler(sig, stop.set)
    server_task = asyncio.create_task(controller.serve())
    await stop.wait()
    server_task.cancel()
    await asyncio.gather(server_task, return_exceptions=True)
    await controller.stop_runner()


async def _watch_parent(parent_pid: int, stop: asyncio.Event) -> None:
    while os.getppid() == parent_pid:
        await asyncio.sleep(2)
    stop.set()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--parent-pid", type=int)
    asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    main()
