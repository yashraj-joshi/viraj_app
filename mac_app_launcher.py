from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

import uvicorn

from app import INPUT_FILE, OUTPUT_DIR, app, configure_shutdown_handler


HOST = "127.0.0.1"
PREFERRED_PORT = 8000


def prepare_standard_streams() -> None:
    """PyInstaller windowed apps do not have terminal output streams."""
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")


def bind_server_socket() -> socket.socket:
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        server_socket.bind((HOST, PREFERRED_PORT))
    except OSError:
        server_socket.bind((HOST, 0))
    server_socket.listen(128)
    return server_socket


def open_browser_when_ready(url: str) -> None:
    health_url = f"{url}/health"
    for _ in range(150):
        try:
            with urllib.request.urlopen(health_url, timeout=0.5) as response:
                if response.status == 200:
                    webbrowser.open(url, new=2)
                    return
        except (OSError, urllib.error.URLError):
            time.sleep(0.1)


def show_startup_error(message: str) -> None:
    safe_message = message[:2000]
    script = (
        f"display dialog {json.dumps(safe_message)} "
        'with title "API ID Status Checker" '
        'buttons {"OK"} default button "OK" with icon stop'
    )
    try:
        subprocess.run(
            ["/usr/bin/osascript", "-e", script],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError:
        pass


def run() -> None:
    prepare_standard_streams()
    try:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        if not INPUT_FILE.exists():
            INPUT_FILE.write_text(
                "1T00000001\n1V00000001\n",
                encoding="utf-8",
            )

        server_socket = bind_server_socket()
        port = server_socket.getsockname()[1]
        url = f"http://{HOST}:{port}"

        if os.environ.get("API_CHECKER_NO_BROWSER") != "1":
            threading.Thread(
                target=open_browser_when_ready,
                args=(url,),
                daemon=True,
            ).start()

        config = uvicorn.Config(
            app=app,
            host=HOST,
            port=port,
            loop="asyncio",
            http="h11",
            ws="none",
            lifespan="off",
            access_log=False,
            log_config=None,
        )
        server = uvicorn.Server(config)
        configure_shutdown_handler(lambda: setattr(server, "should_exit", True))
        try:
            server.run(sockets=[server_socket])
        except KeyboardInterrupt:
            pass
        finally:
            configure_shutdown_handler(None)
            server_socket.close()
    except Exception as exc:
        error_path = INPUT_FILE.parent / "launcher_error.txt"
        try:
            error_path.write_text(
                f"{type(exc).__name__}: {exc}\n",
                encoding="utf-8",
            )
        except OSError:
            pass
        show_startup_error(f"The application could not start.\n\n{type(exc).__name__}: {exc}")
        raise


if __name__ == "__main__":
    run()
