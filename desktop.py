# desktop.py
import socket
import threading

import uvicorn
import webview

from src.web.app import create_app


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def main():
    app = create_app()
    port = _free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)

    server_thread = threading.Thread(target=server.run, daemon=True)
    server_thread.start()

    window = webview.create_window("YouTube Analytics Extractor", f"http://127.0.0.1:{port}")

    def on_closed():
        server.should_exit = True

    window.events.closed += on_closed

    webview.start()
    server_thread.join(timeout=5)


if __name__ == "__main__":
    main()
