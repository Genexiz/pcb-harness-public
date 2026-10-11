from pathlib import Path
import argparse
import asyncio
import json
import os
import sys
import time

from mcp import Client, StdioServerParameters


HOST_DISCLOSURE = {
    "name": "Codex desktop subscription",
    "exact_model": "unavailable",
    "sampling_settings": "unavailable",
    "provider_tokens": "unavailable",
    "provider_cost": "unavailable",
    "model_api_key_used_by_harness": False,
}


def _server_environment():
    return {
        key: value for key, value in os.environ.items()
        if "API_KEY" not in key.upper() and "TOKEN" not in key.upper()
    }


def _append_fsync(path: Path, row: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as stream:
        stream.write(json.dumps(row, sort_keys=True, allow_nan=False) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


async def relay(client, source, sink, transcript: Path):
    if Path(transcript).exists():
        raise FileExistsError("M2 transcript must be fresh")
    sequence = 0
    for line in source:
        command = json.loads(line)
        if (not isinstance(command, dict) or set(command) != {"tool", "arguments"}
                or not isinstance(command["tool"], str)
                or not isinstance(command["arguments"], dict)):
            raise ValueError("commands require a tool name and object arguments")
        reply = await client.call_tool(command["tool"], command["arguments"])
        sequence += 1
        row = {
            "schema_version": 1,
            "sequence": sequence,
            "tool": command["tool"],
            "arguments": command["arguments"],
            "result": reply.structured_content,
            "is_error": bool(reply.is_error),
            "host": dict(HOST_DISCLOSURE),
            "recorded_at": time.time(),
        }
        _append_fsync(Path(transcript), row)
        sink.write(json.dumps(row, sort_keys=True, allow_nan=False) + "\n")
        sink.flush()


async def run_stdio_session(*, workspace: Path, run_directory: Path, transcript: Path,
                            backend: str, source, sink, project: Path | None = None,
                            socket: str = "ipc:///tmp/kicad/api.sock",
                            max_actions: int = 300, max_duration_seconds: float = 1200):
    workspace = Path(workspace).resolve()
    run_directory = Path(run_directory).resolve()
    transcript = Path(transcript).resolve()
    if transcript.exists() or run_directory.exists():
        raise FileExistsError("M2 session requires fresh transcript and service paths")
    if backend not in {"memory", "kicad"}:
        raise ValueError("backend must be memory or kicad")
    if backend == "kicad" and project is None:
        raise ValueError("native sessions require a project")
    arguments = [
        "-m", "pcb_harness.mcp_server",
        "--workspace", str(workspace),
        "--run-directory", str(run_directory),
        "--backend", backend,
        "--max-actions", str(max_actions),
        "--max-duration-seconds", str(max_duration_seconds),
        "--socket", socket,
    ]
    if project is not None:
        arguments.extend(["--project", str(Path(project).resolve())])
    parameters = StdioServerParameters(
        command=sys.executable,
        args=arguments,
        env=_server_environment(),
    )
    async with Client(parameters) as client:
        await relay(client, source, sink, transcript)


def main():
    parser = argparse.ArgumentParser(description="Policy-free host-to-MCP session relay")
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--run-directory", type=Path, required=True)
    parser.add_argument("--transcript", type=Path, required=True)
    parser.add_argument("--backend", choices=["kicad", "memory"], default="kicad")
    parser.add_argument("--project", type=Path)
    parser.add_argument("--socket", default="ipc:///tmp/kicad/api.sock")
    parser.add_argument("--max-actions", type=int, default=300)
    parser.add_argument("--max-duration-seconds", type=float, default=1200)
    options = parser.parse_args()
    asyncio.run(run_stdio_session(
        workspace=options.workspace,
        run_directory=options.run_directory,
        transcript=options.transcript,
        backend=options.backend,
        project=options.project,
        socket=options.socket,
        max_actions=options.max_actions,
        max_duration_seconds=options.max_duration_seconds,
        source=sys.stdin,
        sink=sys.stdout,
    ))


if __name__ == "__main__":
    main()
