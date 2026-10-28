"""Windows desktop test client with an embedded, on-demand FastAPI host."""
import os
import sys
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")
import socket
import threading
import time
import urllib.request
import webbrowser

import uvicorn
from app.main import app


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def main():
    port = free_port()
    url = f"http://127.0.0.1:{port}/"
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", log_config=None, use_colors=False, lifespan="off")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        try:
            urllib.request.urlopen(url, timeout=0.2).close()
            break
        except Exception:
            time.sleep(0.1)
    else:
        raise RuntimeError("Could not start the local game service")
    try:
        import webview
        webview.create_window("Pentagon Island v0.8.3 - Multiplayer & Trade Update", url, width=1280, height=860, min_size=(760, 560))
        webview.start()
    except ImportError:
        webbrowser.open(url)
        print(f"Open {url} in your browser; press Ctrl+C to stop.")
        try:
            while thread.is_alive():
                time.sleep(0.3)
        except KeyboardInterrupt:
            pass
    finally:
        server.should_exit = True
        thread.join(timeout=4)


if __name__ == "__main__":
    main()
