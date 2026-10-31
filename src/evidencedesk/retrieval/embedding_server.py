"""Launch an isolated Ollama runner for raw last-token Qwen embeddings."""

import argparse
import os
import shutil
import socket
import subprocess
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=11435)
    parser.add_argument("--ollama", help="Path to an installed Ollama executable.")
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535 or args.port == 11434:
        parser.error("Use an unprivileged embedding port other than the standard chat port 11434.")

    executable = args.ollama or shutil.which("ollama")
    if not executable and os.name == "nt":
        executable = str(
            Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama.exe"
        )
    if not executable or not Path(executable).is_file():
        parser.error("Ollama was not found. Install it or pass --ollama with its executable path.")

    with socket.socket() as connection:
        connection.settimeout(1)
        if connection.connect_ex(("127.0.0.1", args.port)) == 0:
            parser.error(f"Port {args.port} is already in use; do not start a second runner there.")

    environment = os.environ.copy()
    environment.update(
        OLLAMA_HOST=f"127.0.0.1:{args.port}",
        LLAMA_ARG_EMBEDDINGS="1",
        LLAMA_ARG_POOLING="last",
        OLLAMA_KEEP_ALIVE="1m",
    )
    print(
        f"Starting embedding-only Ollama at http://127.0.0.1:{args.port}. "
        "Use the regular Ollama service for generation. "
        "Requests must use the existing qwen3:4b model; no model is downloaded.",
        flush=True,
    )
    with subprocess.Popen([executable, "serve"], env=environment) as process:
        try:
            return process.wait()
        except KeyboardInterrupt:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            return 130


if __name__ == "__main__":
    raise SystemExit(main())
