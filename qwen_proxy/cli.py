"""Qwen Proxy CLI — start/stop server, check status."""

from __future__ import annotations

import subprocess
import sys

import typer

app = typer.Typer(
    name="qwen-proxy",
    help="Qwen Proxy - OpenAI-compatible API for Qwen AI",
    add_completion=False,
)


@app.command()
def start(
    host: str = typer.Option("0.0.0.0", help="Host to bind"),
    port: int = typer.Option(8000, help="Port to bind"),
    reload: bool = typer.Option(False, "--reload", help="Enable auto-reload for development"),
) -> None:
    """Start the Qwen Proxy server."""
    cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "hubia.main:app",
        "--host",
        host,
        "--port",
        str(port),
    ]
    if reload:
        cmd.append("--reload")

    typer.echo(f"Starting Qwen Proxy on http://{host}:{port}")
    typer.echo(f"API docs: http://{host}:{port}/docs")
    typer.echo(f"Web UI:   http://{host}:{port}/")
    typer.echo("")

    try:
        subprocess.run(cmd)
    except KeyboardInterrupt:
        typer.echo("\nServer stopped.")


@app.command()
def status() -> None:
    """Check if the Qwen Proxy server is running."""
    import httpx

    try:
        response = httpx.get("http://localhost:8089/health", timeout=2.0)
        if response.status_code == 200:
            typer.echo("Qwen Proxy is running on http://localhost:8000")
        else:
            typer.echo(f"Qwen Proxy responded with status {response.status_code}")
    except httpx.ConnectError:
        typer.echo("Qwen Proxy is not running.")
    except Exception as exc:
        typer.echo(f"Could not connect: {exc}")


@app.command()
def version() -> None:
    """Show the Qwen Proxy version."""
    from qwen_proxy import __version__

    typer.echo(f"qwen-proxy {__version__}")


if __name__ == "__main__":
    app()
