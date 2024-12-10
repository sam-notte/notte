import threading
import time
from http.server import SimpleHTTPRequestHandler
from pathlib import Path
from socketserver import TCPServer


class SnapshotServer:
    def __init__(self, snapshot_dir: str, port: int = 8080):
        self.snapshot_dir: Path = Path(snapshot_dir)
        self.port: int = port
        self.httpd: TCPServer | None = None
        self.thread: threading.Thread | None = None
        self.snapshots: list[Path] = sorted(self.snapshot_dir.iterdir())
        self.current_index: int = 0
        self.base_url: str = f"http://localhost:{port}"

        if not self.snapshots:
            raise ValueError(f"No snapshots found in {snapshot_dir}")

    async def start(self) -> None:
        """
        Start the HTTP server in a separate thread.
        """
        self.snapshot_dir = self.snapshot_dir.resolve()

        def run_server():
            handler = SimpleHTTPRequestHandler
            self.httpd = TCPServer(("0.0.0.0", self.port), handler)
            print(f"Serving HTTP on port {self.port}...")
            self.httpd.serve_forever()

        self.thread = threading.Thread(target=run_server)
        self.thread.daemon = True
        self.thread.start()
        time.sleep(1)  # Allow the server to start

    async def close(self) -> None:
        """
        Stop the HTTP server.
        """
        if self.httpd:
            self.httpd.shutdown()
            self.httpd.server_close()
            print("HTTP server stopped.")
        if self.thread:
            self.thread.join()

    async def step(self, forward: bool = True) -> None:
        """
        Move to the next or previous snapshot and render it.

        Args:
            forward (bool): Move forward if True, backward if False.
        """
        if forward:
            if self.current_index < len(self.snapshots) - 1:
                self.current_index += 1
            else:
                print("Already at the last snapshot.")
        else:
            if self.current_index > 0:
                self.current_index -= 1
            else:
                print("Already at the first snapshot.")

    async def serve(self) -> str:
        """
        Starts the server, serves a snapshot, and waits for page load.

        Args:
            page: Playwright page object
        """
        if not self.thread or not self.thread.is_alive():
            await self.start()

        current_snapshot = self.snapshots[self.current_index]
        return f"{self.base_url}/{current_snapshot.name}/index.html"
